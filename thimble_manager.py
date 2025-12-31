import json
import os
import time
from datetime import datetime, timedelta

from utils.app_utils import get_app_base_path

# 数据文件的路径
DATA_FILE = os.path.join(get_app_base_path(), 'thimble_data.json')

class ThimbleManager:
    """
    管理测试顶针使用次数和时间的类。
    数据将存储在 thimble_data.json 文件中。
    
    Data Structure (V3):
    {
        "Station_1": {
            "version": 3,
            "fixtures": {
                "FIX_001": {
                    "total_usage": 123,
                    "limit": 5000,
                    "warning_days": 180,
                    "first_use_timestamp": 1234567890.0,
                    "snooze_until": 0.0,
                    "sequences": {
                        "TestSeq_A.json": 50,
                        "TestSeq_B.json": 73
                    }
                }
            },
            "mappings": {
                "TestSeq_A.json": "FIX_001",
                "TestSeq_B.json": "FIX_001"
            }
        }
    }
    """
    def __init__(self):
        self.data = self._load_data()
        self._ensure_v3_structure()

    def _ensure_v3_structure(self):
        """确保所有工位的数据结构都是 V3 格式。"""
        changed = False
        # 1. 迁移顶层旧数据 (V0 -> V1 Station Key)
        old_keys = [k for k in self.data.keys() if k.endswith('.json')]
        if old_keys:
            if "Station_1" not in self.data: self.data["Station_1"] = {}
            for k in old_keys:
                self.data["Station_1"][k] = self.data[k]
                del self.data[k]
            changed = True

        # 2. 迁移到 V2/V3
        for station_id in list(self.data.keys()):
            s_data = self.data[station_id]
            if not isinstance(s_data, dict):
                continue

            # If version is already 3, skip
            if s_data.get("version") == 3:
                continue
                
            # This is V1 or V2 format, needs migration
            print(f"正在将工位 {station_id} 的顶针数据迁移到 V3 格式...")
            
            # Check if it's V2 (has fixtures and mappings)
            if "fixtures" in s_data and "mappings" in s_data:
                # V2 -> V3: Add 'sequences' sub-dict and 'total_usage' to each fixture
                for fix_code, fix_info in s_data["fixtures"].items():
                    if "sequences" not in fix_info:
                        fix_info["sequences"] = {}
                    if "total_usage" not in fix_info:
                        # Initialize total_usage from old 'count' or sum of existing
                        fix_info["total_usage"] = fix_info.pop("count", 0)
                s_data["version"] = 3
                changed = True
            elif "fixtures" not in s_data:
                # V1 format (all sequence keys at top level)
                new_struct = {"version": 3, "fixtures": {}, "mappings": {}}
                
                for seq_key, old_info in s_data.items():
                    if not isinstance(old_info, dict): continue
                    
                    fix_code = f"Fix_{seq_key.replace('.json', '')}"
                    
                    new_struct["fixtures"][fix_code] = {
                        "total_usage": old_info.get("count", 0),
                        "limit": old_info.get("count_limit", old_info.get("limit", 0)),
                        "warning_days": old_info.get("time_limit_days", old_info.get("warning_days", 0)),
                        "first_use_timestamp": old_info.get("first_use_timestamp", 0.0),
                        "snooze_until": old_info.get("snooze_until", 0.0),
                        "sequences": {seq_key: old_info.get("count", 0)}
                    }
                    new_struct["mappings"][seq_key] = fix_code
                
                self.data[station_id] = new_struct
                changed = True
        
        if changed:
            self._save_data()

    def _load_data(self):
        """从JSON文件加载数据，如果文件不存在则返回空字典。"""
        try:
            if os.path.exists(DATA_FILE):
                with open(DATA_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"警告: 无法加载顶针数据文件 '{DATA_FILE}': {e}")
        return {}

    def _save_data(self):
        """将当前数据保存到JSON文件。"""
        try:
            with open(DATA_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, indent=4, ensure_ascii=False)
        except IOError as e:
            print(f"错误: 无法保存顶针数据文件 '{DATA_FILE}': {e}")

    def _get_station_data(self, station_id):
        if station_id not in self.data:
            self.data[station_id] = {"version": 3, "fixtures": {}, "mappings": {}}
        return self.data[station_id]

    # --- Public API for First-Run Check ---

    def get_fixture_for_sequence(self, sequence_path, station_id):
        """
        Returns the fixture code associated with a sequence, or None if not associated.
        This is the key method for the "first-test" popup logic.
        """
        if not sequence_path: return None
        seq_key = os.path.basename(sequence_path)
        
        # 直接检查station_id（不创建新条目）
        if station_id in self.data:
            result = self.data[station_id].get("mappings", {}).get(seq_key)
            if result:
                return result
        
        # 兼容性：检查是否有大小写不同的station_id存在数据
        # 例如 Station_1 vs station_1
        for key in self.data.keys():
            if key.lower() == station_id.lower():
                result = self.data[key].get("mappings", {}).get(seq_key)
                if result:
                    return result
        
        return None

    def associate_sequence(self, sequence_path, fixture_code, station_id):
        """
        Associates a sequence with a fixture. Creates the fixture if it doesn't exist.
        """
        if not sequence_path or not fixture_code: return
        
        seq_key = os.path.basename(sequence_path)
        s_data = self._get_station_data(station_id)
        
        # Create fixture if it doesn't exist
        if fixture_code not in s_data["fixtures"]:
            s_data["fixtures"][fixture_code] = {
                "total_usage": 0,
                "limit": 20000,        # 默认使用上限
                "warning_days": 90,    # 默认预警天数
                "first_use_timestamp": 0.0,
                "snooze_until": 0.0,
                "sequences": {}
            }
        
        # Initialize sequence count if not present
        if seq_key not in s_data["fixtures"][fixture_code]["sequences"]:
            s_data["fixtures"][fixture_code]["sequences"][seq_key] = 0
        
        # Update mapping
        s_data["mappings"][seq_key] = fixture_code
        self._save_data()

    # --- Public API for UI ---

    def get_fixtures(self, station_id):
        """获取指定工位的所有治具定义 {Code: Info}"""
        return self._get_station_data(station_id).get("fixtures", {})

    def get_mappings(self, station_id):
        """获取指定工位的所有序列映射 {SeqName: FixCode}"""
        return self._get_station_data(station_id).get("mappings", {})

    def update_fixture(self, station_id, fixture_code, limit, warning_days):
        """Updates settings for a single fixture."""
        s_data = self._get_station_data(station_id)
        if fixture_code in s_data["fixtures"]:
            s_data["fixtures"][fixture_code]["limit"] = limit
            s_data["fixtures"][fixture_code]["warning_days"] = warning_days
            self._save_data()

    def add_fixture(self, station_id, fixture_code):
        """Adds a new, empty fixture."""
        s_data = self._get_station_data(station_id)
        if fixture_code not in s_data["fixtures"]:
            s_data["fixtures"][fixture_code] = {
                "total_usage": 0,
                "limit": 20000,        # 默认使用上限
                "warning_days": 90,    # 默认预警天数
                "first_use_timestamp": 0.0,
                "snooze_until": 0.0,
                "sequences": {}
            }
            self._save_data()

    def remove_fixture(self, station_id, fixture_code):
        """Removes a fixture and all its mappings."""
        s_data = self._get_station_data(station_id)
        if fixture_code in s_data["fixtures"]:
            del s_data["fixtures"][fixture_code]
            # Also remove all mappings to this fixture
            s_data["mappings"] = {k: v for k, v in s_data["mappings"].items() if v != fixture_code}
            self._save_data()

    def remove_sequence_from_fixture(self, station_id, fixture_code, seq_name):
        """Removes a sequence association from a fixture."""
        s_data = self._get_station_data(station_id)
        if fixture_code in s_data["fixtures"]:
            if seq_name in s_data["fixtures"][fixture_code].get("sequences", {}):
                del s_data["fixtures"][fixture_code]["sequences"][seq_name]
            if seq_name in s_data["mappings"] and s_data["mappings"][seq_name] == fixture_code:
                del s_data["mappings"][seq_name]
            self._save_data()

    def reset_fixture_usage(self, station_id, fixture_code):
        """重置指定治具的使用记录"""
        s_data = self._get_station_data(station_id)
        if fixture_code in s_data["fixtures"]:
            fix = s_data["fixtures"][fixture_code]
            fix["total_usage"] = 0
            fix["first_use_timestamp"] = 0.0
            fix["snooze_until"] = 0.0
            # Also reset per-sequence counts
            for seq_key in fix.get("sequences", {}):
                fix["sequences"][seq_key] = 0
            self._save_data()

    def copy_station_data(self, source_station_id, target_station_id):
        """复制工位配置（完全覆盖）"""
        if source_station_id not in self.data: return False
        import copy
        self.data[target_station_id] = copy.deepcopy(self.data[source_station_id])
        self._save_data()
        return True

    # --- Runtime Logic ---

    def increment_usage(self, sequence_path, duration_seconds, station_id):
        """为一个测试序列增加使用次数，实际上是增加其绑定的治具的使用次数。"""
        if not sequence_path: return

        seq_key = os.path.basename(sequence_path)
        s_data = self._get_station_data(station_id)
        
        mappings = s_data.get("mappings", {})
        fixtures = s_data.get("fixtures", {})
        
        fix_code = mappings.get(seq_key)
        
        if not fix_code or fix_code not in fixtures:
            # Not associated, skip (the popup should have handled this)
            return
        
        fix = fixtures[fix_code]
        
        # Increment total usage
        fix["total_usage"] = fix.get("total_usage", 0) + 1
        
        # Increment per-sequence usage
        if "sequences" not in fix:
            fix["sequences"] = {}
        fix["sequences"][seq_key] = fix["sequences"].get(seq_key, 0) + 1
        
        if fix.get("first_use_timestamp", 0.0) == 0.0:
            fix["first_use_timestamp"] = time.time()
        
        self._save_data()

    def check_reminder(self, sequence_path, station_id):
        """检查警告 (根据 Sequence -> Fixture)"""
        if not sequence_path: return False, ""
        
        seq_key = os.path.basename(sequence_path)
        s_data = self._get_station_data(station_id)
        mappings = s_data.get("mappings", {})
        fixtures = s_data.get("fixtures", {})
        
        fix_code = mappings.get(seq_key)
        if not fix_code or fix_code not in fixtures:
            return False, ""
            
        fix = fixtures[fix_code]
        
        # 检查 Snooze
        now = time.time()
        if now < fix.get("snooze_until", 0.0):
            return False, ""
            
        limit = fix.get("limit", 0)
        warning_days = fix.get("warning_days", 0)
        total_usage = fix.get("total_usage", 0)
        
        triggers = []
        if limit > 0 and total_usage >= limit:
            triggers.append(f"使用次数 ({total_usage}) 已达上限 {limit}")
            
        if warning_days > 0 and fix.get("first_use_timestamp", 0.0) > 0:
            elapsed_days = (now - fix["first_use_timestamp"]) / 86400
            if elapsed_days >= warning_days:
                triggers.append(f"使用时间 ({elapsed_days:.1f}天) 已达上限 {warning_days}天")
                
        if triggers:
            msg = f"【{station_id}】治具 '{fix_code}' 触发维护提醒:\n" + "\n".join(triggers)
            return True, msg
            
        return False, ""

    def set_snooze(self, sequence_path, days, station_id):
        """设置贪睡模式 (对 Fixture 生效)"""
        seq_key = os.path.basename(sequence_path)
        s_data = self._get_station_data(station_id)
        fix_code = s_data.get("mappings", {}).get(seq_key)
        
        if fix_code and fix_code in s_data["fixtures"]:
            s_data["fixtures"][fix_code]["snooze_until"] = time.time() + days * 86400
            self._save_data()

    def get_all_sequence_files(self):
        """获取 'sequences' 目录下的所有 .json 文件。"""
        sequences_dir = os.path.join(get_app_base_path(), 'sequences')
        if not os.path.exists(sequences_dir):
            return []
        try:
            return [f for f in os.listdir(sequences_dir) if f.endswith('.json')]
        except OSError:
            return []
            
    def get_usage_info(self, sequence_path, station_id):
        """获取用于报告显示的简要信息"""
        if not sequence_path: return "N/A"
        seq_key = os.path.basename(sequence_path)
        s_data = self._get_station_data(station_id)
        fix_code = s_data.get("mappings", {}).get(seq_key)
        if fix_code and fix_code in s_data["fixtures"]:
            total = s_data["fixtures"][fix_code].get("total_usage", 0)
            return f"治具: {fix_code} (使用: {total}次)"
        return "N/A"
