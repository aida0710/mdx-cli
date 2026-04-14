from mdx_cli.commands._name_pattern import expand_name_pattern, match_names


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
