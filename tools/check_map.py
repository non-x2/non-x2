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

■ もう1つの地図も見張る（2026-10-01 追加＝自己改良バックログの候補47）
`docs/README.md`（📚 docsの歩き方）も、docsフォルダの中身を手で書き写した「地図」。
2026-09-27 に見たときは作業ログ7枚が抜け、「最新」の案内が47日前のままだった。
そこで下の3つを照合する（材料はファイル名だけ＝中身も通信も要らない）。
    ① ガイド・手順書が目次に載っているか（作ったあとの書き足し忘れ）
    ② 省略の線引き（「それより古いもの(◯◯ 以前)は…」）より新しい作業ログが全部載っているか
    ③ 「🚀 まず読むもの」が最新と呼んでいる作業ログが、本当にいちばん新しい日付か

■ 使い方
    python3 tools/check_map.py
    npm run check:map          （同じもの）

■ 出力例（◯には実際の個数、日付には実際の日付が入る）
    ✅ tools/ の◯個の道具は、すべてCLAUDE.mdの構成表に載っています。
    ✅ .github/workflows/ の◯枚の自動実行は、すべてCLAUDE.mdの構成表に載っています。
    ✅ docs/ の◯枚の文書は、すべて docs/README.md の目次に載っています（最新の作業ログの案内も ◯◯◯◯-◯◯-◯◯ で合っています）。

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
#   path     : 実物のフォルダ（＝構成表に書かれている名前と同じつづり）
#   suffixes : 地図に載せる対象の拡張子（README などを除くため）
#   unit     : 報告文の数え方（「3個の道具」「9枚の自動実行」）
TARGETS = [
    {"path": "tools", "suffixes": (".py", ".js"), "unit": "個の道具"},
    {"path": ".github/workflows", "suffixes": (".yml", ".yaml"), "unit": "枚の自動実行"},
]

# 構成表の1行から名前を取り出す（例: "│   ├── check_offices.py   #    👀 ..." → "check_offices.py"）
ENTRY_RE = re.compile(r"^│\s+[├└]──\s+(\S+)")

# docs/README.md の照合に使うもの
# 「[作業ログ_2026-08-22.md](作業ログ_2026-08-22.md)」のような同じフォルダ内へのリンク先だけを拾う。
# `/` と `:` を除いているので、よそのフォルダ（`docs/○○.md`）や外部のURL（`https://…`）は拾わない。
# 「○○.md#見出し」のように見出しへ飛ばすリンクも、ファイル名のぶんだけ拾う。
DOCS_LINK_RE = re.compile(r"\]\(([^)/:#]+\.md)(?:#[^)]*)?\)")
WORKLOG_RE = re.compile(r"^作業ログ_(\d{4}-\d{2}-\d{2})\.md$")
# 「それより古いもの(2026-08-01 以前)はファイル一覧から探してください。」の線引きの日付
CUTOFF_RE = re.compile(r"それより古いもの[（(](\d{4}-\d{2}-\d{2})\s*以前[）)]")


def read_actual(target: dict) -> set[str]:
    """実際にそのフォルダにあるファイル名を集める。"""
    folder = REPO_ROOT / target["path"]
    return {
        path.name
        for path in folder.iterdir()
        if path.is_file() and path.suffix in target["suffixes"]
    }


def read_mapped(target: dict, lines: list[str]) -> set[str] | None:
    """CLAUDE.md の構成表の、そのフォルダの中に書かれているファイル名を集める。

    構成表にそのフォルダの行が無いときは None を返す（呼び出し側でエラーにする）。
    """
    # 「├── tools/」のような、このフォルダが始まる行を探す（ここから下が中身）
    start = None
    for i, line in enumerate(lines):
        for branch in ("├── ", "└── "):
            if line.startswith(f"{branch}{target['path']}/"):
                start = i + 1
                break
        if start is not None:
            break
    if start is None:
        return None

    names: set[str] = set()
    for line in lines[start:]:
        # 「│」で始まらなくなったら、このフォルダの中身は終わり（次のフォルダに移った）
        if not line.startswith("│"):
            break
        matched = ENTRY_RE.match(line)
        if matched:
            names.add(matched.group(1))
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


def main() -> int:
    lines = CLAUDE_MD.read_text(encoding="utf-8").splitlines()

    results = [check(target, lines) for target in TARGETS]
    docs_ok = check_docs_index()

    if all(results) and docs_ok:
        return 0

    ng = [t["path"] for t, ok in zip(TARGETS, results) if not ok]
    if ng:
        print(f"\n❌ 地図（CLAUDE.mdの構成表）と実際の中身がズレています：{'、'.join(f'{p}/' for p in ng)}")
        print("   CLAUDE.md の該当フォルダのブロックに、1行（ファイル名＋何をするかの説明）を足すか消してください。")
    if not docs_ok:
        print("\n❌ もう1つの地図（docs/README.md の目次）と docs/ の中身がズレています。")
        print("   docs/README.md の該当する見出しの下に、1行（リンク＋どんなときに読むか）を足すか消してください。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
