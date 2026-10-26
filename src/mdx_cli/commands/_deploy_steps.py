"""vm deploy で聞く項目。引数で渡されなかった項目だけを、Esc で戻れる手順（Step）として聞く。

引数で渡された値は従来どおり検証し、誤りなら終了する。対話で入れた値が使えないときは、
理由を出してその場で聞き直す。
"""

from dataclasses import dataclass
from pathlib import Path

import questionary
from questionary import Choice

from mdx_cli.commands._common import fail, prompt_int, select_from_list
from mdx_cli.commands._deploy_plan import DeployPlan
from mdx_cli.commands._name_pattern import expand_name_pattern, expand_name_pattern_for_deploy
from mdx_cli.commands._prompt_steps import Step, ask
from mdx_cli.console import console
from mdx_cli.models.pack import PACK_SPECS, pack_choice_label

# 公開鍵のプレビューで前後に見せる文字数
_KEY_PREVIEW_CHARS = 30


@dataclass(frozen=True)
class DeployOptions:
    """vm deploy の引数のうち、聞く項目に対応するもの（None なら対話で聞く）。"""
    template: str | None
    name: str | None
    pack_type: str | None
    pack_num: int | None
    disk: int | None
    service_level: str | None
    key: str | None
    power_on: bool
    yes: bool


@dataclass
class DeployAnswers:
    """引数と対話で集めた値。戻ったり直したりするときは、ここの値を初期値にする。"""
    template: object = None
    segment_uuid: str | None = None
    key_path: Path | None = None
    shared_key: str | None = None
    name_pattern: str | None = None
    pack_type: str | None = None
    pack_num: int | None = None
    disk_size: int | None = None
    service_level: str | None = None
    power_on: bool = False

    def to_plan(self) -> DeployPlan:
        return DeployPlan(
            template=self.template,
            segment_uuid=self.segment_uuid,
            name_pattern=self.name_pattern,
            disk_size=self.disk_size,
            pack_type=self.pack_type,
            pack_num=self.pack_num,
            service_level=self.service_level,
            shared_key=self.shared_key,
            power_on=self.power_on,
        )


def list_pubkeys() -> list[Path]:
    """~/.ssh にある公開鍵(.pub)の一覧を返す。標準的な鍵名を優先して並べる。"""
    ssh_dir = Path.home() / ".ssh"
    if not ssh_dir.is_dir():
        return []
    priority = {"id_ed25519.pub": 0, "id_rsa.pub": 1, "id_ecdsa.pub": 2}
    return sorted(
        ssh_dir.glob("*.pub"),
        key=lambda p: (priority.get(p.name, 99), p.name),
    )


def preview_key_text(content: str) -> str:
    """公開鍵の内容を、先頭と末尾だけ見せる形に縮める。"""
    if len(content) <= _KEY_PREVIEW_CHARS * 2 + 3:
        return content
    return f"{content[:_KEY_PREVIEW_CHARS]}...{content[-_KEY_PREVIEW_CHARS:]}"


def pubkey_preview(path: Path) -> str:
    """公開鍵ファイル内容のプレビュー。"""
    try:
        return preview_key_text(path.read_text().strip())
    except OSError:
        return "(読み取り不可)"


def _read_key(key_path: Path) -> str:
    """公開鍵を読む。使えないときは理由を ValueError で返す。"""
    if not key_path.is_absolute():
        raise ValueError("絶対パスまたは ~/... で指定してください")
    if not key_path.exists():
        raise ValueError(f"ファイルが見つかりません: {key_path}")
    return key_path.read_text().strip()


def _format_template(template) -> str:
    os_info = f" [cyan]{template.os_name or ''} {template.os_version or ''}[/cyan]" if template.os_name else ""
    gpu = " [red]GPU必須[/red]" if template.gpu_required else ""
    line = f"{template.name}{os_info}{gpu} [dim]disk≥{template.lower_limit_disk}GB[/dim]"
    if template.description:
        line += f"\n     [dim]{template.description}[/dim]"
    return line


