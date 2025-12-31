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


# --- HTML模板保持不变 ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>自动化测试报告 - ${uut_sn}</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "Noto Sans", sans-serif; margin: 0; padding: 40px; background-color: #ffffff; color: #333; font-size: 14px; }
        .container { max-width: 1400px; margin: auto; }
        h1 { font-size: 24px; font-weight: 600; color: #2c3e50; text-align: center; margin-bottom: 40px; }
        .summary-table { width: auto; margin-bottom: 30px; border-collapse: collapse; margin-left: 0; margin-right: auto; }
        .summary-table td { padding: 6px 0; vertical-align: top; }
        .summary-table td.label { font-weight: 600; padding-right: 10px; color: #34495e; text-align: left; white-space: nowrap; }
        .summary-table td.value { text-align: left; }
        .status-pass { color: #27ae60; font-weight: bold; }
        .status-fail { color: #c0392b; font-weight: bold; }
        .status-user_stopped { color: #7f8c8d; font-weight: bold; }
        hr { border: none; border-top: 1px solid #ecf0f1; margin: 30px 0; }
        h2 { font-size: 18px; font-weight: 600; color: #2c3e50; border-bottom: 2px solid #ecf0f1; padding-bottom: 10px; margin-bottom: 20px; }
        .details-table { width: 100%; border-collapse: collapse; margin-top: 20px; table-layout: fixed; }
        .details-table th, .details-table td { border: 1px solid #ddd; padding: 10px; text-align: left; word-wrap: break-word; overflow-wrap: break-word; }
        .details-table th { background-color: #34495e; color: white; font-weight: normal; }
        tr:nth-child(even) { background-color: #f9f9f9; }
        .step-pass { color: #27ae60; }
        .step-fail { color: #c0392b; font-weight: bold; }
        .step-skipped { color: #7f8c8d; }
        .block-row { background-color: #bdc3c7 !important; font-weight: bold; text-align: center; }
        .flow-control { font-style: italic; color: #34495e; }
    </style>
</head>
<body>
    <div class="container">
        <h1>自动化测试报告</h1>
        <table class="summary-table">
            <tbody>
                <tr><td class="label">产品型号:</td><td class="value">${product_model}</td></tr>
                <tr><td class="label">测试程序版本:</td><td class="value">${sequence_version}</td></tr>
                <tr><td class="label">产品SN:</td><td class="value">${uut_sn}</td></tr>
                <tr><td class="label">工位号:</td><td class="value">${station_id}</td></tr>
                <tr><td class="label">操作员工号:</td><td class="value">${operator_id}</td></tr> <!-- NEW -->
                <tr><td class="label">测试时间:</td><td class="value">${start_time}</td></tr>
                <tr><td class="label">测试用时:</td><td class="value">${duration_seconds}s</td></tr>
                <tr><td class="label">测试结果:</td><td class="value ${final_status_class}">${final_status}</td></tr>
                ${failure_details_row}
            </tbody>
        </table>
        <hr>
        <h2>测试详情</h2>
        <table class="details-table">
            <thead>
                <tr>
                    <th style="width: 3%;">步骤</th><th style="width: 15%;">测试名称</th><th style="width: 10%;">模块</th>
                    <th style="width: 10%;">函数</th><th style="width: 20%;">参数</th><th style="width: 6%;">范围</th>
                    <th style="width: 4%;">状态</th><th style="width: 12%;">结果值</th><th style="width: 20%;">信息</th>
                </tr>
            </thead>
            <tbody>${table_rows}</tbody>
        </table>
    </div>
</body>
</html>
"""


class TestEngineLogger:
    def __init__(self, station_id, signals): self.station_id, self.signals = station_id, signals

    def log(self, message, level='INFO'): self.signals.log.emit(
        (f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] {message}", level.upper()))

    def info(self, message): self.log(message, 'INFO')

    def error(self, message, exc_info=False): self.log(message + ('\n' + traceback.format_exc() if exc_info else ''),
                                                       'ERROR')

    def warning(self, message): self.log(message, 'WARNING')

    def debug(self, message): self.log(message, 'DEBUG')

    def step_update(self, content): self.signals.step_update.emit(
        {'station_id': self.station_id, 'type': 'step_update', 'content': content})

    def final_status(self, content): self.signals.final_status.emit(
        {'station_id': self.station_id, 'type': 'final_status', 'content': content})

    def progress(self, value): self.signals.progress.emit(value)

    def paused_at(self, step_index): self.signals.paused_at.emit(step_index)


class TestEngine:
    def __init__(self, station_id, uut_sn, global_config, hardware_manager, sequence_data, available_modules, signals,
                 is_debugging, breakpoints, local_stop_event, stop_all_event, pause_event, step_event, resume_event,
                 sequence_file_path, report_output_dir=None, operator_id=None, operator_name=None, 
                 work_order=None, target_qty=None, station_count=1):
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
        if self.sequence_file_path:
            filename_without_ext = os.path.splitext(os.path.basename(self.sequence_file_path))[0]
            parts = filename_without_ext.split('_')
            if len(parts) >= 4 and parts[-1].lower() == 'sequence':
                self.product_model, self.sequence_version = parts[1], parts[2]
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
        self.logger.signals.user_interaction.emit(payload)
        
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
        try:
            return eval(f"dict({params_str})", {})
        except SyntaxError:
            try:
                # 尝试修复 Windows 路径中的单反斜杠问题 (例如 D:\path 变为 D:\\path)
                # 排除 \" 的情况，避免破坏转义引号
                sanitized_str = re.sub(r'\\(?!")', r'\\\\', params_str)
                self.logger.warning(f"参数解析遇到语法错误(可能是反斜杠导致)，尝试自动修复: {sanitized_str}")
                return eval(f"dict({sanitized_str})", {})
            except Exception:
                raise # 修复失败，抛出异常

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
            dependencies = {**self.global_config, "logger": self.logger, "station_id": self.station_id,
                            "uut_sn": self.uut_sn, "hardware_manager": self.hardware_manager,
                            "test_engine_instance": self, "variables": variables,
                            "last_result": last_result_wrapper['value'],
                            "get_psu_handle": lambda psu_id=None: self.hardware_manager.get_station_psu(self.station_id),
                            "power_supply_mode": self.global_config.get('power_supply_mode', {}),
                            **self.station_config}
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
        if not isinstance(value_str, str) or value_str == '': return None
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
        if mode in ['InRange', 'NotInRange', '==', '!=', '>', '>=', '<', '<=']:
            try:
                numeric_result = float(value_for_comparison) if isinstance(value_for_comparison,
                                                                           bool) else self._to_numeric(
                    str(value_for_comparison))
                if numeric_result is None: raise ValueError(f"Result '{value_for_comparison}' is not a valid number.")
            except (ValueError, TypeError):
                return False, f"结果 '{result_val}' 中的值 '{value_for_comparison}' 不是一个有效的数字，无法进行数值比较。"
            lower_limit, upper_limit = self._to_numeric(lower_limit_str), self._to_numeric(upper_limit_str)
            if mode == 'InRange':
                if lower_limit is None or upper_limit is None: return False, "InRange 模式需要有效的最小值和最大值。"
                is_pass = lower_limit <= numeric_result <= upper_limit
                return is_pass, f"实测值={numeric_result}, 范围=[{lower_limit}, {upper_limit}]"
            if mode == 'NotInRange':
                if lower_limit is None or upper_limit is None: return False, "NotInRange 模式需要有效的最小值和最大值。"
                is_pass = not (lower_limit <= numeric_result <= upper_limit)
                return is_pass, f"实测值={numeric_result}, 禁止范围=[{lower_limit}, {upper_limit}]"
            if mode in ['==', '!=', '>',
                        '>='] and lower_limit is None: return False, f"{mode} 模式需要一个有效的最小值。"
            if mode in ['<', '<='] and upper_limit is None: return False, f"{mode} 模式需要一个有效的最大值。"
            ops = {'==': (lambda a, b: a == b), '!=': (lambda a, b: a != b), '>': (lambda a, b: a > b),
                   '>=': (lambda a, b: a >= b), '<': (lambda a, b: a < b), '<=': (lambda a, b: a <= b)}
            target = upper_limit if mode in ['<', '<='] else lower_limit
            is_pass = ops[mode](numeric_result, target)
            # 改进消息格式：显示 "实测值=X, 设定值=Y (要求: mode)"
            return is_pass, f"实测值={numeric_result}, 设定值={target} (要求: {mode})"
        elif mode in ['Contains', 'NotContains']:
            str_result, substring = str(value_for_comparison), lower_limit_str
            if not substring: return False, f"{mode} 模式需要在‘最小值’字段中指定一个用于搜索的子字符串。"
            if mode == 'Contains': return substring in str_result, f"'{str_result}' contains '{substring}'"
            if mode == 'NotContains': return substring not in str_result, f"'{str_result}' does not contain '{substring}'"
        return None

    def _mark_skipped_steps(self, start_ptr_idx, end_ptr_idx, original_indices, block_df, reason):
        for i in range(start_ptr_idx, end_ptr_idx):
            skipped_original_index = original_indices[i]
            skipped_step = block_df[block_df['original_index'] == skipped_original_index].iloc[0]
            test_name = str(skipped_step.get('TestName', '')).strip()
            if test_name.startswith(('*', '#')): self.all_step_results_for_report.append(
                {**skipped_step.to_dict(), 'type': 'block'}); continue
            step_result_content = {'status': 'SKIPPED', 'result': '', 'message': reason}
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

            status, msg = "SKIPPED", ""
            test_name = str(step.get('TestName', '')).strip()
            func_name = step.get('Function')

            if not step.get('Enable'):
                self.all_step_results_for_report.append(
                    {**step.to_dict(), 'status': 'SKIPPED', 'result': '', 'message': '此步骤被禁用'});
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

            elif func_name == 'break_loop':
                if self.loop_stack:
                    is_breaking_loop = True
                    broken_loop_idx = self.loop_stack[-1]
                    end_for_idx = self.control_flow_map.get(broken_loop_idx, {}).get('end_for')
                    self.all_step_results_for_report.append(
                        {**step.to_dict(), 'status': 'PASS', 'message': '请求跳出循环'})
                    if end_for_idx and end_for_idx in original_indices:
                        target_ptr = original_indices.index(end_for_idx)
                        self._mark_skipped_steps(ptr + 1, target_ptr, original_indices, block_df,
                                                 "执行BREAK，跳至循环末尾")
                        ptr = target_ptr
                    else:
                        test_passed, first_fail_info = False, {'step_index': original_index,
                                                               'message': '未找到匹配的 end_for 用于 break'}; break
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

            if var_to_store := step.get('Variable'): variables[var_to_store] = raw_result; self.logger.info(
                f"步骤结果已存入变量 '{var_to_store}'。")
            if (compare_mode := step.get('Compare')) and status == "PASS":
                if (comparison_result := self._perform_comparison(compare_mode, value_for_comparison,
                                                                  step.get('LowerLimit'),
                                                                  step.get('UpperLimit'))) is not None:
                    is_pass, compare_msg = comparison_result
                    if not is_pass: status = "FAIL"; msg = f"比较失败: {compare_msg}" if compare_msg else f"比较 '{compare_mode}' 失败。"


            # Preserve raw_result for data analysis, but use string for display
            step_result_content = {'status': status, 'result': raw_result, 'message': msg}
            
            # For UI display: if result is a tuple (bool, message), show only the bool
            ui_update_content = step_result_content.copy()
            if isinstance(raw_result, tuple) and len(raw_result) >= 2 and isinstance(raw_result[0], bool):
                ui_update_content['result'] = str(raw_result[0])  # Show only True/False
            else:
                ui_update_content['result'] = str(raw_result)
            
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

            log_data = {
                'timestamp': datetime.now().isoformat(),
                'sequence_name': sequence_name,
                'station_id': self.station_id,
                'employee_id': self.operator_id,
                'uut_sn': self.uut_sn,
                'status': final_status,
                'duration': duration,
                'fail_step': fail_step,
                'fail_message': fail_message
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
                    raw_result = step.get('result')

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
            final_status, final_message = ("FAIL", {'fail_details': first_fail_details}) if first_fail_details else (
                "PASS", "测试通过")
            if self._should_stop() and first_fail_details is None: final_status, final_message = "USER_STOPPED", "用户中止"
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

            # 构建最终的文件名 (保持您原有的文件名结构)
            station_num = self.station_id.split('_')[-1]
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            safe_uut_sn = re.sub(r'[\\/:*?"<>|]', '_', self.uut_sn)
            filename = f"{final_status}_station_{station_num}_{safe_uut_sn}_{timestamp}{extension}"

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

        # 这是唯一的、必须的修改：如果_get_report_filepath因为权限等问题返回了None，
        # 我们需要在这里中止操作，以防止程序因 open(None, ...) 而崩溃。
        if filepath is None:
            self.logger.error("由于未能生成有效的报告文件路径，HTML报告的保存操作被中止。")
            return

        failure_details_row_html = ""
        try:
            if final_status == "FAIL":
                fail_details = final_message.get('fail_details', {}) if isinstance(final_message, dict) else {};
                fail_msg = fail_details.get('message', '未知错误');
                step_index = fail_details.get('step_index', -1);
                step_name = ""
                if step_index != -1:
                    try:
                        step_name = \
                        self.sequence_df.loc[self.sequence_df['original_index'] == step_index, 'TestName'].iloc[
                            0] + " - "
                    except (KeyError, IndexError):
                        pass
                full_fail_message = f"{step_name}{fail_msg}";
                failure_details_row_html = f"<tr><td class=\"label\">失败详情:</td><td class=\"value status-fail\">{full_fail_message}</td></tr>"

            table_rows = [];
            indent_level = 0
            for step in self.all_step_results_for_report:
                test_name, func_name = step.get('TestName', ''), step.get('Function', '')

                # 计算当前行的缩进
                current_indent = indent_level
                if func_name in ['elseif_variable', 'else_block', 'end_if', 'end_for']:
                    current_indent = max(0, indent_level - 1)

                if step.get('type') == 'block' or test_name.startswith(('*', '#')):
                    block_name = test_name.strip('*# ').strip()
                    table_rows.append(f'<tr class="block-row"><td colspan="9">{block_name}</td></tr>')
                    # 主要的区块标题重置缩进
                    if block_name.lower() in ['setup', 'main', 'cleanup']: indent_level = 0
                    continue

                display_test_name = test_name
                if func_name == 'if_variable':
                    display_test_name = f"<span class='flow-control'>IF ({step.get('result', '')})</span>"
                elif func_name == 'elseif_variable':
                    display_test_name = f"<span class='flow-control'>ELSE IF ({step.get('result', '')})</span>"
                elif func_name == 'else_block':
                    display_test_name = f"<span class='flow-control'>ELSE</span>"
                elif func_name == 'end_if':
                    display_test_name = f"<span class='flow-control'>END IF</span>"
                elif func_name == 'for_loop':
                    display_test_name = f"<span class='flow-control'>FOR ({step.get('result', '')})</span>"
                elif func_name == 'end_for':
                    display_test_name = f"<span class='flow-control'>END FOR ({step.get('result', '')})</span>"
                elif func_name == 'break_loop':
                    display_test_name = f"<span class='flow-control'>BREAK</span>"

                status = step.get('status', 'SKIPPED').upper();
                status_class = f'step-{status.lower()}'
                limits = f"[{step.get('LowerLimit', '')}, {step.get('UpperLimit', '')}]" if step.get(
                    'LowerLimit') or step.get('UpperLimit') else ""
                display_step_num = '' if pd.isna(step_num_val := step.get('step_number')) else int(step_num_val)
                padding_left = 10 + current_indent * 25
                
                # Extract boolean from tuple for display, similar to UI logic
                result_value = step.get('result', '')
                if isinstance(result_value, tuple) and len(result_value) >= 2 and isinstance(result_value[0], bool):
                    result_display = str(result_value[0])  # Show only True/False
                else:
                    result_display = str(result_value)

                row = f"""<tr class="{status_class}">
                    <td>{display_step_num}</td><td style="padding-left: {padding_left}px;">{display_test_name}</td>
                    <td>{step.get('Module', '')}</td><td>{func_name}</td><td>{step.get('Parameters', '')}</td><td>{limits}</td>
                    <td>{status}</td><td>{result_display}</td><td>{step.get('message', '')}</td></tr>"""
                table_rows.append(row)

                # 为下一行准备新的缩进级别
                if func_name in ['if_variable', 'for_loop']:
                    indent_level += 1
                elif func_name in ['end_if', 'end_for']:
                    indent_level = max(0, indent_level - 1)

            template = Template(HTML_TEMPLATE)
            final_html = template.substitute(
                product_model=self.product_model, sequence_version=self.sequence_version, uut_sn=self.uut_sn,
                station_id=self.station_id, final_status=final_status.upper(),
                final_status_class=f'status-{final_status.lower()}',
                duration_seconds=round(duration, 2),
                start_time=datetime.fromtimestamp(self.start_time).strftime('%Y-%m-%d %H:%M:%S'),
                table_rows=''.join(table_rows), failure_details_row=failure_details_row_html,
                operator_id=self.operator_id if self.operator_id else "N/A") # NEW
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(final_html)
            self.logger.info(f"HTML 测试报告已保存至: {filepath}")
        except Exception as e:
            self.logger.error("保存 HTML 测试报告失败！", exc_info=True)
