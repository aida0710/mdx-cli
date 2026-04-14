"""全API通信に対するグローバルスピナー

httpx の event_hooks を使い、最初のリクエストでスピナーを開始。
結果表示前に stop() で停止。
"""

import httpx
from rich.console import Console
from rich.status import Status

_console = Console(stderr=True)

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
        self._status = _console.status("取得中...", spinner="dots")
        self._status.start()
        self._started = True
        _active_spinner = self

    def on_response(self, response: httpx.Response) -> None:
        pass

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
        return {
            "request": [self.on_request],
            "response": [self.on_response],
        }
