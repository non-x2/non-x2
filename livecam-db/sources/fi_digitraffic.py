#!/usr/bin/env python3
"""情報源⑤：🇫🇮 フィンランドの道路気象カメラ（Fintraffic Digitraffic）。

🌍 世界台帳の3つ目の情報源です（1つ目はアイオワ州、2つ目はBC州）。
毎月20日の「🌍 世界カメラ情報源の定期調査」（2026-10）で見つかり、
2026-11-04 に取り込みました。

  台帳データ … https://tie.digitraffic.fi/api/weathercam/v1/stations
               （GeoJSON・鍵なしで1回のアクセスで全件（約810地点）取れる）
  写真       … https://weathercam.digitraffic.fi/<プリセット番号>.jpg
  一般向けページ … https://liikennetilanne.fintraffic.fi/ （フィンランド公式の交通情報）

📄 利用条件（ここが大事）
    Digitraffic の利用規約に「Fintraffic のオープンデータは
    Creative Commons 4.0 BY で提供。商用も含めて配布・改変してよい。条件は出典を書くこと」と明記。
      → https://www.digitraffic.fi/en/terms-of-service/
    規約が示している出典の書き方（**消さないこと**）:
    "Source: Fintraffic / digitraffic.fi, license CC 4.0 BY"

⚠️ 取り込むときの判断
    - **1地点＝1台**にしています。1つの地点には向きの違うカメラ（プリセット）が
      2〜4枚あり（全部で約2,300枚）、全部入れると同じ場所に点が重なるうえ、
      ページも重くなるためです。写真は「道路の進行方向」を写したものを優先し、
      路面だけを写すもの（番号の末尾が 09）は、ほかが無いときだけ使います。
    - 名前は一覧の `vt2_Karkkila_Korpi` のような形から「Road 2 Karkkila Korpi」を作ります。
      地点ごとの詳しい情報（自治体名など）は1地点ずつ聞かないと取れず、
      約810回のアクセスになって相手の負担になるので、**聞きにいきません**。
    - **高速道路の区別はしていません**（全部 `road`）。路線番号（vt＝国道など）は
      道路の格であって高速かどうかではないため、BC州と同じく決めつけません。
    - 一時停止中の地点（`REMOVED_TEMPORARILY` など）は入れません。
    - 規約のお願いに従い、アクセスには `Digitraffic-User` という名乗りの見出しを付けます。

外部のライブラリは使いません（Python 3 の標準機能だけ）。
"""

from __future__ import annotations

import gzip
import json
import re

from .base import TIMEOUT, open_url, tidy

DATA_URL = "https://tie.digitraffic.fi/api/weathercam/v1/stations"
PAGE_URL = "https://liikennetilanne.fintraffic.fi/"
IMG_BASE = "https://weathercam.digitraffic.fi/"

SOURCE = {
    "id": "fi-digitraffic",
    "name": "フィンランド 道路気象カメラ（Fintraffic Digitraffic）",
    "page": PAGE_URL,
    "data": DATA_URL,
    "license": "CC BY 4.0（出典を書けば商用利用も含め再利用可）",
    "attribution": "Source: Fintraffic / digitraffic.fi, license CC 4.0 BY",
    "note": "🌍 世界台帳の3つ目の情報源。1地点につき写真1枚（向きの違うカメラは代表1枚だけ）",
}

# フィンランドのだいたいの範囲（ここから外れる座標はまちがいとみなす）
FI_BOUNDS = (59.3, 70.2, 19.0, 31.7)  # 南, 北, 西, 東

# 名前の先頭の「道路の格」。どれも Road（Tie）として表示する
ROAD_PREFIX = re.compile(r"^(vt|kt|st|yt|mt)(\d+)[_\s]*(.*)$", re.IGNORECASE)

# 路面だけを写すプリセット（番号の末尾）。景色が分かりにくいので後回しにする
SURFACE_SUFFIX = "09"


def _fetch(url: str):
    # Digitraffic は圧縮（gzip）を受け取れると名乗らないと 406 で断ってくる
    headers = {"Digitraffic-User": "nonlabo-livecam", "Accept-Encoding": "gzip"}
    with open_url(url, TIMEOUT * 3, headers=headers) as res:
        body = res.read()
        if res.headers.get("Content-Encoding", "").lower() == "gzip":
            body = gzip.decompress(body)
    return json.loads(body.decode("utf-8"))


def _name(raw: str, station_id: str) -> str:
    text = tidy(raw)
    m = ROAD_PREFIX.match(text)
    if m:
        rest = tidy(m.group(3).replace("_", " "))
        return f"Road {m.group(2)} {rest}".strip()
    return tidy(text.replace("_", " ")) or f"Weathercam {station_id}"


def _pick_preset(presets: list[dict]) -> str | None:
    ids = [p.get("id") for p in presets if p.get("inCollection") and p.get("id")]
    if not ids:
        return None
    ids.sort()
    for pid in ids:
        if not pid.endswith(SURFACE_SUFFIX):
            return pid
    return ids[0]


def _in_fi(lat: float, lon: float) -> bool:
    s, n, w, e = FI_BOUNDS
    return s <= lat <= n and w <= lon <= e


def collect_all(only: list[str] | None = None) -> tuple[list[dict], list[dict]]:
    """フィンランドのカメラを取ってくる。返り値は（カメラ一覧, 情報源の記録）。"""
    if only and SOURCE["id"] not in only:
        return [], []

    data = _fetch(DATA_URL)
    features = (data or {}).get("features") or []
    if not features:
        raise RuntimeError("フィンランドのカメラ一覧が空でした")

    cams = []
    paused = 0
    for f in features:
        props = f.get("properties") or {}
        if props.get("collectionStatus") != "GATHERING":
            paused += 1
            continue
        coords = (f.get("geometry") or {}).get("coordinates") or []
        if len(coords) < 2:
            continue
        try:
            lon = float(coords[0])
            lat = float(coords[1])
        except (TypeError, ValueError):
            continue
        if not _in_fi(lat, lon):
            continue

        station_id = props.get("id") or f.get("id") or ""
        preset = _pick_preset(props.get("presets") or [])

        cams.append({
            "src": SOURCE["id"],
            # 高速かどうかを見分ける印がデータに無いため、決めつけずに全部「道路」にする
            "cat": "road",
            "name": _name(props.get("name") or "", station_id),
            "place": "フィンランド",
            "lat": round(lat, 6),
            "lon": round(lon, 6),
            "img": f"{IMG_BASE}{preset}.jpg" if preset else None,
            "page": PAGE_URL,
            "owner": "フィンランド交通管理会社（Fintraffic）",
        })

    print(f"  ✅ {SOURCE['name']}: {len(cams)} 件"
          f"（一時停止中などの {paused} 地点は取り込みませんでした）")
    used = [{
        "id": SOURCE["id"],
        "name": SOURCE["name"],
        "page": SOURCE["page"],
        "data": SOURCE["data"],
        "count": len(cams),
        "license": SOURCE["license"],
        "attribution": SOURCE["attribution"],
        "note": SOURCE["note"],
    }]
    return cams, used
