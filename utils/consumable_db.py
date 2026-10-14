# -*- coding: utf-8 -*-
"""
耗材管理数据库模块
管理线缆主数据(cable_master)和顶针历史记录(pogo_history)
"""
import os
import sqlite3
import threading
from datetime import datetime, date

from utils.app_utils import get_app_base_path

# 线程锁保证数据库操作安全
consumable_db_lock = threading.Lock()

def get_consumable_db_path():
    """获取耗材数据库路径（与work_order_db共用同一个数据库文件）"""
    base_path = get_app_base_path()
    return os.path.join(base_path, 'test_data.db')

def init_consumable_tables():
    """初始化耗材管理相关表"""
    db_path = get_consumable_db_path()
    
    with consumable_db_lock:
        try:
            con = sqlite3.connect(db_path, timeout=5)
            cur = con.cursor()
            
            # 线缆主数据表
            cur.execute("""
                CREATE TABLE IF NOT EXISTS cable_master (
                    sn TEXT PRIMARY KEY,
                    total_count INTEGER DEFAULT 0,
                    max_limit INTEGER DEFAULT 10000,
                    last_seen_date TEXT,
                    status TEXT DEFAULT 'active',
                    created_at TEXT
                )
            """)
            
            # 顶针更换历史表
            cur.execute("""
                CREATE TABLE IF NOT EXISTS pogo_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    station_id TEXT NOT NULL,
                    fixture_code TEXT NOT NULL,
                    reset_time TEXT NOT NULL,
                    count_before_reset INTEGER DEFAULT 0,
                    first_use_time TEXT,
                    operator_id TEXT,
                    notes TEXT
                )
            """)
            
            con.commit()
            con.close()
            print("[ConsumableDB] Tables initialized successfully.")
        except Exception as e:
            print(f"[ConsumableDB] Init failed: {e}")

# ========== 线缆管理 API ==========

def check_cable_sn(sn):
    """
    检查线缆SN是否存在，如果不存在则自动创建。
    返回线缆信息字典。
    """
    if not sn:
        return None
    
    db_path = get_consumable_db_path()
    init_consumable_tables()
    
    with consumable_db_lock:
        try:
            con = sqlite3.connect(db_path, timeout=5)
            con.row_factory = sqlite3.Row
            cur = con.cursor()
            
            cur.execute("SELECT * FROM cable_master WHERE sn = ?", (sn,))
            row = cur.fetchone()
            
            if row:
                result = dict(row)
            else:
                # 自动创建新记录
                now = datetime.now().isoformat()
                cur.execute("""
                    INSERT INTO cable_master (sn, total_count, max_limit, last_seen_date, status, created_at)
                    VALUES (?, 0, 10000, ?, 'active', ?)
                """, (sn, now, now))
                con.commit()
                result = {
                    'sn': sn,
                    'total_count': 0,
                    'max_limit': 10000,
                    'last_seen_date': now,
                    'status': 'active',
                    'created_at': now
                }
            
            con.close()
            return result
            
        except Exception as e:
            print(f"[ConsumableDB] Check cable SN failed: {e}")
            return None

def increment_cable_count(sn):
    """线缆使用计数+1"""
    if not sn or sn == "Not used":
        return False
    
    # 确保记录存在（若不存在则自动用默认寿命10000初始化）
    check_cable_sn(sn)

    db_path = get_consumable_db_path()
    
    with consumable_db_lock:
        try:
            con = sqlite3.connect(db_path, timeout=5)
            cur = con.cursor()
            
            now = datetime.now().isoformat()
            cur.execute("""
                UPDATE cable_master 
                SET total_count = total_count + 1, last_seen_date = ?
                WHERE sn = ?
            """, (now, sn))
            
            con.commit()
            con.close()
            return True
            
        except Exception as e:
            print(f"[ConsumableDB] Increment cable count failed: {e}")
            return False

def get_cable_info(sn):
    """获取线缆详细信息"""
    return check_cable_sn(sn)  # 复用check_cable_sn逻辑

def update_cable_limit(sn, max_limit):
    """更新线缆寿命上限"""
    if not sn:
        return False
    
    db_path = get_consumable_db_path()
    
    with consumable_db_lock:
        try:
            con = sqlite3.connect(db_path, timeout=5)
            cur = con.cursor()
            
            cur.execute("UPDATE cable_master SET max_limit = ? WHERE sn = ?", (max_limit, sn))
            
            con.commit()
            con.close()
            return True
            
        except Exception as e:
            print(f"[ConsumableDB] Update cable limit failed: {e}")
            return False

def retire_cable(sn):
    """标记线缆为报废"""
    if not sn:
        return False
    
    db_path = get_consumable_db_path()
    
    with consumable_db_lock:
        try:
            con = sqlite3.connect(db_path, timeout=5)
            cur = con.cursor()
            
            cur.execute("UPDATE cable_master SET status = 'retired' WHERE sn = ?", (sn,))
            
            con.commit()
            con.close()
            return True
            
        except Exception as e:
            print(f"[ConsumableDB] Retire cable failed: {e}")
            return False

def get_all_cables():
    """获取所有线缆记录"""
    db_path = get_consumable_db_path()
    if not os.path.exists(db_path):
        return []
    
    with consumable_db_lock:
        try:
            con = sqlite3.connect(db_path, timeout=5)
            con.row_factory = sqlite3.Row
            cur = con.cursor()
            
            cur.execute("SELECT * FROM cable_master ORDER BY last_seen_date DESC")
            rows = cur.fetchall()
            con.close()
            
            return [dict(row) for row in rows]
            
        except Exception as e:
            print(f"[ConsumableDB] Get all cables failed: {e}")
            return []

# ========== 顶针历史 API ==========

def log_pogo_reset(station_id, fixture_code, count_before, first_use_time=None, operator_id=None, notes=None):
    """记录顶针重置操作"""
    db_path = get_consumable_db_path()
    init_consumable_tables()
    
    with consumable_db_lock:
        try:
            con = sqlite3.connect(db_path, timeout=5)
            cur = con.cursor()
            
            now = datetime.now().isoformat()
            cur.execute("""
                INSERT INTO pogo_history 
                (station_id, fixture_code, reset_time, count_before_reset, first_use_time, operator_id, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (station_id, fixture_code, now, count_before, first_use_time, operator_id, notes))
            
            con.commit()
            con.close()
            return True
            
        except Exception as e:
            print(f"[ConsumableDB] Log pogo reset failed: {e}")
            return False

def get_all_pogo_history():
    """获取所有顶针重置历史"""
    db_path = get_consumable_db_path()
    if not os.path.exists(db_path):
        return []
    
    with consumable_db_lock:
        try:
            con = sqlite3.connect(db_path, timeout=5)
            con.row_factory = sqlite3.Row
            cur = con.cursor()
            
            cur.execute("SELECT * FROM pogo_history ORDER BY reset_time DESC")
            rows = cur.fetchall()
            con.close()
            
            return [dict(row) for row in rows]
            
        except Exception as e:
            print(f"[ConsumableDB] Get pogo history failed: {e}")
            return []
