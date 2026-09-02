#!/usr/bin/env python3
"""👀 tools/ の道具のdocstringに書かれた「出力例」が、実際の出力とズレていないか照合する見張り番。

■ なぜ必要か
docstringの出力例は手で書くので、道具の中身を直したときにうっかり
書き換え忘れて実際の出力とズレることがある（例：typhoon_map_coords.py で発生。
自己改良バックログの候補17で発見・修正した）。この道具は、docstring中の
コマンド例を実際に実行して、書かれている出力例と一致するかを機械的に照合する。

■ 使い方
    python3 tools/check_docstrings.py
        （対象は下の TARGETS リストに書かれた道具だけ。まずは
         typhoon_map_coords.py の使用例2つだけを対象にした小さな版）

外部のライブラリは使いません（Python 3 の標準機能だけ）。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# 照合したいコマンド例を手動で登録する（まずは typhoon_map_coords.py の2つだけ）
TARGETS = [
    {
        "tool": "tools/typhoon_map_coords.py",
        "label": "順方向（緯度経度→x,y）",
        "args": ["24.5", "132.0", "26.0", "135.4"],
        "expected_lines": [
            "24.5,132.0 → x=101.4,y=278.1",
            "26.0,135.4 → x=136.0,y=261.3",
        ],
    },
    {
        "tool": "tools/typhoon_map_coords.py",
        "label": "逆方向（x,y→緯度経度）",
        "args": ["--xy", "101.4", "278.1", "136.0", "261.3"],
        "expected_lines": [
            "x=101.4,y=278.1 → 24.5,132.0",
            "x=136.0,y=261.3 → 26.0,135.4",
        ],
    },
]


def run_tool(tool: str, args: list[str]) -> list[str]:
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / tool), *args],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def main() -> int:
    ok = True
    for target in TARGETS:
        actual_lines = run_tool(target["tool"], target["args"])
        for expected in target["expected_lines"]:
            if expected in actual_lines:
                print(f"✅ {target['tool']}（{target['label']}）: 「{expected}」は実際の出力と一致")
            else:
                ok = False
                print(f"❌ {target['tool']}（{target['label']}）: 「{expected}」が実際の出力に見つかりません")
                print(f"   実際の出力: {actual_lines}")
    if ok:
        print("\n✅ すべての出力例が実際の出力と一致しています。")
        return 0
    print("\n❌ docstringの出力例が実際の出力とズレています。該当箇所を直してください。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
