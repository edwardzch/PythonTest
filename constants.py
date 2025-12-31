# -*- coding: utf-8 -*-

"""
全局常量模块
"""

APP_VERSION = "1.2.3"

DEFAULT_SEQUENCE_DATA = [{"TestName": "* Setup 区块", "Block": "Setup"}, {"TestName": "* Main 区块", "Block": "Main"},
                         {"TestName": "* Cleanup 区块", "Block": "Cleanup"}]

STATUS_STYLES = {
    'IDLE': ('空闲', '#868e96'),
    'RUNNING': ('测试中', '#3a6381'),
    'PASS': ('通过', '#28a745'),
    'FAIL': ('失败', '#dc3545'),
    'PREPARING': ('准备中...', '#17a2b8'),
    'PAUSED': ('已暂停', '#ffc107'),
    'DEBUG_PAUSED': ('单步模式', '#3a6381'),
    'DEBUG_RUNNING': ('运行模式', '#3a6381'),
    'DEBUG_STOP': ('调试结束', '#6c757d'),
    'USER_STOPPED': ('用户中止', '#6c757d')
}

LOG_LEVEL_COLORS = {
    'INFO': '#28a745',
    'WARNING': '#ffc111', # Corrected from #ffc107 to a valid hex
    'ERROR': '#dc3545',
    'DEBUG': '#adb5bd'
}
