import importlib
import inspect
import os
import sys
from types import ModuleType
from typing import Callable, List, Union

def is_valid_function(func: Callable, module_name: str) -> bool:
    """
    Check if a function should be exposed.
    Ignores:
    - private functions (start with _)
    - imported symbols (different module)
    - lambdas
    - functions marked with @ignore
    """
    if not inspect.isfunction(func) and not inspect.ismethod(func):
        return False
        
    func_name = getattr(func, "__name__", "")
    if func_name.startswith("_"):
        return False
        
    if func_name == "<lambda>":
        return False
        
    if getattr(func, "__module__", "") != module_name:
        return False
        
    if getattr(func, "__automesh_ignore__", False):
        return False
        
    return True

def discover_module(module: Union[str, ModuleType]) -> List[Callable]:
    """
    Discover functions in a given module.
    """
    if isinstance(module, str):
        module = importlib.import_module(module)
        
    functions = []
    module_name = module.__name__
    
    for name, obj in inspect.getmembers(module):
        if is_valid_function(obj, module_name):
            functions.append(obj)
            
        # Optionally support class methods if needed
        if inspect.isclass(obj) and getattr(obj, "__module__", "") == module_name:
            for method_name, method in inspect.getmembers(obj):
                if is_valid_function(method, module_name):
                    functions.append(method)
                    
    return functions

def discover_path(path: str) -> List[Callable]:
    """
    Scans a folder recursively and discovers functions in all python files.
    """
    functions = []
    path = os.path.abspath(path)
    
    if path not in sys.path:
        sys.path.insert(0, path)
        
    for root, _, files in os.walk(path):
        for file in files:
            if file.endswith(".py") and not file.startswith("_"):
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, path)
                
                # Convert path to module name (e.g. dir/foo.py -> dir.foo)
                module_name = rel_path[:-3].replace(os.sep, ".")
                
                try:
                    module = importlib.import_module(module_name)
                    functions.extend(discover_module(module))
                except ImportError as e:
                    print(f"Warning: Failed to import {module_name}: {e}")
                    
    return functions
