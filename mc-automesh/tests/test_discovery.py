import os
import tempfile
import sys
from mc_automesh.discovery import discover_module, discover_path
from mc_automesh.decorators import expose, ignore

def public_func(): pass
def _private_func(): pass
lambda_func = lambda: None

@ignore
def ignored_func(): pass

@expose(name="custom")
def exposed_func(): pass

def test_discover_module():
    # Since this test file is a module, we can discover it!
    functions = discover_module(__name__)
    names = [f.__name__ for f in functions]
    
    assert "public_func" in names
    assert "exposed_func" in names
    assert "_private_func" not in names
    assert "<lambda>" not in names
    assert "ignored_func" not in names
    assert "lambda_func" not in names

def test_discover_path():
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a simple python module
        pyfile = os.path.join(tmpdir, "sample.py")
        with open(pyfile, "w") as f:
            f.write("def func_in_path(): pass\n")
            f.write("def _priv_in_path(): pass\n")
            
        functions = discover_path(tmpdir)
        names = [f.__name__ for f in functions]
        
        assert "func_in_path" in names
        assert "_priv_in_path" not in names
