import sqlite3
import threading
import os
from datetime import datetime

# 从 app_utils 导入我们新的、可靠的路径获取函数
from .app_utils import get_app_base_path

# 使用锁来确保多线程环境下的数据库写入安全
db_lock = threading.Lock()


def get_db_path():
    """
    构造指向程序根目录下数据库文件的可靠路径。
    （无论是开发环境还是打包后的EXE环境）
    """
    # 使用新的、可靠的函数来定位根目录
    base_path = get_app_base_path()
    
    # 从配置文件读取数据库名称
    import json
    config_path = os.path.join(base_path, 'config.json')
    database_name = 'test_history'  # 默认值
    
    try:
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                database_name = config.get('database_name', 'test_history')
    except Exception as e:
        print(f"[DatabaseLogger] 读取数据库配置失败，使用默认名称: {e}")
    
    # 将数据库文件名与根目录拼接成绝对路径
    return os.path.join(base_path, f'{database_name}.db')


def initialize_database():
    """
    如果数据库或必要的表不存在，则创建它们。
    此函数可以安全地多次调用。
    """
    db_path = get_db_path()
    with db_lock:
        try:
            con = sqlite3.connect(db_path, timeout=10)
            cur = con.cursor()

            # --- 创建 test_results 表 ---
            # 这是主测试结果表
            cur.execute('''
                CREATE TABLE IF NOT EXISTS test_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    sequence_name TEXT NOT NULL,
                    station_id TEXT NOT NULL,
                    employee_id TEXT,  -- 员工工号
                    uut_sn TEXT NOT NULL,
                    status TEXT NOT NULL,
                    duration REAL NOT NULL,
                    fail_step TEXT,
                    fail_message TEXT
                )
            ''')

            # --- 创建 test_step_results 表 ---
            # 这是用于CPK分析的详细步骤结果表
            cur.execute('''
                CREATE TABLE IF NOT EXISTS test_step_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    result_id INTEGER NOT NULL,
                    step_name TEXT,
                    measurement_value REAL,
                    upper_limit REAL,
                    lower_limit REAL,
                    FOREIGN KEY (result_id) REFERENCES test_results (id) ON DELETE CASCADE
                )
            ''')

            # 为常用查询字段创建索引以提高性能
            cur.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON test_results (timestamp);')
            cur.execute('CREATE INDEX IF NOT EXISTS idx_sequence_name ON test_results (sequence_name);')
            cur.execute('CREATE INDEX IF NOT EXISTS idx_station_id ON test_results (station_id);')
            cur.execute('CREATE INDEX IF NOT EXISTS idx_employee_id ON test_results (employee_id);')
            cur.execute('CREATE INDEX IF NOT EXISTS idx_step_result_id ON test_step_results (result_id);')  # 为外键创建索引

            # 自动添加新列
            cur.execute("PRAGMA table_info(test_results)")
            existing_cols = {row[1] for row in cur.fetchall()}
            for col in ['adapter_cables', 'adapter_cable_life', 'thimble_life']:
                if col not in existing_cols:
                    try:
                        cur.execute(f"ALTER TABLE test_results ADD COLUMN {col} TEXT;")
                    except Exception:
                        pass

            con.commit()
            con.close()
        except Exception as e:
            # 增加一个更明确的错误日志
            print(f"[DatabaseLogger] CRITICAL: 无法在路径 '{db_path}' 初始化数据库。错误: {e}")


