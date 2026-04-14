import json

from pydantic import BaseModel
from rich.console import Console
from rich.table import Table

from mdx_cli.api.spinner import stop_active_spinner

console = Console()


def render_json(data: BaseModel | list[BaseModel]) -> None:
    stop_active_spinner()
    if isinstance(data, list):
        output = [item.model_dump(mode="json") for item in data]
    else:
        output = data.model_dump(mode="json")
    print(json.dumps(output, indent=2, ensure_ascii=False))


def render_table(data: list[BaseModel], columns: list[tuple[str, str]]) -> None:
    stop_active_spinner()
    table = Table()
    for header, _ in columns:
        table.add_column(header)
    for item in data:
        row = []
        for _, field in columns:
            value = getattr(item, field, None)
            if value is None:
                extra = getattr(item, "model_extra", None) or {}
                value = extra.get(field, "")
            row.append(str(value) if value is not None else "")
        table.add_row(*row)
    console.print(table)


def render(
    data: BaseModel | list[BaseModel],
    columns: list[tuple[str, str]],
    json_mode: bool,
) -> None:
    if json_mode:
        render_json(data)
    else:
        items = data if isinstance(data, list) else [data]
        render_table(items, columns)
