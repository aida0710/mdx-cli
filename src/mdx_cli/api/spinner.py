"""全API通信に対するグローバルスピナーと進捗表示

- RequestSpinner: httpx の event_hooks を使い、最初のリクエストでスピナーを開始。
  結果表示前に stop_active_spinner() で停止。
- progress_status: 並列処理の「ラベル... (done/total)」進捗表示を共通化する
  コンテキストマネージャ。
"""

from contextlib import contextmanager
from typing import Iterator

import httpx
from rich.status import Status

from mdx_cli.console import err_console

# グローバルで現在アクティブなスピナーを追跡
_active_spinner: "RequestSpinner | None" = None


def stop_active_spinner() -> None:
    """アクティブなスピナーがあれば停止する。render() 等から呼ぶ。"""
    global _active_spinner
    if _active_spinner:
        _active_spinner.stop()


class RequestSpinner:
    """httpx event hooks 用のスピナー管理"""

    def __init__(self, silent: bool = False):
        self._silent = silent
        self._status: Status | None = None
        self._started = False

    def on_request(self, request: httpx.Request) -> None:
        global _active_spinner
        if self._silent or self._started:
            return
        self._status = err_console.status("取得中...", spinner="dots")
        self._status.start()
        self._started = True
        _active_spinner = self

    def update(self, message: str) -> None:
        if self._status:
            self._status.update(message)

    def stop(self) -> None:
        global _active_spinner
        if self._status:
            self._status.stop()
            self._status = None
        self._started = False
        if _active_spinner is self:
            _active_spinner = None

    def hooks(self) -> dict:
        return {"request": [self.on_request]}


class ProgressStatus:
    """「ラベル... (done/total) サフィックス」形式の進捗スピナー。

    enabled=False（--json 時）はスピナーを作らず、全操作が no-op になる。
    """

    def __init__(self, label: str, total: int, enabled: bool = True):
        self._label = label
        self._total = total
        self._done = 0
        self._enabled = enabled
        self._status: Status | None = None

    def _message(self, suffix: str = "") -> str:
        msg = f"{self._label}... ({self._done}/{self._total})"
        return f"{msg} {suffix}" if suffix else msg

    def start(self) -> None:
        if self._enabled:
            self._status = err_console.status(self._message(), spinner="dots")
            self._status.start()

    def advance(self, suffix: str = "") -> None:
        """完了数を1増やして表示を更新する。"""
        self._done += 1
        if self._status:
            self._status.update(self._message(suffix))

    def stop(self) -> None:
        if self._status:
            self._status.stop()
            self._status = None


@contextmanager
def progress_status(
    label: str, total: int, enabled: bool = True
) -> Iterator[ProgressStatus]:
    """進捗スピナーを開始し、with を抜けるとき必ず停止する。"""
    progress = ProgressStatus(label, total, enabled=enabled)
    progress.start()
    try:
        yield progress
    finally:
        progress.stop()
