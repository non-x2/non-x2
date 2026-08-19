#!/usr/bin/env python3
"""情報源④：🇨🇦 カナダ ブリティッシュコロンビア州の道路ライブカメラ（DriveBC HighwayCams）。

🌍 世界台帳の2つ目の情報源です（1つ目はアイオワ州）。
毎月20日の「🌍 世界カメラ情報源の定期調査」（2026-08）で見つかった有望候補を、
2026-08-19 に取り込みました。

  台帳データ … https://www.drivebc.ca/api/webcams/
               （JSON形式・鍵なしで1回のアクセスで全件（1,060台）取れる）
  一般向けページ … https://www.drivebc.ca/  （BC州公式の道路情報サイト）

📄 利用条件（ここが大事）
    BC州の公式データカタログで、データセット「DriveBC HighwayCams」の
    ライセンスが **Open Government Licence - British Columbia** と明記されています。
    複製・改変・配布・商用利用まで認められ、条件は**出典を書くことだけ**です。
      → https://catalogue.data.gov.bc.ca/dataset/bc-highway-cams
      → ライセンス本文: https://www2.gov.bc.ca/gov/content?id=A519A56BC2BF44E4A008B33FCF527F61
    ライセンス本文が指定している出典の文言（**消さないこと**）:
    "Contains information licensed under the Open Government Licence – British Columbia."

⚠️ 取り込むときの大事な判断：`credit` 欄の扱い
    データには `credit` という自由記述の欄があり、**82台**に何か書かれています。
    ただしこれは「提供元」専用の欄ではなく、**運用のお知らせも混ざっています**。

      ・他所が写真を提供している例（34台）… "Images courtesy of TransLink" /
        "Camera images provided by Parks Canada." / "City of Vancouver" など
      ・ただの運用メモの例（48台）… 「太陽光発電なので遅れることがあります」
        「監視のため向きが変わることがあります」「ライオンズゲート橋は対面通行」など

    → **他所が写真を提供していると読める言い回しのものだけ**を除いています（34台）。
      82台を丸ごと除くと、州が自分で運用している**48台を誤って捨てる**ことになります。
      逆に1台も除かないと、州のライセンスの外にあるかもしれない写真を載せてしまいます。

⚠️ 日本の情報源とのちがい
    - 写真URLは**最初から https://** なので、読み替えは不要（開けるかの確認だけする）
    - 市区町村付け（国土地理院＝日本専用）は使えないため、place は
      データに入っている地域名（region_name）を使って「カナダ・BC州（Lower Mainland）」の形にする
    - **高速道路の区別はしていません**（`cat` は全部 `road`）。
      アイオワ州は路線名が「I-80」のように高速だと分かりましたが、BC州のデータには
      高速かどうかを見分けられる印がありません。**分からないものを決めつけない**ため、
      全部「道路」として扱います。

外部のライブラリは使いません（Python 3 の標準機能だけ）。
"""

from __future__ import annotations

import re

from .base import fetch_json, tidy

DATA_URL = "https://www.drivebc.ca/api/webcams/"
PAGE_URL = "https://www.drivebc.ca/"
IMG_BASE = "https://www.drivebc.ca/images/"

SOURCE = {
    "id": "ca-bc",
    "name": "ブリティッシュコロンビア州 道路ライブカメラ（DriveBC HighwayCams）",
    "page": PAGE_URL,
    "data": DATA_URL,
    "license": "Open Government Licence – British Columbia（出典を書けば商用利用も含め再利用可）",
    "attribution": "Contains information licensed under the Open Government Licence – British Columbia.",
    "note": "🌍 世界台帳の2つ目の情報源。他所が写真を提供しているカメラは除いてある",
}

# 「他所が写真を提供している」と読める言い回し。これに当たるカメラは取り込まない。
# ⚠️ 安全側に少し広めにしてある（例：「Camera power provided by ...」は電源の話だが、
#    紛らわしいので除く。2台だけなので、取りこぼすより安全）。
THIRD_PARTY_CREDIT = re.compile(
    r"provided by|courtesy of|co-?operation with|installed and maintained by",
    re.IGNORECASE,
)

# BC州のだいたいの範囲（ここから外れる座標はまちがいとみなす）
BC_BOUNDS = (48.0, 60.5, -139.5, -113.5)  # 南, 北, 西, 東

# 地域名（データの region_name）を日本語に。知らない名前はそのまま出す。
REGION_JA = {
    "Lower Mainland": "ローワーメインランド",
    "Vancouver Island": "バンクーバー島",
    "Southern Interior": "南部内陸",
    "Northern": "北部",
    "Border Cams": "国境",
}


def _in_bc(lat: float, lon: float) -> bool:
    s, n, w, e = BC_BOUNDS
    return s <= lat <= n and w <= lon <= e


def collect_all(only: list[str] | None = None) -> tuple[list[dict], list[dict]]:
    """BC州のカメラを取ってくる。返り値は（カメラ一覧, 情報源の記録）。"""
    if only and SOURCE["id"] not in only:
        return [], []

    items = fetch_json(DATA_URL, timeout=90)
    if not isinstance(items, list) or not items:
        raise RuntimeError("BC州のカメラ一覧が空でした")

    cams = []
    skipped_credit = 0
    for it in items:
        coords = (it.get("location") or {}).get("coordinates") or []
        if len(coords) < 2:
            continue
        try:
            lon = float(coords[0])
            lat = float(coords[1])
        except (TypeError, ValueError):
            continue
        if not _in_bc(lat, lon):
            continue

        # 他所が写真を提供しているカメラは、州のライセンスの外にあるかもしれないので取り込まない
        if THIRD_PARTY_CREDIT.search(it.get("credit") or ""):
            skipped_credit += 1
            continue

        cam_id = it.get("id")
        if cam_id is None:
            continue

        # 写真URL。`links.imageDisplay` は「?t=時刻」つきで古くなるので、
        # 番号から組み立てた安定した形を使う（実際にJPEGが返ることを確認済み）。
        img = f"{IMG_BASE}{cam_id}.jpg"
        if not it.get("https_cam", True):
            img = None  # httpsで見られないカメラは、ページ内に出せないので写真なし扱い
        elif not it.get("is_on", True):
            # 止まっているカメラ。古い写真を「今の様子」として見せないため写真なし扱いにする
            # （カメラ自体は残し、公式ページへの案内にする）
            img = None

        name = tidy(it.get("name_override")) or tidy(it.get("name")) or f"BC HighwayCam {cam_id}"
        highway = tidy(str(it.get("highway") or ""))
        if highway:
            name = f"Hwy {highway} {name}"

        region = tidy(it.get("region_name"))
        region_ja = REGION_JA.get(region, region)
        place = f"カナダ・BC州（{region_ja}）" if region_ja else "カナダ・BC州"

        cams.append({
            "src": SOURCE["id"],
            # 高速かどうかを見分ける印がデータに無いため、決めつけずに全部「道路」にする
            "cat": "road",
            "name": name,
            "place": place,
            "lat": round(lat, 6),
            "lon": round(lon, 6),
            "img": img,
            "page": PAGE_URL,
            "owner": "ブリティッシュコロンビア州 交通・運輸省（BC Ministry of Transportation and Transit）",
        })

    print(f"  ✅ {SOURCE['name']}: {len(cams)} 件"
          f"（他所が写真を提供している {skipped_credit} 台は取り込みませんでした）")
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
