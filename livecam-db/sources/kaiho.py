#!/usr/bin/env python3
"""情報源②：海上保安庁 ライブカメラ（灯台・港・岬）。

全国の灯台などに設置されたライブカメラです。
JICE（道路・河川）とは重ならない「海」のカメラなので、台帳の穴を埋めてくれます。

  カメラ一覧  … https://camera.mics.kaiho.mlit.go.jp/camportalAPI/camera/getlist
  写真        … https://camera.mics.kaiho.mlit.go.jp/camportalAPI/camera/getthumbnail?id=◯
  カメラページ … https://camera.mics.kaiho.mlit.go.jp/camstream/{base_name}/

📄 利用条件（ここが大事）
    海上保安庁のサイトのコンテンツには **公共データ利用規約（第1.0版・PDL1.0）** が
    適用されており、**出典を書けば再利用してよい**と明記されています。
    そこで台帳の情報源欄に「出典：海上保安庁ホームページ」を必ず残し、
    ページにも管理者名として表示します。
    → https://www.kaiho.mlit.go.jp/questions/post-1.html

外部のライブラリは使いません（Python 3 の標準機能だけ）。
"""

from __future__ import annotations

from .base import fetch_json, in_japan, tidy

BASE = "https://camera.mics.kaiho.mlit.go.jp"
LIST_URL = f"{BASE}/camportalAPI/camera/getlist"
THUMB_URL = f"{BASE}/camportalAPI/camera/getthumbnail?id="
PAGE_URL = f"{BASE}/camstream/"

SOURCE = {
    "id": "kaiho",
    "name": "海上保安庁 ライブカメラ（灯台・港・岬）",
    "page": "https://camera.mics.kaiho.mlit.go.jp/",
    "data": LIST_URL,
    "license": "公共データ利用規約（第1.0版）PDL1.0",
    "attribution": "出典：海上保安庁ホームページ（https://camera.mics.kaiho.mlit.go.jp/）",
    "note": "灯台などに設置されたライブカメラ。道路・河川のカメラとは重ならない「海」の情報",
}


def collect_all(only: list[str] | None = None) -> tuple[list[dict], list[dict]]:
    """海上保安庁のカメラを取ってくる。返り値は（カメラ一覧, 情報源の記録）。"""
    if only and SOURCE["id"] not in only:
        return [], []

    data = fetch_json(LIST_URL)
    items = data.get("live_camera_list") or []
    if not items:
        raise RuntimeError("海上保安庁のカメラ一覧が空でした")

    cams = []
    for item in items:
        try:
            lat = float(item["latitude"])
            lon = float(item["longitude"])
        except (KeyError, TypeError, ValueError):
            continue
        if not in_japan(lat, lon):
            continue

        cam_id = item.get("id")
        base_name = tidy(item.get("base_name"))
        # 管理者は「◯◯海上保安部」。無ければ管区名を使う。
        owner = tidy(item.get("hoanbu")) or tidy(item.get("kanku"))

        cams.append({
            "src": SOURCE["id"],
            "cat": "sea",
            "name": tidy(item.get("jp_name")) or "ライブカメラ",
            "place": "",                       # 市区町村名は build.py が付けます
            "lat": round(lat, 6),
            "lon": round(lon, 6),
            "img": f"{THUMB_URL}{cam_id}" if cam_id is not None else None,
            "page": f"{PAGE_URL}{base_name}/" if base_name else SOURCE["page"],
            "owner": f"海上保安庁 {owner}".strip(),
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
