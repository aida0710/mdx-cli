"""Render the documentation using markdown-it-py (already in the dev environment)."""
from pathlib import Path
from html import escape
import json
import re
import shutil
import tomllib

from markdown_it import MarkdownIt

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'pages'
OUTPUT = SOURCE / '_site'
GROUPS = [
    ('はじめる', [('index', 'はじめに'), ('install', 'インストール'), ('auth', 'ログインと認証'), ('projects', 'プロジェクトと利用状況')]),
    ('使い方', [('vm', 'VMを操作する'), ('ssh', 'SSH接続'), ('network', 'ネットワーク'), ('templates', 'テンプレート'), ('tasks', 'タスクと操作履歴')]),
    ('リファレンス', [('settings', '出力・設定・シェル補完'), ('agent', 'AIエージェント連携'), ('troubleshooting', 'トラブルシューティング')]),
]
PAGES = [(group, slug, title) for group, items in GROUPS for slug, title in items]


def build():
    OUTPUT.mkdir(exist_ok=True)
    shutil.copytree(SOURCE / 'assets', OUTPUT / 'assets', dirs_exist_ok=True)
    (OUTPUT / '.nojekyll').touch()
    version = tomllib.loads((ROOT / 'pyproject.toml').read_text())['project']['version']
    md = MarkdownIt('commonmark', {'html': False}).enable('table')
    search = []
    for number, (group, slug, label) in enumerate(PAGES):
        source = (SOURCE / 'content' / f'{slug}.md').read_text()
        tokens = md.parse(source)
        toc = []
        for index, token in enumerate(tokens):
            if token.type == 'heading_open' and token.tag in ('h2', 'h3'):
                anchor = f'section-{len(toc) + 1}'
                token.attrSet('id', anchor)
                toc.append((anchor, tokens[index + 1].content, token.tag))
        body = md.renderer.render(tokens, md.options, {})
        body = re.sub(r'<table>.*?</table>', lambda m: '<div class="table-scroll" tabindex="0" role="region" aria-label="横スクロールできる表">' + m[0] + '</div>', body, flags=re.S)
        title = tokens[1].content
        nav = ''
        for name, items in GROUPS:
            nav += f'<div class="nav-group"><p>{name}</p>'
            for target, text in items:
                current = ' aria-current="page"' if target == slug else ''
                nav += f'<a href="{target}.html"{current}>{text}</a>'
            nav += '</div>'
        outline = ''.join(f'<a class="{level}" href="#{anchor}">{escape(text)}</a>' for anchor, text, level in toc)
        pager = ''
        for neighbor, caption in [(number - 1, '← 前のページ'), (number + 1, '次のページ →')]:
            if 0 <= neighbor < len(PAGES):
                _, target, text = PAGES[neighbor]
                pager += f'<a href="{target}.html"><span>{caption}</span><strong>{text}</strong></a>'
            else:
                pager += '<span></span>'
        page = f'''<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)} | mdx-cli ドキュメント</title>
<meta name="description" content="mdx-cli 非公式CLIツールの利用手引き。{escape(title)}。">
<link rel="icon" href="assets/favicon.svg" type="image/svg+xml"><link rel="stylesheet" href="assets/style.css">
<script src="assets/search-index.js" defer></script><script src="assets/app.js" defer></script></head>
<body><a class="skip" href="#main">本文へ移動</a>
<header class="header"><div class="header-inner">
<a href="index.html" class="brand" aria-label="mdx-cli はじめに"><span class="brand-mark" aria-hidden="true">›_</span><strong>mdx<span>-cli</span></strong></a>
<span class="header-divider"></span><span class="doc-label">ドキュメント</span><span class="badge">非公式</span>
<button class="search-trigger" aria-haspopup="dialog"><span>⌕ <span class="search-label">ドキュメントを検索</span></span><kbd>⌘ K</kbd></button>
<a class="github" href="https://github.com/aida0710/mdx-cli">GitHub ↗</a>
<button class="menu-button" aria-controls="navigation" aria-expanded="false" aria-label="メニューを開閉">☰</button>
</div></header>
<div class="layout"><aside class="sidebar" id="navigation"><nav aria-label="ドキュメント">{nav}</nav>
<div class="sidebar-bottom"><span class="version-dot"></span> v{version}<a href="https://github.com/aida0710/mdx-cli/releases">リリース ↗</a></div></aside>
<main id="main" tabindex="-1"><div class="breadcrumb">ドキュメント <span>/</span> {group}</div><article>{body}</article>
<nav class="pager" aria-label="前後のページ">{pager}</nav>
<footer><span>mdx-cli · 利用手引き</span><a href="https://github.com/aida0710/mdx-cli/blob/main/pages/content/{slug}.md">このページのソース ↗</a></footer>
</main><aside class="outline"><p>このページの内容</p><nav aria-label="ページ内目次">{outline}</nav><div class="official-link">mdx自体の仕様は<a href="https://docs.mdx.jp/ja/index.html">公式の利用手引き ↗</a></div></aside></div>
<dialog class="search-dialog" aria-labelledby="search-title"><div class="search-top"><label id="search-title" for="search-input">ドキュメントを検索</label><button class="search-close" aria-label="検索を閉じる">閉じる <kbd>Esc</kbd></button></div><input id="search-input" type="search" placeholder="例：SSH、OTP、VM、--json" autocomplete="off"><p id="search-status" role="status"></p><div id="search-results"></div><div class="search-hint">キーワードやコマンド名で、すべてのページを検索できます。</div></dialog>
<div id="copy-status" class="sr-only" role="status"></div></body></html>'''
        (OUTPUT / f'{slug}.html').write_text(page)
        search.append({'title': title, 'group': group, 'url': f'{slug}.html', 'text': source})
    (OUTPUT / 'assets' / 'search-index.js').write_text('window.DOC_SEARCH = ' + json.dumps(search, ensure_ascii=False) + ';\n')
    print(f'Built {len(PAGES)} pages → {OUTPUT}')


if __name__ == '__main__':
    build()