def _print_name_expansion(pattern: str) -> None:
    """複数台になる名前パターンなら、展開結果の概要を表示する。"""
    vm_names = expand_name_pattern(pattern)
    deploy_patterns = expand_name_pattern_for_deploy(pattern)
    if len(vm_names) <= 1:
        return
    if len(deploy_patterns) < len(vm_names):
        console.print(
            f"  → {len(vm_names)}台 ({len(deploy_patterns)} リクエストにバッチ集約): "
            f"{vm_names[0]} 〜 {vm_names[-1]}"
        )
    else:
        console.print(f"  → {len(vm_names)}台: {vm_names[0]} 〜 {vm_names[-1]}")


def _default_number(items: list, value) -> int | None:
    return items.index(value) + 1 if value in items else None


class _DeployQuestions:
    """各項目を聞いて answers へ書き込む。前の答えを初期値にする。"""

    def __init__(self, answers: DeployAnswers, templates: list, segments: list) -> None:
        self.answers = answers
        self.templates = templates
        self.segments = segments

    def template(self) -> None:
        self.answers.template = select_from_list(
            self.templates, _format_template, title="テンプレート:",
            default=_default_number(self.templates, self.answers.template),
        )

    def segment(self) -> None:
        segment_uuids = [segment.uuid for segment in self.segments]
        self.answers.segment_uuid = select_from_list(
            self.segments, lambda segment: segment.name, title="セグメント:",
            default=_default_number(segment_uuids, self.answers.segment_uuid),
        ).uuid

    def ssh_key(self) -> None:
        console.print("\n[bold]SSH公開鍵[/bold]")
        pubkeys = list_pubkeys()
        if pubkeys:
            console.print("[dim]  ~/.ssh/ にある公開鍵:[/dim]")
            for i, path in enumerate(pubkeys, 1):
                console.print(f"  {i}) {path.name}")
                console.print(f"     [grey50]{pubkey_preview(path)}[/grey50]")
            console.print("[dim]  番号で選択、または絶対パス/~/... を直接入力[/dim]")
        else:
            console.print("[yellow]  警告: ~/.ssh/ に .pub ファイルが見つかりません[/yellow]")
            console.print("[dim]  絶対パスまたは ~/... で公開鍵のパスを指定してください[/dim]")

        previous = self.answers.key_path
        if previous in pubkeys:
            default = str(pubkeys.index(previous) + 1)
        else:
            default = str(previous) if previous else ("1" if pubkeys else "")
        while True:
            answer = ask(questionary.text("番号またはパス:" if pubkeys else "パス:", default=default)).strip()
            if answer.isdigit() and 1 <= int(answer) <= len(pubkeys):
                key_path = pubkeys[int(answer) - 1]
            else:
                key_path = Path(answer).expanduser()
            try:
                self.answers.shared_key = _read_key(key_path)
            except ValueError as exc:
                console.print(f"[red]{exc}[/red]")
                default = answer
                continue
            self.answers.key_path = key_path
            console.print(f"[green]{key_path.name} が選択されました[/green]")
            return

    def name_pattern(self) -> None:
        console.print("\n[bold]VM名[/bold]")
        console.print(
            "[dim]  パターンで一括作成: my-vm-{0-9} → 10台 (1リクエスト), "
            "name-{a-c}-{0-9} → 30台 (3リクエスト)[/dim]"
        )
        while True:
            pattern = ask(questionary.text("VM名:", default=self.answers.name_pattern or "")).strip()
            if pattern:
                break
            console.print("[yellow]VM名を入力してください[/yellow]")
        self.answers.name_pattern = pattern
        _print_name_expansion(pattern)

    def pack_type(self) -> None:
        self.answers.pack_type = ask(questionary.select(
            "パックタイプ:",
            choices=[Choice(pack_choice_label(pt), value=pt) for pt in PACK_SPECS],
            default=self.answers.pack_type,
        ))

    def pack_num(self) -> None:
        spec = PACK_SPECS[self.answers.pack_type]
        previous = self.answers.pack_num
        # パックタイプを変えて上限を超えた前の値は使わない
        default = previous if previous is not None and previous <= spec.max_num else spec.default_num
        self.answers.pack_num = prompt_int(
            f"パック数 (最大{spec.max_num}):", max_val=spec.max_num, default=str(default)
        )

    def disk_size(self) -> None:
        default = self.answers.disk_size or self.answers.template.lower_limit_disk
        self.answers.disk_size = prompt_int("ディスクサイズ(GB):", default=str(default))

    def service_level(self) -> None:
        self.answers.service_level = ask(questionary.select(
            "サービスレベル:",
            choices=[
                Choice("spot（低価格・中断あり）", value="spot"),
                Choice("guarantee（高価格・中断なし）", value="guarantee"),
            ],
            default=self.answers.service_level,
        ))

    def power_on(self) -> None:
        self.answers.power_on = ask(questionary.confirm(
            "デプロイ後に自動起動しますか？", default=self.answers.power_on
        ))


