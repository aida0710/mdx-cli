from mdx_cli.credentials.store import CredentialStore


def test_save_and_load_project_id(tmp_path):
    """プロジェクトIDの保存・読込ラウンドトリップ"""
    store = CredentialStore(config_dir=tmp_path)
    store.save_project_id("proj-abc-123")
    result = store.load_project_id()
    assert result == "proj-abc-123"


def test_load_project_id_when_none_saved(tmp_path):
    """プロジェクトIDが保存されていない場合はNoneを返す"""
    store = CredentialStore(config_dir=tmp_path)
    result = store.load_project_id()
    assert result is None


def test_save_project_id_overwrites_previous(tmp_path):
    """新しいプロジェクトIDで上書き保存できる"""
    store = CredentialStore(config_dir=tmp_path)
    store.save_project_id("proj-first")
    store.save_project_id("proj-second")
    result = store.load_project_id()
    assert result == "proj-second"
