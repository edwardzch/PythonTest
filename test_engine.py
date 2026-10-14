# 文件路径: test_engine.py (报告完美对齐终极版 - 完整代码)

import time
import pandas as pd
from datetime import datetime
import json
import traceback
import inspect
import threading
import os
import copy
import re
import sqlite3
from string import Template
import math # Added based on the provided Code Edit
from utils.database_logger import log_test_result # ADDED: Import for database logging
from utils.app_utils import get_app_base_path
from utils import work_order_db # Added based on instruction
import uuid

# 全局结果存储，用于跨线程传递用户交互结果
_INTERACTION_RESULTS = {}

# HTML template moved to utils.report_generator
class TestEngineLogger:
    def __init__(self, station_id, signals): self.station_id, self.signals = station_id, signals

    def _safe_emit(self, signal, *args):
        try:
            signal.emit(*args)
        except RuntimeError as e:
            if "deleted" not in str(e).lower():
                raise

    def log(self, message, level='INFO'): self._safe_emit(self.signals.log, 
        (f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] {message}", level.upper()))

    def info(self, message): self.log(message, 'INFO')

    def error(self, message, exc_info=False): self.log(message + ('\n' + traceback.format_exc() if exc_info else ''),
                                                       'ERROR')

    def warning(self, message): self.log(message, 'WARNING')

    def debug(self, message): self.log(message, 'DEBUG')

    def step_update(self, content): self._safe_emit(self.signals.step_update, 
        {'station_id': self.station_id, 'type': 'step_update', 'content': content})

    def final_status(self, content): self._safe_emit(self.signals.final_status, 
        {'station_id': self.station_id, 'type': 'final_status', 'content': content})

    def progress(self, value): self._safe_emit(self.signals.progress, value)

    def paused_at(self, step_index): self._safe_emit(self.signals.paused_at, step_index)


class TestEngine:
    def __init__(self, station_id, uut_sn, global_config, hardware_manager, sequence_data, available_modules, signals,
                 is_debugging, breakpoints, local_stop_event, stop_all_event, pause_event, step_event, resume_event,
                 sequence_file_path, report_output_dir=None, operator_id=None, operator_name=None, 
                 work_order=None, target_qty=None, station_count=1, adapter_cables=None, adapter_cable_life=None):
        self.station_id, self.uut_sn, self.global_config, self.hardware_manager = station_id, uut_sn, global_config, hardware_manager
        self.station_config = global_config['stations'][station_id]
        self.available_modules, self.logger = available_modules, TestEngineLogger(station_id, signals)
        self.sequence_file_path = sequence_file_path
        self.report_output_dir = report_output_dir
        self.is_debugging, self.breakpoints = is_debugging, breakpoints
        self.local_stop_event, self.stop_all_event = local_stop_event, stop_all_event
        self.pause_event, self.step_event, self.resume_event = pause_event, step_event, resume_event
        self._is_waiting_for_step, self.start_time = True, 0
        self.all_step_results_for_report, self.sequence_snapshot = [], copy.deepcopy(sequence_data)
        self.loop_counters, self.loop_stack = {}, []
        self.product_model, self.sequence_version = "N/A", ""
        self.operator_id = operator_id
        self.operator_name = operator_name  # 【新增】操作员姓名
        self.work_order = work_order
        self.target_qty = target_qty
        self.station_count = station_count  # 【新增】工位数
        # 自动从配方中提取转接线编码 (无需依赖外部开关)
        if not adapter_cables or adapter_cables == ["Not used"]:
            if self.sequence_file_path:
                try:
                    from recipe_manager import get_recipe_manager
                    rm = get_recipe_manager()
                    matched_recipe = rm.find_matching_recipe(self.sequence_file_path, self.uut_sn)
                    if matched_recipe and matched_recipe.get('adapter_cables'):
                        adapter_cables = matched_recipe.get('adapter_cables')
                except Exception as e:
                    print(f"[TestEngine] 自动读取配方转接线异常: {e}")

        self.adapter_cables = adapter_cables if adapter_cables else ["Not used"]

        # 实时查询转接线寿命
        if self.adapter_cables and self.adapter_cables != ["Not used"]:
            try:
                from utils.consumable_db import check_cable_sn
                life_parts = []
                for cable_sn in self.adapter_cables:
                    c_info = check_cable_sn(cable_sn)
                    used = c_info.get('total_count', 0) if c_info else 0
                    limit = c_info.get('max_limit', 10000) if c_info else 10000
                    life_parts.append(f"{cable_sn} ({used}/{limit})")
                self.adapter_cable_life = ", ".join(life_parts)
            except Exception as e:
                print(f"[TestEngine] 查询转接线寿命异常: {e}")
                self.adapter_cable_life = adapter_cable_life or "Not used"
        else:
            self.adapter_cable_life = "Not used"

        # 顶针使用寿命初始化（如未启用则显示 Not used）
        thimble_enabled = self.global_config.get('thimble_tracking', {}).get('enabled', True)
        if not thimble_enabled:
            self.thimble_life = "Not used"
        else:
            self.thimble_life = "Not used"
            if self.sequence_file_path:
                try:
                    from thimble_manager import ThimbleManager
                    tm = ThimbleManager()
                    fix_code = tm.get_fixture_for_sequence(self.sequence_file_path, self.station_id)
                    if fix_code:
                        fixtures = tm.get_fixtures(self.station_id)
                        fix_info = fixtures.get(fix_code, {})
                        used = fix_info.get('total_usage', 0)
                        limit = fix_info.get('limit', 20000)
                        self.thimble_life = f"{fix_code} ({used}/{limit})"
                    else:
                        self.thimble_life = "未绑定治具"
                except Exception:
                    self.thimble_life = "Not used"
        if self.sequence_file_path:
            filename_without_ext = os.path.splitext(os.path.basename(self.sequence_file_path))[0]
            import re
            
            # 规则：版本号是紧接在 _sequence 前面的 _V 开头的部分
            # 例如：17419400001501_SEA20(16)M-6S47STTC_V1.0_sequence -> V1.0
            # 如果没有 _sequence 后缀，则取最后一个 _V 开头的部分
            
            # 优先匹配：_V版本号_sequence 或 _V版本号$ (文件末尾)
            version_match = re.search(r'_([Vv]\d+(?:\.\d+)?)_sequence', filename_without_ext, re.IGNORECASE)
            if not version_match:
                # 回退：匹配最后一个 _V 版本号（即使后面不是 sequence）
                version_match = re.search(r'_([Vv]\d+(?:\.\d+)?)(?:_|$)(?!.*_[Vv]\d)', filename_without_ext)
            if not version_match:
                # 最终回退：匹配任意 _V 版本号
                version_match = re.search(r'_([Vv]\d+(?:\.\d+)?)', filename_without_ext)
                
            if version_match:
                self.sequence_version = version_match.group(1)
            
            # 提取产品型号：取第一个下划线后到版本号之前的部分
            parts = filename_without_ext.split('_')
            if len(parts) >= 2:
                # 找到版本号的位置（从后往前找，优先靠近 sequence 的）
                version_idx = -1
                for i in range(len(parts) - 1, -1, -1):
                    if re.match(r'^[Vv]\d+(?:\.\d+)?$', parts[i]):
                        # 如果后面是 sequence，则这就是版本号
                        if i + 1 < len(parts) and parts[i + 1].lower() == 'sequence':
                            version_idx = i
                            break
                        # 否则记录这个位置，继续找
                        if version_idx == -1:
                            version_idx = i
                
                if version_idx > 1:
                    self.product_model = '_'.join(parts[1:version_idx])
                elif len(parts) >= 2:
                    self.product_model = parts[1]
            else:
                self.product_model = filename_without_ext
        self.sequence_df = self._prepare_sequence(sequence_data)
        self.control_flow_map = self._build_control_flow_map(self.sequence_df)
        print(f"[Engine-{station_id.split('_')[-1]}] --- TestEngine for {station_id} Initialized ---")
        print(f"    - 产品型号: {self.product_model}");
        print(f"    - 程序版本: {self.sequence_version}")

    def request_user_interaction(self, interaction_type, **kwargs):
        """
        请求主线程进行用户交互（如弹框）。
        此方法是线程安全的，会阻塞直到用户响应。
        """
        # 使用全局字典存储结果，通过唯一ID关联
        request_id = str(uuid.uuid4())
        event = threading.Event()
        
        payload = {
            'station_id': self.station_id,
            'type': interaction_type,
            'kwargs': kwargs,
            'event': event,
            'request_id': request_id
        }
        
        # 发送信号给主线程
        try:
            self.logger.signals.user_interaction.emit(payload)
        except RuntimeError as e:
            if "deleted" in str(e).lower():
                return None
            raise
        
        # 等待主线程处理完成
        event.wait()
        
        # 从全局字典获取结果
        result = _INTERACTION_RESULTS.pop(request_id, None)
        return result

    def _build_control_flow_map(self, df):
        jump_map = {};
        stack = []
        self.logger.debug("Building control flow map for if/elseif/else/for...")
        for _, row in df.iterrows():
            original_index = row['original_index'];
            func_name = row.get('Function')
            if func_name in ['if_variable', 'for_loop']:
                stack.append({'type': func_name, 'index': original_index})
            elif func_name == 'elseif_variable':
                if not stack or stack[-1]['type'] not in ['if_variable', 'elseif_variable']: self.logger.warning(
                    f"Dangling '{func_name}' at step index {original_index}."); continue
                prev_block_index = stack[-1]['index']
                if prev_block_index not in jump_map: jump_map[prev_block_index] = {}
                jump_map[prev_block_index]['next_branch'] = original_index;
                stack[-1] = {'type': func_name, 'index': original_index}
            elif func_name == 'else_block':
                if not stack or stack[-1]['type'] not in ['if_variable', 'elseif_variable']: self.logger.warning(
                    f"Dangling '{func_name}' at step index {original_index}."); continue
                prev_block_index = stack.pop()['index']
                if prev_block_index not in jump_map: jump_map[prev_block_index] = {}
                jump_map[prev_block_index]['next_branch'] = original_index;
                stack.append({'type': 'else', 'index': original_index})
            elif func_name == 'end_if':
                if not stack or stack[-1]['type'] not in ['if_variable', 'elseif_variable',
                                                          'else']: self.logger.warning(
                    f"Dangling '{func_name}' at step index {original_index}."); continue
                stack.pop()
            elif func_name == 'end_for':
                if not stack or stack[-1]['type'] != 'for_loop': self.logger.warning(
                    f"Dangling '{func_name}' at step index {original_index}."); continue
                for_index = stack.pop()['index']
                if for_index not in jump_map: jump_map[for_index] = {}
                jump_map[for_index]['end_for'] = original_index;
                jump_map[original_index] = {'for_loop': for_index}
            elif func_name == 'do_while_start':
                stack.append({'type': 'do_while', 'index': original_index})
            elif func_name == 'end_do_while':
                if not stack or stack[-1]['type'] != 'do_while':
                    self.logger.warning(f"Dangling '{func_name}' at step index {original_index}."); continue
                do_while_index = stack.pop()['index']
                if do_while_index not in jump_map: jump_map[do_while_index] = {}
                jump_map[do_while_index]['end_do_while'] = original_index
                # end_do_while points back to do_while_start
                jump_map[original_index] = {'do_while': do_while_index}
        if_chain_stack = []
        for _, row in df.iterrows():
            idx, func = row['original_index'], row.get('Function')
            if func == 'if_variable':
                if_chain_stack.append(idx)
            elif func == 'end_if' and if_chain_stack:
                start_if_idx = if_chain_stack.pop()
                current_node_idx = start_if_idx
                while current_node_idx is not None:
                    if current_node_idx not in jump_map: jump_map[current_node_idx] = {}
                    jump_map[current_node_idx]['endif'] = idx
                    current_node_idx = jump_map[current_node_idx].get('next_branch')
        if stack or if_chain_stack: self.logger.error(
            f"Unclosed control flow blocks detected. Stack: {stack}, IfStack: {if_chain_stack}")
        self.logger.debug(f"Control flow map built: {jump_map}");
        return jump_map

    def _prepare_sequence(self, sequence_data):
        df = pd.DataFrame(sequence_data)
        if 'Enable' not in df.columns:
            df['Enable'] = True
        else:
            df['Enable'] = df['Enable'].apply(lambda x: str(x).strip().upper() not in ['0', 'FALSE', 'N', 'NO', 'NO'])
        if 'Skip' in df.columns: df['Enable'] = df.apply(
            lambda row: False if str(row.get('Skip', '')).strip().upper() == 'YES' else row['Enable'], axis=1)
        for col in ['Result', 'Value', 'Message', 'StartTime', 'EndTime']:
            if col not in df.columns: df[col] = None
        df.reset_index(inplace=True);
        df.rename(columns={'index': 'original_index'}, inplace=True)
        is_executable_step = ~df['TestName'].str.strip().str.startswith(('*', '#'))
        df['step_number'] = is_executable_step.cumsum();
        df.loc[~is_executable_step, 'step_number'] = pd.NA
        object_cols = df.select_dtypes(include=['object']).columns
        for col in object_cols: df[col] = df[col].fillna('')
        return df

    def _should_stop(self):
        return self.local_stop_event.is_set() or self.stop_all_event.is_set()

    def _check_and_pause_if_needed(self, step_index):
        self.pause_event.wait()
        if self._should_stop(): return
        if not self.is_debugging: return
        is_breakpoint = step_index in self.breakpoints
        if is_breakpoint or self._is_waiting_for_step:
            self.logger.debug(
                f"调试暂停于步骤 original_index={step_index} (断点: {is_breakpoint}, 单步等待: {self._is_waiting_for_step})")
            self.logger.paused_at(step_index);
            self.step_event.clear();
            self.resume_event.clear()
            while not (self.step_event.is_set() or self.resume_event.is_set()):
                if self._should_stop(): return
                time.sleep(0.05)
            if self.resume_event.is_set():
                self.logger.debug("收到 'Resume' 命令"); self._is_waiting_for_step = False
            else:
                self.logger.debug("收到 'Step' 命令"); self._is_waiting_for_step = True

    def _safe_eval_params(self, params_str):
        if not params_str: return {}
        
        # 尝试1: 直接 json.loads（标准 JSON，路径用双反斜杠或正斜杠）
        try:
            result = json.loads(params_str)
            if isinstance(result, dict):
                return self._normalize_path_values(result)
        except (json.JSONDecodeError, ValueError):
            pass
        
        # 尝试2: 修复 Windows 路径单反斜杠后再 json.loads
        # 例如用户从地址栏粘贴 D:\1encoder\program，在 JSON 中 \1 和 \p 不是合法转义
        # 将所有非标准转义的单反斜杠替换为双反斜杠（保留 \", \\, \/, \n, \r, \t, \b, \f, \uXXXX）
        try:
            sanitized = re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', params_str)
            result = json.loads(sanitized)
            if isinstance(result, dict):
                self.logger.warning(f"参数中检测到 Windows 路径单反斜杠，已自动修复")
                return self._normalize_path_values(result)
        except (json.JSONDecodeError, ValueError):
            pass
        
        # 尝试3: 用 eval 解析 Python dict 语法（兼容旧的 key=value 写法）
        try:
            result = eval(f"dict({params_str})", {})
            return self._normalize_path_values(result)
        except SyntaxError:
            try:
                sanitized_str = re.sub(r'\\(?!["\\/])', r'\\\\', params_str)
                self.logger.warning(f"参数解析遇到语法错误(可能是反斜杠导致)，尝试自动修复")
                result = eval(f"dict({sanitized_str})", {})
                return self._normalize_path_values(result)
            except Exception:
                raise  # 修复失败，抛出异常

    def _normalize_path_values(self, params_dict):
        """将参数字典中路径类的值统一规范化（反斜杠 -> 正斜杠）"""
        path_keywords = ('path', 'file', 'dir', 'folder')
        for key, value in params_dict.items():
            if isinstance(value, str) and any(kw in key.lower() for kw in path_keywords):
                # 将反斜杠统一替换为正斜杠
                params_dict[key] = value.replace('\\', '/')
        return params_dict

    def _parse_and_execute(self, step_info, variables, last_result_wrapper):
        try:
            module_name, func_name, params_str = step_info.get('Module'), step_info.get('Function'), step_info.get(
                'Parameters', '')
            if not module_name or not func_name: return "FAIL", "步骤缺少 'Module' 或 'Function' 字段"
            if func_name == 'store_last_result':
                try:
                    params_from_json = self._safe_eval_params(params_str)
                    if var_name := params_from_json.get('name'):
                        value_to_store = last_result_wrapper['value'];
                        variables[var_name] = value_to_store;
                        msg = f"结果 '{value_to_store}' 已存为变量 '{var_name}'。";
                        self.logger.info(msg);
                        return "PASS", msg
                    else:
                        msg = "store_last_result 缺少 'name' 参数。"; self.logger.error(msg); return "FAIL", msg
                except Exception as e:
                    msg = f"处理 store_last_result 时出错: {e}"; self.logger.error(msg,
                                                                                   exc_info=True); return "FAIL", msg
            if module_name not in self.available_modules: return "FAIL", f"模块 '{module_name}' 未找到"
            module = self.available_modules[module_name]
            if not (func := getattr(module, func_name,
                                    None)): return "FAIL", f"函数 '{func_name}' 在模块 '{module_name}' 中未找到"
            params_from_json = self._safe_eval_params(params_str)
            for key, value in params_from_json.items():
                if isinstance(value, str):
                    if not (var_names := re.findall(r'\{([a-zA-Z_][a-zA-Z0-9_]*)\}', value)): continue
                    if len(var_names) == 1 and value == f"{{{var_names[0]}}}":
                        var_name = var_names[0]
                        if var_name in variables:
                            params_from_json[key] = variables[var_name]
                        else:
                            return "FAIL", f"在参数 '{key}' 中找不到变量 '{{{var_name}}}'。"
                    else:
                        temp_val = value;
                        all_vars_found = True
                        for var_name in set(var_names):
                            if var_name in variables:
                                temp_val = temp_val.replace(f'{{{var_name}}}', str(variables[var_name]))
                            else:
                                all_vars_found = False; return "FAIL", f"在参数 '{key}' 的表达式 '{value}' 中找不到变量 '{{{var_name}}}'。"
                        if all_vars_found: params_from_json[key] = temp_val
            # 【关键修复】优先从 serial_config.modbus_slaves 获取共享设备地址，兼容旧格式
            modbus_slaves = self.global_config.get('serial_config', {}).get('modbus_slaves', {})
            if not modbus_slaves:
                modbus_slaves = self.station_config.get('modbus_slaves', {})
            
            # 【重要】modbus_slaves 必须放在 **self.station_config 之后，否则会被旧配置覆盖
            dependencies = {**self.global_config, **self.station_config,
                            "logger": self.logger, "station_id": self.station_id,
                            "uut_sn": self.uut_sn, "hardware_manager": self.hardware_manager,
                            "test_engine_instance": self, "variables": variables,
                            "last_result": last_result_wrapper['value'],
                            "get_psu_handle": lambda psu_id=None: self.hardware_manager.get_station_psu(self.station_id),
                            "power_supply_mode": self.global_config.get('power_supply_mode', {}),
                            "modbus_slaves": modbus_slaves}  # 放在最后，确保不被覆盖
            all_possible_args = {**dependencies, **params_from_json};
            sig = inspect.signature(func);
            func_param_names = sig.parameters.keys()
            args_to_pass = all_possible_args if any(
                p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()) else {
                name: all_possible_args[name] for name in func_param_names if name in all_possible_args}
            result = func(**args_to_pass);
            last_result_wrapper['value'] = result
            if func_name in ['if_variable', 'elseif_variable']: return "PASS", str(result[1]) if isinstance(result,
                                                                                                            tuple) and len(
                result) > 1 else ""
            if isinstance(result, tuple) and len(result) >= 1 and isinstance(result[0], bool):
                return "PASS" if result[0] else "FAIL", str(result[1]) if len(result) > 1 else ""
            elif result is None or result is True:
                return "PASS", ""
            elif result is False:
                return "FAIL", "函数返回 False"
            else:
                return "PASS", str(result)
        except Exception as e:
            self.logger.error("执行步骤时发生内部错误", exc_info=True); return "FAIL", f"执行异常: {e}"

    def _to_numeric(self, value_str):
        if value_str is None or value_str == '': return None
        if isinstance(value_str, (int, float)): return float(value_str)
        if not isinstance(value_str, str): value_str = str(value_str)
        try:
            return int(value_str, 0)
        except (ValueError, TypeError):
            try:
                return float(value_str)
            except (ValueError, TypeError):
                # Try to strip non-numeric characters (e.g., "3.3V", "500mA")
                try:
                    import re
                    # Extract the first valid number found
                    match = re.search(r'-?\d+(\.\d+)?', str(value_str))
                    if match:
                        return float(match.group())
                except Exception:
                    pass
                return None

    def _perform_comparison(self, mode, result_val, lower_limit_str, upper_limit_str):
        value_for_comparison = result_val[0] if isinstance(result_val, tuple) and len(result_val) > 0 else result_val
        
        def _format_with_hex(val):
            """格式化数值，添加十六进制显示"""
            if isinstance(val, (int, float)) and float(val) == int(val):
                int_val = int(val)
                if int_val >= 0:
                    return f"{int_val}(0x{int_val & 0xFFFF:04X})"
                else:
                    return f"{int_val}(-0x{(-int_val) & 0xFFFF:04X})"
            return str(val)
        
        if mode in ['InRange', 'NotInRange', '||', '==', '!=', '>', '>=', '<', '<=']:
            try:
                numeric_result = float(value_for_comparison) if isinstance(value_for_comparison,
                                                                           bool) else self._to_numeric(
                    str(value_for_comparison))
                if numeric_result is None: raise ValueError(f"Result '{value_for_comparison}' is not a valid number.")
            except (ValueError, TypeError):
                return False, f"结果 '{result_val}' 中的值 '{value_for_comparison}' 不是一个有效的数字，无法进行数值比较。"
                
            # 特殊处理 || (多个 Range 采用 OR 逻辑)
            if mode == '||':
                if not lower_limit_str or not upper_limit_str:
                    return False, "|| 模式需要利用逗号分隔的有效的最小值和最大值列表。"
                lower_parts = [part.strip() for part in str(lower_limit_str).split(',')]
                upper_parts = [part.strip() for part in str(upper_limit_str).split(',')]
                if len(lower_parts) != len(upper_parts):
                    return False, "|| 模式下，填写的逗号分隔的最小值和最大值数量必须成对匹配！"
                
                pass_any = False
                range_msgs = []
                for l_str, u_str in zip(lower_parts, upper_parts):
                    l_val = self._to_numeric(l_str)
                    u_val = self._to_numeric(u_str)
                    if l_val is None or u_val is None:
                        return False, f"|| 模式中检测到无效数字: 最小 '{l_str}' 或 最大 '{u_str}'"
                    
                    if l_val <= u_val:
                        in_this_range = l_val <= numeric_result <= u_val
                        range_msgs.append(f"[{_format_with_hex(l_val)}, {_format_with_hex(u_val)}]")
                    else:
                        in_this_range = numeric_result >= l_val or numeric_result <= u_val
                        range_msgs.append(f"[{_format_with_hex(l_val)}~360/0~{_format_with_hex(u_val)}]")
                        
                    if in_this_range:
                        pass_any = True
                
                result_formatted = _format_with_hex(numeric_result)
                ranges_str = " 或者 ".join(range_msgs)
                return pass_any, f"实测值：{result_formatted}, 范围：{ranges_str}"

            # 正常单独数值解析
            lower_limit, upper_limit = self._to_numeric(lower_limit_str), self._to_numeric(upper_limit_str)
            
            result_formatted = _format_with_hex(numeric_result)
            
            if mode == 'InRange':
                if lower_limit is None or upper_limit is None: return False, "InRange 模式需要有效的最小值和最大值。"
                is_pass = lower_limit <= numeric_result <= upper_limit
                return is_pass, f"实测值：{result_formatted}, 范围：[{_format_with_hex(lower_limit)}, {_format_with_hex(upper_limit)}]"
            if mode == 'NotInRange':
                if lower_limit is None or upper_limit is None: return False, "NotInRange 模式需要有效的最小值和最大值。"
                is_pass = not (lower_limit <= numeric_result <= upper_limit)
                return is_pass, f"实测值：{result_formatted}, 禁止范围：[{_format_with_hex(lower_limit)}, {_format_with_hex(upper_limit)}]"
            if mode in ['==', '!=', '>',
                        '>='] and lower_limit is None: return False, f"{mode} 模式需要一个有效的最小值。"
            if mode in ['<', '<='] and upper_limit is None: return False, f"{mode} 模式需要一个有效的最大值。"
            ops = {'==': (lambda a, b: a == b), '!=': (lambda a, b: a != b), '>': (lambda a, b: a > b),
                   '>=': (lambda a, b: a >= b), '<': (lambda a, b: a < b), '<=': (lambda a, b: a <= b)}
            target = upper_limit if mode in ['<', '<='] else lower_limit
            is_pass = ops[mode](numeric_result, target)
            # 改进消息格式：显示 "实测值：X(0xX), 设定值：Y(0xY) (判断条件: mode)"
            return is_pass, f"实测值：{result_formatted}, 设定值：{_format_with_hex(target)} (判断条件: {mode})"
        elif mode in ['Contains', 'NotContains']:
            str_result, substring = str(value_for_comparison), lower_limit_str
            if not substring: return False, f"{mode} 模式需要在'最小值'字段中指定一个用于搜索的子字符串。"
            
            # 修复：将前端表格中输入的 Literal "\r\n" 字符串转换回真实的换行符，以便正确匹配（保留，防止用户想强匹配格式）
            substring_literal = substring.replace('\\r', '\r').replace('\\n', '\n')
            
            # 新增增强匹配：把源字符串和要寻找的子串中的所有换行符都替换为空格，并将连续空格压缩为单个空格
            import re
            norm_str_result = re.sub(r'\s+', ' ', str_result).strip()
            norm_substring = re.sub(r'\s+', ' ', substring_literal).strip()
            
            # 我们优先尝试原样精准匹配，如果失败，再尝试去除了换行的“模糊匹配”
            if mode == 'Contains': 
                 if substring_literal in str_result:
                      return True, f"'{str_result}' contains '{substring_literal}'"
                 elif norm_substring in norm_str_result:
                      return True, f"匹配成功(忽略换行): '{norm_str_result}' contains '{norm_substring}'"
                 else:
                      return False, f"'{str_result}' does not contain '{substring}'"
            if mode == 'NotContains':
                 # NotContains 我们需要原串和模糊串都不包含，才是真正的 NotContains
                 if substring_literal not in str_result and norm_substring not in norm_str_result:
                      return True, f"'{str_result}' does not contain '{substring}'"
                 else:
                      return False, f"匹配失败: '{str_result}' contains '{substring}'"
        return None

    def _mark_skipped_steps(self, start_ptr_idx, end_ptr_idx, original_indices, block_df, reason):
        for i in range(start_ptr_idx, end_ptr_idx):
            skipped_original_index = original_indices[i]
            skipped_step = block_df[block_df['original_index'] == skipped_original_index].iloc[0]
            test_name = str(skipped_step.get('TestName', '')).strip()
            if test_name.startswith(('*', '#')): self.all_step_results_for_report.append(
                {**skipped_step.to_dict(), 'type': 'block'}); continue
            step_result_content = {'status': 'SKIP', 'result': 'SKIP', 'message': reason}
            self.logger.step_update({'step_index': skipped_original_index, **step_result_content})
            self.all_step_results_for_report.append({**skipped_step.to_dict(), **step_result_content})

    def _execute_block(self, block_df, variables, last_result_wrapper, block_name, is_cleanup_block=False):
        test_passed, first_fail_info = True, None
        original_indices = block_df['original_index'].tolist()
        num_steps = len(original_indices)
        ptr = 0
        executed_if_branch = False
        is_breaking_loop = False

        while ptr < num_steps:
            original_index = original_indices[ptr]
            step = self.sequence_df.loc[self.sequence_df['original_index'] == original_index].iloc[0]

            if self._should_stop() and not is_cleanup_block: test_passed, first_fail_info = False, {
                'step_index': original_index, 'message': '用户中止'}; break
            if not str(step.get('TestName', '')).strip().startswith(('*', '#')) and step.get(
                'Enable') and not is_cleanup_block: self._check_and_pause_if_needed(original_index)
            if self._should_stop() and not is_cleanup_block: test_passed, first_fail_info = False, {
                'step_index': original_index, 'message': '用户中止'}; break

            status, msg = "SKIP", ""
            test_name = str(step.get('TestName', '')).strip()
            func_name = step.get('Function')

            if not step.get('Enable'):
                self.all_step_results_for_report.append(
                    {**step.to_dict(), 'status': 'SKIP', 'result': 'SKIP', 'message': '此步骤被禁用'});
                ptr += 1;
                continue
            if test_name.startswith(('*', '#')):
                self.all_step_results_for_report.append({'type': 'block', **step.to_dict()});
                ptr += 1;
                continue

            if func_name == 'if_variable':
                executed_if_branch = False
                status, msg = self._parse_and_execute(step, variables, last_result_wrapper)
                result_tuple = last_result_wrapper.get('value');
                condition_is_true = bool(result_tuple[0]) if isinstance(result_tuple, tuple) else bool(result_tuple)
                result_val, status = str(condition_is_true), "PASS"
                self.all_step_results_for_report.append(
                    {**step.to_dict(), 'status': status, 'result': result_val, 'message': msg})
                if condition_is_true:
                    executed_if_branch = True; ptr += 1
                else:
                    jump_targets = self.control_flow_map.get(original_index, {});
                    next_branch_idx = jump_targets.get('next_branch', jump_targets.get('endif'))
                    if next_branch_idx and next_branch_idx in original_indices:
                        target_ptr = original_indices.index(next_branch_idx)
                        self._mark_skipped_steps(ptr + 1, target_ptr, original_indices, block_df, "IF条件不满足");
                        ptr = target_ptr
                    else:
                        test_passed, first_fail_info = False, {'step_index': original_index,
                                                               'message': 'IF结构错误或未关闭'}; break
                continue

            elif func_name == 'elseif_variable':
                if executed_if_branch:
                    endif_idx = self.control_flow_map.get(original_index, {}).get('endif')
                    if endif_idx and endif_idx in original_indices:
                        target_ptr = original_indices.index(endif_idx)
                        self._mark_skipped_steps(ptr, target_ptr, original_indices, block_df,
                                                 "前置IF/ELSEIF条件已满足");
                        ptr = target_ptr
                    else:
                        test_passed, first_fail_info = False, {'step_index': original_index,
                                                               'message': 'ELSEIF结构错误或未关闭'}; break
                else:
                    status, msg = self._parse_and_execute(step, variables, last_result_wrapper)
                    result_tuple = last_result_wrapper.get('value');
                    condition_is_true = bool(result_tuple[0]) if isinstance(result_tuple, tuple) else bool(result_tuple)
                    result_val, status = str(condition_is_true), "PASS"
                    self.all_step_results_for_report.append(
                        {**step.to_dict(), 'status': status, 'result': result_val, 'message': msg})
                    if condition_is_true:
                        executed_if_branch = True; ptr += 1
                    else:
                        jump_targets = self.control_flow_map.get(original_index, {});
                        next_branch_idx = jump_targets.get('next_branch', jump_targets.get('endif'))
                        if next_branch_idx and next_branch_idx in original_indices:
                            target_ptr = original_indices.index(next_branch_idx)
                            self._mark_skipped_steps(ptr + 1, target_ptr, original_indices, block_df,
                                                     "ELSEIF条件不满足");
                            ptr = target_ptr
                        else:
                            test_passed, first_fail_info = False, {'step_index': original_index,
                                                                   'message': 'ELSEIF结构错误或未关闭'}; break
                continue

            elif func_name == 'else_block':
                if executed_if_branch:
                    endif_idx = self.control_flow_map.get(original_index, {}).get('endif')
                    if endif_idx and endif_idx in original_indices:
                        target_ptr = original_indices.index(endif_idx)
                        self._mark_skipped_steps(ptr, target_ptr, original_indices, block_df,
                                                 "前置IF/ELSEIF条件已满足");
                        ptr = target_ptr
                    else:
                        test_passed, first_fail_info = False, {'step_index': original_index,
                                                               'message': 'ELSE结构错误或未关闭'}; break
                else:
                    self.all_step_results_for_report.append({**step.to_dict(), 'status': "PASS"}); ptr += 1
                continue

            elif func_name == 'end_if':
                self.all_step_results_for_report.append({**step.to_dict(), 'status': "PASS"});
                ptr += 1;
                continue

            elif func_name == 'for_loop':
                params = self._safe_eval_params(step.get('Parameters', ''))
                count = int(params.get('count', 1))
                self.all_step_results_for_report.append(
                    {**step.to_dict(), 'status': 'PASS', 'result': f"总计 {count} 次"})
                if count > 0:
                    self.loop_counters[original_index] = {'current': 1, 'total': count};
                    self.loop_stack.append(original_index);
                    ptr += 1
                else:
                    end_for_idx = self.control_flow_map.get(original_index, {}).get('end_for')
                    if end_for_idx and end_for_idx in original_indices:
                        target_ptr = original_indices.index(end_for_idx)
                        self._mark_skipped_steps(ptr + 1, target_ptr, original_indices, block_df, "循环次数为0");
                        ptr = target_ptr
                    else:
                        test_passed, first_fail_info = False, {'step_index': original_index,
                                                               'message': '未找到匹配的 end_for'}; break
                continue

            elif func_name == 'end_for':
                for_loop_idx = self.control_flow_map.get(original_index, {}).get('for_loop')
                if for_loop_idx and for_loop_idx in self.loop_counters:
                    loop_info = self.loop_counters[for_loop_idx]
                    self.all_step_results_for_report.append({**step.to_dict(), 'status': 'PASS',
                                                             'result': f"迭代 {loop_info['current']}/{loop_info['total']}"})
                    if is_breaking_loop:
                        is_breaking_loop = False
                        del self.loop_counters[for_loop_idx]
                        if self.loop_stack and self.loop_stack[-1] == for_loop_idx: self.loop_stack.pop()
                        ptr += 1
                    elif loop_info['current'] < loop_info['total']:
                        loop_info['current'] += 1
                        time.sleep(0.01)  # FOR 循环迭代间延时 10ms
                        ptr = original_indices.index(for_loop_idx) + 1
                    else:
                        del self.loop_counters[for_loop_idx]
                        if self.loop_stack and self.loop_stack[-1] == for_loop_idx: self.loop_stack.pop()
                        ptr += 1
                else:
                    self.all_step_results_for_report.append({**step.to_dict(), 'status': 'PASS'})
                    ptr += 1
                continue



            elif func_name == 'do_while_start':
                # WHILE Loop Start: Evaluation Condition immediately
                status, msg = self._parse_and_execute(step, variables, last_result_wrapper)
                result_tuple = last_result_wrapper.get('value')
                # Check Condition (True = Enter Loop, False = Skip Loop)
                condition_is_true = bool(result_tuple[0]) if isinstance(result_tuple, tuple) else bool(result_tuple)
                
                result_val = str(condition_is_true)
                self.all_step_results_for_report.append(
                    {**step.to_dict(), 'status': 'PASS', 'result': result_val, 'message': f"While条件: {msg}"})

                if condition_is_true:
                    # Enter Loop: Push to stack so 'break' knows where we are
                    self.loop_stack.append(original_index)
                    ptr += 1
                else:
                    # Skip Loop: Jump to end_do_while + 1
                    end_do_while_idx = self.control_flow_map.get(original_index, {}).get('end_do_while')
                    if end_do_while_idx and end_do_while_idx in original_indices:
                        target_ptr = original_indices.index(end_do_while_idx)
                        self._mark_skipped_steps(ptr + 1, target_ptr + 1, original_indices, block_df, "While条件不满足，跳过")
                        ptr = target_ptr + 1
                    else:
                        test_passed, first_fail_info = False, {'step_index': original_index, 'message': 'While 结构错误: 未找到匹配的 end_do_while'}; break
                continue

            elif func_name == 'end_do_while':
                # WHILE Loop End
                do_while_idx = self.control_flow_map.get(original_index, {}).get('do_while')
                self.all_step_results_for_report.append({**step.to_dict(), 'status': 'PASS', 'message': '循环结束，跳回循环起点'})
                
                if is_breaking_loop:
                    # Handle Break
                    is_breaking_loop = False
                    if self.loop_stack and self.loop_stack[-1] == do_while_idx:
                        self.loop_stack.pop()
                    ptr += 1 # Continue past end_do_while
                elif do_while_idx and do_while_idx in original_indices:
                    # Normal Loop: Pop stack (clean up current iteration push) and Jump back to Start
                    # Note: We must pop the stack because do_while_start will push again if entered.
                    if self.loop_stack and self.loop_stack[-1] == do_while_idx:
                        self.loop_stack.pop()
                    
                    target_ptr = original_indices.index(do_while_idx)
                    ptr = target_ptr
                    time.sleep(0.01)
                else:
                    test_passed, first_fail_info = False, {'step_index': original_index, 'message': 'While 结构错误: 找不到起始点'}; break
                continue

            elif func_name == 'break_loop':
                if self.loop_stack:
                    is_breaking_loop = True
                    broken_loop_idx = self.loop_stack[-1]
                    
                    # 尝试查找 end_for (FOR循环)
                    end_for_idx = self.control_flow_map.get(broken_loop_idx, {}).get('end_for')
                    
                    # 尝试查找 end_do_while (WHILE循环)
                    end_do_while_idx = self.control_flow_map.get(broken_loop_idx, {}).get('end_do_while')

                    self.all_step_results_for_report.append(
                        {**step.to_dict(), 'status': 'PASS', 'message': '请求跳出循环'})
                    
                    if end_for_idx and end_for_idx in original_indices:
                        target_ptr = original_indices.index(end_for_idx)
                        self._mark_skipped_steps(ptr + 1, target_ptr, original_indices, block_df,
                                                 "执行BREAK，跳至循环末尾")
                        ptr = target_ptr
                    elif end_do_while_idx and end_do_while_idx in original_indices:
                        # 对于 WHILE 循环，break 意味着跳到 end_do_while
                        target_ptr = original_indices.index(end_do_while_idx)
                        self._mark_skipped_steps(ptr + 1, target_ptr, original_indices, block_df,
                                                 "执行BREAK，跳至循环末尾")
                        ptr = target_ptr
                    else:
                        test_passed, first_fail_info = False, {'step_index': original_index,
                                                               'message': '未找到匹配的 end_for 或 end_do_while 用于 break'}; break
                else:
                    test_passed, first_fail_info = False, {'step_index': original_index,
                                                           'message': 'break_loop 不在任何循环内'}; break
                continue

            # --- 普通测试步骤 ---
            self.logger.info(f"开始执行: {test_name} (步骤 {step.get('step_number', '')})")
            self.logger.step_update({'step_index': original_index, 'status': 'RUNNING'})
            status, msg = self._parse_and_execute(step, variables, last_result_wrapper)
            raw_result = last_result_wrapper.get('value')

            # 修正BUG：确保在比较时使用元组的第二个值（测量结果）
            if isinstance(raw_result, tuple) and len(raw_result) > 1 and isinstance(raw_result[0], bool):
                value_for_comparison = raw_result[1]
            else:
                value_for_comparison = raw_result

            if var_to_store := step.get('Variable'):
                variables[var_to_store] = raw_result
                self.logger.info(f"步骤结果已存入变量 '{var_to_store}'。")
                # 将变量赋值信息添加到消息中
                var_assign_msg = f"[赋值给变量 '{var_to_store}']"
                msg = f"{msg} {var_assign_msg}" if msg else var_assign_msg
                
            if (compare_mode := step.get('Compare')) and status == "PASS":
                if (comparison_result := self._perform_comparison(compare_mode, value_for_comparison,
                                                                  step.get('LowerLimit'),
                                                                  step.get('UpperLimit'))) is not None:
                    is_pass, compare_msg = comparison_result
                    if not is_pass:
                        status = "FAIL"
                        # 保留原始消息（包含地址信息）+ 比较结果
                        original_msg = msg if msg else ""
                        msg = f"{original_msg}, 比较失败: {compare_msg}" if compare_msg else f"比较 '{compare_mode}' 失败。"


            # Preserve raw_result for data analysis, but use string for display
            # 提取显示用的结果值（只显示数值，不显示完整元组）
            if isinstance(raw_result, tuple) and len(raw_result) >= 2:
                if isinstance(raw_result[0], bool):
                    display_result = raw_result[1] if len(raw_result) > 1 else raw_result[0]
                elif isinstance(raw_result[0], (int, float)) and isinstance(raw_result[1], str):
                    display_result = raw_result[0]
                else:
                    display_result = raw_result[0]
            else:
                display_result = raw_result
            
            # 判断是否为执行类操作（结果为 True 或 (True, msg) 格式）
            # 执行类操作：写入寄存器、打开串口、设置电源等，结果列只显示 "Done"
            is_execution_type = False
            if raw_result is True:
                is_execution_type = True
            elif isinstance(raw_result, tuple) and len(raw_result) >= 1 and raw_result[0] is True:
                is_execution_type = True
            
            if is_execution_type:
                display_result = "Done"
            
            # 用于保存到报告的内容（result 使用处理后的显示值, raw_result 保留原始值供CPK分析）
            step_result_content = {'status': status, 'result': display_result, 'raw_result': raw_result, 'message': msg}
            
            # For UI display
            ui_update_content = step_result_content.copy()
            ui_update_content['result'] = str(display_result)
            
            self.logger.step_update({'step_index': original_index, **ui_update_content})
            self.all_step_results_for_report.append({**step.to_dict(), **step_result_content})

            ptr_incremented = False
            if executed_if_branch:
                is_last_step_of_branch = False
                if ptr + 1 < num_steps:
                    next_step_func = self.sequence_df.loc[
                        self.sequence_df['original_index'] == original_indices[ptr + 1], 'Function'].iloc[0]
                    if next_step_func in ['elseif_variable', 'else_block', 'end_if']: is_last_step_of_branch = True
                else:
                    is_last_step_of_branch = True
                if is_last_step_of_branch:
                    current_if_head = original_index
                    while True:
                        if_start_node = self.control_flow_map.get(current_if_head)
                        if if_start_node and 'if_start' in if_start_node:
                            current_if_head = if_start_node['if_start']
                        else:
                            break
                    endif_idx = self.control_flow_map.get(current_if_head, {}).get('endif')
                    if endif_idx and endif_idx in original_indices: ptr = original_indices.index(
                        endif_idx); ptr_incremented = True

            if not ptr_incremented: ptr += 1

            # 步骤间延时，避免通信过于频繁导致设备响应不完整
            time.sleep(0.01)  # 10ms

            if status == "FAIL":
                if test_passed: test_passed, first_fail_info = False, {'step_index': original_index, 'message': msg,
                                                                       'result': raw_result}
                self.logger.error(f"步骤失败: {test_name} - {msg}")
                if is_cleanup_block: self.logger.warning("Cleanup 步骤失败，将继续执行下一个 Cleanup 步骤。"); continue
                action = step.get('StepAction', 'stop')
                if action == 'continue':
                    self.logger.warning("步骤失败，但设置为 [Continue]，继续测试..."); continue
                elif action == 'fail_goto_step' and (goto_step_num_str := str(step.get('GotoStep', '')).strip()):
                    try:
                        target_original_index = \
                        self.sequence_df[self.sequence_df['step_number'] == int(goto_step_num_str)].iloc[0][
                            'original_index']
                        ptr = original_indices.index(target_original_index);
                        continue
                    except (ValueError, IndexError, KeyError):
                        self.logger.error(f"无法定位跳转步骤 '{step.get('GotoStep')}'，测试终止！"); break
                else:
                    self.logger.error("步骤失败，设置为 [Stop]，测试终止！"); break
            elif status == "PASS" and step.get('StepAction') == 'pass_goto_step' and str(
                    step.get('GotoStep', '')).strip():
                try:
                    target_original_index = \
                    self.sequence_df[self.sequence_df['step_number'] == int(step.get('GotoStep'))].iloc[0][
                        'original_index']
                    ptr = original_indices.index(target_original_index);
                    continue
                except (ValueError, IndexError, KeyError):
                    self.logger.warning(f"无法定位跳转步骤 '{step.get('GotoStep')}'。")
        return test_passed, first_fail_info

    def _get_db_path(self):
        """
        可靠地获取数据库文件的路径，该文件应与EXE在同一目录。
        """
        # 使用我们从 app_utils 导入的可靠函数 get_app_base_path()
        base_path = get_app_base_path()
        
        # 从配置读取数据库名称
        database_name = self.global_config.get('database_name', 'test_history')
        
        return os.path.join(base_path, f'{database_name}.db')

    def _log_final_result_to_db(self, final_status, first_fail_details, duration):
        """Logs the final test result to the database."""
        try:
            sequence_name = os.path.splitext(os.path.basename(self.sequence_file_path))[0] if self.sequence_file_path else "Unsaved_Sequence"
            
            fail_step = None
            fail_message = None
            if final_status == "FAIL" and first_fail_details:
                fail_step_index = first_fail_details.get('step_index')
                if fail_step_index is not None and fail_step_index != -1:
                    try:
                        fail_step = self.sequence_df.loc[self.sequence_df['original_index'] == fail_step_index, 'TestName'].iloc[0]
                    except (KeyError, IndexError):
                        fail_step = f"Index {fail_step_index}"
                fail_message = first_fail_details.get('message')

            cables_str = ", ".join(self.adapter_cables) if isinstance(self.adapter_cables, list) else (str(self.adapter_cables) if self.adapter_cables else "N/A")
            life_str = str(self.adapter_cable_life) if self.adapter_cable_life else "N/A"

            log_data = {
                'timestamp': datetime.now().isoformat(),
                'sequence_name': sequence_name,
                'station_id': self.station_id,
                'employee_id': self.operator_id,
                'uut_sn': self.uut_sn,
                'status': final_status,
                'duration': duration,
                'fail_step': fail_step,
                'fail_message': fail_message,
                'adapter_cables': cables_str,
                'adapter_cable_life': life_str,
                'thimble_life': getattr(self, 'thimble_life', 'Not used')
            }
            result_id = log_test_result(log_data)
            if result_id:
                self._log_step_results_to_db(result_id)
                self.logger.info(f"测试结果 (ID: {result_id}) 已记录到数据库: {final_status} for SN {self.uut_sn}")
            else:
                self.logger.error("未能获取主测试记录的ID，详细步骤数据无法记录。")
            return result_id
        except Exception as e:
            self.logger.error(f"记录最终测试结果到数据库失败: {e}", exc_info=True)
            return None

    def _log_step_results_to_db(self, result_id):
        """Logs detailed results of individual test steps to the database for CPK analysis."""
        try:
            steps_to_log = []
            for step in self.all_step_results_for_report:
                # Ensure the result is a numeric value
                # First, determine if we should log this step for CPK
                # Logic:
                # 1. If CPK is explicitly 'True' -> Log it.
                # 2. Everything else (False, Empty, Missing) -> Skip it.
                cpk_setting = str(step.get('CPK', '')).strip().lower()

                if cpk_setting != 'true':
                    continue

                try:
                    # Handle cases where result is a tuple (e.g., from a comparison)
                    raw_result = step.get('raw_result', step.get('result'))

                    # CRITICAL FIX: Communication functions return (value, message_string)
                    # We need to extract the NUMERIC value, not parse the message string!
                    if isinstance(raw_result, tuple) and len(raw_result) >= 2:
                        # Check if first element is a boolean (test result from _execute_step)
                        if isinstance(raw_result[0], bool):
                            # Format: (True/False, actual_value)
                            measurement_value = self._to_numeric(str(raw_result[1]))
                        else:
                            # Format: (numeric_value, message_string) - from communication functions
                            # Use raw_result[0] directly, not the message string!
                            measurement_value = self._to_numeric(str(raw_result[0]))
                    else:
                        measurement_value = self._to_numeric(str(raw_result))
                except (ValueError, TypeError):
                    self.logger.warning(f"CPK-flagged step '{step.get('TestName')}' result '{step.get('result')}' is not numeric. Skipping.")
                    continue
                
                if measurement_value is None:
                    continue

                # Ensure limits are valid numbers
                upper_limit = self._to_numeric(step.get('UpperLimit'))
                lower_limit = self._to_numeric(step.get('LowerLimit'))
                # Check if both limits are missing
                if upper_limit is None and lower_limit is None:
                    # Only log a warning if it looks like a test step (has a Compare mode) but no limits
                    if step.get('Compare'):
                         self.logger.warning(f"Step '{step.get('TestName')}' has CPK=True but no valid numeric limits. CPK data not logged.")
                    continue

                # Debug log to confirm what is being logged
                # self.logger.debug(f"Logging CPK data for step '{step.get('TestName')}': Val={measurement_value}, USL={upper_limit}, LSL={lower_limit}")

                steps_to_log.append((
                    result_id,
                    step.get('TestName', 'Unknown Step'),
                    measurement_value,
                    upper_limit,
                    lower_limit
                ))

            if not steps_to_log:
                return

            db_path = self._get_db_path()
            con = sqlite3.connect(db_path)
            cursor = con.cursor()
            cursor.executemany(
                "INSERT INTO test_step_results (result_id, step_name, measurement_value, upper_limit, lower_limit) VALUES (?, ?, ?, ?, ?)",
                steps_to_log
            )
            con.commit()
            con.close()
            self.logger.info(f"成功记录 {len(steps_to_log)} 个步骤的详细数据到数据库。")

        except Exception as e:
            self.logger.error(f"记录详细步骤数据到数据库失败: {e}", exc_info=True)

    def run_sequence(self):
        self.start_time = time.time();
        self.logger.info(f"测试开始, SN: {self.uut_sn}")
        variables, last_result_wrapper = {'uut_sn': self.uut_sn}, {'value': None};
        first_fail_details = None
        try:
            for block_name in ['setup', 'main']:
                block_df = self.sequence_df[self.sequence_df['Block'].str.lower() == block_name]
                if block_df.empty: continue
                self.logger.info(f"进入 {block_name.capitalize()} 区块")
                passed, fail_info = self._execute_block(block_df, variables, last_result_wrapper,
                                                        block_name.capitalize())
                if not passed:
                    if first_fail_details is None: first_fail_details = fail_info
                    if fail_info is None or fail_info.get('message') != '用户中止': break
        except Exception as e:
            self.logger.error("TestEngine 发生严重异常", exc_info=True)
            if first_fail_details is None: first_fail_details = {'step_index': -1, 'message': f"引擎异常: {e}",
                                                                 'result': 'N/A'}
        finally:
            if not (cleanup_df := self.sequence_df[self.sequence_df['Block'].str.lower() == 'cleanup']).empty:
                self.logger.info("进入 Cleanup 区块");
                passed, fail_info = self._execute_block(cleanup_df, variables, last_result_wrapper, "Cleanup",
                                                        is_cleanup_block=True)
                if not passed and fail_info and first_fail_details is None: first_fail_details = fail_info
            duration = time.time() - self.start_time
            final_status = "PASS"
            final_message = "测试通过"
            
            if first_fail_details:
                if first_fail_details.get('message') == '用户中止':
                    final_status = "USER_STOPPED"
                    final_message = {'fail_details': first_fail_details}
                else:
                    final_status = "FAIL"
                    final_message = {'fail_details': first_fail_details}
            elif self._should_stop():
                 final_status = "USER_STOPPED"
                 final_message = {'fail_details': {'message': '用户中止', 'step_index': -1}}

            # 测试结束，只要进行了测试 (PASS 或 FAIL)，自动对配方转接线进行使用寿命+1，并刷新最新使用次数
            if final_status in ["PASS", "FAIL"] and self.adapter_cables and self.adapter_cables != ["Not used"]:
                try:
                    from utils.consumable_db import increment_cable_count, check_cable_sn
                    life_parts = []
                    for c_sn in self.adapter_cables:
                        if c_sn and c_sn != "Not used":
                            increment_cable_count(c_sn)
                            c_info = check_cable_sn(c_sn)
                            used = c_info.get('total_count', 0) if c_info else 0
                            limit = c_info.get('max_limit', 10000) if c_info else 10000
                            life_parts.append(f"{c_sn} ({used}/{limit})")
                    if life_parts:
                        self.adapter_cable_life = ", ".join(life_parts)
                except Exception as e:
                    print(f"[TestEngine] 自动累加转接线寿命及刷新报告信息失败: {e}")

            if final_status != "USER_STOPPED": self._save_html_report(final_status, final_message, duration)
            
            # ADDED: Log to database for normal tests
            db_record_id = None
            if self.report_output_dir is None: # Only log normal tests to the database
                db_record_id = self._log_final_result_to_db(final_status, first_fail_details, duration)
                
                # --- Log to Work Order DB (自动使用序列名) ---
                # 【修改】始终使用序列名自动记录，不再依赖传入的工单号
                sequence_name = os.path.basename(self.sequence_file_path) if self.sequence_file_path else None
                if sequence_name:
                    try:
                        threading.Thread(target=self._log_to_work_order_db, 
                                         args=(sequence_name, duration, final_status)).start()
                    except Exception as e:
                        self.logger.error(f"Failed to start thread for Work Order DB logging: {e}")

            self.logger.info(f"测试结束, 结果: {final_status}, 耗时: {duration:.2f}s")
            self.logger.final_status({
                'uut_sn': self.uut_sn,
                'status': final_status, 
                'message': final_message, 
                'duration': f"{duration:.2f}s",
                'duration_raw': duration,
                'all_steps_results': self.all_step_results_for_report, # 【核心修改】将所有步骤结果包含在最终信号中
                'operator_id': self.operator_id,
                'db_record_id': db_record_id  # 【新增】数据库记录ID，用于复测通过时更新数据库
            })

    def _get_report_filepath(self, extension, final_status):
        """
        可靠地获取报告文件的完整绝对路径。
        报告将始终保存在程序根目录下的 'reports' 文件夹中。
        """
        try:
            # 优先使用 self.report_output_dir (用于临时报告的重新分析，此逻辑保持)
            if self.report_output_dir:
                full_report_dir = self.report_output_dir
            else:
                # 正常测试时，强制使用程序根目录下的 'reports' 文件夹
                # 使用我们可靠的 get_app_base_path() 函数
                base_path = os.path.join(get_app_base_path(), 'reports')

                # 构建完整的报告目录路径 (保持您原有的子目录结构)
                sequence_name = os.path.splitext(os.path.basename(self.sequence_file_path))[
                    0] if self.sequence_file_path else "Unsaved_Sequence"
                result_folder = "PASS" if final_status == "PASS" else "FAIL"
                year_month_folder = datetime.now().strftime("%Y%m")
                full_report_dir = os.path.join(base_path, sequence_name, result_folder, year_month_folder)

            # 确保最终的目标目录存在，如果不存在则创建
            os.makedirs(full_report_dir, exist_ok=True)

            # 保存报告目录路径供外部模块使用（如黑匣子报告）
            self.report_dir = full_report_dir

            # 构建最终的文件名 (包含产品SN与配方转接线SN)
            station_num = self.station_id.split('_')[-1]
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            safe_uut_sn = re.sub(r'[\\/:*?"<>|]', '_', self.uut_sn)

            # 若配方绑定了转接线，在产品SN后面附加上线缆SN
            cable_suffix = ""
            if hasattr(self, 'adapter_cables') and isinstance(self.adapter_cables, list) and self.adapter_cables and self.adapter_cables != ["Not used"]:
                cable_str = "_".join([str(c) for c in self.adapter_cables if c and c != "Not used"])
                if cable_str:
                    safe_cable = re.sub(r'[\\/:*?"<>|]', '_', cable_str)
                    cable_suffix = f"_{safe_cable}"

            filename = f"{final_status}_station_{station_num}_{safe_uut_sn}{cable_suffix}_{timestamp}{extension}"

            return os.path.join(full_report_dir, filename)

        except PermissionError:
            # 使用 try-except 块来处理可能的权限问题
            log_dir = full_report_dir if 'full_report_dir' in locals() else "未知"
            self.logger.error(
                f"【权限错误】无法在路径 '{log_dir}' 创建文件夹或写入文件！请检查程序权限。"
            )
            return None
        except Exception as e:
            log_dir = full_report_dir if 'full_report_dir' in locals() else "未知"
            self.logger.error(f"在路径 '{log_dir}' 创建报告时发生未知错误: {e}", exc_info=True)
            return None

    def _log_to_work_order_db(self, sequence_name, duration, status):
        """Helper to log to work order DB safely using new session system."""
        try:
            # 使用新的会话系统API
            work_order_db.add_session_sample(
                sequence_name=sequence_name,
                duration=duration,
                status=status,
                station_count=getattr(self, 'station_count', 1),
                operator_name=getattr(self, 'operator_name', None),
                operator_id=self.operator_id
            )
        except Exception as e:
            print(f"[Engine] Failed to log to WorkOrderDB: {e}")

    # --- 【【【 核心修改：调整报告生成逻辑以实现完美对齐 】】】 ---
    def _save_html_report(self, final_status, final_message, duration):
        filepath = self._get_report_filepath('.html', final_status)
        from utils.report_generator import save_html_report
        save_html_report(self, filepath, final_status, final_message, duration)
