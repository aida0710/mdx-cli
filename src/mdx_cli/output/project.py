"""プロジェクト情報の縦型表示と、HTMLレポートの表抽出。"""

import json

from bs4 import BeautifulSoup, Tag
from rich.table import Table
from rich.text import Text

from mdx_cli.api.spinner import stop_active_spinner
from mdx_cli.console import console
from mdx_cli.models.project import UsageTable
from mdx_cli.output.tables import (
    PROJECT_OVERVIEW_FIELDS, PROJECT_OVERVIEW_SECTIONS, PROJECT_PACK_FIELDS, PROJECT_RESOURCE_FIELDS,
)


def _display(value) -> str:
    if value is None:
        return "—"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def render_fields(data: dict, fields: list[tuple[str, str]]) -> None:
    stop_active_spinner()
    table = Table("項目", "値")
    for label, key in fields:
        table.add_row(label, Text(_display(data.get(key))))
    console.print(table)


def render_resources(data: dict) -> None:
    stop_active_spinner()
    table = Table("項目", "CPUパック", "GPUパック")
    for label, suffix in PROJECT_PACK_FIELDS:
        table.add_row(label, Text(_display(data.get(f"cpu_pack{suffix}"))),
                      Text(_display(data.get(f"gpu_pack{suffix}"))))
    console.print(table)
    render_fields(data, PROJECT_RESOURCE_FIELDS)


def _overview_rows(value, labels: tuple[str, ...] = ()):
    """未知フィールドや配列も省略せず、入れ子を項目ごとの行へ展開する。"""
    if isinstance(value, dict) and value:
        for key, child in value.items():
            yield from _overview_rows(child, (*labels, PROJECT_OVERVIEW_FIELDS.get(key, key)))
    elif isinstance(value, list) and value:
        for index, child in enumerate(value, 1):
            yield from _overview_rows(child, (*labels, str(index)))
    else:
        text = "なし" if isinstance(value, (dict, list)) else _display(value)
        yield " / ".join(labels) or "値", text


def render_overview(sections: dict) -> None:
    stop_active_spinner()
    for kind, data in sections.items():
        console.print(Text(PROJECT_OVERVIEW_SECTIONS.get(kind, kind), style="bold"))
        table = Table("項目", "値")
        for label, value in _overview_rows(data):
            table.add_row(Text(label), Text(value))
        console.print(table)


def _span(cell: Tag, name: str) -> int:
    try:
        # 異常なHTMLで巨大な表を生成しない。通常の結合セルはそのまま展開する。
        return min(max(int(str(cell.get(name, 1))), 1), 1000)
    except ValueError:
        return 1


def parse_usage_tables(html: str) -> list[UsageTable]:
    """結合セルを展開し、値は単位・桁区切り・精度を含む文字列として保持する。

    headersは先頭のth行（thead内は複数行を結合）。残りは合計行を含むrows。
    ヘッダーがない表も列名を推測せず返す。
    """
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    result = []
    for table in soup.find_all("table"):
        if table.find_parent("table") is not None:
            continue
        rows = []
        header_count = 0
        pending: dict[int, tuple[str, int]] = {}
        for tr in table.find_all("tr"):
            if tr.find_parent("table") is not table:
                continue
            cells = tr.find_all(["th", "td"], recursive=False)
            if not cells and not pending:
                continue
            values = {col: value for col, (value, _) in pending.items()}
            pending = {col: (value, left - 1) for col, (value, left) in pending.items() if left > 1}
            col = 0
            for cell in cells:
                value = " ".join(cell.stripped_strings)
                width, height = _span(cell, "colspan"), _span(cell, "rowspan")
                while any(col + offset in values for offset in range(width)):
                    col += 1
                for offset in range(width):
                    values[col + offset] = value
                    if height > 1:
                        pending[col + offset] = (value, height - 1)
                col += width
            rows.append([values.get(i, "") for i in range(max(values, default=-1) + 1)])
            if len(rows) == header_count + 1 and cells and (
                tr.find_parent("thead") is not None or all(cell.name == "th" for cell in cells)
            ):
                header_count += 1
        if not rows:
            continue
        width = max(map(len, rows))
        rows = [row + [""] * (width - len(row)) for row in rows]
        headers = [" / ".join(dict.fromkeys(row[i] for row in rows[:header_count] if row[i]))
                   for i in range(width)] if header_count else []
        caption = table.find("caption", recursive=False)
        result.append(UsageTable(caption=caption.get_text(" ", strip=True) if caption else "",
                                 headers=headers, rows=rows[header_count:]))
    return result


def render_usage_tables(tables: list[UsageTable]) -> None:
    stop_active_spinner()
    for data in tables:
        table = Table(title=Text(data.caption), show_header=bool(data.headers))
        width = max([len(data.headers), *(len(row) for row in data.rows)])
        for i in range(width):
            table.add_column(Text(data.headers[i] if data.headers else ""))
        for row in data.rows:
            table.add_row(*(Text(value) for value in row))
        console.print(table)
