#!/usr/bin/env python3
"""情報源⑤：🇫🇮 フィンランドの道路気象カメラ（Fintraffic / Digitraffic weathercam）。

🌍 世界台帳の3つ目の情報源です（アイオワ州・BC州に続く）。
毎月20日の「🌍 世界カメラ情報源の定期調査」（2026-09）で見つかった有望候補を、
2026-09-24 に取り込みました。

  台帳データ … https://tie.digitraffic.fi/api/weathercam/v1/stations
               （GeoJSON・鍵なしで1回のアクセスで全件（約810地点）取れる）
  写真       … https://weathercam.digitraffic.fi/<向きの番号>.jpg
  一般向けページ … https://liikennetilanne.fintraffic.fi/  （Fintraffic公式の交通状況サイト）

📄 利用条件（ここが大事）
    Digitraffic の利用条件に **Creative Commons 4.0 By（CC BY 4.0）** と明記されています。
    商用利用も含めて再利用でき、条件は**出典を書くことだけ**です。
      → https://www.digitraffic.fi/en/terms-of-service/
    推奨されている出典の文言（**消さないこと**）:
    "Source: Fintraffic / digitraffic.fi, license CC 4.0 BY"

⚠️ 取り込むときの判断
    - 1地点に最大で数方向のカメラ（preset＝向き）があります（810地点・約2,270方向）。
      ページを重くしないため **1地点＝1台** とし、写真は「いま撮影中」のいちばん目の向きを使います。
      ほかの向きは公式サイトで見られます。
    - このAPIは **gzip で受け取ると宣言しないと断られる**ので、専用の取り方をしています。
    - 名前の頭の vt（国道）・kt（主要道）・st（地域道）などは道路の格ですが、
      **高速道路かどうかは分からない**ので、決めつけずに全部「道路」（road）として扱います。
    - 一時的に撤去中（REMOVED_TEMPORARILY）の地点は、古い写真を「今の様子」として見せないため写真なし扱い。
    - 写真の更新はおおむね10分ごとです（ページの30秒ごとの撮り直しでも、写真が変わるのは10分おき）。

外部のライブラリは使いません（Python 3 の標準機能だけ）。
"""

from __future__ import annotations

import gzip
import json
import urllib.request

from .base import TIMEOUT, USER_AGENT, tidy

DATA_URL = "https://tie.digitraffic.fi/api/weathercam/v1/stations"
PAGE_URL = "https://liikennetilanne.fintraffic.fi/"
IMG_BASE = "https://weathercam.digitraffic.fi/"

SOURCE = {
    "id": "fi-digitraffic",
    "name": "フィンランド 道路気象カメラ（Fintraffic / Digitraffic weathercam）",
    "page": PAGE_URL,
    "data": DATA_URL,
    "license": "CC BY 4.0（出典を書けば商用利用も含め再利用可）",
    "attribution": "Source: Fintraffic / digitraffic.fi, license CC 4.0 BY",
    "note": "🌍 世界台帳の3つ目の情報源。1地点＝1台（いちばん目の向きの写真）",
}

# フィンランド（オーランド諸島を含む）のだいたいの範囲（ここから外れる座標はまちがいとみなす）
FI_BOUNDS = (59.0, 70.5, 19.0, 32.0)  # 南, 北, 西, 東


def _in_finland(lat: float, lon: float) -> bool:
    s, n, w, e = FI_BOUNDS
    return s <= lat <= n and w <= lon <= e


def _fetch_gzip_json(url: str):
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept-Encoding": "gzip",
        # Digitraffic は利用者の名乗りを求めている（任意だが礼儀として）
        "Digitraffic-User": "non-x2/livecam-db",
    })
    with urllib.request.urlopen(req, timeout=TIMEOUT) as res:
        body = res.read()
        if res.headers.get("Content-Encoding", "").lower() == "gzip":
            body = gzip.decompress(body)
    return json.loads(body.decode("utf-8"))


def collect_all(only: list[str] | None = None) -> tuple[list[dict], list[dict]]:
    """フィンランドのカメラを取ってくる。返り値は（カメラ一覧, 情報源の記録）。"""
    if only and SOURCE["id"] not in only:
        return [], []

    data = _fetch_gzip_json(DATA_URL)
    features = (data or {}).get("features") or []
    if not features:
        raise RuntimeError("フィンランドのカメラ一覧が空でした")

    cams = []
    for ft in features:
        coords = (ft.get("geometry") or {}).get("coordinates") or []
        if len(coords) < 2:
            continue
        try:
            lon = float(coords[0])
            lat = float(coords[1])
        except (TypeError, ValueError):
            continue
        if not _in_finland(lat, lon):
            continue

        props = ft.get("properties") or {}
        presets = [p for p in props.get("presets") or [] if p.get("inCollection") and p.get("id")]
        img = f"{IMG_BASE}{presets[0]['id']}.jpg" if presets else None
        if props.get("collectionStatus") != "GATHERING":
            img = None

        # 例: "vt8_Pori_Vuoltee" → "vt8 Pori Vuoltee"
        name = tidy((props.get("name") or "").replace("_", " ")) or f"Weathercam {props.get('id', '')}"

        cams.append({
            "src": SOURCE["id"],
            "cat": "road",
            "name": name,
            "place": "フィンランド",
            "lat": round(lat, 6),
            "lon": round(lon, 6),
            "img": img,
            "page": PAGE_URL,
            "owner": "Fintraffic（フィンランドの国営交通管制会社）",
        })

    print(f"  ✅ {SOURCE['name']}: {len(cams)} 件")
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
