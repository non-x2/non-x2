#!/usr/bin/env python3
"""情報源③：🇺🇸 アイオワ州交通局（Iowa DOT）の道路ライブカメラ（🌍 世界台帳・試験導入の第1号）。

米国の州で「機械で読める一括データ」と「はっきりした利用許可」の両方が
そろっている、めずらしい情報源です（2026-08-16 の調査で5州を比べて選定）。

  台帳データ … https://data.iowadot.gov/datasets/IowaDOT::traffic-cameras-3.geojson
               （GeoJSON形式・鍵なしで1回のアクセスで全件取れる）
  一般向けページ … https://511ia.org/ （アイオワ州公式の交通情報サイト）

📄 利用条件（ここが大事）
    データセットのページに **CC BY 4.0**（出典を書けば、商用利用も含めて
    コピー・共有・改変が自由）と明記されています。さらにアイオワDOT公式の
    利用規約ページでも「出典を適切に表示すること」が条件と確認済み。
    → https://iowadot.gov/policies_and_statements/terms-of-use#gis
    出典表記の推奨文言（データに記載されているもの）:
    "Iowa Department of Transportation - Office of Traffic Operations"

⚠️ 日本の情報源とのちがい
    - 写真URLは**最初から https://** なので、読み替えは不要（開けるかの確認だけする）
    - 市区町村付け（国土地理院＝日本専用）は使えないため、place は
      「アメリカ・アイオワ州」で固定にしています

外部のライブラリは使いません（Python 3 の標準機能だけ）。
"""

from __future__ import annotations

from .base import fetch_json, tidy

DATA_URL = "https://data.iowadot.gov/datasets/IowaDOT::traffic-cameras-3.geojson"
PAGE_URL = "https://511ia.org/"

SOURCE = {
    "id": "us-iowa",
    "name": "アイオワ州交通局（Iowa DOT）道路ライブカメラ",
    "page": PAGE_URL,
    "data": DATA_URL,
    "license": "CC BY 4.0（出典を書けば商用利用も含め再利用可）",
    "attribution": "Iowa Department of Transportation - Office of Traffic Operations",
    "note": "🌍 世界台帳の試験導入・第1号。高速道路（I-系）・一般道・休憩施設・道路気象カメラを含む",
}

# アイオワ州のだいたいの範囲（ここから外れる座標はまちがいとみなす）
IOWA_BOUNDS = (40.0, 44.0, -97.0, -89.5)  # 南, 北, 西, 東


def _in_iowa(lat: float, lon: float) -> bool:
    s, n, w, e = IOWA_BOUNDS
    return s <= lat <= n and w <= lon <= e


def collect_all(only: list[str] | None = None) -> tuple[list[dict], list[dict]]:
    """アイオワ州のカメラを取ってくる。返り値は（カメラ一覧, 情報源の記録）。"""
    if only and SOURCE["id"] not in only:
        return [], []

    data = fetch_json(DATA_URL, timeout=90)
    feats = data.get("features") or []
    if not feats:
        raise RuntimeError("アイオワ州のカメラ一覧が空でした")

    cams = []
    for feat in feats:
        prop = feat.get("properties") or {}
        try:
            lat = float(prop["latitude"])
            lon = float(prop["longitude"])
        except (KeyError, TypeError, ValueError):
            continue
        if not _in_iowa(lat, lon):
            continue

        img = tidy(prop.get("ImageURL"))
        if not img.startswith("https://"):
            # 写真URLが無い・httpsでないカメラは、確認のしようがないので入れない
            continue
        if "cameraunavailable" in img.lower():
            # 「カメラは利用できません」というお知らせ画像が写真URL欄に入っているカメラ。
            # そのまま出すと「今の様子」ではない画像を見せてしまうので、写真なし扱いにする
            # （カメラ自体は残し、公式ページへの案内にする）
            img = None

        name = tidy(prop.get("Desc_")) or tidy(prop.get("ImageName")) or "Traffic Camera"
        route = tidy(prop.get("Route"))
        # 州間高速道路（Interstate＝「I-80」のような路線名）は日本の台帳の「高速」に合わせる
        cat = "expressway" if route.startswith("I-") else "road"

        cams.append({
            "src": SOURCE["id"],
            "cat": cat,
            "name": name,
            "place": "アメリカ・アイオワ州",
            "lat": round(lat, 6),
            "lon": round(lon, 6),
            "img": img,
            "page": PAGE_URL,
            "owner": "アイオワ州交通局（Iowa DOT）",
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
