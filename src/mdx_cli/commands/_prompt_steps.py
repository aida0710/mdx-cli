"""対話の項目を順に聞く。Esc で前の項目へ戻り、最後の確認では「直す」で項目を選んで入れ直せる。

各項目（Step）は、聞いた結果を呼び出し側の状態へ書き込む関数。戻ったり直したりして
もう一度聞くときは、前に入れた値を初期値にして聞く（各コマンドの関数が状態から初期値を作る）。
"""

from collections.abc import Callable, Sequence
from contextvars import ContextVar
from dataclasses import dataclass, field

import questionary
import typer
from prompt_toolkit.key_binding import KeyBindings, merge_key_bindings
from questionary import Choice

from mdx_cli.console import console

# Esc を押したときに質問が返す値
BACK = object()

# Esc の後に続くキー（矢印キーなど）を待つ時間。prompt_toolkit の既定 0.5 秒だと戻るのが遅い。
# 0.2 秒より短くすると、手元の計測ではかえって 1 秒ほど待たされた（2026-10-26）
_ESCAPE_WAIT_SECONDS = 0.2

# 手順の中だけ Esc を「戻る」にする。手順の外（項目が1つの選択など）では戻り先が無い
_back_enabled: ContextVar[bool] = ContextVar("back_enabled", default=False)


class GoBack(Exception):
    """利用者が Esc で前の項目へ戻ろうとした。"""


@dataclass
class Step:
    label: str  # 「直す」の一覧に出す項目名
    ask: Callable[[], None]  # 聞いて結果を状態へ書き込む
    # 前の答えによって聞かない項目（ICMP のポートなど）。進むときも戻るときも飛ばす
    is_needed: Callable[[], bool] = field(default=lambda: True)


def ask(question):
    """questionary の質問を聞く。手順の中なら Esc で GoBack を投げる。"""
    if not _back_enabled.get():
        return question.unsafe_ask()

    back_binding = KeyBindings()

    @back_binding.add("escape", eager=True)
    def _go_back(event) -> None:
        event.app.exit(result=BACK)

    application = question.application
    application.key_bindings = merge_key_bindings([application.key_bindings, back_binding])
    application.ttimeoutlen = _ESCAPE_WAIT_SECONDS
    answer = question.unsafe_ask()
    if answer is BACK:
        raise GoBack()
    return answer


def run_steps(steps: Sequence[Step], start: int = 0) -> None:
    """start 番目から最後まで順に聞く。Esc なら1つ前の（聞く必要のある）項目へ戻る。"""
    token = _back_enabled.set(True)
    try:
        index = start
        while index < len(steps):
            if not steps[index].is_needed():
                index += 1
                continue
            try:
                steps[index].ask()
                index += 1
            except GoBack:
                previous = _previous_needed_index(steps, index)
                if previous is None:
                    console.print("[dim]これより前の項目はありません[/dim]")
                else:
                    index = previous
    finally:
        _back_enabled.reset(token)


def _previous_needed_index(steps: Sequence[Step], index: int) -> int | None:
    for previous in range(index - 1, -1, -1):
        if steps[previous].is_needed():
            return previous
    return None


def _choose_step_to_edit(steps: Sequence[Step]) -> int | None:
    """直す項目を選ぶ。Esc なら確認へ戻る（None）。"""
    try:
        return ask(questionary.select(
            "どの項目を直しますか？",
            choices=[
                Choice(step.label, value=index) for index, step in enumerate(steps) if step.is_needed()
            ],
        ))
    except GoBack:
        return None


def confirm_or_edit(steps: Sequence[Step], print_summary: Callable[[], None], message: str) -> None:
    """内容を見せて「実行／直す／中止」を聞く。直すなら選んだ項目から最後までを聞き直す。

    中止なら typer.Abort を投げる。Esc は最後の項目へ戻る。
    """
    choices = [Choice("実行する", value="execute")]
    if steps:
        choices.append(Choice("直す", value="edit"))
    choices.append(Choice("中止する", value="cancel"))

    token = _back_enabled.set(bool(steps))
    try:
        while True:
            print_summary()
            try:
                action = ask(questionary.select(f"\n{message}", choices=choices))
            except GoBack:
                last = _previous_needed_index(steps, len(steps))
                if last is not None:
                    run_steps(steps, start=last)
                continue
            if action == "execute":
                return
            if action == "cancel":
                raise typer.Abort()
            index = _choose_step_to_edit(steps)
            if index is not None:
                run_steps(steps, start=index)
    finally:
        _back_enabled.reset(token)
