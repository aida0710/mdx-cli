import pytest

from mdx_cli.commands._name_pattern import (
    expand_name_pattern,
    expand_name_pattern_for_deploy,
    is_name_pattern,
    match_names,
    rename_by_wildcards,
)


def test_no_pattern():
    assert expand_name_pattern("my-vm") == ["my-vm"]


def test_single_digit_range():
    result = expand_name_pattern("vm-{0-9}")
    assert len(result) == 10
    assert result[0] == "vm-0"
    assert result[9] == "vm-9"


def test_single_alpha_range():
    result = expand_name_pattern("vm-{a-c}")
    assert result == ["vm-a", "vm-b", "vm-c"]


def test_double_pattern():
    result = expand_name_pattern("vm-{a-b}-{0-1}")
    assert result == ["vm-a-0", "vm-a-1", "vm-b-0", "vm-b-1"]


def test_large_batch():
    result = expand_name_pattern("crawler-{a-g}-{0-9}")
    assert len(result) == 70  # 7 * 10


def test_zero_padded():
    result = expand_name_pattern("node-{00-05}")
    assert result == ["node-00", "node-01", "node-02", "node-03", "node-04", "node-05"]


def test_partial_range():
    result = expand_name_pattern("vm-{3-5}")
    assert result == ["vm-3", "vm-4", "vm-5"]


# --- match_names ---

ALL_VMS = [
    "crawler-a-0", "crawler-a-1", "crawler-b-0", "crawler-b-1",
    "login-server", "vpn-serv", "db-node-01", "db-node-02",
]


def test_match_glob():
    assert match_names("crawler-*", ALL_VMS) == [
        "crawler-a-0", "crawler-a-1", "crawler-b-0", "crawler-b-1",
    ]


def test_match_exact():
    assert match_names("vpn-serv", ALL_VMS) == ["vpn-serv"]


def test_match_range():
    assert match_names("crawler-{a-b}-0", ALL_VMS) == ["crawler-a-0", "crawler-b-0"]


def test_match_range_with_glob():
    assert match_names("crawler-{a-b}-*", ALL_VMS) == [
        "crawler-a-0", "crawler-a-1", "crawler-b-0", "crawler-b-1",
    ]


def test_match_question_mark():
    assert match_names("db-node-0?", ALL_VMS) == ["db-node-01", "db-node-02"]


def test_match_no_result():
    assert match_names("nonexistent-*", ALL_VMS) == []


# --- expand_name_pattern_for_deploy ---
# MDX deploy API は vm_name の [N-M] 範囲記法をサーバー側で展開する。
# ただし対応は単一桁数値（0-9）のみで、複数桁・ゼロ埋め・アルファベットは非対応。


def test_deploy_no_pattern():
    assert expand_name_pattern_for_deploy("my-vm") == ["my-vm"]


def test_deploy_single_digit_range():
    """単一桁数値範囲はAPI記法を維持して1要素のリストを返す。"""
    assert expand_name_pattern_for_deploy("vm-{0-9}") == ["vm-[0-9]"]


def test_deploy_partial_single_digit_range():
    """単一桁数値の部分範囲もAPI記法を維持。"""
    assert expand_name_pattern_for_deploy("vm-{3-7}") == ["vm-[3-7]"]


def test_deploy_multi_digit_range_expanded():
    """複数桁数値はAPI非対応のためクライアント側で展開。"""
    result = expand_name_pattern_for_deploy("vm-{1-99}")
    assert len(result) == 99
    assert result[0] == "vm-1"
    assert result[-1] == "vm-99"


def test_deploy_double_digit_range_expanded():
    """複数桁数値はAPI非対応のためクライアント側で展開。"""
    result = expand_name_pattern_for_deploy("vm-{10-20}")
    assert len(result) == 11
    assert result[0] == "vm-10"
    assert result[-1] == "vm-20"


def test_deploy_zero_padded_expanded():
    """ゼロ埋めはAPI非対応のためクライアント側で展開。"""
    assert expand_name_pattern_for_deploy("vm-{00-09}") == [
        "vm-00", "vm-01", "vm-02", "vm-03", "vm-04",
        "vm-05", "vm-06", "vm-07", "vm-08", "vm-09",
    ]


def test_deploy_alpha_expanded():
    """アルファベットはAPI非対応のためクライアント側で展開。"""
    assert expand_name_pattern_for_deploy("vm-{a-c}") == ["vm-a", "vm-b", "vm-c"]


def test_deploy_combined_alpha_and_digit():
    """アルファベットは展開、数値部分はAPI記法を維持。"""
    assert expand_name_pattern_for_deploy("vm-{a-c}-{0-9}") == [
        "vm-a-[0-9]", "vm-b-[0-9]", "vm-c-[0-9]",
    ]


def test_deploy_alpha_with_zero_padded():
    """両方がAPI非対応の場合は完全に展開。"""
    result = expand_name_pattern_for_deploy("vm-{a-b}-{00-09}")
    assert len(result) == 20
    assert result[0] == "vm-a-00"
    assert result[-1] == "vm-b-09"


# --- rename_by_wildcards ---


def test_rename_by_wildcards_carries_matched_part_to_new_name():
    """対象パターンの * に当たった部分を、新しい名前の * に入れる"""
    assert rename_by_wildcards("crawler-*", "crawler-01", "yt-*") == "yt-01"
    assert rename_by_wildcards("*-old", "worker-3-old", "*") == "worker-3"
    assert rename_by_wildcards("a-*-b-*", "a-x-b-y", "*_*") == "x_y"


def test_rename_by_wildcards_rejects_mismatched_wildcard_count():
    """新しい名前の * の数が対象パターンと違えば、どこに何を入れるか決まらないので断る"""
    with pytest.raises(ValueError, match=r"\* の数"):
        rename_by_wildcards("crawler-*", "crawler-01", "yt-*-*")


def test_rename_by_wildcards_requires_star_pattern_for_target():
    """対象が * のパターンでなければ、* の置き換えはできない"""
    with pytest.raises(ValueError, match=r"\* の数"):
        rename_by_wildcards("crawler-01", "crawler-01", "yt-*")


def test_is_name_pattern():
    """*・?・{範囲} を含むものをパターンとみなす"""
    assert is_name_pattern("crawler-*")
    assert is_name_pattern("node-?")
    assert is_name_pattern("node-{0-3}")
    assert not is_name_pattern("crawler-01")
