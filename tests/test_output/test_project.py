from mdx_cli.output.project import parse_usage_tables


def test_multiple_tables_and_multilevel_headers():
    tables = parse_usage_tables("""
    <table><thead>
    <tr><th rowspan="2">資源</th><th colspan="2">ポイント</th></tr>
    <tr><th>使用</th><th>残り</th></tr>
    </thead><tbody><tr><th>CPU</th><td>0.0100</td><td>—</td></tr></tbody></table>
    <table><tr><td>GPU<br>pack</td><td>1&nbsp;000</td></tr></table>
    """)
    assert len(tables) == 2
    assert tables[0].headers == ["資源", "ポイント / 使用", "ポイント / 残り"]
    assert tables[0].rows == [["CPU", "0.0100", "—"]]
    assert tables[1].headers == []
    assert tables[1].rows == [["GPU pack", "1\xa0000"]]


def test_sparse_rows_and_invalid_spans():
    tables = parse_usage_tables("""
    <table><tr><th>A</th><th>B</th></tr>
    <tr><td colspan="oops" rowspan="-1">0</td></tr>
    <tr><td></td><td>last</td></tr></table>
    """)
    assert tables[0].rows == [["0", ""], ["", "last"]]


def test_no_tables_and_empty_tables():
    assert parse_usage_tables("<p>No usage</p><table></table>") == []


def test_nested_table_is_not_counted_twice_and_scripts_are_removed():
    tables = parse_usage_tables("""
    <table><tr><td>outer<table><tr><td>inner</td></tr></table></td>
    <td>1<script>hidden()</script><style>.hidden {}</style></td></tr></table>
    """)
    assert len(tables) == 1
    assert tables[0].rows == [["outer inner", "1"]]


def test_overview_preserves_unknown_nested_fields_and_lists(capsys):
    from mdx_cli.output.project import render_overview

    render_overview({"resource_list": {
        "future": [{"state": "[red]literal", "count": 2}], "empty": [], "missing": None,
    }})
    output = capsys.readouterr().out
    assert "割当資源" in output
    assert "future / 1 / state" in output
    assert "[red]literal" in output
    assert "future / 1 / count" in output
    assert "empty" in output and "なし" in output
    assert "missing" in output and "—" in output
