import os
import pytest

# Integration tests require real services.
# Skip all tests in this directory if INTEGRATION env var is not set.
def pytest_collection_modifyitems(config, items):
    if not os.environ.get("INTEGRATION"):
        skip = pytest.mark.skip(reason="Set INTEGRATION=1 to run integration tests")
        for item in items:
            if "integration" in str(item.fspath):
                item.add_marker(skip)
