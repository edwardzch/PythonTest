import sqlite3
import threading
import os
from datetime import datetime, date
from .app_utils import get_app_base_path
from PySide6.QtCore import QSettings

# Lock for thread safety
wo_db_lock = threading.Lock()

def get_wo_db_path():
    """Returns the path to the work order statistics database."""
    base_path = get_app_base_path()
    return os.path.join(base_path, 'work_order_stats.db')

def get_workshop_settings():
    """获取当前车间作息设置"""
    settings = QSettings("MyCompany", "PythonTestPlatform")
    return {
        'work_start': settings.value("Workshop/work_start", "08:00"),
        'work_end': settings.value("Workshop/work_end", "18:00"),
        'lunch_duration': int(settings.value("Workshop/lunch_duration", 60)),
        'dinner_duration': int(settings.value("Workshop/dinner_duration", 40)),
    }

def init_work_order_db():
    """Initializes the work order database and tables."""
    db_path = get_wo_db_path()
    with wo_db_lock:
        try:
            con = sqlite3.connect(db_path, timeout=10)
            cur = con.cursor()
            
            # Table: work_sessions (每个序列每天一条记录)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS work_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sequence_name TEXT NOT NULL,
                    session_date TEXT NOT NULL,
                    station_count INTEGER DEFAULT 1,
                    operator_name TEXT,
                    operator_id TEXT,
                    lunch_duration INTEGER DEFAULT 60,
                    dinner_duration INTEGER DEFAULT 40,
                    work_start TEXT DEFAULT '08:00',
                    work_end TEXT DEFAULT '18:00',
                    pass_qty INTEGER DEFAULT 0,
                    fail_qty INTEGER DEFAULT 0,
                    avg_duration REAL DEFAULT 0.0,
                    pass_rate REAL DEFAULT 0.0,
                    created_at TEXT,
                    last_updated TEXT,
                    UNIQUE(sequence_name, session_date)
                )
            """)
            
            # Table: session_samples (每次测试一条记录)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS session_samples (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER,
                    duration REAL,
                    status TEXT,
                    timestamp TEXT,
                    FOREIGN KEY (session_id) REFERENCES work_sessions (id)
                )
            """)
            
            # Indexes
            cur.execute('CREATE INDEX IF NOT EXISTS idx_sessions_seq_date ON work_sessions (sequence_name, session_date);')
            cur.execute('CREATE INDEX IF NOT EXISTS idx_samples_session ON session_samples (session_id);')
            
            # 保留旧表兼容
            cur.execute("""
                CREATE TABLE IF NOT EXISTS work_orders (
                    order_number TEXT PRIMARY KEY,
                    sequence_name TEXT,
                    target_qty INTEGER DEFAULT 0,
                    pass_qty INTEGER DEFAULT 0,
                    fail_qty INTEGER DEFAULT 0,
                    avg_duration REAL DEFAULT 0.0,
                    pass_rate REAL DEFAULT 0.0,
                    predicted_finish_time TEXT,
                    created_at TEXT,
                    last_updated TEXT
                )
            """)
            
            cur.execute("""
                CREATE TABLE IF NOT EXISTS work_order_samples (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_number TEXT,
                    duration REAL,
                    status TEXT,
                    timestamp TEXT,
                    FOREIGN KEY (order_number) REFERENCES work_orders (order_number)
                )
            """)
            
            con.commit()
            con.close()
        except Exception as e:
            print(f"[WorkOrderDB] Init failed: {e}")

