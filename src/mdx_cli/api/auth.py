import base64
import json
import logging
import time
from pathlib import Path
from typing import Callable, Generator

import httpx

logger = logging.getLogger("mdx_cli")


def decode_jwt_exp(token: str) -> int | None:
    """JWTの exp claim（期限切れunix時刻）を取り出す。

    パースに失敗した場合は None を返す（壊れたトークンは reactive refresh に任せる）。
    """
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        payload_b64 = parts[1]
        padding = (-len(payload_b64)) % 4
        payload_bytes = base64.urlsafe_b64decode(payload_b64 + "=" * padding)
        payload = json.loads(payload_bytes)
        exp = payload.get("exp")
        return int(exp) if exp is not None else None
    except Exception:
        return None


def token_needs_refresh(token: str, threshold_seconds: int = 900) -> bool:
    """トークンの期限が threshold_seconds 以内なら True。

    デコード失敗時は False を返し、MDXAuth の reactive refresh に任せる。
    """
    exp = decode_jwt_exp(token)
    if exp is None:
        return False
    return exp - time.time() < threshold_seconds


def refresh_saved_token(token: str, base_url: str, timeout: int = 30) -> str | None:
    """/api/refresh/ を叩いて新トークンを取得する。

    失敗時は None を返す（例外は投げない）。
    """
    try:
        with httpx.Client(
            base_url=base_url,
            timeout=timeout,
            transport=httpx.HTTPTransport(local_address="0.0.0.0"),
        ) as client:
            resp = client.post("/api/refresh/", json={"token": token})
            if resp.status_code == 200:
                return resp.json().get("token")
    except Exception as e:
        logger.debug("トークンリフレッシュに失敗: %s", e)
    return None


class MDXAuth(httpx.Auth):
    def __init__(
        self,
        token: str | None = None,
        token_save_path: Path | None = None,
        relogin_fn: Callable[[], str | None] | None = None,
    ):
        self.token = token
        self._token_save_path = token_save_path
        self._relogin_fn = relogin_fn

    def auth_flow(
        self, request: httpx.Request
    ) -> Generator[httpx.Request, httpx.Response, None]:
        if self.token:
            request.headers["Authorization"] = f"JWT {self.token}"
        response = yield request

        if response.status_code == 401 and self.token:
            # 1. まずrefreshを試行
            new_token = self._try_refresh(request)
            if new_token:
                logger.debug("トークンをリフレッシュしました")
                self.token = new_token
                self._persist_token(new_token)
                request.headers["Authorization"] = f"JWT {new_token}"
                retry_response = yield request
                if retry_response.status_code == 401:
                    logger.error("リフレッシュ後も認証失敗")
                return

            # 2. refresh失敗 → 保存済みID/PWで再ログイン
            if self._relogin_fn:
                logger.debug("リフレッシュ失敗、再ログインを試行")
                new_token = self._relogin_fn()
                if new_token:
                    self.token = new_token
                    self._persist_token(new_token)
                    request.headers["Authorization"] = f"JWT {new_token}"
                    retry_response = yield request
                    if retry_response.status_code == 401:
                        logger.error("再ログイン後も認証失敗")

    def _try_refresh(self, original_request: httpx.Request) -> str | None:
        base_url = str(original_request.url.scheme) + "://" + str(original_request.url.host)
        if original_request.url.port and original_request.url.port not in (80, 443):
            base_url += f":{original_request.url.port}"
        return refresh_saved_token(self.token or "", base_url)

    def _persist_token(self, token: str) -> None:
        if self._token_save_path:
            self._token_save_path.parent.mkdir(parents=True, exist_ok=True)
            self._token_save_path.write_text(json.dumps({"token": token}))
