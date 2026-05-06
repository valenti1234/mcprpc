from mc_automesh.schema import get_function_schema, extract_metadata
from mc_automesh.decorators import expose

def sample_function(amount: float, rate: float = 0.20) -> float:
    """
    Calculates VAT.
    """
    return amount * rate

def test_get_function_schema():
    schema = get_function_schema(sample_function)
    
    assert "type" in schema
    assert schema["type"] == "object"
    assert "properties" in schema
    assert "amount" in schema["properties"]
    assert "rate" in schema["properties"]
    
    assert schema["properties"]["amount"]["type"] == "number"
    assert schema["properties"]["rate"]["type"] == "number"
    
    # 'amount' has no default, should be required
    assert "amount" in schema["required"]
    # 'rate' has a default, should not be required
    assert "rate" not in schema.get("required", [])

def test_extract_metadata():
    metadata = extract_metadata(sample_function)
    
    assert metadata["name"] == "test_schema.sample_function"
    assert metadata["description"] == "Calculates VAT."
    assert metadata["return_type"] == "float"
    assert metadata["module"] == "test_schema"
    assert metadata["function_name"] == "sample_function"
    assert metadata["acl"] is None
    assert metadata["tags"] is None
    assert "inputSchema" in metadata

def test_extract_metadata_with_expose():
    @expose(name="custom.vat", acl={"roles": ["admin"]}, tags=["billing"])
    def exposed_function(amount: float) -> float:
        """Custom VAT."""
        return amount * 0.25
        
    metadata = extract_metadata(exposed_function)
    
    assert metadata["name"] == "custom.vat"
    assert metadata["description"] == "Custom VAT."
    assert metadata["acl"] == {"roles": ["admin"]}
    assert metadata["tags"] == ["billing"]
