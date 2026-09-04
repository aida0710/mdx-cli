"""TOTP（RFC 6238）ワンタイムパスワードの生成"""

import base64
import hashlib
import hmac
import struct
import time


def generate_totp(secret: str, at: float | None = None, period: int = 30, digits: int = 6) -> str:
    """Base32 シークレットから TOTP コードを生成する。

    認証アプリからコピーしたシークレットは小文字・空白区切り・パディング省略が
    あり得るため、正規化してからデコードする。不正なシークレットは ValueError。
    """
    normalized = secret.replace(" ", "").replace("-", "").upper().rstrip("=")
    if not normalized:
        raise ValueError("TOTP secret is empty")
    padded = normalized + "=" * (-len(normalized) % 8)
    key = base64.b32decode(padded)  # 不正文字・不正長は binascii.Error（ValueError のサブクラス）

    counter = int((time.time() if at is None else at) // period)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(code % 10**digits).zfill(digits)


def verify_totp(
    secret: str,
    code: str,
    at: float | None = None,
    window: int = 1,
) -> bool:
    """認証アプリのコードを現在時刻の前後 ``window`` 区間で検証する。"""
    if len(code) != 6 or not code.isascii() or not code.isdigit():
        return False
    now = time.time() if at is None else at
    try:
        return any(
            hmac.compare_digest(generate_totp(secret, at=now + offset * 30), code)
            for offset in range(-window, window + 1)
        )
    except ValueError:
        return False


def otp_from_store(store, username: str) -> str | None:
    """username に紐付いたシークレットからOTPを生成する。無ければ None。

    別アカウントのシークレットは使わない（他人のOTPを送ってしまうため）。
    呼び出し側は `otp_from_store(store, user) or 手入力` で手入力にフォールバックする。
    """
    entry = store.load_totp_secret()
    if not entry or entry[0] != username:
        return None
    try:
        return generate_totp(entry[1])
    except ValueError:
        return None
