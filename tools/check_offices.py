#!/usr/bin/env python3
"""予報区リスト（OFFICES）がズレていないかを確かめる「見張り番」。

大もとの表は data/offices.json（リポジトリで1か所だけの正）。
台風・防災の両Pythonスクリプトはそのファイルを直接読むので、ズレようがない。
ただし typhoon-app/index.html と bousai-app/index.html は
「1枚だけでブラウザから直接開ける」形にするため、同じ表を中に埋め込んでいる。

このスクリプトは、その埋め込み2か所が大もととズレていないかを照合する。
ズレていたら ❌ を出して終了コード1（GitHub Actions なら赤くなって知らせてくれる）。

使い方（手で試すとき）:
    python3 tools/check_offices.py

外部のライブラリは使いません（Python 3 の標準機能だけ）。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MASTER = ROOT / "data" / "offices.json"
HTMLS = [
    ROOT / "typhoon-app" / "index.html",
    ROOT / "bousai-app" / "index.html",
]


def load_master():
    """大もとの data/offices.json を読み、[(コード, 名前, 地方), ...] の形で返す。"""
    data = json.loads(MASTER.read_text(encoding="utf-8"))
    rows = [(o["code"], o["name"], o["region"]) for o in data["offices"]]
    if not rows:
        sys.exit(f"❌ {MASTER.name} の offices が空です")
    codes = [r[0] for r in rows]
    if len(codes) != len(set(codes)):
        sys.exit(f"❌ {MASTER.name} にコードの重複があります")
    return rows


def load_html(path: Path):
    """index.html の中の『var OFFICES = [...]』を読み取って同じ形で返す。"""
    m = re.search(r"var OFFICES = \[(.*?)\];", path.read_text(encoding="utf-8"), re.S)
    if not m:
        sys.exit(f"❌ {path} に『var OFFICES = [...]』が見つかりません")
    return re.findall(r"\['([^']*)',\s*'([^']*)',\s*'([^']*)'\]", m.group(1))


def main() -> int:
    master = load_master()
    ng = False
    for path in HTMLS:
        rows = load_html(path)
        rel = path.relative_to(ROOT)
        if rows == master:
            continue
        ng = True
        print(f"❌ {rel} の埋め込みが大もと（data/offices.json）とズレています")
        if len(rows) != len(master):
            print(f"   件数が違います: 大もと={len(master)} / {rel}={len(rows)}")
        for i, (a, b) in enumerate(zip(master, rows)):
            if a != b:
                print(f"   {i + 1}行目: 大もと={a} / {rel}={b}")
    if ng:
        print("→ data/offices.json を正として、index.html の埋め込みを同じ内容に直してください。")
        return 1
    print(f"✅ 予報区リストは3か所（大もと＋HTML2枚）ともそろっています（{len(master)}予報区）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
