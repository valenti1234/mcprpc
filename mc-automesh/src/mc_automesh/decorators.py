import functools
from typing import Any, Callable, Dict, List, Optional

def expose(
    name: Optional[str] = None,
    acl: Optional[Dict[str, List[str]]] = None,
    tags: Optional[List[str]] = None
) -> Callable:
    """
    Decorator to explicitly expose a function with custom metadata.
    """
    def decorator(func: Callable) -> Callable:
        func.__automesh_expose__ = True
        if name is not None:
            func.__automesh_name__ = name
        if acl is not None:
            func.__automesh_acl__ = acl
        if tags is not None:
            func.__automesh_tags__ = tags
        return func
    return decorator

def ignore(func: Callable) -> Callable:
    """
    Decorator to skip exporting a function.
    """
    func.__automesh_ignore__ = True
    return func