def log_test_result(result_data):
    """
    将单次测试结果记录到SQLite数据库中。

    :param result_data: 包含测试结果信息的字典。
    :return: 插入的主记录的ID，如果失败则返回None。
    """
    db_path = get_db_path()

    if not os.path.exists(os.path.dirname(db_path)):
        try:
            os.makedirs(os.path.dirname(db_path))
        except Exception as e:
            print(f"[DatabaseLogger] ERROR: 无法创建数据库目录 '{os.path.dirname(db_path)}'. Error: {e}")
            return None

    if not os.path.exists(db_path):
        initialize_database()

    last_id = None
    with db_lock:
        try:
            con = sqlite3.connect(db_path, timeout=10)
            cur = con.cursor()

            sql = ''' INSERT INTO test_results(timestamp, sequence_name, station_id, employee_id, uut_sn, status, duration, fail_step, fail_message, adapter_cables, adapter_cable_life, thimble_life)
                      VALUES(?,?,?,?,?,?,?,?,?,?,?,?) '''

            data_tuple = (
                result_data.get('timestamp', datetime.now().isoformat()),
                result_data.get('sequence_name', 'N/A'),
                result_data.get('station_id', 'N/A'),
                result_data.get('employee_id'),
                result_data.get('uut_sn', 'N/A'),
                result_data.get('status', 'FAIL'),
                result_data.get('duration', 0.0),
                result_data.get('fail_step'),
                result_data.get('fail_message'),
                result_data.get('adapter_cables', 'N/A'),
                result_data.get('adapter_cable_life', 'N/A'),
                result_data.get('thimble_life', 'Not used')
            )

            cur.execute(sql, data_tuple)
            last_id = cur.lastrowid  # 获取刚刚插入的行的ID
            con.commit()
            con.close()
            return last_id  # 返回这个ID，以便 test_engine 可以用它来记录详细步骤

        except Exception as e:
            print(f"[DatabaseLogger] ERROR: 无法记录结果到数据库 '{db_path}'. Error: {e}")
            print(f"[DatabaseLogger] 记录失败的数据: {result_data}")
            return None


# 在模块导入时调用 initialize_database()，确保应用启动时数据库就绪。
# 这行代码的位置和功能都是正确的，保持不变。
initialize_database()


def check_sn_exists(sn, sequence_name=None):
    """
    检查指定的SN是否已经测试通过（PASS）。
    只有PASS的记录才算重复，FAIL的产品可以重新测试。
    
    Args:
        sn: 要检查的产品SN
        sequence_name: 可选，限定在特定测试序列中检查
        
    Returns:
        bool: 如果SN已存在且状态为PASS返回True，否则返回False
    """
    db_path = get_db_path()
    
    if not os.path.exists(db_path):
        return False
    
    with db_lock:
        try:
            con = sqlite3.connect(db_path, timeout=5)
            cur = con.cursor()
            
            if sequence_name:
                # 在特定序列中检查PASS的记录
                cur.execute(
                    "SELECT COUNT(*) FROM test_results WHERE uut_sn = ? AND sequence_name = ? AND status = 'PASS'",
                    (sn, sequence_name)
                )
            else:
                # 全局检查PASS的记录
                cur.execute(
                    "SELECT COUNT(*) FROM test_results WHERE uut_sn = ? AND status = 'PASS'",
                    (sn,)
                )
            
            count = cur.fetchone()[0]
            con.close()
            
            return count > 0
            
        except Exception as e:
            print(f"[DatabaseLogger] ERROR: 检查SN是否存在时出错: {e}")
            return False


