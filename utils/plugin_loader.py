import os
import importlib.util
import sys
import logging

def load_plugins_from_dir(plugin_dir):
    """
    从指定目录加载所有 .py 模块。
    返回: dict {module_name: module_object}
    """
    plugins = {}
    if not os.path.exists(plugin_dir):
        logging.warning(f"插件目录不存在: {plugin_dir}")
        return plugins

    # 将目录加入 sys.path 以便处理内部导入
    sys.path.insert(0, plugin_dir)
    
    try:
        for filename in os.listdir(plugin_dir):
            if (filename.endswith('.py') or filename.endswith('.pyc') or filename.endswith('.pyd')) and not filename.startswith('__'):
                # 去除扩展名获取模块名
                if filename.endswith('.py'):
                    module_name = filename[:-3]
                elif filename.endswith('.pyc'):
                    # 处理 .cpython-312.pyc 这种格式，或者直接去除 .pyc
                    # 简单起见，如果包含 .cpython，则截取到第一个点
                    if '.cpython-' in filename:
                        module_name = filename.split('.')[0]
                    else:
                        module_name = filename[:-4]
                else: # .pyd
                    module_name = filename[:-4]
                
                full_path = os.path.join(plugin_dir, filename)
                try:
                    spec = importlib.util.spec_from_file_location(module_name, full_path)
                    if spec and spec.loader:
                        if module_name in sys.modules:
                            # 如果模块已在内存中，强制重新加载
                            module = importlib.reload(sys.modules[module_name])
                        else:
                            module = importlib.util.module_from_spec(spec)
                            spec.loader.exec_module(module)
                        
                        plugins[module_name] = module
                        logging.debug(f"成功加载插件: {module_name}")
                except Exception as e:
                    logging.error(f"加载插件 {filename} 失败: {e}", exc_info=True)
    finally:
        # 清理 sys.path
        if plugin_dir in sys.path:
            sys.path.remove(plugin_dir)
            
    return plugins

def find_driver_class(driver_name, drivers_dir):
    """
    在 drivers 目录下的所有模块中查找指定的驱动类。
    """
    plugins = load_plugins_from_dir(drivers_dir)
    for module in plugins.values():
        if hasattr(module, driver_name):
            return getattr(module, driver_name)
    return None
