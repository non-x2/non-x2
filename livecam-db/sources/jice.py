#!/usr/bin/env python3
"""情報源①：国土技術研究センター（JICE）の「道路チェック地図」「河川チェック地図」。

国土交通省 各地方整備局などが公開しているライブカメラを、
JICE が地図データ（GeoJSON）としてまとめて公開しているものです。

  - 道路ライブカメラ … https://www.jice.or.jp/knowledge/maps/roads
  - 河川ライブカメラ … https://www.jice.or.jp/knowledge/maps/rivers

どちらも中身の形は同じなので、この1つの係で両方読み取ります。

GeoJSON の1件は、こんな形をしています（説明文がHTMLで入っている）:

    properties.title       … 路線名・河川名（例:「国道1号」「桂沢ダム」）
    properties.discription … <img src='写真URL'> と <a href='ページURL'> と
                             【ライブカメラの管理者・出典元】が入ったHTML

外部のライブラリは使いません（Python 3 の標準機能だけ）。
"""

from __future__ import annotations

import re

from .base import fetch_json, in_japan, tidy

# この情報源の名札
SOURCES = {
    "jice-roads": {
        "name": "国土技術研究センター 道路チェック地図（道路ライブカメラ）",
        "page": "https://www.jice.or.jp/knowledge/maps/roads",
        "data": "https://www.jice.or.jp/cms/gis/roads.geojson",
        "category": "road",
        "note": "国土交通省 各地方整備局ほかが公開する道路ライブカメラの位置",
    },
    "jice-rivers": {
        "name": "国土技術研究センター 河川チェック地図（河川ライブカメラ）",
        "page": "https://www.jice.or.jp/knowledge/maps/rivers",
        "data": "https://www.jice.or.jp/cms/gis/rivers.geojson",
        "category": "river",
        "note": "国土交通省 各地方整備局ほかが公開する河川・ダムのライブカメラの位置",
    },
}

# 写真が無いカメラに使われている「準備中」画像。これは写真として扱いません。
NO_IMAGE_MARK = "no_link.jpg"


def tidy_name(name: str) -> str:
    """名前の表記ゆれをそろえる（「国道 7号」→「国道7号」など）。"""
    name = tidy(name)
    name = re.sub(r"^国道\s+", "国道", name)
    name = re.sub(r"^(国道\d+)\s*号", r"\1号", name)
    return name


def guess_category(default: str, name: str) -> str:
    """名前から、もう少し細かい種類を推測する。"""
    if default == "river":
        if "ダム" in name:
            return "dam"
        if "堰" in name or "水門" in name:
            return "weir"
        return "river"
    return default


def parse_feature(feature: dict, source_id: str, category: str) -> dict | None:
    """地図データ1件から、台帳に必要な情報だけ取り出す。"""
    geom = feature.get("geometry") or {}
    coords = geom.get("coordinates") or []
    if geom.get("type") != "Point" or len(coords) < 2:
        return None
    try:
        lon, lat = float(coords[0]), float(coords[1])
    except (TypeError, ValueError):
        return None
    if not in_japan(lat, lon):
        return None

    props = feature.get("properties") or {}
    desc = props.get("discription") or props.get("description") or ""

    # 写真のURL（<img src='...'>）。「準備中」画像は写真として数えない。
    img = None
    for src in re.findall(r"<img[^>]*src='([^']+)'", desc):
        if NO_IMAGE_MARK not in src:
            img = src
            break

    # カメラのページ（最初の <a href='...'>）
    links = re.findall(r"<a href='([^']+)'", desc)
    page = links[0] if links else None

    # 管理者・出典元の名前
    m = re.search(
        r"【ライブカメラの管理者・出典元】\s*<br>\s*<a href='[^']*'[^>]*>([^<]+)</a>",
        desc,
    )
    owner = tidy(m.group(1)) if m else ""

    name = tidy_name(props.get("title", ""))
    if not name:
        return None

    return {
        "src": source_id,
        "cat": guess_category(category, name),
        "name": name,
        "place": "",          # 市区町村名は後から付ける
        "lat": round(lat, 6),
        "lon": round(lon, 6),
        "img": img,           # 後で https で開けるか確認する
        "page": page,
        "owner": owner,
    }


def collect(source_id: str) -> list[dict]:
    """1つの情報源からカメラを取ってくる。"""
    info = SOURCES[source_id]
    raw = fetch_json(info["data"])
    features = raw.get("features") or []
    if not features:
        raise RuntimeError(f"{info['name']} のデータが空でした")

    cams = []
    for feature in features:
        cam = parse_feature(feature, source_id, info["category"])
        if cam:
            cams.append(cam)
    return cams


def collect_all(only: list[str] | None = None) -> tuple[list[dict], list[dict]]:
    """道路・河川の両方を取ってくる。返り値は（カメラ一覧, 情報源の記録）。

    `only` を渡すと、その情報源だけを取ってきます（例: ["jice-roads"]）。
    いらないデータを取りに行かないので速く終わります。
    """
    cams: list[dict] = []
    used: list[dict] = []
    for source_id, info in SOURCES.items():
        if only and source_id not in only and "jice" not in only:
            continue
        got = collect(source_id)
        print(f"  ✅ {info['name']}: {len(got)} 件")
        cams.extend(got)
        used.append({
            "id": source_id,
            "name": info["name"],
            "page": info["page"],
            "data": info["data"],
            "count": len(got),
            "note": info["note"],
        })
    return cams, used
