"""Richコンソールの共有インスタンス

結果・対話UIは stdout、スピナー・進捗などの装飾は stderr に出す。
--json 出力時もスピナーがパイプ先を汚さないよう、装飾は必ず err_console を使う。
"""

from rich.console import Console

console = Console()
err_console = Console(stderr=True)
