import logging
import re
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger("mdx_cli")


def _parse_form(html: str) -> tuple[str, dict[str, str]]:
    """HTMLからフォームのaction URLとフィールドを抽出する。"""
    soup = BeautifulSoup(html, "html.parser")
    form = soup.find("form")
    if not form:
        raise ValueError("フォームが見つかりません")
    action = form.get("action", "")
    fields: dict[str, str] = {}
    for inp in form.find_all(["input", "button"]):
        name = inp.get("name")
        if name:
            fields[name] = inp.get("value", "")
    return action, fields


def _resolve_url(action: str, current_url: str) -> str:
    """相対URLを絶対URLに変換する。"""
    if action.startswith("http"):
        return action
    return urljoin(current_url, action)


def _detect_form_type(fields: dict[str, str]) -> str:
    """フォームのフィールドからフォームの種類を判定する。"""
    field_names = set(fields.keys())
    if "SAMLResponse" in field_names:
        return "saml"
    if "j_tokenNumber" in field_names:
        return "totp"
    if "j_username" in field_names and "j_password" in field_names:
        return "login"
    if any(k.startswith("shib_idp_ls_") for k in field_names):
        return "ls_check"
    if any(k.startswith("_shib_idp_consent") for k in field_names):
        return "consent"
    return "unknown"


def sso_login(
    base_url: str,
    username: str,
    password: str,
    otp: str,
    timeout: int = 60,
) -> str | None:
    """Shibboleth SSOフローを辿ってJWTトークンを取得する。

    IdPのフォームを自動判定してステップを進める:
      - ls_check: ローカルストレージチェック（自動送信）
      - login: ユーザー名/パスワード入力
      - totp: TOTP入力
      - consent: 属性同意（グローバル同意で自動承認）
      - saml: SAMLResponse送信
    """
    session = httpx.Client(
        follow_redirects=True,
        timeout=timeout,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        },
        transport=httpx.HTTPTransport(local_address="0.0.0.0"),
    )

    # Step 1: Shibboleth SP → IdPログインフォームへ
    url = f"{base_url}/Shibboleth.sso/Login?target={base_url}/api/sso_login"
    logger.debug("SSO開始: GET %s", url)

    try:
        resp = session.get(url)
    except httpx.ConnectError as e:
        logger.error("IdPへの接続に失敗: %s（VPN接続を確認してください）", e)
        return None

    logger.debug("→ %d %s", resp.status_code, resp.url)

    # フォームを順次処理（最大10ステップ）
    for step in range(10):
        # JWT抽出チェック（/api/sso_login/ のレスポンス）
        if "token" in resp.text and ("localStorage" in resp.text or "sso_login" in str(resp.url)):
            logger.debug("Step %d: HTMLからJWTを抽出試行", step)
            logger.debug("Body先頭500文字: %s", resp.text[:500])
            # const token = 'eyJ...'; や token = "eyJ..."; にマッチ
            match = re.search(
                r"""token\s*[=,:]\s*['"]([A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)['"]""",
                resp.text,
            )
            if match:
                token = match.group(1)
                logger.debug("JWT取得成功 (%d文字)", len(token))
                return token
            logger.debug("Step %d: 正規表現でJWTが見つかりません", step)

        # フォーム解析
        try:
            action, fields = _parse_form(resp.text)
        except ValueError:
            break

        form_type = _detect_form_type(fields)
        action = _resolve_url(action, str(resp.url))
        logger.debug("Step %d: フォーム種別=%s fields=%s", step, form_type, list(fields.keys()))

        if form_type == "ls_check":
            # ローカルストレージチェック: そのまま送信
            logger.debug("Step %d: LSチェック送信 → %s", step, action)
            resp = session.post(action, data=fields)

        elif form_type == "login":
            # ログインフォーム: ユーザー名/パスワードを入力
            fields["j_username"] = username
            fields["j_password"] = password
            logger.debug("Step %d: ログイン送信 → %s", step, action)
            resp = session.post(action, data=fields)

            # 同じフォームが再表示された場合は認証失敗
            try:
                _, new_fields = _parse_form(resp.text)
                if _detect_form_type(new_fields) == "login":
                    logger.error("ユーザー名またはパスワードが無効です")
                    return None
            except ValueError:
                pass

        elif form_type == "totp":
            # TOTPフォーム: OTPを入力
            fields["j_tokenNumber"] = otp
            logger.debug("Step %d: TOTP送信 → %s", step, action)
            resp = session.post(action, data=fields)

            # 同じフォームが再表示された場合はTOTP失敗
            try:
                _, new_fields = _parse_form(resp.text)
                if _detect_form_type(new_fields) == "totp":
                    logger.error("TOTP認証に失敗しました（コードが無効または期限切れ）")
                    return None
            except ValueError:
                pass

        elif form_type == "consent":
            # 属性同意: グローバル同意で自動承認
            fields["_shib_idp_consentOptions"] = "_shib_idp_globalConsent"
            logger.debug("Step %d: 属性同意送信 → %s", step, action)
            resp = session.post(action, data=fields)

        elif form_type == "saml":
            # SAMLResponse: SPに送信
            logger.debug("Step %d: SAMLResponse送信 → %s", step, action)
            resp = session.post(action, data=fields)

        else:
            logger.error("Step %d: 不明なフォーム種別: fields=%s", step, list(fields.keys()))
            logger.debug("Body: %s", resp.text[:500])
            break

        logger.debug("→ %d %s", resp.status_code, resp.url)

    # フォームループで取得できなかった場合、セッションCookieで /api/auth/ を試行
    logger.debug("POST /api/auth/ をセッションCookieで試行")
    resp = session.post(f"{base_url}/api/auth/")
    logger.debug("→ %d %s", resp.status_code, resp.text[:200])

    if resp.status_code == 200:
        token = resp.json().get("token")
        if token:
            logger.debug("JWT取得成功 (%d文字)", len(token))
            return token

    logger.error("JWTトークンの取得に失敗しました")
    return None


def refresh_token(client: httpx.Client, token: str) -> str | None:
    """POST /api/refresh/ でJWTトークンをリフレッシュする。"""
    logger.debug("POST %s/api/refresh/", client.base_url)
    resp = client.post("/api/refresh/", json={"token": token})
    logger.debug("→ %d %s", resp.status_code, resp.text[:500])

    if resp.status_code == 200:
        return resp.json().get("token")
    return None
