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

■ 使い方
    python3 tools/check_map.py
    npm run check:map          （同じもの）

■ 出力例（◯には実際の個数が入る）
    ✅ tools/ の◯個の道具は、すべてCLAUDE.mdの構成表に載っています。
    ✅ .github/workflows/ の◯枚の自動実行は、すべてCLAUDE.mdの構成表に載っています。

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


def main() -> int:
    lines = CLAUDE_MD.read_text(encoding="utf-8").splitlines()

    results = [check(target, lines) for target in TARGETS]
    if all(results):
        return 0

    ng = [t["path"] for t, ok in zip(TARGETS, results) if not ok]
    print(f"\n❌ 地図（CLAUDE.mdの構成表）と実際の中身がズレています：{'、'.join(f'{p}/' for p in ng)}")
    print("   CLAUDE.md の該当フォルダのブロックに、1行（ファイル名＋何をするかの説明）を足すか消してください。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