def build_deploy_steps(
    options: DeployOptions, answers: DeployAnswers, *, templates: list, segments: list
) -> list[Step]:
    """引数で渡された値を answers に入れ、渡されなかった項目を聞く手順を返す。"""
    questions = _DeployQuestions(answers, templates, segments)
    steps: list[Step] = []

    if options.template:
        matched = [t for t in templates if options.template.lower() in t.name.lower()]
        if not matched:
            fail(f"テンプレート '{options.template}' が見つかりません")
        answers.template = matched[0]
    else:
        if not templates:
            fail("テンプレートがありません")
        steps.append(Step("テンプレート", questions.template))

    if not segments:
        fail("セグメントがありません")
    if len(segments) == 1 or options.yes:
        answers.segment_uuid = segments[0].uuid
    else:
        steps.append(Step("セグメント", questions.segment))

    if options.key:
        answers.key_path = Path(options.key).expanduser()
        try:
            answers.shared_key = _read_key(answers.key_path)
        except ValueError as exc:
            fail(str(exc))
    else:
        steps.append(Step("SSH公開鍵", questions.ssh_key))

    if options.name:
        answers.name_pattern = options.name
        _print_name_expansion(options.name)
    else:
        steps.append(Step("VM名", questions.name_pattern))

    if options.pack_type:
        if options.pack_type not in PACK_SPECS:
            fail(f"不明なパックタイプです: {options.pack_type}（cpu / gpu）")
        answers.pack_type = options.pack_type
    else:
        steps.append(Step("パックタイプ", questions.pack_type))

    if options.pack_num is not None:
        answers.pack_num = options.pack_num  # 上限はパックタイプが決まってから check_pack_num で確かめる
    else:
        steps.append(Step("パック数", questions.pack_num))

    if options.disk is not None:
        answers.disk_size = options.disk
    else:
        steps.append(Step("ディスクサイズ", questions.disk_size))

    if options.service_level:
        answers.service_level = options.service_level
    else:
        steps.append(Step("サービスレベル", questions.service_level))

    answers.power_on = options.power_on
    if not options.power_on and not options.yes:
        steps.append(Step("自動起動", questions.power_on))

    return steps


def check_pack_num(answers: DeployAnswers) -> None:
    """引数で渡したパック数が、決まったパックタイプの上限に収まるか確かめる。"""
    spec = PACK_SPECS[answers.pack_type]
    if not 1 <= answers.pack_num <= spec.max_num:
        fail(f"パック数は 1〜{spec.max_num} の範囲で指定してください")


def print_deploy_summary(answers: DeployAnswers) -> None:
    plan = answers.to_plan()
    vm_names = plan.vm_names
    console.print("\n[bold]デプロイ内容:[/bold]")
    console.print(f"  テンプレート: {plan.template.name}")
    console.print(f"  ディスク:     {plan.disk_size}GB / {plan.pack_type} x {plan.pack_num} / {plan.service_level}")
    console.print(f"  自動起動:     {'あり' if plan.power_on else 'なし'}")
    console.print(f"  SSH公開鍵:    {answers.key_path.name}  [grey50]{preview_key_text(plan.shared_key)}[/grey50]")
    if len(vm_names) == 1:
        console.print(f"  VM名:         {vm_names[0]}")
    else:
        console.print(f"  VM数:         {len(vm_names)}台 ({vm_names[0]} 〜 {vm_names[-1]})")

