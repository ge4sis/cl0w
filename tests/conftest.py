import pytest

# pytest-asyncio: 모든 async 테스트를 자동으로 처리
def pytest_configure(config):
    config.addinivalue_line(
        "markers", "asyncio: mark test as async"
    )
