#!/usr/bin/env python3
"""気象庁の台風情報を取ってきて、ページが読む形（data/latest.json）に整えて保存する。

これは「人のかわりに調べてくれる係」です。
GitHub Actions が定期的にこれを走らせるので、Claude を開かなくてもページが新しくなります。

使い方（手で試すとき）:
    python3 typhoon-app/scripts/fetch_typhoon.py

外部のライブラリは使いません（Python 3 の標準機能だけ）。
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = "https://www.jma.go.jp/bosai/typhoon/data"
TARGET_URL = f"{BASE}/targetTc.json"
WARNING_DIR = "https://www.jma.go.jp/bosai/warning/data/warning"
OUT_PATH = Path(__file__).resolve().parent.parent / "data" / "latest.json"
JST = timezone(timedelta(hours=9))
TIMEOUT = 30
USER_AGENT = "non-x2-typhoon-app/1.0 (+https://github.com/non-x2/non-x2)"

# ------------------------------------------------------------------ 警報・注意報の決まりごと
#
# 台風のときに気をつける5種類だけを拾います（雷や乾燥などの平常時の注意報は
# 防災ページ bousai-app/ の担当なので、ここでは扱いません）。
#
# 数字は気象庁が決めているコード。「35」なら暴風特別警報、という具合です。
# コード → (種類のキー, 重さ, 正式な呼び名)
WARNING_CODES = {
    "35": ("wind", "特別警報", "暴風特別警報"),
    "05": ("wind", "警報", "暴風警報"),
    "15": ("wind", "注意報", "強風注意報"),  # 暴風の注意報は「強風注意報」という名前
    "37": ("wave", "特別警報", "波浪特別警報"),
    "07": ("wave", "警報", "波浪警報"),
    "16": ("wave", "注意報", "波浪注意報"),
    "38": ("surge", "特別警報", "高潮特別警報"),
    "08": ("surge", "警報", "高潮警報"),
    "19": ("surge", "注意報", "高潮注意報"),
    "33": ("rain", "特別警報", "大雨特別警報"),
    "03": ("rain", "警報", "大雨警報"),
    "10": ("rain", "注意報", "大雨注意報"),
    "04": ("flood", "警報", "洪水警報"),  # 洪水に特別警報はない
    "18": ("flood", "注意報", "洪水注意報"),
}
KIND_ORDER = ["wind", "wave", "surge", "rain", "flood"]  # 並べる順番（危ない順）
RANK = {"注意報": 1, "警報": 2, "特別警報": 3}  # 数が大きいほど重い
ACTIVE_STATUS = {"発表", "継続"}  # この状態のものだけ「いま出ている」と数える

# 全国の予報区（府県など）。code: (名前, 地方ブロック)
# ※ index.html の OFFICES、bousai-app 側の同名の表と同じ内容。直すときはそろえること。
OFFICES = {
    "011000": ("宗谷地方", "北海道"),
    "012000": ("上川・留萌地方", "北海道"),
    "013000": ("網走・北見・紋別地方", "北海道"),
    "014030": ("十勝地方", "北海道"),
    "014100": ("釧路・根室地方", "北海道"),
    "015000": ("胆振・日高地方", "北海道"),
    "016000": ("石狩・空知・後志地方", "北海道"),
    "017000": ("渡島・檜山地方", "北海道"),
    "020000": ("青森県", "東北"),
    "030000": ("岩手県", "東北"),
    "040000": ("宮城県", "東北"),
    "050000": ("秋田県", "東北"),
    "060000": ("山形県", "東北"),
    "070000": ("福島県", "東北"),
    "080000": ("茨城県", "関東・甲信"),
    "090000": ("栃木県", "関東・甲信"),
    "100000": ("群馬県", "関東・甲信"),
    "110000": ("埼玉県", "関東・甲信"),
    "120000": ("千葉県", "関東・甲信"),
    "130000": ("東京都", "関東・甲信"),
    "140000": ("神奈川県", "関東・甲信"),
    "190000": ("山梨県", "関東・甲信"),
    "200000": ("長野県", "関東・甲信"),
    "150000": ("新潟県", "北陸"),
    "160000": ("富山県", "北陸"),
    "170000": ("石川県", "北陸"),
    "180000": ("福井県", "北陸"),
    "210000": ("岐阜県", "東海"),
    "220000": ("静岡県", "東海"),
    "230000": ("愛知県", "東海"),
    "240000": ("三重県", "東海"),
    "250000": ("滋賀県", "近畿"),
    "260000": ("京都府", "近畿"),
    "270000": ("大阪府", "近畿"),
    "280000": ("兵庫県", "近畿"),
    "290000": ("奈良県", "近畿"),
    "300000": ("和歌山県", "近畿"),
    "310000": ("鳥取県", "中国"),
    "320000": ("島根県", "中国"),
    "330000": ("岡山県", "中国"),
    "340000": ("広島県", "中国"),
    "350000": ("山口県", "中国"),
    "360000": ("徳島県", "四国"),
    "370000": ("香川県", "四国"),
    "380000": ("愛媛県", "四国"),
    "390000": ("高知県", "四国"),
    "400000": ("福岡県", "九州"),
    "410000": ("佐賀県", "九州"),
    "420000": ("長崎県", "九州"),
    "430000": ("熊本県", "九州"),
    "440000": ("大分県", "九州"),
    "450000": ("宮崎県", "九州"),
    "460100": ("鹿児島県（奄美地方除く）", "九州"),
    "460040": ("奄美地方", "九州"),
    "471000": ("沖縄本島地方", "沖縄"),
    "472000": ("大東島地方", "沖縄"),
    "473000": ("宮古島地方", "沖縄"),
    "474000": ("八重山地方", "沖縄"),
}


def fetch_json(url: str):
    """URLからJSONを取ってくる。失敗したら例外を投げる。"""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as res:
        return json.loads(res.read().decode("utf-8"))


def pick(dic, *keys, default=None):
    """入れ子の辞書から安全に値を取り出す（途中が無ければ default）。"""
    cur = dic
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur if cur is not None else default


def to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def part_label(part) -> str:
    """part は文字列（title）か {"jp": "実況"} のどちらか。"""
    if isinstance(part, str):
        return part
    return pick(part, "jp", default="") or ""


def normalize_point(spec_part: dict, fc_part: dict | None) -> dict:
    """「実況」「予報◯時間後」1件ぶんを、扱いやすい形に整える。"""
    pos = spec_part.get("position") or {}
    deg = pos.get("deg") or []
    lat = to_float(deg[0]) if len(deg) > 0 else None
    lon = to_float(deg[1]) if len(deg) > 1 else None

    point = {
        "hours": spec_part.get("advancedHours"),
        "label": part_label(spec_part.get("part")),
        "validTime": pick(spec_part, "validtime", "JST"),
        "category": pick(spec_part, "category", "jp"),
        "intensity": spec_part.get("intensity") or "",
        "scale": (spec_part.get("scale") or "").replace("-", ""),
        "location": spec_part.get("location") or "",
        "course": spec_part.get("course") or "",
        "speedKmh": spec_part.get("speed", {}).get("km/h") if isinstance(spec_part.get("speed"), dict) else None,
        "pressure": to_float(spec_part.get("pressure")),
        "windMs": to_float(pick(spec_part, "maximumWind", "sustained", "m/s")),
        "gustMs": to_float(pick(spec_part, "maximumWind", "gust", "m/s")),
        "lat": lat,
        "lon": lon,
        "circleKm": to_float(pick(spec_part, "probabilityCircleRadius", "km")),
    }

    # 暴風域・強風域（実況にだけ入っていることが多い）
    storm = pick(spec_part, "stormWarning", default=[])
    if isinstance(storm, list) and storm:
        point["stormRadiusKm"] = to_float(pick(storm[0], "range", "km"))
    gale = pick(spec_part, "galeWarning", default=[])
    if isinstance(gale, list) and gale:
        point["galeRadiusKm"] = max(
            (to_float(pick(g, "range", "km")) or 0) for g in gale
        ) or None

    if fc_part:
        # 予報円の半径はメートル。specifications 側に無いときの控え。
        radius_m = pick(fc_part, "probabilityCircle", "radius")
        if point["circleKm"] is None and radius_m:
            point["circleKm"] = round(float(radius_m) / 1000, 1)
        center = fc_part.get("center")
        if isinstance(center, list) and len(center) == 2:
            point["lat"] = to_float(center[0])
            point["lon"] = to_float(center[1])

    return point


def build_typhoon(entry: dict) -> dict | None:
    """台風1個ぶんのデータを組み立てる。取れなければ None。"""
    tc_id = entry.get("tropicalCyclone")
    if not tc_id:
        return None

    spec = fetch_json(f"{BASE}/{tc_id}/specifications.json")
    try:
        forecast = fetch_json(f"{BASE}/{tc_id}/forecast.json")
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError):
        forecast = []

    # advancedHours をキーに forecast 側を引けるようにしておく
    fc_by_hours = {}
    track: list[list[float]] = []
    for part in forecast:
        if part_label(part.get("part")) == "title":
            continue
        fc_by_hours[part.get("advancedHours")] = part
        raw_track = pick(part, "track", "typhoon", default=None)
        if raw_track:
            track = [[to_float(p[0]), to_float(p[1])] for p in raw_track if len(p) == 2]

    title = next((p for p in spec if part_label(p.get("part")) == "title"), {})
    points = [
        normalize_point(p, fc_by_hours.get(p.get("advancedHours")))
        for p in spec
        if part_label(p.get("part")) != "title"
    ]
    points.sort(key=lambda p: p["hours"] if p["hours"] is not None else 0)

    number = title.get("typhoonNumber") or entry.get("typhoonNumber") or ""
    return {
        "id": tc_id,
        "number": number,
        # "2613" → 13号
        "numberShort": str(int(number[2:])) if len(number) >= 4 and number[2:].isdigit() else number,
        "name": pick(title, "name", "jp", default=""),
        "nameEn": pick(title, "name", "en", default=""),
        "category": pick(title, "category", "jp", default=entry.get("category", "")),
        "issue": pick(title, "issue", "JST", default=entry.get("issue")),
        "analysis": next((p for p in points if p["hours"] == 0), None),
        "forecast": [p for p in points if p["hours"] not in (0, None)],
        "track": track,
    }


# ------------------------------------------------------------------ 警報・注意報


def scan_office_warnings(data: dict) -> dict:
    """1つの予報区のデータから、台風に関係する5種類の「いちばん重い状態」を拾う。

    1つの予報区の中には市町村がたくさん入っていて、それぞれ別々に警報が出ます。
    ここでは「その県のどこかで暴風警報が出ているか」を知りたいので、
    県の中でいちばん重いものを代表として採用します。
    """
    found: dict[str, str] = {}
    for area_type in data.get("areaTypes") or []:
        if not isinstance(area_type, dict):
            continue
        for area in area_type.get("areas") or []:
            if not isinstance(area, dict):
                continue
            for w in area.get("warnings") or []:
                if not isinstance(w, dict):
                    continue
                if (w.get("status") or "") not in ACTIVE_STATUS:
                    continue
                hit = WARNING_CODES.get(str(w.get("code") or ""))
                if not hit:
                    continue  # 台風に関係しない種類（雷・乾燥など）は無視
                kind, level, _name = hit
                if kind not in found or RANK[level] > RANK[found[kind]]:
                    found[kind] = level
    return found


def build_warnings() -> dict:
    """全国の予報区をひとつずつ確認して、台風に関係する警報が出ている所をまとめる。

    1つでも取得に失敗したら例外を投げます（呼び出し元で中断＝上書きしない）。
    """
    offices = []
    report_times = []
    for code, (name, region) in OFFICES.items():
        data = fetch_json(f"{WARNING_DIR}/{code}.json")
        if not isinstance(data, dict):
            raise ValueError(f"{code} のデータが想定した形ではありません")
        kinds = scan_office_warnings(data)
        if not kinds:
            continue  # 何も出ていない予報区は載せない（一覧が長くなるだけなので）
        # 発表時刻は「実際に警報が出ている予報区」のものだけ見る。
        # 全国ぶんの最大値にすると、どこかが更新されるたびに時刻が動いて
        # 中身が変わっていないのに毎時コミットが増えてしまうため。
        if data.get("reportDatetime"):
            report_times.append(data["reportDatetime"])
        top = max(kinds.values(), key=lambda lv: RANK[lv])
        offices.append(
            {
                "code": code,
                "name": name,
                "region": region,
                "kinds": {k: kinds[k] for k in KIND_ORDER if k in kinds},
                "top": top,
            }
        )
    # 重い順 → 同じ重さなら全国の並び順（北から南）
    order = list(OFFICES.keys())
    offices.sort(key=lambda o: (-RANK[o["top"]], order.index(o["code"])))
    return {
        "reportTime": max(report_times) if report_times else None,
        "offices": offices,
    }


def main() -> int:
    now = datetime.now(JST).replace(microsecond=0)
    try:
        targets = fetch_json(TARGET_URL)
    except Exception as err:  # noqa: BLE001 - 何で失敗しても落とさず伝える
        print(f"❌ 気象庁の一覧が取れませんでした: {err}", file=sys.stderr)
        return 1

    entries = targets if isinstance(targets, list) else []
    typhoons = []
    failed = 0
    for entry in entries:
        try:
            built = build_typhoon(entry)
        except Exception as err:  # noqa: BLE001
            print(f"⚠️ {entry.get('tropicalCyclone')} の取得に失敗: {err}", file=sys.stderr)
            failed += 1
            continue
        if built:
            typhoons.append(built)
        else:
            failed += 1

    # ⚠️ 大事な安全装置
    # 1個でも取れなかったら、ファイルを書き換えない。
    # 通信が一瞬切れただけで「台風はありません」と上書きしてしまうと、
    # 本当に台風が来ているときに危険な表示になるため。
    if failed:
        print(
            f"❌ {len(entries)}個中{failed}個が取得できませんでした。"
            "古い情報のほうが安全なので、ファイルは書き換えません。",
            file=sys.stderr,
        )
        return 1

    # 警報・注意報も同じ安全装置。取れなかったら何も書き換えない。
    # （台風だけ新しくて警報だけ古い、というちぐはぐな状態を作らないため）
    try:
        warnings = build_warnings()
    except Exception as err:  # noqa: BLE001
        print(
            f"❌ 警報・注意報が取れませんでした: {err}"
            "　古い情報のほうが安全なので、ファイルは書き換えません。",
            file=sys.stderr,
        )
        return 1

    payload = {
        "generatedAt": now.isoformat(),
        "source": "気象庁（https://www.jma.go.jp/bosai/typhoon/）",
        "count": len(typhoons),
        "typhoons": typhoons,
        "warnings": warnings,
    }

    # 中身が前回と同じなら書き換えない（取得しただけの無意味なコミットを増やさないため）。
    # 「いつ取りに行ったか」ではなく「気象庁がいつ発表したか」が大事なので、
    # generatedAt だけの違いは "変わっていない" とみなす。
    if OUT_PATH.exists():
        try:
            before = json.loads(OUT_PATH.read_text(encoding="utf-8"))
            if {k: v for k, v in before.items() if k != "generatedAt"} == {
                k: v for k, v in payload.items() if k != "generatedAt"
            }:
                print("✅ 気象庁の発表に変わりはありませんでした（ファイルはそのまま）")
                return 0
        except (OSError, ValueError):
            pass  # 読めなければ普通に書き直す

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )

    if typhoons:
        # 気象庁は「まだ台風になっていない熱帯低気圧」も混ぜて発表する。
        # そのとき番号は数字ではなく記号（例：b）、名前は空なので「b号（）」と出さない。
        def label(t):
            num = str(t.get("numberShort") or "")
            if not num.isdigit():
                return t.get("category") or "熱帯低気圧"
            return f"{num}号（{t['name']}）" if t.get("name") else f"{num}号"

        names = "、".join(label(t) for t in typhoons)
        print(f"✅ {len(typhoons)}個ぶん保存しました: {names} → {OUT_PATH}")
    else:
        print(f"✅ 発生中の台風はありません → {OUT_PATH}")

    hit = warnings["offices"]
    if hit:
        heavy = [o["name"] for o in hit if o["top"] != "注意報"]
        print(
            f"⚠️ 台風に関係する警報・注意報：{len(hit)}予報区"
            + (f"（うち警報以上：{'、'.join(heavy)}）" if heavy else "（すべて注意報）")
        )
    else:
        print("✅ 台風に関係する警報・注意報は出ていません")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
