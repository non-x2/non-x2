#!/usr/bin/env python3
"""🗺 CLAUDE.md の「ディレクトリ構成」と、実際のフォルダの中身がそろっているか照合する見張り番。

■ なぜ必要か
CLAUDE.md の構成表は、新しいセッションが毎回いちばん最初に読む「のんラボの地図」。
ところがファイルを新しく作ったとき、この表に書き足すのを**忘れやすい**
（2026-09-10 に道具3つの抜けが同時に見つかった＝自己改良バックログの候補28・29／
  2026-09-25 には自動実行 `a11y-check.yml` が**25日間**載っていないのが見つかった＝候補43）。
地図に載っていないものは、次のセッションから見えない＝使われないままになる。
この道具は「実際にあるファイル」と「地図に書かれている行」を突き合わせて、
どちらかにしか無いものを知らせる。

■ 見張っているフォルダ（下の TARGETS に1つ足すだけで増やせる）
    tools/               … 小さな道具箱（.py / .js）
    .github/workflows/   … 自動で動くもの（.yml / .yaml）
    .claude/skills/      … 型（スキル）。中身がファイルではなく**フォルダ**なので
                            `kind: "dir"` を付ける（2026-10-07 追加＝候補30の残り）

■ もう1つの地図も見張る（2026-10-01 追加＝自己改良バックログの候補47）
`docs/README.md`（📚 docsの歩き方）も、docsフォルダの中身を手で書き写した「地図」。
2026-09-27 に見たときは作業ログ7枚が抜け、「最新」の案内が47日前のままだった。
そこで下の3つを照合する（材料はファイル名だけ＝中身も通信も要らない）。
    ① ガイド・手順書が目次に載っているか（作ったあとの書き足し忘れ）
    ② 省略の線引き（「それより古いもの(◯◯ 以前)は…」）より新しい作業ログが全部載っているか
    ③ 「🚀 まず読むもの」が最新と呼んでいる作業ログが、本当にいちばん新しい日付か

■ 身内どうしのリンクも見張る（2026-10-12 追加＝自己改良バックログの候補39）
文書の中の「[こちら](docs/○○.md)」の形のリンクは、ファイルを引っ越したり
名前を変えたりすると**黙って切れる**（押しても何も出ない）。
外のサイトへのリンクは `tools/check_links.py` が見張っているが、
のんラボの中どうしのリンクは誰も見ていなかった。そこで全Markdownを読んで、
リンク先の実物があるか確かめる（材料は手元のファイル名だけ＝通信は要らない）。
※ `docs/◯◯.md` や `作業ログ_....md` のような**書き方の見本**は、実物が無くて
   当たり前なので数えない（◯・○・…・* が入っているリンク先は見本とみなす）。

■ 🌐 公開ページどうしのリンクも見張る（2026-10-13 追加＝自己改良バックログの候補75）
Markdownの身内リンクは上で見張れるようになったが、**HTMLの `href` / `src`** は
まだ誰も見ていなかった。入口ページ `index.html` は公開4ページへのリンクを持っていて、
フォルダ名が変わると**公開サイトでいちばん目立つ場所がリンク切れ**になる。
そこで「Webに出しているページ」の中のリンクだけを拾って、次の3つを確かめる。
    ① 行き先の実物があるか（引っ越し・名前変えのあとの書き替え忘れ）
    ② フォルダを指すリンク（例：`../world-livecam/`）の中に `index.html` があるか
       （無いとWebでは真っ白になる。手元でファイルを開くぶんには気づけない）
    ③ 行き先が**Webに公開している範囲の中**か（手元にはあるのに公開していない
       `docs/` などを指していると、公開サイトだけで404になる）
※ どのページを見張るかは `.github/workflows/pages-deploy.yml` の `cp` の行
   （＝実際にWebへ出している一覧そのもの）から読むので、公開ページが増えても
   この道具を直す必要はない。外のサイトへのリンクは `tools/check_links.py` の担当。

■ 🧭 公開ページの「一覧を持つ文書」も見張る（2026-10-14 追加＝自己改良バックログの候補51）
公開ページの一覧は**4つの文書**（表紙 `README.md`・入口ページ `index.html`・
`docs/クラウドとローカルの使い分け.md`・この `CLAUDE.md`）が別々に持っている。
そのためページが増えるたびに、このうちどれか1つが必ず書き漏れていた
（2026-09-25＝表紙に公開4ページが1行も無い／2026-09-28＝入口ページがカナダBC州ぶんを
  40日間欠落／2026-09-30＝使い分けガイドが45日間3ページのまま）。
そこで「`pages-deploy.yml` が実際に配っているページ」が、4つの文書すべてに
出てくるかを照合する（材料は文字列だけ＝通信も要らない）。
※ **どの文書が一覧を持っているか**だけは手で書いている（機械には決められないため）。
   そこは増えることが少ないうえ、下の DOC_LIST に1行足すだけで増やせる。
※ 照合は「ページのフォルダ名が、その文書の中に出てくるか」という素朴な方法。
   別の用途でその名前が出ているだけでも ✅ になる（＝見落としはあり得るが、
   嘘の ❌ は出さない安全側の作り）。

■ 使い方
    python3 tools/check_map.py
    npm run check:map          （同じもの）

■ 出力例（◯には実際の個数、日付には実際の日付が入る）
    ✅ tools/ の◯個の道具は、すべてCLAUDE.mdの構成表に載っています。
    ✅ .github/workflows/ の◯枚の自動実行は、すべてCLAUDE.mdの構成表に載っています。
    ✅ .claude/skills/ の◯つの型（スキル）は、すべてCLAUDE.mdの構成表に載っています。
    ✅ docs/ の◯枚の文書は、すべて docs/README.md の目次に載っています（最新の作業ログの案内も ◯◯◯◯-◯◯-◯◯ で合っています）。
    ✅ Markdown ◯枚の中の内部リンク◯本は、すべて実物にたどり着けます。
    ✅ 公開ページ◯枚の中のリンク◯本は、すべて公開しているファイルにたどり着けます。
    ✅ 公開ページ◯つは、一覧を持つ◯つの文書すべてに載っています。

ズレていたときは、足りない側を ❌ で並べて表示し、終了コード1で終わる。
※ 直すのは人の仕事（この道具はCLAUDE.mdを書き換えない）。地図の説明文は
   「何をする道具か」を日本語で書くところなので、機械には書けないため。
※ 見張れるのは「**行があるか無いか**」だけ。説明文の中身（例：自動実行の周期を
   「毎週月曜」→「毎日」に変えたときの書き替え漏れ）までは判定できない。

外部のライブラリは使いません（Python 3 の標準機能だけ）。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CLAUDE_MD = REPO_ROOT / "CLAUDE.md"
DOCS_DIR = REPO_ROOT / "docs"
DOCS_INDEX = DOCS_DIR / "README.md"

# 見張る対象。新しいフォルダを足したいときは、この list に1つ書き足すだけ。
#   path     : 実物のフォルダ（リポジトリの根っこから見た場所）
#   suffixes : 地図に載せる対象の拡張子（README などを除くため。kind="dir" のときは不要）
#   unit     : 報告文の数え方（「10個の道具」「9枚の自動実行」「7つの型（スキル）」）
#   kind     : "file"（既定）＝中身はファイル／"dir"＝中身はフォルダ
#   label    : 構成表に書かれているつづり（既定は path と同じ）。
#              構成表が入れ子になっていて途中のフォルダ名だけが書かれているときに使う
#              （例：`.claude/skills` は構成表では `│   └── skills/` と1段下がって書かれている）
TARGETS = [
    {"path": "tools", "suffixes": (".py", ".js"), "unit": "個の道具"},
    {"path": ".github/workflows", "suffixes": (".yml", ".yaml"), "unit": "枚の自動実行"},
    {"path": ".claude/skills", "unit": "つの型（スキル）", "kind": "dir", "label": "skills"},
]

# 構成表の1行から名前を取り出す（例: "│   ├── check_offices.py   #    👀 ..." → "check_offices.py"）
ENTRY_RE = re.compile(r"^│\s+[├└]──\s+(\S+)")

# docs/README.md の照合に使うもの
# 「[作業ログ_2026-08-22.md](作業ログ_2026-08-22.md)」のような同じフォルダ内へのリンク先だけを拾う。
# `/` と `:` を除いているので、よそのフォルダ（`docs/○○.md`）や外部のURL（`https://…`）は拾わない。
# 「○○.md#見出し」のように見出しへ飛ばすリンクも、ファイル名のぶんだけ拾う。
DOCS_LINK_RE = re.compile(r"\]\(([^)/:#]+\.md)(?:#[^)]*)?\)")
WORKLOG_RE = re.compile(r"^作業ログ_(\d{4}-\d{2}-\d{2})\.md$")
# 全Markdownの内部リンク照合に使うもの（2026-10-12 追加＝自己改良バックログの候補39）
# 「[こちら](docs/○○.md)」の形から、リンク先のファイル名だけを拾う（見出し `#…` は切り落とす）。
MD_LINK_RE = re.compile(r"\]\((?!https?://|mailto:)([^)\s]+?\.md)(?:#[^)]*)?\)")
# 読みに行かないフォルダ（Gitの内部・取ってきただけの部品置き場）
SKIP_DIR_NAMES = {".git", "node_modules", ".venv", "__pycache__"}
# リンク先が「実在するファイル」ではなく**書き方の見本**のときの目印。
# 例：`docs/◯◯.md`（アイデア帳）／`作業ログ_....md`（/handoffの型）。
# これを除かないと、健全なのに3件ズレたと誤報する（2026-09-21 の手計測でも同じ3件だった）。
PLACEHOLDER_MARKS = ("◯", "○", "〇", "…", "...", "*")

# 🌐 公開ページ（HTML）のリンク照合に使うもの（2026-10-13 追加＝自己改良バックログの候補75）
# 「href="../world-livecam/"」「src="data/livecams.json"」の形から、行き先だけを拾う。
HTML_LINK_RE = re.compile(r'(?:href|src)\s*=\s*"([^"]+)"')
# この道具の担当ではない行き先。
#   https://… ・mailto: → 外のサイト（`tools/check_links.py` が見張っている）
#   #tab-map             → 同じページの中のしるしへ飛ぶだけ（ファイルではない）
OUTSIDE_LINK_RE = re.compile(r"^(?:https?:|mailto:|tel:|data:|javascript:|//|#)")
# Webに出しているものを決めている大もと（この中の `cp` の行が公開の一覧そのもの）
PAGES_DEPLOY = REPO_ROOT / ".github/workflows/pages-deploy.yml"
PUBLISH_RE = re.compile(r"^\s*cp\s+(?:-r\s+)?(\S+)\s+_site/", re.MULTILINE)

# 🧭 公開ページの一覧を持っている文書（2026-10-14 追加＝自己改良バックログの候補51）
# ここだけは手で書いている（「一覧を持っているか」は機械には決められないため）。
# 増えたときは1行足すだけ。※ ページそのものの一覧は pages-deploy.yml から読む。
DOC_LIST = [
    ("README.md", "表紙"),
    ("index.html", "入口ページ"),
    ("docs/クラウドとローカルの使い分け.md", "使い分けガイド"),
    ("CLAUDE.md", "この案内"),
]

# 「それより古いもの(2026-08-01 以前)はファイル一覧から探してください。」の線引きの日付
CUTOFF_RE = re.compile(r"それより古いもの[（(](\d{4}-\d{2}-\d{2})\s*以前[）)]")


def read_actual(target: dict) -> set[str]:
    """実際にそのフォルダにある中身（ファイル名、またはフォルダ名）を集める。"""
    folder = REPO_ROOT / target["path"]
    if target.get("kind") == "dir":
        # 中身がフォルダのとき（例：.claude/skills/ の各スキル）。
        # 「.」で始まるもの（.git など隠しフォルダ）は地図に載せない約束なので数えない。
        return {
            path.name
            for path in folder.iterdir()
            if path.is_dir() and not path.name.startswith(".")
        }
    return {
        path.name
        for path in folder.iterdir()
        if path.is_file() and path.suffix in target["suffixes"]
    }


def read_mapped(target: dict, lines: list[str]) -> set[str] | None:
    """CLAUDE.md の構成表の、そのフォルダの中に書かれているファイル名を集める。

    構成表にそのフォルダの行が無いときは None を返す（呼び出し側でエラーにする）。
    """
    # 「├── tools/」「│   └── skills/」のような、このフォルダが始まる行を探す
    # （ここから下が中身。入れ子になっていて左に「│」が並ぶ形にも対応する）
    label = target.get("label", target["path"])
    start_re = re.compile(r"^[│\s]*[├└]──\s+" + re.escape(label) + r"/")
    start = None
    for i, line in enumerate(lines):
        if start_re.match(line):
            start = i + 1
            break
    if start is None:
        return None

    names: set[str] = set()
    depth = None   # このフォルダの「中身」の字下がり（＝名前が始まる位置）
    for line in lines[start:]:
        # 「│」で始まらなくなったら、このフォルダの中身は終わり（いちばん外側に戻った）
        if not line.startswith("│"):
            break
        matched = ENTRY_RE.match(line)
        if not matched:
            continue
        indent = matched.start(1)
        if depth is None:
            depth = indent
        elif indent < depth:
            break      # 字下がりが浅くなった＝親のフォルダに戻ったので終わり
        elif indent > depth:
            continue   # もっと深い階層（孫）は、このフォルダの中身として数えない
        # フォルダは「skills/」のように末尾に「/」が付いているので外して比べる
        names.add(matched.group(1).rstrip("/"))
    return names


def check(target: dict, lines: list[str]) -> bool:
    """1つのフォルダを照合する。そろっていれば True。"""
    folder = target["path"]
    actual = read_actual(target)
    mapped = read_mapped(target, lines)

    if mapped is None:
        print(f"❌ CLAUDE.md の構成表に「{folder}/」の行が見つかりません。")
        return False

    missing = sorted(actual - mapped)   # 実物はあるのに地図に無い
    ghosts = sorted(mapped - actual)    # 地図にあるのに実物が無い

    if not missing and not ghosts:
        print(f"✅ {folder}/ の{len(actual)}{target['unit']}は、すべてCLAUDE.mdの構成表に載っています。")
        return True

    for name in missing:
        print(f"❌ {folder}/{name} が CLAUDE.md の構成表に載っていません（作ったあとの書き足し忘れ）")
    for name in ghosts:
        print(f"❌ CLAUDE.md の構成表にある {folder}/{name} が実際には見つかりません（消したあとの消し忘れ）")
    return False


def _newest_worklog_in_section(index_text: str, heading: str) -> str | None:
    """見出し（例：「🚀 まず読むもの」）の中にある作業ログの日付を返す。無ければ None。"""
    inside = False
    for line in index_text.splitlines():
        if line.startswith("## "):
            inside = heading in line     # 見出しに来たら「この中か」を入れ替える
            continue
        if not inside:
            continue
        for name in DOCS_LINK_RE.findall(line):
            matched = WORKLOG_RE.match(name)
            if matched:
                return matched.group(1)
    return None


def check_docs_index() -> bool:
    """docs/ の中身と docs/README.md（📚 docsの歩き方）の目次を照合する。

    作業ログは数が多いので、目次には「ある日付より新しいぶんだけ」を並べて、
    それより古いものは省略する約束になっている。その線引きの一文を読み取って、
    「省略してよい作業ログ」と「載っていないといけない作業ログ」を分ける。
    """
    if not DOCS_INDEX.exists():
        print("❌ docs/README.md（docsの歩き方）が見つかりません。")
        return False

    index_text = DOCS_INDEX.read_text(encoding="utf-8")
    # 目次が目次自身（README.md）を指していても「案内し忘れ」の話ではないので、両方から外しておく
    linked = set(DOCS_LINK_RE.findall(index_text)) - {"README.md"}
    actual = {path.name for path in DOCS_DIR.glob("*.md")} - {"README.md"}

    worklogs = {name for name in actual if WORKLOG_RE.match(name)}
    guides = actual - worklogs
    problems: list[str] = []

    # ① ガイド・手順書（作業ログ以外）は全部が目次に載っていないといけない
    for name in sorted(guides - linked):
        problems.append(
            f"❌ docs/{name} が docs/README.md の目次に載っていません（作ったあとの書き足し忘れ）"
        )

    # 目次にあるのに実物が無いもの（消したあとの消し忘れ・ファイル名の打ち間違い）
    for name in sorted(linked - actual):
        problems.append(
            f"❌ docs/README.md の目次にある {name} が docs/ に見つかりません（消したあとの消し忘れ）"
        )

    # ② 省略の線引きより新しい作業ログは、全部が「📝 作業ログ(新しい順)」に並んでいないといけない
    cutoff_matched = CUTOFF_RE.search(index_text)
    if cutoff_matched is None:
        problems.append(
            "❌ docs/README.md に「それより古いもの(◯◯◯◯-◯◯-◯◯ 以前)は…」の省略の線引きが見つかりません"
            "（どこから省略してよいのか機械が判断できません）"
        )
    else:
        cutoff = cutoff_matched.group(1)
        for name in sorted(worklogs - linked, reverse=True):
            if WORKLOG_RE.match(name).group(1) > cutoff:
                problems.append(
                    f"❌ docs/{name} が docs/README.md の作業ログ一覧に載っていません"
                    f"（省略してよいのは {cutoff} 以前のぶんだけです）"
                )

    # ③ 「🚀 まず読むもの」が最新と呼んでいる作業ログが、本当にいちばん新しい日付か
    newest = max((WORKLOG_RE.match(n).group(1) for n in worklogs), default=None)
    introduced = _newest_worklog_in_section(index_text, "まず読むもの")

    if newest is None:
        problems.append("❌ docs/ に作業ログ（作業ログ_YYYY-MM-DD.md）が1枚もありません。")
    elif introduced is None:
        problems.append(
            "❌ docs/README.md の「🚀 まず読むもの」に、最新の作業ログへの案内が見つかりません。"
        )
    elif introduced != newest:
        problems.append(
            f"❌ docs/README.md の「🚀 まず読むもの」が案内しているのは {introduced} ですが、"
            f"いちばん新しい作業ログは {newest} です（新しいログを足したあとの差し替え忘れ）"
        )

    if problems:
        for problem in problems:
            print(problem)
        return False

    print(
        f"✅ docs/ の{len(actual)}枚の文書は、すべて docs/README.md の目次に載っています"
        f"（最新の作業ログの案内も {newest} で合っています）。"
    )
    return True


def _markdown_files() -> list[Path]:
    """リポジトリの中のMarkdownを全部集める（Gitの内部や部品置き場は見ない）。"""
    found = []
    for path in sorted(REPO_ROOT.rglob("*.md")):
        if any(part in SKIP_DIR_NAMES for part in path.relative_to(REPO_ROOT).parts):
            continue
        found.append(path)
    return found


def check_md_links() -> bool:
    """Markdownどうしの内部リンクが、ちゃんと実物にたどり着けるか照合する。

    文書の中の「[こちら](docs/○○.md)」は、ファイルを引っ越したり名前を変えたりすると
    黙って切れる（押しても何も出ない）。外のサイトへのリンクは
    `tools/check_links.py` が見張っているが、**身内どうしのリンク**は誰も見ていなかった。
    材料は手元のファイル名だけなので、通信は要らない。
    """
    files = _markdown_files()
    total = 0
    problems: list[str] = []

    for path in files:
        text = path.read_text(encoding="utf-8")
        here = path.relative_to(REPO_ROOT)
        for target in MD_LINK_RE.findall(text):
            if any(mark in target for mark in PLACEHOLDER_MARKS):
                continue  # 書き方の見本なので、実物が無くて当たり前
            total += 1
            if target.startswith("/"):
                destination = REPO_ROOT / target.lstrip("/")
            else:
                destination = path.parent / target
            if not destination.exists():
                problems.append(
                    f"❌ {here} のリンク先 {target} が見つかりません"
                    "（引っ越し・名前変えのあとの書き替え忘れ）"
                )

    if problems:
        for problem in problems:
            print(problem)
        return False

    print(
        f"✅ Markdown {len(files)}枚の中の内部リンク{total}本は、すべて実物にたどり着けます。"
    )
    return True


def _published_paths() -> list[Path]:
    """Webに出しているファイル・フォルダの一覧を pages-deploy.yml から読む。

    手で書き写した一覧を持つと、ページが増えたときに必ず置いていかれる
    （＝アイデア帳の候補51と同じワナ）。実際に公開を実行している
    ワークフローの `cp` の行をそのまま材料にするので、ページが増えても
    この道具を直す必要はない。
    """
    text = PAGES_DEPLOY.read_text(encoding="utf-8")
    return [REPO_ROOT / name for name in PUBLISH_RE.findall(text)]


def _is_published(path: Path, published: list[Path]) -> bool:
    """その行き先が「Webに出している範囲の中」かどうか。"""
    if path == REPO_ROOT:
        return True  # 根っこは入口ページ（index.html）として公開している
    for entry in published:
        if path == entry or entry in path.parents:
            return True
    return False


def check_html_links() -> bool:
    """公開ページ（HTML）の中のリンクが、公開しているファイルにたどり着けるか照合する。

    入口ページ `index.html` は公開4ページへのリンクを持っているので、フォルダ名が
    変わると**公開サイトでいちばん目立つ場所がリンク切れ**になる。外のサイトは
    `tools/check_links.py`、文書どうしは `check_md_links()` が見張っているので、
    残っていた隙間がここ。材料は手元のファイル名だけ＝通信は要らない。
    """
    published = _published_paths()
    pages = sorted(
        page
        for entry in published
        for page in ([entry] if entry.suffix == ".html" else entry.rglob("*.html"))
    )
    total = 0
    problems: list[str] = []

    for page in pages:
        here = page.relative_to(REPO_ROOT)
        for raw in HTML_LINK_RE.findall(page.read_text(encoding="utf-8")):
            if OUTSIDE_LINK_RE.match(raw):
                continue  # 外のサイト／同じページの中のしるし＝この道具の担当ではない
            total += 1
            target = raw.split("#")[0].split("?")[0]
            if target.startswith("/"):
                destination = REPO_ROOT / target.lstrip("/")
            else:
                destination = page.parent / target
            destination = destination.resolve()

            if destination.is_dir():
                # フォルダを指すリンク（例：../world-livecam/）は、中の index.html が
                # 表示される。無いとWebでは真っ白（手元でファイルを開くと気づけない）。
                if not (destination / "index.html").exists():
                    problems.append(
                        f"❌ {here} のリンク先 {raw} に index.html がありません"
                        "（Webでは真っ白になります）"
                    )
                    continue
            elif not destination.exists():
                problems.append(
                    f"❌ {here} のリンク先 {raw} が見つかりません"
                    "（引っ越し・名前変えのあとの書き替え忘れ）"
                )
                continue

            if not _is_published(destination, published):
                problems.append(
                    f"❌ {here} のリンク先 {raw} は、手元にはあるのにWebへ公開していない場所です"
                    "（公開ページからは開けません）"
                )

    if problems:
        for problem in problems:
            print(problem)
        return False

    print(
        f"✅ 公開ページ{len(pages)}枚の中のリンク{total}本は、"
        "すべて公開しているファイルにたどり着けます。"
    )
    return True


def check_page_lists() -> bool:
    """公開ページの一覧を持つ文書に、いまWebへ出しているページが全部載っているか照合する。

    一覧を**4つの文書が別々に持っている**ので、ページが増えるたびに
    どれか1つが必ず書き漏れていた（2026-09-25・09-28・09-30 の3回）。
    ページの一覧は `pages-deploy.yml`（＝実際に配っているもの）から読むので、
    ページが増えてもこの道具を直す必要はない。
    """
    # 入口ページ（根っこの index.html）そのものは「一覧に載せる相手」ではないので外す。
    pages = [entry.name for entry in _published_paths() if entry.is_dir()]
    problems: list[str] = []

    for path_text, label in DOC_LIST:
        doc = REPO_ROOT / path_text
        if not doc.exists():
            problems.append(f"❌ {label}（{path_text}）が見つかりません（引っ越し・名前変え？）")
            continue
        text = doc.read_text(encoding="utf-8")
        missing = [name for name in pages if name not in text]
        if missing:
            problems.append(
                f"❌ {label}（{path_text}）に {'・'.join(missing)} の案内がありません"
                "（ページを増やしたときの書き足し忘れ）"
            )

    if problems:
        for problem in problems:
            print(problem)
        return False

    print(
        f"✅ 公開ページ{len(pages)}つは、一覧を持つ{len(DOC_LIST)}つの文書すべてに載っています。"
    )
    return True


def main() -> int:
    lines = CLAUDE_MD.read_text(encoding="utf-8").splitlines()

    results = [check(target, lines) for target in TARGETS]
    docs_ok = check_docs_index()
    links_ok = check_md_links()
    html_ok = check_html_links()
    pages_ok = check_page_lists()

    if all(results) and docs_ok and links_ok and html_ok and pages_ok:
        return 0

    ng = [t["path"] for t, ok in zip(TARGETS, results) if not ok]
    if ng:
        print(f"\n❌ 地図（CLAUDE.mdの構成表）と実際の中身がズレています：{'、'.join(f'{p}/' for p in ng)}")
        print("   CLAUDE.md の該当フォルダのブロックに、1行（ファイル名＋何をするかの説明）を足すか消してください。")
    if not docs_ok:
        print("\n❌ もう1つの地図（docs/README.md の目次）と docs/ の中身がズレています。")
        print("   docs/README.md の該当する見出しの下に、1行（リンク＋どんなときに読むか）を足すか消してください。")
    if not links_ok:
        print("\n❌ Markdownどうしの内部リンクが切れています（押しても何も出ない状態）。")
        print("   リンク先の正しい場所に書き替えるか、相手のファイルを元の場所に戻してください。")
    if not html_ok:
        print("\n❌ 公開ページ（HTML）の中のリンクが、公開しているファイルにたどり着けません。")
        print("   そのままWebに出すと、公開サイトでリンク切れ（404や真っ白）になります。")
    if not pages_ok:
        print("\n❌ 公開ページの一覧を持つ文書に、載っていないページがあります。")
        print("   その文書に1行（ページの名前・公開URL・どんなときに見るか）を足してください。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
