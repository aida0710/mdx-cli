from mdx_cli.settings import Settings


def test_default_base_url():
    settings = Settings()
    assert settings.base_url == "https://oprpl.mdx.jp"


def test_default_request_timeout():
    settings = Settings()
    assert settings.request_timeout == 120


def test_default_task_poll_interval():
    settings = Settings()
    assert settings.task_poll_interval == 3


def test_default_task_poll_timeout():
    settings = Settings()
    assert settings.task_poll_timeout == 600


def test_default_project_id_is_none():
    settings = Settings()
    assert settings.default_project_id is None


def test_env_override(monkeypatch):
    monkeypatch.setenv("MDX_BASE_URL", "https://test.example.com")
    monkeypatch.setenv("MDX_DEFAULT_PROJECT_ID", "test-project-123")
    settings = Settings()
    assert settings.base_url == "https://test.example.com"
    assert settings.default_project_id == "test-project-123"
