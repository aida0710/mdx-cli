"""VM名のパターン展開とマッチング

展開（デプロイ用）:
  {0-9}    → 0, 1, 2, ..., 9
  {a-g}    → a, b, c, ..., g
  {00-05}  → 00, 01, 02, 03, 04, 05（ゼロ埋め）

マッチング（一括操作用）:
  crawler-*        → glob パターン
  crawler-{a-c}-*  → {range} を展開してからglobマッチ
"""

import fnmatch
import itertools
import re


def _expand_range(match: str) -> list[str]:
    """単一の {start-end} を展開する。"""
    inner = match[1:-1]  # { } を除去
    parts = inner.split("-", 1)
    if len(parts) != 2:
        return [match]

    start, end = parts[0], parts[1]

    # 数値範囲
    if start.isdigit() and end.isdigit():
        width = len(start)  # ゼロ埋め幅
        return [str(i).zfill(width) for i in range(int(start), int(end) + 1)]

    # アルファベット範囲
    if len(start) == 1 and len(end) == 1 and start.isalpha() and end.isalpha():
        return [chr(c) for c in range(ord(start), ord(end) + 1)]

    return [match]


def expand_name_pattern(pattern: str) -> list[str]:
    """パターンを展開してVM名のリストを返す。

    パターンがなければ単一要素のリストを返す。
    """
    # {..} を全て見つける
    ranges = re.findall(r"\{[^}]+\}", pattern)
    if not ranges:
        return [pattern]

    # 各範囲を展開
    expanded = [_expand_range(r) for r in ranges]

    # 全組み合わせを生成
    names = []
    for combo in itertools.product(*expanded):
        name = pattern
        for original, replacement in zip(ranges, combo):
            name = name.replace(original, replacement, 1)
        names.append(name)

    return names


def _expand_range_for_deploy(match: str) -> list[str]:
    """deploy API 用に {start-end} を展開する。

    MDX deploy API は vm_name の [N-M] 範囲記法をサーバー側で展開するが、
    対応は単一桁数値（0-9）のみ。それ以外はクライアント側で展開する。
    """
    inner = match[1:-1]
    parts = inner.split("-", 1)
    if len(parts) != 2:
        return [match]

    start, end = parts[0], parts[1]

    # 単一桁数値範囲はAPI記法を維持（API側で展開させる）
    if (
        len(start) == 1
        and len(end) == 1
        and start.isdigit()
        and end.isdigit()
    ):
        return [f"[{start}-{end}]"]

    # それ以外はクライアント側で展開（既存ロジックと同じ）
    return _expand_range(match)


def expand_name_pattern_for_deploy(pattern: str) -> list[str]:
    """deploy API 用にパターンを展開する。

    単一桁数値範囲（{0-9} 等）は [0-9] のまま残してAPIに展開を任せる。
    アルファベット・複数桁・ゼロ埋めはクライアント側で展開する。
    """
    ranges = re.findall(r"\{[^}]+\}", pattern)
    if not ranges:
        return [pattern]

    expanded = [_expand_range_for_deploy(r) for r in ranges]

    names = []
    for combo in itertools.product(*expanded):
        name = pattern
        for original, replacement in zip(ranges, combo):
            name = name.replace(original, replacement, 1)
        names.append(name)

    return names


def match_names(pattern: str, names: list[str]) -> list[str]:
    """パターンに一致する名前をフィルタする。

    1. {range} があれば展開して完全一致
    2. * があれば glob マッチ
    3. どちらもなければ完全一致
    """
    # {range} パターンを含む場合は展開して完全一致セット
    if "{" in pattern and "}" in pattern:
        expanded = set(expand_name_pattern(pattern))
        # 展開結果に * が含まれていればglob
        if any("*" in e for e in expanded):
            matched = []
            for e in expanded:
                matched.extend(n for n in names if fnmatch.fnmatch(n, e))
            return sorted(set(matched))
        return [n for n in names if n in expanded]

    # glob パターン
    if "*" in pattern or "?" in pattern:
        return [n for n in names if fnmatch.fnmatch(n, pattern)]

    # 完全一致
    return [n for n in names if n == pattern]


def is_name_pattern(text: str) -> bool:
    """match_names() がパターンとして扱う記号（*・?・{範囲}）を含むか。"""
    return "*" in text or "?" in text or ("{" in text and "}" in text)


# 対象パターンの可変部分: {範囲}・?・*。match_names() が扱う記号と同じ
_WILDCARD_TOKEN = re.compile(r"\{[^}]+\}|\?|\*")


def count_wildcards(target_pattern: str) -> int:
    """対象パターンの可変部分（{範囲}・?・*）の数。新しい名前に書く * の数と揃える。"""
    return len(_WILDCARD_TOKEN.findall(target_pattern))


def _wildcard_regex(target_pattern: str) -> str:
    """対象パターンの可変部分を、左から順に取り出すグループにした正規表現を作る。"""
    parts = []
    position = 0
    for token in _WILDCARD_TOKEN.finditer(target_pattern):
        parts.append(re.escape(target_pattern[position:token.start()]))
        text = token.group()
        if text == "*":
            parts.append("(.*?)")  # 複数の * は左から短く取る
        elif text == "?":
            parts.append("(.)")
        else:
            parts.append("(" + "|".join(re.escape(value) for value in _expand_range(text)) + ")")
        position = token.end()
    parts.append(re.escape(target_pattern[position:]))
    return "".join(parts)


def rename_by_wildcards(target_pattern: str, name: str, new_pattern: str) -> str:
    """新しい名前の * に、対象パターンの可変部分（{範囲}・?・*）に当たった name の部分を左から順に入れる。

    対象が名前そのもの（可変部分なし）なら、* は今の名前全体を表す。
    例: ("crawler-*", "crawler-01", "yt-*") → "yt-01"、("crawler-01", "crawler-01", "*-old") → "crawler-01-old"
    """
    matched = re.fullmatch(_wildcard_regex(target_pattern), name)
    if matched is None:
        raise ValueError(f"{name} は '{target_pattern}' に一致しません")
    captured = matched.groups()
    if not captured:
        return new_pattern.replace("*", name)

    star_count = new_pattern.count("*")
    if star_count != len(captured):
        example = "・".join(f"'{part}'" for part in captured)
        raise ValueError(
            f"対象 '{target_pattern}' には可変部分が{len(captured)}か所あります（{name} なら {example}）。"
            f"新しい名前にも * を{len(captured)}つ書いてください（今は{star_count}つ）"
        )
    pieces = new_pattern.split("*")
    return pieces[0] + "".join(part + rest for part, rest in zip(captured, pieces[1:]))
