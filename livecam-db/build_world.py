#!/usr/bin/env python3
"""🌍 世界のライブカメラ台帳（試験）を作る司令塔。

日本の台帳（build.py → data/livecams.json）とは**別のファイル**
（data/livecams_world.json）を作ります。分けている理由:

  1. 日本のアプリ（traffic-app）に世界のカメラが混ざって、ページが重くならないように
     （export.py は日本の台帳だけを配るので、既存ページへの影響はゼロ）
  2. 市区町村付け（国土地理院＝日本専用）など、日本専用の処理を通さないため

やることは build.py と同じ流れの世界版です:
  1. `sources/` の世界の係に「取ってきて」と頼む（いまはアイオワ州だけ）
  2. 重複をまとめる（build.py の関数をそのまま再利用）
  3. 写真URLが本当に開けるかを1台ずつ確かめる
  4. `data/livecams_world.json` に保存する

使い方:
    python3 livecam-db/build_world.py               # 全部やる（数分かかります）
    python3 livecam-db/build_world.py --no-verify   # 写真の確認をとばす（前回の結果を使う）

外部のライブラリは使いません（Python 3 の標準機能だけ）。
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build import dedupe  # noqa: E402  （重複をまとめる係は日本版と共通）
from sources import base, us_iowa  # noqa: E402

DB_PATH = Path(__file__).resolve().parent / "data" / "livecams_world.json"

# 世界の情報源の係の一覧。新しい国・州を足すときはここに登録します。
# ⚠️ 足す前に必ず利用条件を確かめること（livecam-db/README.md の「情報源を選ぶときの約束」）
COLLECTORS = {
    "us-iowa": us_iowa.collect_all,
}

# 台帳がこの数を下回ったら「こわれている」とみなして上書きしない（安全装置）
MIN_EXPECTED = 700

# 情報源ごとに、前回の台数のこの割合を下回ったら中止する（安全装置・build.py と同じ）
SOURCE_MIN_RATIO = 0.7


def load_previous() -> tuple[set[str], dict[str, int]]:
    """前回の台帳から「開けた写真URL」と「情報源ごとの台数」を読み込む。"""
    known_ok: set[str] = set()
    counts: dict[str, int] = {}
    if not DB_PATH.exists():
        return known_ok, counts
    try:
        old = json.loads(DB_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return known_ok, counts
    for cam in old.get("cams", []):
        if cam.get("img"):
            known_ok.add(cam["img"])
    for src in old.get("sources", []):
        if src.get("id"):
            counts[src["id"]] = src.get("count", 0)
    return known_ok, counts


def build(only: list[str] | None, verify: bool) -> dict:
    print("⏳ 🌍 世界の情報源からカメラを集めています…")
    cams: list[dict] = []
    sources: list[dict] = []

    for key, collect in COLLECTORS.items():
        if only and key not in only:
            continue
        got, used = collect(only)
        cams.extend(got)
        sources.extend(used)

    if not cams:
        raise RuntimeError("カメラが1台も集まりませんでした")

    print(f"📋 集まったカメラ: {len(cams)} 台")
    cams = dedupe(cams)
    print(f"🔁 重複をまとめた後: {len(cams)} 台")

    known_ok, prev_counts = load_previous()

    # 🛡 安全装置：情報源ごとに、前回より大きく減っていないか確かめる
    for src in sources:
        before = prev_counts.get(src["id"])
        if before and src["count"] < before * SOURCE_MIN_RATIO:
            raise RuntimeError(
                f"{src['name']} が {before}台 → {src['count']}台 に激減しました"
                f"（前回の{SOURCE_MIN_RATIO:.0%}未満）。相手のサイトの不調かもしれないので中止します"
            )

    shown = base.verify_images(cams, known_ok, enabled=verify)
    print(f"📷 ページ内で映像を出せるカメラ: {shown} 台 / 公式ページで見るカメラ: {len(cams) - shown} 台")

    # 並び順を安定させる（北から南へ）。差分が見やすくなります。
    cams.sort(key=lambda c: (-c["lat"], c["lon"], c["name"]))
    for i, cam in enumerate(cams):
        cam["id"] = f"{cam['src']}-{i:05d}"

    by_cat: dict[str, int] = {}
    for cam in cams:
        by_cat[cam["cat"]] = by_cat.get(cam["cat"], 0) + 1

    return {
        "updated": datetime.now(base.JST).isoformat(timespec="seconds"),
        "count": len(cams),
        "withImage": shown,
        "withPlace": sum(1 for c in cams if c.get("place")),
        "byCategory": by_cat,
        "sources": sources,
        "cams": cams,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="🌍 世界のライブカメラ台帳（試験）を作ります")
    parser.add_argument("--no-verify", action="store_true",
                        help="写真が開けるかの確認をとばす（前回の結果を使います）")
    parser.add_argument("--only", nargs="+", metavar="情報源",
                        help="使う情報源をしぼる（例: --only us-iowa）")
    args = parser.parse_args()

    try:
        db = build(only=args.only, verify=not args.no_verify)
    except Exception as exc:  # 失敗したら、今ある台帳は上書きしない（安全装置）
        print(f"⚠️ 取得に失敗したので、今ある台帳はそのままにします: {exc}", file=sys.stderr)
        return 1

    if not args.only and db["count"] < MIN_EXPECTED:
        print(
            f"⚠️ カメラが {db['count']} 台しか集まりませんでした（いつもは {MIN_EXPECTED} 台以上）。"
            "こわれたデータで上書きしないため中止します。",
            file=sys.stderr,
        )
        return 1

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    DB_PATH.write_text(
        json.dumps(db, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    print(f"💾 保存しました: {DB_PATH}（{DB_PATH.stat().st_size / 1024:.0f} KB）")
    print("   内訳: " + " / ".join(f"{k} {v}台" for k, v in sorted(db["byCategory"].items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
