import logging
from pathlib import Path
from typing import Callable, Generator

import httpx

logger = logging.getLogger("mdx_cli")


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
        try:
            with httpx.Client(base_url=base_url, timeout=30) as client:
                resp = client.post("/api/refresh/", json={"token": self.token})
                if resp.status_code == 200:
                    return resp.json().get("token")
        except httpx.HTTPError:
            pass
        return None

    def _persist_token(self, token: str) -> None:
        if self._token_save_path:
            import json
            self._token_save_path.parent.mkdir(parents=True, exist_ok=True)
            self._token_save_path.write_text(json.dumps({"token": token}))
