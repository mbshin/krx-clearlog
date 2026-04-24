import pytest

from krx_parser import load_default_registry


@pytest.fixture(scope="session")
def registry():
    return load_default_registry()
