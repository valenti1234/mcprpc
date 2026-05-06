import inspect
from typing import Any, Callable, Dict, Optional
from pydantic import create_model

def get_function_schema(func: Callable) -> Dict[str, Any]:
    """
    Generate JSON Schema for a function's arguments using Pydantic.
    """
    sig = inspect.signature(func)
    
    fields = {}
    for param_name, param in sig.parameters.items():
        if param_name in ("self", "cls"):
            continue
            
        annotation = param.annotation if param.annotation != inspect.Parameter.empty else Any
        default = param.default if param.default != inspect.Parameter.empty else ...
        
        fields[param_name] = (annotation, default)
        
    model_name = f"{func.__name__.capitalize()}Params"
    model = create_model(model_name, **fields)
    
    # Remove 'title' from the top level and properties to keep schema clean
    schema = model.model_json_schema()
    schema.pop("title", None)
    
    return schema

def extract_metadata(func: Callable) -> Dict[str, Any]:
    """
    Extract metadata from a function for MCP registration.
    """
    doc = inspect.getdoc(func) or ""
    
    module_name = getattr(func, "__module__", "")
    func_name = getattr(func, "__name__", "")
    
    default_name = f"{module_name}.{func_name}" if module_name else func_name
    
    name = getattr(func, "__automesh_name__", default_name)
    acl = getattr(func, "__automesh_acl__", None)
    tags = getattr(func, "__automesh_tags__", None)
    
    input_schema = get_function_schema(func)
    
    sig = inspect.signature(func)
    return_annotation = sig.return_annotation
    if return_annotation == inspect.Parameter.empty:
        return_type = "Any"
    else:
        # Try to get a string representation of the return type
        if hasattr(return_annotation, "__name__"):
            return_type = return_annotation.__name__
        else:
            return_type = str(return_annotation)
            
    return {
        "name": name,
        "description": doc,
        "inputSchema": input_schema,
        "return_type": return_type,
        "module": module_name,
        "function_name": func_name,
        "acl": acl,
        "tags": tags,
    }
