#!/usr/bin/env python3
"""気象庁の防災情報（地震・津波・雷・大雨）を取ってきて data/latest.json に整えて保存する。

これは「人のかわりに調べてくれる係」です。
GitHub Actions が定期的にこれを走らせるので、Claude を開かなくてもページが新しくなります。

使い方（手で試すとき）:
    python3 bousai-app/scripts/fetch_bousai.py

観察モード（データの生の形を確認したいとき。ファイルは書き換えません）:
    python3 bousai-app/scripts/fetch_bousai.py --probe

外部のライブラリは使いません（Python 3 の標準機能だけ）。

⚠️ 安全装置（台風ページの教訓 T12 と同じ）:
    どれか1種類でも取得に失敗したら、ファイルをまったく書き換えずに終了します。
    古い情報が残るほうが、間違った「何もありません」より安全だからです。
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = "https://www.jma.go.jp/bosai"
QUAKE_LIST = f"{BASE}/quake/data/list.json"
TSUNAMI_LIST = f"{BASE}/tsunami/data/list.json"
WARNING_DIR = f"{BASE}/warning/data/warning"
AREA_CONST = f"{BASE}/common/const/area.json"
OUT_PATH = Path(__file__).resolve().parent.parent / "data" / "latest.json"
JST = timezone(timedelta(hours=9))
TIMEOUT = 30
USER_AGENT = "non-x2-bousai-app/1.0 (+https://github.com/non-x2/non-x2)"

QUAKE_MAX = 15  # 保存する地震の件数（新しい順）
TSUNAMI_RECENT_MAX = 5  # 保存する津波関連の発表の件数

# 警報・注意報の種類コード（気象庁の決まりごと）
RAIN_CODES = {"33": "特別警報", "03": "警報", "10": "注意報"}  # 大雨
FLOOD_CODES = {"04": "警報", "18": "注意報"}  # 洪水
THUNDER_CODE = "14"  # 雷注意報
ACTIVE_STATUS = {"発表", "継続"}  # この状態のものだけ「出ている」と数える

# 全国の予報区（府県など）。code: (名前, 地方ブロック)
# ※ index.html の OFFICES と同じ内容。直すときは両方そろえること。
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


def to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------- 地震


def parse_depth_km(cod: str):
    """位置の文字列（例 "+37.5+137.2-10000/"）から深さ(km)を取り出す。"""
    if not isinstance(cod, str):
        return None
    body = cod.rstrip("/")
    # 3個目の符号つき数字が「深さ（メートル、地下がマイナス）」
    parts = []
    cur = ""
    for ch in body:
        if ch in "+-" and cur:
            parts.append(cur)
            cur = ch
        else:
            cur += ch
    if cur:
        parts.append(cur)
    if len(parts) < 3:
        return None
    depth_m = to_float(parts[2])
    if depth_m is None:
        return None
    return abs(depth_m) / 1000


def build_quakes(raw_list) -> list[dict]:
    """地震一覧を新しい順に整える。同じ地震の続報は1件にまとめる。"""
    by_event: dict[str, dict] = {}
    order: list[str] = []
    for entry in raw_list or []:
        if not isinstance(entry, dict):
            continue
        eid = entry.get("eid") or entry.get("ctt")
        if not eid:
            continue
        if eid not in by_event:
            by_event[eid] = {
                "id": eid,
                "time": None,
                "place": "",
                "magnitude": None,
                "maxIntensity": "",
                "depthKm": None,
            }
            order.append(eid)
        q = by_event[eid]
        # 続報で情報が増えることがあるので「空いている欄を埋める」方式
        if not q["time"]:
            q["time"] = entry.get("at") or entry.get("rdt")
        if not q["place"] and entry.get("anm"):
            q["place"] = entry["anm"]
        if q["magnitude"] is None:
            mag = entry.get("mag")
            # M不明のとき "M不明" や "" が入ることがある
            q["magnitude"] = to_float(mag)
        if not q["maxIntensity"] and entry.get("maxi"):
            q["maxIntensity"] = str(entry["maxi"])
        if q["depthKm"] is None:
            q["depthKm"] = parse_depth_km(entry.get("cod"))
    quakes = [by_event[eid] for eid in order if by_event[eid]["time"]]
    quakes.sort(key=lambda q: q["time"], reverse=True)

    # 「震度速報」（震源がまだ分からない第一報）は別IDで届くので、
    # 5分以内に震源つきの情報がある場合は同じ地震とみなして省く。
    def minutes(t):
        try:
            return datetime.fromisoformat(t).timestamp() / 60
        except (TypeError, ValueError):
            return None

    result = []
    for q in quakes:
        if not q["place"]:
            m = minutes(q["time"])
            if m is not None and any(
                other["place"]
                and (lambda om: om is not None and abs(om - m) <= 5)(minutes(other["time"]))
                for other in quakes
            ):
                continue  # 震源つきの続報があるので、この速報は省く
        result.append(q)
    return result[:QUAKE_MAX]


# ---------------------------------------------------------------- 津波


def walk_tsunami_items(node, found: list):
    """津波の詳細データの中から「地域名＋警報の種類」の組を探す。

    実データは Body→Tsunami→Forecast→Item の中に
    {"Area": {"Name": …}, "Category": {"Kind": {"Name": …, "Code": …}}} という形
    （頭文字が大文字。2026-08-02 の観察モードで確認）。
    形が多少違っても拾えるよう、大文字・小文字の両方に対応しておく。
    """

    def get(dic, *names):
        for n in names:
            if isinstance(dic, dict) and n in dic:
                return dic[n]
        return None

    if isinstance(node, list):
        for item in node:
            walk_tsunami_items(item, found)
        return
    if not isinstance(node, dict):
        return
    area = get(node, "Area", "area")
    category = get(node, "Category", "category")
    if isinstance(area, dict) and isinstance(category, dict):
        name = get(area, "Name", "name") or ""
        kind = get(category, "Kind", "kind") or {}
        kind_name = (get(kind, "Name", "name") or "") if isinstance(kind, dict) else ""
        kind_code = str(get(kind, "Code", "code") or "") if isinstance(kind, dict) else ""
        if name:
            found.append({"name": name, "kind": kind_name, "code": kind_code})
        return  # この枝はもう見た
    for value in node.values():
        walk_tsunami_items(value, found)


# 「解除」「なし」を表すとされるコード。名前も見るので、コードは補助扱い。
TSUNAMI_INACTIVE_CODES = {"00", "50", "60", "71", "72", "73"}


def latest_tsunami_report(entries):
    """津波の「警報・注意報・予報」の電文（VTSE41）でいちばん新しいものを返す。

    ⚠️ 題名で探してはいけない：注意報が解除されると、解除のお知らせは
    「津波予報」という題名で届くため、題名に「注意報」を含むものを探すと
    解除前の古い発表を最新と勘違いしてしまう（2026-08-02 の観察モードで確認）。
    """
    for e in entries:
        if "VTSE41" in (e.get("json") or ""):
            return e
    # 念のための控え：ファイル名の形式が変わったら題名で探す
    return next(
        (
            e
            for e in entries
            if "津波警報" in (e.get("ttl") or "")
            or "津波注意報" in (e.get("ttl") or "")
            or "津波予報" in (e.get("ttl") or "")
        ),
        None,
    )


def tsunami_item_active(item: dict) -> bool:
    kind = item.get("kind") or ""
    code = item.get("code") or ""
    if "解除" in kind or "なし" in kind:
        return False
    if "大津波警報" in kind or "津波警報" in kind or "津波注意報" in kind:
        return True
    # 名前で判断できないときはコードで補助判断
    if code and code not in TSUNAMI_INACTIVE_CODES:
        return True
    return False


def build_tsunami(raw_list) -> dict:
    """津波の現在の状況＋最近の発表一覧を整える。"""
    entries = [e for e in (raw_list or []) if isinstance(e, dict)]
    recent = [
        {"time": e.get("rdt") or e.get("at"), "title": e.get("ttl") or ""}
        for e in entries[:TSUNAMI_RECENT_MAX]
    ]

    # 「津波警報・注意報・予報」という種類の、いちばん新しい発表を探す
    latest = latest_tsunami_report(entries)

    status = "none"  # 見つからない＝直近に発表そのものが無い
    issued = None
    areas: list[dict] = []
    if latest:
        issued = latest.get("rdt") or latest.get("at")
        detail_name = latest.get("json")
        if not detail_name:
            status = "unknown"
        else:
            try:
                detail = fetch_json(f"{BASE}/tsunami/data/{detail_name}")
            except Exception as err:  # noqa: BLE001
                print(f"⚠️ 津波の詳細が取れませんでした: {err}", file=sys.stderr)
                # 発表があったことは分かるのに中身が読めない → 「不明」として安全側に
                detail = None
            if detail is None:
                status = "unknown"
            elif isinstance(detail, dict) and detail.get("cancelled") is True:
                status = "none"
            else:
                found: list = []
                walk_tsunami_items(detail, found)
                active = [i for i in found if tsunami_item_active(i)]
                if active:
                    status = "active"
                    seen = set()
                    for i in active:
                        key = (i["name"], i["kind"])
                        if key in seen:
                            continue
                        seen.add(key)
                        areas.append({"name": i["name"], "kind": i["kind"] or "津波情報"})
                elif found:
                    status = "none"  # 地域は載っているが全部「解除」など
                else:
                    status = "unknown"  # 形が読めなかった。断言しない

    return {"status": status, "issued": issued, "areas": areas, "recent": recent}


# ---------------------------------------------------------------- 警報・注意報（雷・大雨・洪水）


def scan_office_warnings(data: dict) -> dict:
    """1つの予報区のデータから、大雨・洪水・雷の状況を拾う。"""
    rain = None  # "特別警報" > "警報" > "注意報"
    flood = None
    thunder = False
    rank = {"特別警報": 3, "警報": 2, "注意報": 1}

    for area_type in data.get("areaTypes") or []:
        if not isinstance(area_type, dict):
            continue
        for area in area_type.get("areas") or []:
            if not isinstance(area, dict):
                continue
            for w in area.get("warnings") or []:
                if not isinstance(w, dict):
                    continue
                code = str(w.get("code") or "")
                status = w.get("status") or ""
                if status not in ACTIVE_STATUS:
                    continue
                if code in RAIN_CODES:
                    level = RAIN_CODES[code]
                    if rain is None or rank[level] > rank[rain]:
                        rain = level
                elif code in FLOOD_CODES:
                    level = FLOOD_CODES[code]
                    if flood is None or rank[level] > rank[flood]:
                        flood = level
                elif code == THUNDER_CODE:
                    thunder = True
    return {"rain": rain, "flood": flood, "thunder": thunder}


def build_warnings() -> dict:
    """全国の予報区をひとつずつ確認して、雷・大雨・洪水が出ている所をまとめる。"""
    offices = []
    report_times = []
    for code, (name, region) in OFFICES.items():
        data = fetch_json(f"{WARNING_DIR}/{code}.json")  # 失敗したら例外→呼び出し元で中断
        if not isinstance(data, dict):
            raise ValueError(f"{code} のデータが想定した形ではありません")
        if data.get("reportDatetime"):
            report_times.append(data["reportDatetime"])
        result = scan_office_warnings(data)
        if result["rain"] or result["flood"] or result["thunder"]:
            offices.append(
                {
                    "code": code,
                    "name": name,
                    "region": region,
                    "rain": result["rain"],
                    "flood": result["flood"],
                    "thunder": result["thunder"],
                }
            )
    return {
        "reportTime": max(report_times) if report_times else None,
        "offices": offices,
    }


# ---------------------------------------------------------------- 観察モード


def probe() -> int:
    """データの生の形を目で確かめるためのモード（ファイルは書き換えない）。"""

    def show(label, value, limit=1500):
        text = json.dumps(value, ensure_ascii=False, indent=1)
        print(f"\n===== {label} =====")
        print(text[:limit] + ("\n…（長いので省略）" if len(text) > limit else ""))

    quake_list = fetch_json(QUAKE_LIST)
    print(f"地震一覧: {len(quake_list)}件")
    show("地震一覧の先頭2件（生データ）", quake_list[:2])

    tsunami_list = fetch_json(TSUNAMI_LIST)
    print(f"\n津波一覧: {len(tsunami_list)}件")
    show("津波一覧の先頭3件（生データ）", tsunami_list[:3], 2000)
    latest = latest_tsunami_report([e for e in tsunami_list if isinstance(e, dict)])
    if latest and latest.get("json"):
        detail = fetch_json(f"{BASE}/tsunami/data/{latest['json']}")
        show(f"いちばん新しい津波発表の詳細（{latest['json']}）", detail, 4000)
        found = []
        walk_tsunami_items(detail, found)
        show("↑から読み取れた地域と種類", found, 2000)
    else:
        print("（一覧に津波警報・注意報の発表が見当たりません）")

    area = fetch_json(AREA_CONST)
    offices_real = area.get("offices") if isinstance(area, dict) else {}
    print(f"\n気象庁の予報区一覧: {len(offices_real)}件")
    missing = [c for c in OFFICES if c not in offices_real]
    extra = [
        f"{c}:{v.get('name')}"
        for c, v in offices_real.items()
        if c not in OFFICES and str(v.get("name") or "")
    ]
    print(f"このスクリプトにあるのに気象庁に無いコード: {missing or 'なし'}")
    print(f"気象庁にあるのにこのスクリプトに無いコード: {extra or 'なし'}")
    wrong = [
        f"{c}: 手元={OFFICES[c][0]} / 気象庁={offices_real[c].get('name')}"
        for c in OFFICES
        if c in offices_real and OFFICES[c][0] != offices_real[c].get("name")
    ]
    print(f"名前が食い違うコード: {wrong or 'なし'}")

    sample = fetch_json(f"{WARNING_DIR}/130000.json")
    show("警報・注意報データの例（東京都 130000.json）", sample, 3000)
    print("\n観察モード終了（ファイルは書き換えていません）")
    return 0


# ---------------------------------------------------------------- 本体


def main() -> int:
    if "--probe" in sys.argv:
        return probe()

    now = datetime.now(JST).replace(microsecond=0)
    failed = []

    try:
        quakes = build_quakes(fetch_json(QUAKE_LIST))
    except Exception as err:  # noqa: BLE001
        print(f"❌ 地震情報が取れませんでした: {err}", file=sys.stderr)
        quakes, failed = [], failed + ["地震"]

    try:
        tsunami = build_tsunami(fetch_json(TSUNAMI_LIST))
    except Exception as err:  # noqa: BLE001
        print(f"❌ 津波情報が取れませんでした: {err}", file=sys.stderr)
        tsunami, failed = None, failed + ["津波"]

    try:
        warnings = build_warnings()
    except Exception as err:  # noqa: BLE001
        print(f"❌ 警報・注意報が取れませんでした: {err}", file=sys.stderr)
        warnings, failed = None, failed + ["警報・注意報"]

    # ⚠️ 大事な安全装置：1種類でも取れなかったら、書き換えずに失敗として終わる。
    if failed:
        print(
            f"❌ {'、'.join(failed)}の取得に失敗しました。"
            "古い情報のほうが安全なので、ファイルは書き換えません。",
            file=sys.stderr,
        )
        return 1

    payload = {
        "generatedAt": now.isoformat(),
        "source": "気象庁（https://www.jma.go.jp/）",
        "quakes": quakes,
        "tsunami": tsunami,
        "warnings": warnings,
    }

    # 中身が前回と同じなら書き換えない（無意味なコミットを増やさないため）。
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

    rain_n = sum(1 for o in warnings["offices"] if o["rain"])
    thunder_n = sum(1 for o in warnings["offices"] if o["thunder"])
    print(
        f"✅ 保存しました: 地震{len(quakes)}件 / 津波={tsunami['status']} / "
        f"大雨が出ている予報区{rain_n} / 雷注意報{thunder_n} → {OUT_PATH}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
