from pathlib import Path
import inspect
import importlib

from logg import logger
from .plugin_base import PluginBase

plugins_dir = Path(__file__).parent

PLUGIN_OBJECTS:list[PluginBase]=[]

"""
python live import 
"""
for path in plugins_dir.glob("*"):
    if path.is_dir():
        try:
            module=importlib.import_module("plugins."+path.name)
            for name, obj in inspect.getmembers(module):
                if (inspect.isclass(obj)
                    and issubclass(obj,PluginBase)):
                        PLUGIN_OBJECTS.append(obj)
        except Exception as exc:
            logger.error(f"[ERROR] import module:{path.name} failed: {exc}")

