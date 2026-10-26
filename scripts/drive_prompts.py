"""疑似端末で mdx の対話を操作し、画面の出力を表示する（対話の動作確認用）。

手順は「待つ文字列（正規表現）|送るキー」を順に並べる。キーはバックスラッシュ記法で書く:
Esc は \\x1b、Enter は \\r、下矢印は \\x1b[B、行の消去は \\x15。
実APIを使うコマンドで試すときは、最後に必ず「中止する」を選ぶ。

例: uv run python scripts/drive_prompts.py "プロトコル|\\r" "送信元アドレス|\\x1b" -- network acl add
"""

import os
import pty
import re
import select
import sys
import time

# 待つ文字列が出るまでの上限（秒）。実APIの一覧取得を含めても足りる長さ
_WAIT_SECONDS = 25
# 画面が描き終わる前にキーを送らないための間（秒）
_KEY_DELAY_SECONDS = 0.25
_ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]")
_FINISHED = r"Aborted|受け付けました|開始しました|ログインしました|登録しました"


def _plain(data: bytes) -> str:
    return _ANSI_ESCAPE.sub("", data.decode(errors="ignore"))


def main() -> None:
    separator = sys.argv.index("--")
    steps, mdx_args = sys.argv[1:separator], sys.argv[separator + 1:]
    pid, fd = pty.fork()
    if pid == 0:
        os.environ["COLUMNS"] = "140"
        os.execvp("uv", ["uv", "run", "--no-sync", "mdx", *mdx_args])

    output = b""

    def wait_for(pattern: str) -> None:
        nonlocal output
        start = len(output)
        deadline = time.time() + _WAIT_SECONDS
        while time.time() < deadline:
            if not select.select([fd], [], [], 0.05)[0]:
                continue
            try:
                output += os.read(fd, 65536)
            except OSError:
                return
            if re.search(pattern, _plain(output[start:])):
                return
        print(f"!! 待っても出なかった: {pattern!r}")

    for step in steps:
        expected, keys = step.split("|", 1)
        wait_for(expected)
        time.sleep(_KEY_DELAY_SECONDS)
        os.write(fd, keys.encode().decode("unicode_escape").encode())
    wait_for(_FINISHED)

    lines = _plain(output).replace("\r", "").splitlines()
    print("\n".join(line for line in lines if line.strip() and "取得中" not in line))


if __name__ == "__main__":
    main()
