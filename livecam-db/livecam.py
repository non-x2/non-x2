#!/usr/bin/env python3
"""ライブカメラ台帳を「使う」ための小さな道具。

台帳（data/livecams.json）を読み込んで、次のような取り出し方ができます。
別のプロジェクトからも、このファイルを取り込むだけで使えます。

--------------------------------------------------------------------
プログラムから使う
--------------------------------------------------------------------

    import sys; sys.path.insert(0, "livecam-db")
    import livecam

    db = livecam.load()

    # ① ある地点の近くのカメラ（近い順）
    for cam in livecam.near(db, 35.681, 139.767, radius_m=10000, limit=5):
        print(cam["name"], cam["place"], round(cam["distance_m"]), "m")

    # ② ルート沿いのカメラ（出発地からの順）
    #    route は [[緯度, 経度], [緯度, 経度], …] の並び
    for cam in livecam.along_route(db, route, radius_m=1500):
        print(cam["name"], "出発から", round(cam["along_m"] / 1000, 1), "km")

    # ③ 名前・場所で探す
    for cam in livecam.search(db, "国道1号", pref="静岡県"):
        print(cam["name"], cam["place"])

    # ④ 種類でしぼる（road=一般道 / expressway=高速 / river=河川 / dam=ダム / sea=海）
    rivers = livecam.filter_cams(db, category="river", with_image=True)

--------------------------------------------------------------------
コマンドから使う
--------------------------------------------------------------------

    python3 livecam-db/livecam.py info
    python3 livecam-db/livecam.py near 35.681 139.767 --radius 10000 --limit 10
    python3 livecam-db/livecam.py search 国道1号 --pref 静岡県
    python3 livecam-db/livecam.py near 34.70 137.73 --radius 10000 --category river
    python3 livecam-db/livecam.py route 40.81,140.45 40.83,140.73 --radius 1500

外部のライブラリは使いません（Python 3 の標準機能だけ）。
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "data" / "livecams.json"
R_EARTH = 6371000.0  # 地球の半径（メートル）


# ------------------------------------------------------------------ 読み込み

def load(path: str | Path | None = None) -> dict:
    """台帳を読み込む。"""
    p = Path(path) if path else DB_PATH
    if not p.exists():
        raise FileNotFoundError(
            f"台帳が見つかりません: {p}\n"
            "先に『python3 livecam-db/build.py』を実行して作ってください。"
        )
    return json.loads(p.read_text(encoding="utf-8"))


# ------------------------------------------------------------------ 距離の計算

def distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """2点間のだいたいの距離（メートル）。日本の範囲なら十分な精度です。"""
    mid = math.radians((lat1 + lat2) / 2)
    dx = math.radians(lon2 - lon1) * math.cos(mid)
    dy = math.radians(lat2 - lat1)
    return math.hypot(dx, dy) * R_EARTH


def _dist_to_segment(lat: float, lon: float,
                     a: tuple[float, float], b: tuple[float, float]) -> float:
    """点と線分の距離（メートル）。道の途中にあるカメラも拾えるようにするため。"""
    k = math.cos(math.radians((a[0] + b[0]) / 2))
    px, py = (lon - a[1]) * k, lat - a[0]
    vx, vy = (b[1] - a[1]) * k, b[0] - a[0]
    len2 = vx * vx + vy * vy
    t = 0.0 if len2 == 0 else max(0.0, min(1.0, (px * vx + py * vy) / len2))
    return math.hypot(px - vx * t, py - vy * t) * math.pi / 180 * R_EARTH


# ------------------------------------------------------------------ しぼり込み

def filter_cams(db: dict, category: str | None = None, source: str | None = None,
                pref: str | None = None, with_image: bool | None = None) -> list[dict]:
    """種類・情報源・都道府県・写真の有無でしぼる。"""
    out = db["cams"]
    if category:
        out = [c for c in out if c.get("cat") == category]
    if source:
        out = [c for c in out if c.get("src") == source]
    if pref:
        out = [c for c in out if (c.get("place") or "").startswith(pref)]
    if with_image is True:
        out = [c for c in out if c.get("img")]
    elif with_image is False:
        out = [c for c in out if not c.get("img")]
    return out


def search(db: dict, keyword: str, **kwargs) -> list[dict]:
    """名前・場所・管理者に言葉が含まれるカメラを探す。"""
    key = keyword.strip()
    return [
        c for c in filter_cams(db, **kwargs)
        if key in (c.get("name") or "")
        or key in (c.get("place") or "")
        or key in (c.get("owner") or "")
    ]


# ------------------------------------------------------------------ 場所で探す

def near(db: dict, lat: float, lon: float, radius_m: float = 5000,
         limit: int | None = None, **kwargs) -> list[dict]:
    """ある地点の近くのカメラを、近い順に返す。

    返ってくるカメラには `distance_m`（その地点からの距離）が付きます。
    """
    found = []
    for cam in filter_cams(db, **kwargs):
        d = distance_m(lat, lon, cam["lat"], cam["lon"])
        if d <= radius_m:
            found.append(dict(cam, distance_m=d))
    found.sort(key=lambda c: c["distance_m"])
    return found[:limit] if limit else found


def along_route(db: dict, route: list, radius_m: float = 1500, **kwargs) -> list[dict]:
    """ルート（[[緯度, 経度], …]）沿いのカメラを、出発地からの順に返す。

    返ってくるカメラには次の2つが付きます。
      off_route_m … ルートからの距離（どれくらい道から離れているか）
      along_m     … 出発地からの道のり
    """
    pts = [(float(p[0]), float(p[1])) for p in route if p and len(p) >= 2]
    if len(pts) < 2:
        return []

    # ルートの点を「マス目」に登録しておき、カメラの近くのマスだけを調べる（総当たりを避ける）
    cell = 0.05                                     # 約5.5km四方
    span = max(1, math.ceil(radius_m / 5500))
    grid: dict[tuple[int, int], list[int]] = {}
    for i, p in enumerate(pts):
        grid.setdefault((int(p[0] // cell), int(p[1] // cell)), []).append(i)

    # 出発地からの積算距離
    cum = [0.0] * len(pts)
    for i in range(1, len(pts)):
        cum[i] = cum[i - 1] + distance_m(*pts[i - 1], *pts[i])

    found = []
    for cam in filter_cams(db, **kwargs):
        gy, gx = int(cam["lat"] // cell), int(cam["lon"] // cell)
        best, best_i = float("inf"), -1
        for dy in range(-span, span + 1):
            for dx in range(-span, span + 1):
                for i in grid.get((gy + dy, gx + dx), ()):
                    d = _dist_to_segment(cam["lat"], cam["lon"], pts[i - 1] if i else pts[i], pts[i])
                    if d < best:
                        best, best_i = d, i
        if best_i >= 0 and best <= radius_m:
            found.append(dict(cam, off_route_m=best, along_m=cum[best_i]))

    found.sort(key=lambda c: c["along_m"])
    return found


# ------------------------------------------------------------------ コマンドとして使う

def _show(cams: list[dict], as_json: bool) -> None:
    if as_json:
        print(json.dumps(cams, ensure_ascii=False, indent=2))
        return
    if not cams:
        print("  該当なし")
        return
    for c in cams:
        bits = [f"{c['name']}"]
        if c.get("place"):
            bits.append(c["place"])
        if "distance_m" in c:
            bits.append(f"{c['distance_m'] / 1000:.1f}km")
        if "along_m" in c:
            bits.append(f"出発から{c['along_m'] / 1000:.1f}km / 道から{c['off_route_m']:.0f}m")
        bits.append("📷映像あり" if c.get("img") else "🔗ページのみ")
        print("  " + "　".join(bits))
    print(f"  （{len(cams)} 台）")


def main() -> int:
    ap = argparse.ArgumentParser(description="ライブカメラ台帳を調べます")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("info", help="台帳の中身の要約を出す")

    p_near = sub.add_parser("near", help="ある地点の近くのカメラを探す")
    p_near.add_argument("lat", type=float)
    p_near.add_argument("lon", type=float)
    p_near.add_argument("--radius", type=float, default=5000, help="半径（メートル）")
    p_near.add_argument("--limit", type=int, default=20)

    p_search = sub.add_parser("search", help="名前・場所・管理者で探す")
    p_search.add_argument("keyword")
    p_search.add_argument("--limit", type=int, default=30)

    p_route = sub.add_parser(
        "route", help="ルート沿いのカメラを探す（緯度,経度 を2つ以上ならべる）")
    p_route.add_argument("points", nargs="+", metavar="緯度,経度",
                         help="例: 35.17,136.88 34.70,137.73")
    p_route.add_argument("--radius", type=float, default=1500, help="道からの距離（メートル）")
    p_route.add_argument("--limit", type=int, default=30)

    for p in (p_near, p_search, p_route):
        p.add_argument("--category", help="road / river / dam / weir")
        p.add_argument("--pref", help="都道府県名（例: 静岡県）")
        p.add_argument("--with-image", action="store_true", help="映像が出せるカメラだけ")
        p.add_argument("--json", action="store_true", help="JSONで出す")

    args = ap.parse_args()
    db = load()

    if args.cmd == "info":
        print(f"📋 ライブカメラ台帳　更新: {db['updated'][:10]}")
        print(f"   総数 {db['count']} 台 / 映像を出せる {db['withImage']} 台 / 市区町村つき {db['withPlace']} 台")
        print("   種類別: " + " / ".join(f"{k} {v}台" for k, v in sorted(db["byCategory"].items())))
        print("   情報源:")
        for s in db["sources"]:
            print(f"     ・{s['name']}（{s['count']}台）")
        return 0

    kw = {}
    if args.category:
        kw["category"] = args.category
    if args.pref:
        kw["pref"] = args.pref
    if args.with_image:
        kw["with_image"] = True

    if args.cmd == "near":
        _show(near(db, args.lat, args.lon, args.radius, args.limit, **kw), args.json)
    elif args.cmd == "route":
        pts = []
        for text in args.points:
            try:
                lat, lon = (float(v) for v in text.split(","))
            except ValueError:
                print(f"⚠️ 「{text}」は 緯度,経度 の形になっていません", file=sys.stderr)
                return 1
            pts.append([lat, lon])
        if len(pts) < 2:
            print("⚠️ 地点を2つ以上ならべてください（例: 35.17,136.88 34.70,137.73）",
                  file=sys.stderr)
            return 1
        _show(along_route(db, pts, args.radius, **kw)[:args.limit], args.json)
    else:
        _show(search(db, args.keyword, **kw)[:args.limit], args.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
