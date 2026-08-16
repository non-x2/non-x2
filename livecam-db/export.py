#!/usr/bin/env python3
"""台帳を「使う側」に配る係。

ライブカメラ台帳（data/livecams.json）は**大もと**です。
各アプリはここから配ってもらう形にして、正しい情報を1か所にまとめています
（`data/offices.json` と同じ考え方です）。

いまの配り先:
  - traffic-app … 交通・ライブカメラのページ（🇯🇵 日本の台帳）
      ① traffic-app/data/livecams.json … 人が読める形
      ② traffic-app/index.html の埋め込み … ページが読む形（軽くしたもの）
      ※ ①②の両方を同時に書き換えるので、ズレません。
      ※ ページに埋め込むのは、index.html をダブルクリックで開いたとき
         （file://）でも動くようにするためです。
  - world-livecam … 🌍 世界のライブカメラのページ（世界の台帳・試験）
      ①② の考え方は traffic-app と同じ。ただし**読む台帳が別ファイル**
      （data/livecams_world.json）なので、日本のページには一切混ざりません。

使い方:
    python3 livecam-db/export.py                      # 全部の配り先に配る
    python3 livecam-db/export.py --target traffic-app
    python3 livecam-db/export.py --target world-livecam

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

WORLD_JSON = ROOT / "world-livecam" / "data" / "livecams_world.json"
WORLD_HTML = ROOT / "world-livecam" / "index.html"

# index.html の中の、台帳を書き込む場所の目印
EMBED_START = '<script id="livecam-data" type="application/json">'
EMBED_END = "</script>"


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


def write_html_embed(db: dict, html_path: Path) -> bool:
    """index.html の中の台帳を書き換える。"""
    if not html_path.exists():
        print(f"⚠️ {html_path} が見つからないので、埋め込みは省略します", file=sys.stderr)
        return False

    html = html_path.read_text(encoding="utf-8")
    start = html.find(EMBED_START)
    if start < 0:
        print(f"⚠️ {html_path.name} に台帳の目印が見つかりませんでした", file=sys.stderr)
        return False
    body_start = start + len(EMBED_START)
    end = html.find(EMBED_END, body_start)
    if end < 0:
        print(f"⚠️ {html_path.name} の台帳の終わりが見つかりませんでした", file=sys.stderr)
        return False

    payload = json.dumps(to_compact(db), ensure_ascii=False, separators=(",", ":"))
    # </script> が混ざると途中でページが切れてしまうので、念のため無害化する
    payload = payload.replace("</", "<\\/")

    html_path.write_text(html[:body_start] + "\n" + payload + "\n" + html[end:], encoding="utf-8")
    return True


def write_copy(db: dict, json_path: Path, note: str) -> None:
    """台帳の「人が読める形」のコピーを置く。"""
    payload = {
        "updated": db["updated"],
        "count": db["count"],
        "withImage": db["withImage"],
        "withPlace": db["withPlace"],
        "byCategory": db["byCategory"],
        "note": note,
        "sources": db["sources"],
        "cams": db["cams"],
    }
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    print(f"💾 配りました: {json_path}（{json_path.stat().st_size / 1024:.0f} KB）")


def export_traffic_app(db: dict) -> None:
    """交通・ライブカメラのページに配る（🇯🇵 日本の台帳）。"""
    write_copy(db, TRAFFIC_JSON,
               "この台帳の大もとは livecam-db/data/livecams.json です。"
               "直接編集せず、livecam-db/build.py と export.py で作りなおしてください。")
    if write_html_embed(db, TRAFFIC_HTML):
        print(f"💾 ページにも埋め込みました: {TRAFFIC_HTML}（{TRAFFIC_HTML.stat().st_size / 1024:.0f} KB）")


def export_world_livecam(db: dict) -> None:
    """🌍 世界のライブカメラのページに配る（世界の台帳・試験）。"""
    write_copy(db, WORLD_JSON,
               "この台帳の大もとは livecam-db/data/livecams_world.json です。"
               "直接編集せず、livecam-db/build_world.py と export.py で作りなおしてください。")
    if write_html_embed(db, WORLD_HTML):
        print(f"💾 ページにも埋め込みました: {WORLD_HTML}（{WORLD_HTML.stat().st_size / 1024:.0f} KB）")


# 配り先ごとに「どの台帳を読むか」も決めておく（日本と世界は別ファイル）
TARGETS = {
    "traffic-app": (DB_PATH, export_traffic_app),
    "world-livecam": (WORLD_DB_PATH, export_world_livecam),
}


def main() -> int:
    ap = argparse.ArgumentParser(description="ライブカメラ台帳を各アプリに配ります")
    ap.add_argument("--target", nargs="+", choices=sorted(TARGETS), default=sorted(TARGETS),
                    help="配り先（省略すると全部）")
    args = ap.parse_args()

    if not DB_PATH.exists():
        print(f"⚠️ 台帳がありません: {DB_PATH}\n"
              "   先に『python3 livecam-db/build.py』を実行してください。", file=sys.stderr)
        return 1

    cache: dict[Path, dict] = {}

    for name in args.target:
        db_path, export = TARGETS[name]
        if db_path not in cache:
            if not db_path.exists():
                # 🌍 世界の台帳（試験）がまだ無くても、日本の配布は止めません。
                # ここで止めると、週1の自動更新まるごとが失敗してしまうためです。
                print(f"⚠️ 台帳がないので「{name}」への配布は省略します: {db_path}", file=sys.stderr)
                continue
            cache[db_path] = json.loads(db_path.read_text(encoding="utf-8"))
            db = cache[db_path]
            print(f"📋 {db_path.name}: {db['count']} 台（映像を出せる {db['withImage']} 台）")
        export(cache[db_path])

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
