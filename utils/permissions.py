# utils/permissions.py

import functools
from PySide6.QtWidgets import QMessageBox

# A set to hold all permission IDs discovered by the decorator
REGISTERED_PERMISSIONS = set([
    'file_new',
    'file_save',
    'file_save_as',
    'edit_test_sequence',
    'access_config_editor',
    'edit_station_count',
    'allow_cycle_test',
    'manage_users',
    'access_sniffer_tool',      # 抓包工具权限
    'manage_thimble_usage',     # 顶针管理权限
    'manage_cables',            # 线缆管理权限
    'access_time_prediction'    # 测试时间预测权限
])

def require_permission(permission_id):
    """
    A decorator to check if the user has the required permission before executing a method.
    It assumes the decorated method is part of a class that has a 'has_permission' method
    or has an 'app' attribute pointing to the main application instance.
    """
    REGISTERED_PERMISSIONS.add(permission_id)

    def decorator(func):
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            # 'self' is the instance of the class where the method is defined (e.g., TestApp)
            
            # Find the has_permission method.
            permission_checker = None
            if hasattr(self, 'has_permission') and callable(self.has_permission):
                permission_checker = self.has_permission
            elif hasattr(self, 'app') and hasattr(self.app, 'has_permission') and callable(self.app.has_permission):
                permission_checker = self.app.has_permission

            if permission_checker and permission_checker(permission_id):
                return func(self, *args, **kwargs)
            else:
                # If we can't find a checker, we should deny access for safety.
                # Find a parent widget for the message box if possible
                parent_widget = None
                if hasattr(self, 'central_widget'): # Assuming 'self' is the main window
                    parent_widget = self
                elif hasattr(self, 'parent') and callable(self.parent):
                    parent_widget = self.parent()

                QMessageBox.warning(
                    parent_widget,
                    "权限不足",
                    f"您没有执行此操作所需的权限。"
                )
                print(f"Permission denied for user to access '{func.__name__}' (requires: '{permission_id}')")
                return None # Stop execution
        return wrapper
    return decorator
