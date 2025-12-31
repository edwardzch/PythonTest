# -*- coding: utf-8 -*-
"""
耗材管理器模块
整合线缆追踪和顶针历史管理功能
"""
import os
from datetime import datetime

from utils import consumable_db
from utils.app_utils import get_app_base_path


class ConsumableManager:
    """
    耗材管理器
    管理流动线缆的使用追踪和顶针重置历史
    """
    
    def __init__(self):
        # 当前会话的工位-线缆映射 {'Station_1': 'CABLE_SN_001', ...}
        self.current_session_cables = {}
        # 初始化数据库表
        consumable_db.init_consumable_tables()
    
    # ========== 线缆管理 ==========
    
    def check_cable_sn(self, sn):
        """
        检查线缆SN，如果不存在则自动创建。
        返回: dict with {sn, total_count, max_limit, status} or None
        """
        return consumable_db.check_cable_sn(sn)
    
    def increment_cable_count(self, sn):
        """线缆使用计数+1"""
        return consumable_db.increment_cable_count(sn)
    
    def get_cable_info(self, sn):
        """获取线缆详情"""
        return consumable_db.get_cable_info(sn)
    
    def retire_cable(self, sn):
        """标记线缆为报废"""
        return consumable_db.retire_cable(sn)
    
    def is_cable_over_limit(self, sn):
        """检查线缆是否超过寿命上限"""
        info = self.get_cable_info(sn)
        if not info:
            return False
        return info.get('total_count', 0) >= info.get('max_limit', 10000)
    
    # ========== 会话管理 ==========
    
    def bind_cable_to_station(self, station_id, cable_sn):
        """
        将线缆绑定到工位（内存映射）
        返回: (success, message)
        """
        if not cable_sn:
            return False, "线缆SN不能为空"
        
        # 检查是否已被其他工位使用
        for sid, sn in self.current_session_cables.items():
            if sn == cable_sn and sid != station_id:
                return False, f"线缆 {cable_sn} 已绑定到 {sid}"
        
        # 检查/创建线缆记录
        info = self.check_cable_sn(cable_sn)
        if not info:
            return False, "无法访问数据库"
        
        # 检查状态
        if info.get('status') == 'retired':
            return False, f"线缆 {cable_sn} 已报废"
        
        # 检查是否超限
        if info.get('total_count', 0) >= info.get('max_limit', 10000):
            return False, f"线缆 {cable_sn} 已达寿命上限 ({info['total_count']}/{info['max_limit']})"
        
        # 绑定成功
        self.current_session_cables[station_id] = cable_sn
        return True, f"已使用: {info['total_count']}/{info['max_limit']}"
    
    def get_cable_for_station(self, station_id):
        """获取工位当前绑定的线缆SN"""
        return self.current_session_cables.get(station_id)
    
    def clear_session(self):
        """清空当前会话的所有绑定"""
        self.current_session_cables.clear()
    
    def on_test_complete(self, station_id):
        """
        测试完成时调用，增加对应线缆的计数
        """
        cable_sn = self.current_session_cables.get(station_id)
        if cable_sn:
            return self.increment_cable_count(cable_sn)
        return False
    
    # ========== 顶针历史 ==========
    
    def log_pogo_reset(self, station_id, fixture_code, count_before, first_use_time=None, operator_id=None, notes=None):
        """记录顶针重置操作到历史"""
        return consumable_db.log_pogo_reset(
            station_id=station_id,
            fixture_code=fixture_code,
            count_before=count_before,
            first_use_time=first_use_time,
            operator_id=operator_id,
            notes=notes
        )
    
    def get_pogo_history(self):
        """获取所有顶针重置历史"""
        return consumable_db.get_all_pogo_history()
    
    def get_all_cables(self):
        """获取所有线缆记录"""
        return consumable_db.get_all_cables()


# 全局实例
_consumable_manager = None

def get_consumable_manager():
    """获取全局ConsumableManager实例"""
    global _consumable_manager
    if _consumable_manager is None:
        _consumable_manager = ConsumableManager()
    return _consumable_manager