def get_or_create_session(sequence_name, station_count=1, operator_name=None, operator_id=None):
    """
    获取或创建当天的会话记录。
    每个序列每天只有一条记录。
    """
    db_path = get_wo_db_path()
    init_work_order_db()
    
    today = date.today().isoformat()
    workshop = get_workshop_settings()
    
    with wo_db_lock:
        try:
            con = sqlite3.connect(db_path, timeout=5)
            con.row_factory = sqlite3.Row
            cur = con.cursor()
            
            # 检查是否已存在今天的会话
            cur.execute("""
                SELECT id FROM work_sessions 
                WHERE sequence_name = ? AND session_date = ?
            """, (sequence_name, today))
            row = cur.fetchone()
            
            if row:
                session_id = row['id']
                # 【修复】更新工位数和操作员信息
                cur.execute("""
                    UPDATE work_sessions 
                    SET station_count = ?, operator_name = ?, operator_id = ?, last_updated = ?
                    WHERE id = ?
                """, (station_count, operator_name, operator_id, datetime.now().isoformat(), session_id))
            else:
                # 创建新会话
                now = datetime.now().isoformat()
                cur.execute("""
                    INSERT INTO work_sessions 
                    (sequence_name, session_date, station_count, operator_name, operator_id,
                     lunch_duration, dinner_duration, work_start, work_end, created_at, last_updated)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (sequence_name, today, station_count, operator_name, operator_id,
                      workshop['lunch_duration'], workshop['dinner_duration'],
                      workshop['work_start'], workshop['work_end'], now, now))
                session_id = cur.lastrowid
                
            con.commit()
            con.close()
            return session_id
            
        except Exception as e:
            print(f"[WorkOrderDB] Get/Create session failed: {e}")
            return None

def add_session_sample(sequence_name, duration, status, station_count=1, operator_name=None, operator_id=None):
    """
    添加测试样本到当天的会话中。
    """
    db_path = get_wo_db_path()
    
    session_id = get_or_create_session(sequence_name, station_count, operator_name, operator_id)
    if not session_id:
        return False
    
    with wo_db_lock:
        try:
            con = sqlite3.connect(db_path, timeout=5)
            cur = con.cursor()
            now = datetime.now().isoformat()
            
            # 1. 添加样本
            cur.execute("""
                INSERT INTO session_samples (session_id, duration, status, timestamp)
                VALUES (?, ?, ?, ?)
            """, (session_id, duration, status, now))
            
            # 2. 更新计数
            if status.upper() == 'PASS':
                cur.execute("UPDATE work_sessions SET pass_qty = pass_qty + 1 WHERE id = ?", (session_id,))
            elif status.upper() == 'FAIL':
                cur.execute("UPDATE work_sessions SET fail_qty = fail_qty + 1 WHERE id = ?", (session_id,))
            
            # 3. 计算滚动平均
            cur.execute("""
                SELECT duration FROM session_samples 
                WHERE session_id = ? 
                ORDER BY id DESC LIMIT 50
            """, (session_id,))
            rows = cur.fetchall()
            
            if rows:
                durations = [r[0] for r in rows]
                new_avg = sum(durations) / len(durations)
                
                cur.execute("SELECT pass_qty, fail_qty FROM work_sessions WHERE id = ?", (session_id,))
                counts = cur.fetchone()
                if counts:
                    p, f = counts
                    total = p + f
                    rate = (p / total * 100) if total > 0 else 0.0
                    
                    cur.execute("""
                        UPDATE work_sessions 
                        SET avg_duration = ?, pass_rate = ?, last_updated = ?
                        WHERE id = ?
                    """, (new_avg, rate, now, session_id))
            
            con.commit()
            con.close()
            return True
            
        except Exception as e:
            print(f"[WorkOrderDB] Add session sample failed: {e}")
            return False

def get_all_sessions():
    """获取所有会话记录"""
    db_path = get_wo_db_path()
    if not os.path.exists(db_path):
        return []
        
    with wo_db_lock:
        try:
            con = sqlite3.connect(db_path, timeout=5)
            con.row_factory = sqlite3.Row
            cur = con.cursor()
            
            cur.execute("""
                SELECT * FROM work_sessions 
                ORDER BY session_date DESC, last_updated DESC
            """)
            
            rows = cur.fetchall()
            con.close()
            
            return [dict(row) for row in rows]
        except Exception as e:
            print(f"[WorkOrderDB] Get all sessions failed: {e}")
            return []

def get_session_handling_time(session_id, lunch_duration=60, dinner_duration=40):
    """
    计算会话的平均拿取耗时。
    算法：
    1. 用前10次间隔建立初始基准
    2. 用基准值的3倍作为阈值
    3. 过滤所有间隔（包括前10次），重新计算真实平均值
    """
    db_path = get_wo_db_path()
    
    with wo_db_lock:
        try:
            con = sqlite3.connect(db_path, timeout=5)
            cur = con.cursor()
            
            cur.execute("""
                SELECT timestamp, duration FROM session_samples 
                WHERE session_id = ? 
                ORDER BY id ASC
            """, (session_id,))
            rows = cur.fetchall()
            con.close()
            
            if not rows or len(rows) < 2:
                return 0.0
            
            # 计算所有间隔
            all_gaps = []
            for i in range(1, len(rows)):
                prev_ts_str, prev_dur = rows[i-1]
                curr_ts_str, _ = rows[i]
                
                prev_ts = datetime.fromisoformat(prev_ts_str).timestamp()
                curr_ts = datetime.fromisoformat(curr_ts_str).timestamp()
                
                gap = (curr_ts - float(prev_dur if prev_dur else 0)) - prev_ts
                
                if gap > 0:
                    all_gaps.append(gap)
            
            if not all_gaps:
                return 0.0
            
            # 用前10次（或全部）建立初始基准
            baseline_samples = all_gaps[:10] if len(all_gaps) >= 10 else all_gaps
            baseline_avg = sum(baseline_samples) / len(baseline_samples)
            
            # 用3倍基准作为阈值，过滤所有间隔（包括前10次）
            threshold = baseline_avg * 3
            filtered_gaps = [g for g in all_gaps if g <= threshold]
            
            if not filtered_gaps:
                return baseline_avg
            
            # 用过滤后的数据计算真实平均值
            return sum(filtered_gaps) / len(filtered_gaps)
            
        except Exception as e:
            print(f"[WorkOrderDB] Get handling time failed: {e}")
            return 0.0

def get_session_total_times(session_id, lunch_duration=60, dinner_duration=40):
    """
    获取会话的两种总耗时：
    1. 实际总耗时：从第一次测试到最后一次测试的时间差
    2. 工作总耗时：减去实际跨过的吃饭时间
    """
    db_path = get_wo_db_path()
    
    with wo_db_lock:
        try:
            con = sqlite3.connect(db_path, timeout=5)
            cur = con.cursor()
            
            cur.execute("""
                SELECT MIN(timestamp), MAX(timestamp) FROM session_samples 
                WHERE session_id = ?
            """, (session_id,))
            row = cur.fetchone()
            con.close()
            
            if not row or not row[0] or not row[1]:
                return 0.0, 0.0
            
            first_ts = datetime.fromisoformat(row[0])
            last_ts = datetime.fromisoformat(row[1])
            
            actual_elapsed = (last_ts - first_ts).total_seconds()
            
            # 智能扣除吃饭时间：只有当会话时间跨过午餐/晚餐时段时才扣除
            # 假设午餐12:00-13:00，晚餐17:00-18:00
            meal_deduction = 0
            
            # 午餐时段 (12:00)
            lunch_start_hour = 12
            # 如果会话开始在午餐前，结束在午餐后，则扣除午餐时间
            if first_ts.hour < lunch_start_hour and last_ts.hour >= lunch_start_hour:
                meal_deduction += lunch_duration * 60
            
            # 晚餐时段 (17:00)
            dinner_start_hour = 17
            # 如果会话开始在晚餐前，结束在晚餐后，则扣除晚餐时间
            if first_ts.hour < dinner_start_hour and last_ts.hour >= dinner_start_hour:
                meal_deduction += dinner_duration * 60
            
            work_elapsed = max(0, actual_elapsed - meal_deduction)
            
            return actual_elapsed, work_elapsed
            
        except Exception as e:
            print(f"[WorkOrderDB] Get total times failed: {e}")
            return 0.0, 0.0


# ========== 兼容旧API ==========

def get_work_order_info(order_number):
    """兼容旧API：获取工单信息（只统计今天的数据）"""
    db_path = get_wo_db_path()
    if not os.path.exists(db_path):
        return None
    
    today = date.today().isoformat()
        
    with wo_db_lock:
        try:
            con = sqlite3.connect(db_path, timeout=5)
            con.row_factory = sqlite3.Row 
            cur = con.cursor()
            
            # 只从今天的 work_sessions 记录查询序列的统计数据
            cur.execute("""
                SELECT 
                    sequence_name,
                    pass_qty,
                    fail_qty,
                    avg_duration,
                    pass_rate
                FROM work_sessions 
                WHERE sequence_name = ? AND session_date = ?
            """, (order_number, today))
            row = cur.fetchone()
            con.close()
            
            if row:
                return dict(row)
            return None
        except Exception as e:
            print(f"[WorkOrderDB] Get info failed: {e}")
            return None

def create_or_update_work_order(order_number, sequence_name=None, target_qty=None):
    """兼容旧API"""
    pass  # 不再使用

def add_test_sample(order_number, duration, status):
    """兼容旧API - 重定向到新的会话系统"""
    # 使用 order_number 作为 sequence_name
    return add_session_sample(order_number, duration, status)

def get_historical_avg_for_sequence(sequence_name):
    """获取序列的历史平均测试时间"""
    db_path = get_wo_db_path()
    if not os.path.exists(db_path): 
        return None
        
    with wo_db_lock:
        try:
            con = sqlite3.connect(db_path, timeout=5)
            cur = con.cursor()
            
            cur.execute("""
                SELECT AVG(avg_duration) FROM work_sessions 
                WHERE sequence_name = ? AND avg_duration > 0
            """, (sequence_name,))
            
            result = cur.fetchone()
            con.close()
            
            if result and result[0]:
                return result[0]
            return None
        except Exception as e:
            print(f"[WorkOrderDB] Get historical avg failed: {e}")
            return None

def get_avg_handling_time(sequence_name):
    """获取序列的平均拿取耗时（从所有会话）"""
    db_path = get_wo_db_path()
    if not os.path.exists(db_path):
        return 5.0
    
    # 先获取会话列表（在锁内）
    sessions = []
    with wo_db_lock:
        try:
            con = sqlite3.connect(db_path, timeout=5)
            cur = con.cursor()
            
            cur.execute("""
                SELECT id, lunch_duration, dinner_duration FROM work_sessions 
                WHERE sequence_name = ?
            """, (sequence_name,))
            sessions = cur.fetchall()
            con.close()
        except Exception as e:
            print(f"[WorkOrderDB] Get avg handling time failed: {e}")
            return 5.0
    
    # 在锁外计算拿取耗时（避免死锁）
    if not sessions:
        return 5.0
    
    total_handling = 0.0
    count = 0
    for session_id, lunch_dur, dinner_dur in sessions:
        ht = get_session_handling_time(session_id, lunch_dur or 60, dinner_dur or 40)
        if ht > 0:
            total_handling += ht
            count += 1
    
    return total_handling / count if count > 0 else 5.0

def get_sequence_handling_time_avg(sequence_name):
    """获取序列历史平均拿取耗时 - 重定向到 get_avg_handling_time"""
    return get_avg_handling_time(sequence_name)

def get_all_work_orders():
    """兼容旧API - 返回会话数据"""
    return get_all_sessions()
