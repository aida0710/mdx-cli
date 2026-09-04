"""TOTP（RFC 6238）生成のテスト"""

import pytest

from mdx_cli.credentials.totp import generate_totp, otp_from_store, verify_totp

# RFC 6238 のテストベクタ用シークレット（ASCII "12345678901234567890" の Base32）
RFC_SECRET = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"


def test_generate_totp_matches_rfc6238_vector_at_t59():
    assert generate_totp(RFC_SECRET, at=59) == "287082"


def test_generate_totp_matches_rfc6238_vector_at_t1111111109():
    assert generate_totp(RFC_SECRET, at=1111111109) == "081804"


def test_generate_totp_accepts_lowercase_and_spaces():
    """認証アプリからコピーしたシークレットは小文字・空白区切りのことがある。"""
    assert generate_totp("gezd gnbv gy3t qojq gezd gnbv gy3t qojq", at=59) == "287082"


def test_generate_totp_accepts_secret_without_padding():
    """Base32 のパディング `=` が省かれたシークレットも受け付ける。"""
    unpadded = "GEZDGNBVGY3TQOJQGEZA"  # 20文字（8の倍数でない = "====" が必要）
    assert generate_totp(unpadded, at=59) == generate_totp(unpadded + "====", at=59)


def test_generate_totp_rejects_invalid_secret():
    with pytest.raises(ValueError):
        generate_totp("not-base32!", at=59)


def test_generate_totp_rejects_empty_secret():
    with pytest.raises(ValueError):
        generate_totp("", at=59)


def test_otp_from_store_returns_none_when_secret_not_registered(mocker):
    store = mocker.MagicMock()
    store.load_totp_secret.return_value = None
    assert otp_from_store(store, "alice") is None


def test_otp_from_store_generates_code_from_saved_secret(mocker):
    store = mocker.MagicMock()
    store.load_totp_secret.return_value = ("alice", RFC_SECRET)
    assert otp_from_store(store, "alice") == generate_totp(RFC_SECRET)


def test_otp_from_store_ignores_secret_of_another_user(mocker):
    """別アカウントでログインするときは他人のシークレットを使わない（手入力に戻す）"""
    store = mocker.MagicMock()
    store.load_totp_secret.return_value = ("alice", RFC_SECRET)
    assert otp_from_store(store, "bob") is None


def test_verify_totp_accepts_current_and_adjacent_time_windows():
    current = generate_totp(RFC_SECRET, at=60)
    previous = generate_totp(RFC_SECRET, at=30)

    assert verify_totp(RFC_SECRET, current, at=60)
    assert verify_totp(RFC_SECRET, previous, at=60)


def test_verify_totp_rejects_invalid_code_and_secret():
    assert not verify_totp(RFC_SECRET, "999999", at=60)
    assert not verify_totp(RFC_SECRET, "not-a-code", at=60)
    assert not verify_totp("not-base32!", "123456", at=60)


def test_otp_from_store_ignores_corrupt_secret(mocker):
    """保存値が壊れていてもログインを落とさず、手入力へ戻す。"""
    store = mocker.MagicMock()
    store.load_totp_secret.return_value = ("alice", "not-base32!")

    assert otp_from_store(store, "alice") is None
