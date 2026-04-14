from mdx_cli.models.template import Template


def test_template_from_api_response():
    """実際のAPIレスポンス形式でTemplateを作成できる"""
    data = {
        "uuid": "tmpl-1",
        "name": "Ubuntu 22.04",
        "template_name": "ubuntu-22.04",
        "os_type": "Linux",
        "os_name": "Ubuntu",
        "os_version": "22.04",
        "gpu_required": False,
        "lower_limit_disk": 40,
        "login_username": "mdxuser",
        "description": "Ubuntu 22.04 LTS",
    }
    tmpl = Template.model_validate(data)
    assert tmpl.uuid == "tmpl-1"
    assert tmpl.name == "Ubuntu 22.04"
    assert tmpl.template_name == "ubuntu-22.04"
    assert tmpl.os_type == "Linux"
    assert tmpl.os_name == "Ubuntu"
    assert tmpl.os_version == "22.04"
    assert tmpl.gpu_required is False
    assert tmpl.lower_limit_disk == 40
    assert tmpl.login_username == "mdxuser"
    assert tmpl.description == "Ubuntu 22.04 LTS"


def test_template_optional_fields_none():
    """オプションフィールドがNoneでも作成できる"""
    data = {
        "uuid": "tmpl-2",
        "name": "Minimal Template",
        "template_name": None,
        "os_type": None,
        "os_name": None,
        "os_version": None,
        "login_username": None,
        "description": None,
    }
    tmpl = Template.model_validate(data)
    assert tmpl.uuid == "tmpl-2"
    assert tmpl.template_name is None
    assert tmpl.os_type is None
    assert tmpl.os_name is None
    assert tmpl.os_version is None
    assert tmpl.login_username is None
    assert tmpl.description is None


def test_template_defaults():
    """必須フィールドのみ指定した場合のデフォルト値を確認"""
    data = {
        "uuid": "tmpl-3",
        "name": "Default Template",
    }
    tmpl = Template.model_validate(data)
    assert tmpl.template_name == ""
    assert tmpl.os_type == ""
    assert tmpl.os_name == ""
    assert tmpl.os_version == ""
    assert tmpl.gpu_required is False
    assert tmpl.lower_limit_disk == 40
    assert tmpl.login_username == "mdxuser"
    assert tmpl.description == ""


def test_template_extra_fields_allowed():
    """未知フィールドがあってもエラーにならない（extra='allow'）"""
    data = {
        "uuid": "tmpl-4",
        "name": "Extra Fields Template",
        "unknown_field": "some_value",
        "another_unknown": 42,
    }
    tmpl = Template.model_validate(data)
    assert tmpl.uuid == "tmpl-4"
    assert tmpl.name == "Extra Fields Template"