def update_test_result_to_pass(record_id, new_station_id=None):
    """
    更新测试记录状态从FAIL变为PASS。
    用于1分钟内复测通过的场景。
    
    Args:
        record_id: 要更新的测试记录ID
        new_station_id: 可选，新的工位ID（用于跨工位复测成功时更新工位）
        
    Returns:
        bool: 更新成功返回True，否则返回False
    """
    db_path = get_db_path()
    
    if not os.path.exists(db_path):
        return False
    
    with db_lock:
        try:
            con = sqlite3.connect(db_path, timeout=10)
            cur = con.cursor()
            
            # 更新状态为PASS，并清空失败相关信息
            if new_station_id:
                # 跨工位复测：同时更新station_id
                cur.execute(
                    """UPDATE test_results 
                       SET status = 'PASS', station_id = ?, fail_step = NULL, fail_message = NULL 
                       WHERE id = ?""",
                    (new_station_id, record_id)
                )
            else:
                # 同工位复测：只更新状态
                cur.execute(
                    """UPDATE test_results 
                       SET status = 'PASS', fail_step = NULL, fail_message = NULL 
                       WHERE id = ?""",
                    (record_id,)
                )
            
            rows_affected = cur.rowcount
            con.commit()
            con.close()
            
            if rows_affected > 0:
                station_info = f" (工位更新为 {new_station_id})" if new_station_id else ""
                print(f"[DatabaseLogger] INFO: 记录 {record_id} 已从FAIL更新为PASS{station_info}")
                return True
            else:
                print(f"[DatabaseLogger] WARNING: 未找到记录 {record_id}")
                return False
            
        except Exception as e:
            print(f"[DatabaseLogger] ERROR: 更新记录状态时出错: {e}")
            return False


def delete_test_record(record_id):
    """
    删除指定的测试记录。
    用于1分钟内复测通过时，删除新创建的重复记录。
    
    Args:
        record_id: 要删除的测试记录ID
        
    Returns:
        bool: 删除成功返回True，否则返回False
    """
    db_path = get_db_path()
    
    if not os.path.exists(db_path):
        return False
    
    with db_lock:
        try:
            con = sqlite3.connect(db_path, timeout=10)
            cur = con.cursor()
            
            # 先删除关联的步骤结果（外键约束）
            cur.execute("DELETE FROM test_step_results WHERE result_id = ?", (record_id,))
            
            # 再删除主记录
            cur.execute("DELETE FROM test_results WHERE id = ?", (record_id,))
            
            rows_affected = cur.rowcount
            con.commit()
            con.close()
            
            if rows_affected > 0:
                print(f"[DatabaseLogger] INFO: 记录 {record_id} 已删除（复测成功，移除重复记录）")
                return True
            else:
                print(f"[DatabaseLogger] WARNING: 未找到记录 {record_id}")
                return False
            
        except Exception as e:
            print(f"[DatabaseLogger] ERROR: 删除记录时出错: {e}")
            return False


def get_recent_fail_record(sn, sequence_name=None, seconds=60):
    """
    获取指定SN在指定时间内的最近FAIL记录。
    用于判断是否可以进行复测通过抵消。
    
    Args:
        sn: 产品SN
        sequence_name: 可选，限定在特定测试序列中检查
        seconds: 查找多少秒内的记录，默认60秒
        
    Returns:
        dict: 如果找到返回 {'id': record_id, 'timestamp': timestamp, 'station_id': station_id}
              否则返回 None
    """
    db_path = get_db_path()
    
    if not os.path.exists(db_path):
        return None
    
    with db_lock:
        try:
            con = sqlite3.connect(db_path, timeout=5)
            cur = con.cursor()
            
            # 计算时间阈值
            from datetime import datetime, timedelta
            time_threshold = (datetime.now() - timedelta(seconds=seconds)).isoformat()
            
            if sequence_name:
                cur.execute(
                    """SELECT id, timestamp, station_id FROM test_results 
                       WHERE uut_sn = ? AND sequence_name = ? AND status = 'FAIL' 
                       AND timestamp >= ?
                       ORDER BY timestamp DESC LIMIT 1""",
                    (sn, sequence_name, time_threshold)
                )
            else:
                cur.execute(
                    """SELECT id, timestamp, station_id FROM test_results 
                       WHERE uut_sn = ? AND status = 'FAIL' AND timestamp >= ?
                       ORDER BY timestamp DESC LIMIT 1""",
                    (sn, time_threshold)
                )
            
            row = cur.fetchone()
            con.close()
            
            if row:
                return {
                    'id': row[0],
                    'timestamp': row[1],
                    'station_id': row[2]
                }
            return None
            
        except Exception as e:
            print(f"[DatabaseLogger] ERROR: 查询最近FAIL记录时出错: {e}")
            return None

