# mdx-cli v2.0.0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** TOTP 自動入力と安全な単体バイナリ配布を完成させ、v2.0.0 を公開する。

**Architecture:** TOTP の生成を SSO のフォーム送信時まで遅延させ、登録経路は対話入力と stdin を使う非対話入力に分ける。インストーラは uv 管理下の entrypoint を保護し、checksum を必須化し、Windows 更新をロールバック可能にする。

**Tech Stack:** Python 3.13, Typer, httpx, questionary, cryptography, pytest, Ruff, POSIX sh, PowerShell, GitHub Actions, PyInstaller

**Spec:** `docs/superpowers/specs/2026-09-04-mdx-cli-v2-release-design.md`

## Global Constraints

- 新しいパッケージをインストールしない。既存の `.venv` を `uv run --no-sync` で使う。
- パスワード、TOTP シークレット、OTP を argv、環境変数、ログ、標準出力へ出さない。
- TOTP 非対話入力は `--non-interactive` と標準入力を使い、TTY からの平文入力を拒否する。
- checksum が確認できないバイナリは配置・実行しない。
- v2.0.0 のタグを公開する前に全テスト、lint、構文、バイナリ起動を検証する。

---

### Task 1: TOTP の検証と送信直前生成

**Files:**
- Modify: `src/mdx_cli/credentials/totp.py`
- Modify: `src/mdx_cli/api/endpoints/auth.py`
- Modify: `src/mdx_cli/commands/auth.py`
- Modify: `src/mdx_cli/api/client.py`
- Test: `tests/test_credentials/test_totp.py`
- Test: `tests/test_api/test_endpoints/test_auth.py`
- Test: `tests/test_commands/test_auth.py`
- Test: `tests/test_api/test_client.py`

**Interfaces:**
- Produces: `verify_totp(secret: str, code: str, at: float | None = None, window: int = 1) -> bool`
- Produces: `sso_login(..., otp: str | Callable[[], str], ...) -> str | None`
- Consumes: `otp_from_store(store, username) -> str | None`

- [x] **Step 1:** `verify_totp`、壊れた保存値のフォールバック、provider の遅延呼び出しを示すテストを書く。
- [x] **Step 2:** `uv run --no-sync pytest` で新規テストが期待どおり失敗することを確認する。
- [x] **Step 3:** 定時間比較、例外フォールバック、SSOフォーム内provider呼び出しを最小実装する。
- [x] **Step 4:** 対象テストを再実行し、成功を確認する。

### Task 2: Web/IPMI向け非対話登録とOTP非表示化

**Files:**
- Modify: `src/mdx_cli/commands/auth.py`
- Modify: `README.md`
- Test: `tests/test_commands/test_auth.py`

**Interfaces:**
- Produces: `mdx auth otp --non-interactive`
- Consumes: stdin の先頭行にある Base32 シークレット

- [x] **Step 1:** TTY拒否、stdin登録、非対話削除、対話コード照合、OTP非表示のテストを書く。
- [x] **Step 2:** 対象テストが未実装理由で失敗することを確認する。
- [x] **Step 3:** `--non-interactive` と対話検証を実装する。
- [x] **Step 4:** 対象テストを再実行し、成功を確認する。

### Task 3: uv移行ガードとchecksum必須化

**Files:**
- Modify: `install.sh`
- Modify: `install.ps1`
- Modify: `README.md`
- Modify: `tests/test_docs.py`

**Interfaces:**
- Produces: uv tool receipt 検出時に変更前終了するインストーラ
- Produces: `checksums.txt` を検証できた場合だけ配置するインストーラ

- [x] **Step 1:** uv移行案内、checksum fail-closed、Windowsロールバックを要求するテストを書く。
- [x] **Step 2:** テストが現行スクリプトに対して失敗することを確認する。
- [x] **Step 3:** 両インストーラとREADMEの移行手順を修正する。
- [x] **Step 4:** pytest、`sh -n`、PowerShell parserを実行する。

### Task 4: v2.0.0リリースゲート

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/mdx_cli/__init__.py`
- Modify: `.github/workflows/release.yml`
- Modify: `CLAUDE.md`
- Modify: `README.md`
- Test: `tests/test_docs.py`
- Test: `tests/test_main.py`

**Interfaces:**
- Produces: `mdx --version` = `2.0.0`
- Produces: `v2.0.0` tagのみ公開できるrelease gate

- [x] **Step 1:** バージョンとworkflow検査のテストを追加・更新する。
- [x] **Step 2:** 2.0.0へ更新して対象テストを通す。
- [x] **Step 3:** workflowでpytestとRuffをビルド前に実行する。
- [x] **Step 4:** 全テスト、lint、diff check、両スクリプト構文、PyInstaller起動を検証する。

### Task 5: コミットと公開

**Files:**
- Commit: 上記すべて

- [x] **Step 1:** `git diff` と `git status` で意図した変更だけであることを確認する。
- [ ] **Step 2:** v2.0.0リリースとしてコミットし、annotated tag `v2.0.0` を作成してpushする。
- [ ] **Step 3:** Release資産が公開された後、`main` をpushする。
- [ ] **Step 4:** GitHub Actions完了とRelease資産を確認する。
- [ ] **Step 5:** checksumを使うインストーラを一時ディレクトリで実行し、`mdx --version` が2.0.0になることを確認する。
