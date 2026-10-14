# -*- coding: utf-8 -*-
"""
硬件驱动基类与虚拟通道代理 (HAL & Multi-station Proxy)
为 ATE 4 工位并行测试与独立/共用模式提供统一的生命周期、线程互斥锁与通道透明代理。
"""

import threading
import logging
import inspect
from contextlib import contextmanager


class HardwareError(Exception):
    """通用硬件异常"""
    pass


class ConnectionError(HardwareError):
    """连接异常"""
    pass


class LockTimeoutError(HardwareError):
    """硬件通信锁超时异常"""
    pass


class BaseDriver:
    """
    所有 ATE 硬件驱动的标准基类。
    规范驱动生命周期，并内置带超时机制的线程互斥锁，避免多工位并发测试时死锁。
    """

    # 驱动元数据（子类重写）
    DRIVER_META = {
        "name": "BaseDriver",
        "display_name": "硬件驱动基类",
        "category": "generic",
        "interface": "generic",
        "channels": 1,
        "supports_shared_mode": False,
        "supports_independent_mode": True,
        "version": "1.0.0",
        "author": "ATE Team"
    }

    # 配置 Schema（用于系统配置界面自动渲染，子类可定义）
    CONFIG_SCHEMA = {}

    def __init__(self, **kwargs):
        self.config = kwargs
        self._connected = False
        self._lock = threading.RLock()
        self.logger = kwargs.get('logger') or logging.getLogger(self.__class__.__name__)

    @contextmanager
    def acquire_lock(self, timeout=10.0):
        """
        获取驱动通信互斥锁的上下文管理器，带超时保护。
        在 4 工位共用模式下，防止某工位仪器通信假死导致所有工位永久卡死。
        """
        acquired = self._lock.acquire(timeout=timeout)
        if not acquired:
            err_msg = f"[{self.__class__.__name__}] 获取通信锁超时 ({timeout}s)，可能有其他工位正在执行耗时操作或设备通信挂起！"
            self.logger.error(err_msg)
            raise LockTimeoutError(err_msg)
        try:
            yield self
        finally:
            self._lock.release()

    def connect(self) -> bool:
        """建立连接（子类实现）"""
        self._connected = True
        return True

    def disconnect(self):
        """断开连接（子类实现）"""
        self._connected = False

    def is_connected(self) -> bool:
        """检查连接状态"""
        return self._connected

    def reset(self):
        """复位仪器状态（整机复位）"""
        pass

    def health_check(self) -> bool:
        """健康自检，默认只要已连接即返回 True"""
        return self.is_connected()


class VirtualChannelProxy:
    """
    虚拟通道代理（Virtual Channel Proxy）。
    用于抹平 4 工位测试中【独立模式】与【共用模式】对测试脚本编写的差异。

    - 独立模式（is_shared=False）：工位独占一台仪器，直接透传调用。
    - 共用模式（is_shared=True）：4 工位共用一台多通道仪器，代理会自动检查被调用方法
      是否包含 channel/ch 参数，若包含则自动将本工位绑定的物理通道注入进去。

    测试脚本编写者无论面对独立电源还是共用多通道电源，统一调用：
    psu.set_voltage(5.0)
    psu.turn_on()
    """

    def __init__(self, real_driver, station_id, channel=None, is_shared=False):
        self._real_driver = real_driver
        self._station_id = station_id
        self._channel = channel
        self._is_shared = is_shared

    @property
    def real_driver(self):
        return self._real_driver

    @property
    def channel(self):
        return self._channel

    @property
    def is_shared(self):
        return self._is_shared

    def __getattr__(self, name):
        attr = getattr(self._real_driver, name)
        if not callable(attr):
            return attr

        def proxy_method(*args, **kwargs):
            # 若不是共享模式或没有绑定通道，直接透传
            if not self._is_shared or self._channel is None:
                return attr(*args, **kwargs)

            # 共享模式：检查目标函数签名是否接受 channel 或 ch 参数
            try:
                sig = inspect.signature(attr)
                param_names = sig.parameters.keys()
                
                # 如果调用方没有显式传 channel，自动注入工位绑定的 channel
                if 'channel' in param_names and 'channel' not in kwargs:
                    kwargs['channel'] = self._channel
                elif 'ch' in param_names and 'ch' not in kwargs:
                    kwargs['ch'] = self._channel
            except (ValueError, TypeError):
                pass

            return attr(*args, **kwargs)

        return proxy_method
