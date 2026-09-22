import sys
import os

# Set stdout unbuffered
sys.stdout.reconfigure(line_buffering=True)

import pytest

print("=== STARTING PYTEST ===", flush=True)
exit_code = pytest.main(["tests/test_manager_credentials.py", "-v", "--tb=short"])
print(f"=== PYTEST FINISHED WITH EXIT CODE {exit_code} ===", flush=True)
sys.exit(exit_code)
