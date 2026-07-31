"""共通テストフィクスチャ"""

import pytest


@pytest.fixture(autouse=True)
def _clear_singleton_caches():
    """get_settings() / get_store() / keyring_available() のキャッシュを分離する。"""
    from mdx_cli.credentials.store import get_store, keyring_available
    from mdx_cli.settings import get_settings

    def _clear():
        get_settings.cache_clear()
        get_store.cache_clear()
        keyring_available.cache_clear()

    _clear()
    yield
    _clear()
