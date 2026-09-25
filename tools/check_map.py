#!/usr/bin/env python3
"""🗺 CLAUDE.md の「ディレクトリ構成」と、実際の `tools/` の中身がそろっているか照合する見張り番。

■ なぜ必要か
CLAUDE.md の構成表は、新しいセッションが毎回いちばん最初に読む「のんラボの地図」。
ところが道具を新しく作ったとき、この表に書き足すのを**忘れやすい**
（2026-09-10 に3つの抜けが同時に見つかった＝自己改良バックログの候補28・29）。
地図に載っていない道具は、次のセッションから見えない＝使われないままになる。
この道具は「実際にあるファイル」と「地図に書かれている行」を突き合わせて、
どちらかにしか無いものを知らせる。

■ 使い方
    python3 tools/check_map.py
    npm run check:map          （同じもの）

■ 出力例（◯には実際の個数が入る）
    ✅ tools/ の◯個の道具は、すべてCLAUDE.mdの構成表に載っています。

ズレていたときは、足りない側を ❌ で並べて表示し、終了コード1で終わる。
※ 直すのは人の仕事（この道具はCLAUDE.mdを書き換えない）。地図の説明文は
   「何をする道具か」を日本語で書くところなので、機械には書けないため。

外部のライブラリは使いません（Python 3 の標準機能だけ）。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CLAUDE_MD = REPO_ROOT / "CLAUDE.md"
TOOLS_DIR = REPO_ROOT / "tools"

# 地図に載せる対象（道具そのもの）。説明用の README などは対象外
TOOL_SUFFIXES = (".py", ".js")

# 構成表の1行から名前を取り出す（例: "│   ├── check_offices.py   #    👀 ..." → "check_offices.py"）
ENTRY_RE = re.compile(r"^│\s+[├└]──\s+(\S+)")


def read_actual_tools() -> set[str]:
    """実際に tools/ にあるファイル名を集める。"""
    return {
        path.name
        for path in TOOLS_DIR.iterdir()
        if path.is_file() and path.suffix in TOOL_SUFFIXES
    }


def read_mapped_tools() -> set[str]:
    """CLAUDE.md の構成表の「tools/」の中に書かれているファイル名を集める。"""
    lines = CLAUDE_MD.read_text(encoding="utf-8").splitlines()

    # 「├── tools/」の行を探す（ここから下がこのフォルダの中身）
    start = None
    for i, line in enumerate(lines):
        if line.startswith("├── tools/") or line.startswith("└── tools/"):
            start = i + 1
            break
    if start is None:
        print("❌ CLAUDE.md の構成表に「tools/」の行が見つかりません。")
        sys.exit(1)

    names: set[str] = set()
    for line in lines[start:]:
        # 「│」で始まらなくなったら、tools/ の中身は終わり（次のフォルダに移った）
        if not line.startswith("│"):
            break
        matched = ENTRY_RE.match(line)
        if matched:
            names.add(matched.group(1))
    return names


def main() -> int:
    actual = read_actual_tools()
    mapped = read_mapped_tools()

    missing = sorted(actual - mapped)   # 実物はあるのに地図に無い
    ghosts = sorted(mapped - actual)    # 地図にあるのに実物が無い

    if not missing and not ghosts:
        print(f"✅ tools/ の{len(actual)}個の道具は、すべてCLAUDE.mdの構成表に載っています。")
        return 0

    for name in missing:
        print(f"❌ tools/{name} が CLAUDE.md の構成表に載っていません（作ったあとの書き足し忘れ）")
    for name in ghosts:
        print(f"❌ CLAUDE.md の構成表にある tools/{name} が実際には見つかりません（消したあとの消し忘れ）")

    print("\n❌ 地図（CLAUDE.mdの構成表）と実際の tools/ がズレています。")
    print("   CLAUDE.md の「├── tools/」のブロックに、1行（ファイル名＋何をする道具かの説明）を足すか消してください。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
