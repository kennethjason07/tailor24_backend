import pytest
import sys

print("Running test suite...")
ret = pytest.main(["tests/test_manager_credentials.py", "-v", "-s"])
print(f"Test suite finished with code: {ret}")
sys.exit(ret)
