from typing import List, Dict

class ACLError(Exception):
    pass

def validate_acl(acl: Dict[str, List[str]], context_roles: List[str]):
    """
    Validate basic ACL:
    if acl.roles exists, context.roles must contain at least one role.
    """
    if not acl:
        return

    allowed_roles = acl.get("roles")
    if allowed_roles is not None:
        # If allowed_roles is empty, perhaps it means no one is allowed, or everyone is allowed.
        # Assuming if it exists and is a list, context must have at least one of them.
        if not allowed_roles:
            raise ACLError("No roles are allowed to access this function.")
        
        has_access = any(role in allowed_roles for role in context_roles)
        if not has_access:
            raise ACLError("Access denied: insufficient roles.")
