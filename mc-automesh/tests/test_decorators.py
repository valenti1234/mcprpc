from mc_automesh.decorators import expose, ignore

def test_expose_decorator():
    @expose(name="custom.name", acl={"roles": ["admin"]}, tags=["tag1", "tag2"])
    def sample_func():
        pass
        
    assert getattr(sample_func, "__automesh_expose__") is True
    assert getattr(sample_func, "__automesh_name__") == "custom.name"
    assert getattr(sample_func, "__automesh_acl__") == {"roles": ["admin"]}
    assert getattr(sample_func, "__automesh_tags__") == ["tag1", "tag2"]

def test_ignore_decorator():
    @ignore
    def sample_func():
        pass
        
    assert getattr(sample_func, "__automesh_ignore__") is True
