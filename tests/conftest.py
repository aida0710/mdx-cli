"""共通テストフィクスチャ"""

import pytest


@pytest.fixture(autouse=True)
def _clear_singleton_caches():
    """get_settings() / get_store() のキャッシュをテスト間で分離する。"""
    from mdx_cli.credentials.store import get_store
    from mdx_cli.settings import get_settings

    get_settings.cache_clear()
    get_store.cache_clear()
    yield
    get_settings.cache_clear()
    get_store.cache_clear()
