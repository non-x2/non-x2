#!/usr/bin/env python3
"""ライブカメラ台帳（データベース）を作る司令塔。

やることは4つだけです:

  1. `sources/` の各係に「取ってきて」と頼む
  2. 同じ場所のカメラが重複していたら1つにまとめる
  3. 写真URLが https で開けるかを1台ずつ確かめる（ページ内に出せるかの判定）
  4. 緯度経度から市区町村名を付けて、`data/livecams.json` に保存する

使い方:
    python3 livecam-db/build.py                 # 全部やる（時間がかかります）
    python3 livecam-db/build.py --no-verify     # 写真の確認をとばす（前回の結果を使う）
    python3 livecam-db/build.py --no-geocode    # 市区町村の調べ直しをとばす
    python3 livecam-db/build.py --only jice-roads   # 情報源をしぼる

外部のライブラリは使いません（Python 3 の標準機能だけ）。
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sources import base, jice  # noqa: E402

DB_PATH = Path(__file__).resolve().parent / "data" / "livecams.json"

# 情報源の係の一覧。新しい情報源を足すときはここに登録します。
COLLECTORS = {
    "jice": jice.collect_all,
}

# 台帳がこの数を下回ったら「こわれている」とみなして上書きしない（安全装置）
MIN_EXPECTED = 2000


def dedupe(cams: list[dict]) -> list[dict]:
    """ほぼ同じ場所・同じ写真のカメラを1つにまとめる。

    別々の情報源に同じカメラが載っていることがあるためです。
    判定は「写真URLが同じ」または「約11m以内で名前も同じ」。
    """
    by_img: dict[str, dict] = {}
    by_spot: dict[tuple, dict] = {}
    out: list[dict] = []

    for cam in cams:
        img = cam.get("img")
        spot = (round(cam["lat"], 4), round(cam["lon"], 4), cam["name"])

        twin = (by_img.get(img) if img else None) or by_spot.get(spot)
        if twin is not None:
            # 情報が足りないほうを、あるほうで補う
            for key in ("img", "page", "owner", "place"):
                if not twin.get(key) and cam.get(key):
                    twin[key] = cam[key]
            twin.setdefault("also", [])
            if cam["src"] not in twin["also"] and cam["src"] != twin["src"]:
                twin["also"].append(cam["src"])
            continue

        out.append(cam)
        if img:
            by_img[img] = cam
        by_spot[spot] = cam

    return out


def load_previous() -> tuple[set[str], dict[str, str]]:
    """前回の台帳から「開けた写真URL」と「場所ごとの市区町村名」を読み込む。"""
    known_ok: set[str] = set()
    places: dict[str, str] = {}
    if not DB_PATH.exists():
        return known_ok, places
    try:
        old = json.loads(DB_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return known_ok, places
    for cam in old.get("cams", []):
        if cam.get("img"):
            known_ok.add(cam["img"])
        if cam.get("place") and cam.get("lat") is not None:
            places[base.place_key(cam["lat"], cam["lon"])] = cam["place"]
    return known_ok, places


def build(only: list[str] | None, verify: bool, geocode: bool) -> dict:
    print("⏳ 情報源からカメラを集めています…")
    cams: list[dict] = []
    sources: list[dict] = []

    for key, collect in COLLECTORS.items():
        if only and key not in only and not any(o.startswith(key) for o in only):
            continue
        got, used = collect(only)
        cams.extend(got)
        sources.extend(used)

    if not cams:
        raise RuntimeError("カメラが1台も集まりませんでした")

    print(f"📋 集まったカメラ: {len(cams)} 台")
    cams = dedupe(cams)
    print(f"🔁 重複をまとめた後: {len(cams)} 台")

    known_ok, place_cache = load_previous()

    shown = base.verify_images(cams, known_ok, enabled=verify)
    print(f"📷 ページ内で映像を出せるカメラ: {shown} 台 / 公式ページで見るカメラ: {len(cams) - shown} 台")

    placed = base.fill_places(cams, place_cache, enabled=geocode)
    print(f"🗾 市区町村名が付いたカメラ: {placed} 台")

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
        "withPlace": placed,
        "byCategory": by_cat,
        "sources": sources,
        "cams": cams,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="ライブカメラ台帳を作ります")
    parser.add_argument("--no-verify", action="store_true",
                        help="写真が開けるかの確認をとばす（前回の結果を使います）")
    parser.add_argument("--no-geocode", action="store_true",
                        help="市区町村名の調べ直しをとばす（前回の結果を使います）")
    parser.add_argument("--only", nargs="+", metavar="情報源",
                        help="使う情報源をしぼる（例: --only jice-roads）")
    args = parser.parse_args()

    try:
        db = build(only=args.only, verify=not args.no_verify, geocode=not args.no_geocode)
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
