import pytest
from app.acl import validate_acl, ACLError

def test_acl_allowed():
    acl = {"roles": ["admin", "user"]}
    context_roles = ["admin"]
    # Should not raise
    validate_acl(acl, context_roles)

def test_acl_denied():
    acl = {"roles": ["admin"]}
    context_roles = ["user"]
    with pytest.raises(ACLError) as exc:
        validate_acl(acl, context_roles)
    assert "Access denied" in str(exc.value)

def test_acl_empty_roles_allowed():
    acl = {"roles": []}
    context_roles = ["admin"]
    with pytest.raises(ACLError) as exc:
        validate_acl(acl, context_roles)
    assert "No roles are allowed" in str(exc.value)

def test_acl_none():
    acl = {}
    context_roles = ["user"]
    # Should not raise
    validate_acl(acl, context_roles)
