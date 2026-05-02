import base64
import json
import time

import httpx
import respx

from mdx_cli.api.auth import MDXAuth, decode_jwt_exp, token_needs_refresh


def _make_jwt(exp: int | None) -> str:
    """テスト用の簡易JWT（署名なし、payloadのみ検証対象）。"""
    header = base64.urlsafe_b64encode(b'{"alg":"HS256","typ":"JWT"}').rstrip(b"=").decode()
    payload_dict = {"exp": exp} if exp is not None else {}
    payload = base64.urlsafe_b64encode(json.dumps(payload_dict).encode()).rstrip(b"=").decode()
    signature = "abc"
    return f"{header}.{payload}.{signature}"


def test_auth_injects_jwt_header():
    """保存済みトークンがあればAuthorizationヘッダーに注入される"""
    auth = MDXAuth(token="test-jwt-token")
    request = httpx.Request("GET", "https://oprpl.mdx.jp/api/project/assigned/")
    flow = auth.auth_flow(request)
    modified_request = next(flow)
    assert modified_request.headers["Authorization"] == "JWT test-jwt-token"


def test_auth_no_token():
    """トークンがなければヘッダーは付与されない"""
    auth = MDXAuth(token=None)
    request = httpx.Request("GET", "https://oprpl.mdx.jp/api/project/assigned/")
    flow = auth.auth_flow(request)
    modified_request = next(flow)
    assert "Authorization" not in modified_request.headers


@respx.mock
def test_auth_refreshes_on_401():
    """401応答時に自動でリフレッシュを試行する"""
    respx.get("https://oprpl.mdx.jp/api/project/assigned/").side_effect = [
        httpx.Response(401),
        httpx.Response(200, json={"results": []}),
    ]
    respx.post("https://oprpl.mdx.jp/api/refresh/").mock(
        return_value=httpx.Response(200, json={"token": "new-jwt"})
    )
    auth = MDXAuth(token="old-jwt")
    client = httpx.Client(base_url="https://oprpl.mdx.jp/", auth=auth)
    resp = client.get("/api/project/assigned/")
    assert resp.status_code == 200
    assert auth.token == "new-jwt"


# --- decode_jwt_exp ---


def test_decode_jwt_exp_valid():
    """有効なJWTから exp を取り出す。"""
    token = _make_jwt(exp=1700000000)
    assert decode_jwt_exp(token) == 1700000000


def test_decode_jwt_exp_no_exp_claim():
    """exp claim がない場合は None。"""
    token = _make_jwt(exp=None)
    assert decode_jwt_exp(token) is None


def test_decode_jwt_exp_malformed():
    """壊れたトークンは None。"""
    assert decode_jwt_exp("not-a-jwt") is None
    assert decode_jwt_exp("") is None
    assert decode_jwt_exp("only.two") is None


# --- token_needs_refresh ---


def test_token_needs_refresh_expires_soon():
    """閾値以内に期限切れならTrue。"""
    soon = int(time.time()) + 300  # 5分後
    token = _make_jwt(exp=soon)
    assert token_needs_refresh(token, threshold_seconds=900) is True


def test_token_needs_refresh_still_valid():
    """閾値より余裕があればFalse。"""
    later = int(time.time()) + 7200  # 2時間後
    token = _make_jwt(exp=later)
    assert token_needs_refresh(token, threshold_seconds=900) is False


def test_token_needs_refresh_already_expired():
    """既に期限切れならTrue。"""
    past = int(time.time()) - 100
    token = _make_jwt(exp=past)
    assert token_needs_refresh(token, threshold_seconds=900) is True


def test_token_needs_refresh_malformed_returns_false():
    """デコード失敗時は False（reactive refresh に任せる）。"""
    assert token_needs_refresh("bad-token") is False
    assert token_needs_refresh("") is False
