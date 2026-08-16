#!/usr/bin/env python3
"""台帳を「使う側」に配る係。

ライブカメラ台帳（data/livecams.json）は**大もと**です。
各アプリはここから配ってもらう形にして、正しい情報を1か所にまとめています
（`data/offices.json` と同じ考え方です）。

いまの配り先:
  - traffic-app … 交通・ライブカメラのページ
      ① traffic-app/data/livecams.json … 人が読める形
      ② traffic-app/index.html の埋め込み … ページが読む形（軽くしたもの）
      ※ ①②の両方を同時に書き換えるので、ズレません。
      ※ ページに埋め込むのは、index.html をダブルクリックで開いたとき
         （file://）でも動くようにするためです。

使い方:
    python3 livecam-db/export.py              # 全部の配り先に配る
    python3 livecam-db/export.py --target traffic-app

外部のライブラリは使いません（Python 3 の標準機能だけ）。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = Path(__file__).resolve().parent / "data" / "livecams.json"
WORLD_DB_PATH = Path(__file__).resolve().parent / "data" / "livecams_world.json"

TRAFFIC_JSON = ROOT / "traffic-app" / "data" / "livecams.json"
TRAFFIC_HTML = ROOT / "traffic-app" / "index.html"
WORLD_HTML = ROOT / "traffic-app" / "world.html"

# index.html の中の、台帳を書き込む場所の目印
EMBED_START = '<script id="livecam-data" type="application/json">'
EMBED_END = "</script>"
# world.html（🌍 世界版ページ）の目印
EMBED_START_WORLD = '<script id="livecam-world-data" type="application/json">'


def to_compact(db: dict) -> dict:
    """同じ文字のくり返しをまとめて、ページに載せる用の軽い形にする。

    n=名前 / m=管理者 / a=市区町村 / p=カメラのページ / b=写真URLの前半 / k=種類
    c=カメラ本体 [緯度*10万, 経度*10万, n番号, m番号, a番号, p番号, b番号, 写真URLの後半, k番号]
    """
    tables: dict[str, list[str]] = {"n": [], "m": [], "a": [], "p": [], "b": [], "k": []}
    index: dict[str, dict[str, int]] = {key: {} for key in tables}

    def idx(kind: str, value: str) -> int:
        if not value:
            return -1
        if value not in index[kind]:
            index[kind][value] = len(tables[kind])
            tables[kind].append(value)
        return index[kind][value]

    rows = []
    for cam in db["cams"]:
        img = cam.get("img") or ""
        cut = img.rfind("/") + 1 if img else 0
        head, tail = (img[:cut], img[cut:]) if img else ("", "")
        rows.append([
            round(cam["lat"] * 1e5),
            round(cam["lon"] * 1e5),
            idx("n", cam.get("name", "")),
            idx("m", cam.get("owner", "")),
            idx("a", cam.get("place", "")),
            idx("p", cam.get("page", "")),
            idx("b", head),
            tail,
            idx("k", cam.get("cat", "road")),
        ])

    return {
        "u": db["updated"][:10],
        "n": tables["n"], "m": tables["m"], "a": tables["a"],
        "p": tables["p"], "b": tables["b"], "k": tables["k"],
        "c": rows,
    }


def write_html_embed(db: dict, html_path: Path, marker: str = EMBED_START) -> bool:
    """ページの中の台帳（埋め込み）を書き換える。"""
    if not html_path.exists():
        print(f"⚠️ {html_path} が見つからないので、埋め込みは省略します", file=sys.stderr)
        return False

    html = html_path.read_text(encoding="utf-8")
    start = html.find(marker)
    if start < 0:
        print(f"⚠️ {html_path.name} に台帳の目印が見つかりませんでした", file=sys.stderr)
        return False
    body_start = start + len(marker)
    end = html.find(EMBED_END, body_start)
    if end < 0:
        print(f"⚠️ {html_path.name} の台帳の終わりが見つかりませんでした", file=sys.stderr)
        return False

    payload = json.dumps(to_compact(db), ensure_ascii=False, separators=(",", ":"))
    # </script> が混ざると途中でページが切れてしまうので、念のため無害化する
    payload = payload.replace("</", "<\\/")

    html_path.write_text(html[:body_start] + "\n" + payload + "\n" + html[end:], encoding="utf-8")
    return True


def export_traffic_app(db: dict) -> None:
    """交通・ライブカメラのページに配る。"""
    payload = {
        "updated": db["updated"],
        "count": db["count"],
        "withImage": db["withImage"],
        "withPlace": db["withPlace"],
        "byCategory": db["byCategory"],
        "note": "この台帳の大もとは livecam-db/data/livecams.json です。"
                "直接編集せず、livecam-db/build.py と export.py で作りなおしてください。",
        "sources": db["sources"],
        "cams": db["cams"],
    }
    TRAFFIC_JSON.parent.mkdir(parents=True, exist_ok=True)
    TRAFFIC_JSON.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    print(f"💾 配りました: {TRAFFIC_JSON}（{TRAFFIC_JSON.stat().st_size / 1024:.0f} KB）")

    if write_html_embed(db, TRAFFIC_HTML):
        print(f"💾 ページにも埋め込みました: {TRAFFIC_HTML}（{TRAFFIC_HTML.stat().st_size / 1024:.0f} KB）")


def export_world(_db: dict) -> None:
    """🌍 世界版ページ（traffic-app/world.html）に配る。

    読むのは日本の台帳ではなく **世界台帳**（data/livecams_world.json）です。
    日本の台帳（引数の db）は使いません。
    """
    if not WORLD_DB_PATH.exists():
        print(f"⚠️ 世界台帳がありません: {WORLD_DB_PATH}\n"
              "   先に『python3 livecam-db/build_world.py』を実行してください。", file=sys.stderr)
        return
    world = json.loads(WORLD_DB_PATH.read_text(encoding="utf-8"))
    print(f"🌍 世界台帳: {world['count']} 台（映像を出せる {world['withImage']} 台）")
    if write_html_embed(world, WORLD_HTML, marker=EMBED_START_WORLD):
        print(f"💾 世界版ページに埋め込みました: {WORLD_HTML}（{WORLD_HTML.stat().st_size / 1024:.0f} KB）")


TARGETS = {"traffic-app": export_traffic_app, "world": export_world}


def main() -> int:
    ap = argparse.ArgumentParser(description="ライブカメラ台帳を各アプリに配ります")
    ap.add_argument("--target", nargs="+", choices=sorted(TARGETS), default=sorted(TARGETS),
                    help="配り先（省略すると全部）")
    args = ap.parse_args()

    if not DB_PATH.exists():
        print(f"⚠️ 台帳がありません: {DB_PATH}\n"
              "   先に『python3 livecam-db/build.py』を実行してください。", file=sys.stderr)
        return 1

    db = json.loads(DB_PATH.read_text(encoding="utf-8"))
    print(f"📋 台帳: {db['count']} 台（映像を出せる {db['withImage']} 台）")

    for name in args.target:
        TARGETS[name](db)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
