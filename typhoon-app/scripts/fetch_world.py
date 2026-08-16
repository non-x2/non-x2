#!/usr/bin/env python3
"""世界の台風（ハリケーンなど）を取ってきて、ページが読む形（data/world.json）に整えて保存する。

日本のまわりの台風は気象庁の担当（fetch_typhoon.py → latest.json）。
こちらは「それ以外の海」を、🌐 3D地球儀タブに描くための控えを作る係です。

いまカバーしている海：
    大西洋・東太平洋・中部太平洋 … 米国ハリケーンセンター（NHC/CPHC）
    南半球・北インド洋           … 米軍合同台風警報センター（JTWC）
    ※ どちらも米政府の作品＝パブリックドメイン（出典を書くのがマナー）。
    ※ 北西太平洋（日本周辺）はこのファイルでは扱わない＝気象庁が正。
      JTWCは北西太平洋・東太平洋も発表しているが、気象庁・NHCと二重になるので拾わない。

使い方（手で試すとき）:
    python3 typhoon-app/scripts/fetch_world.py

外部のライブラリは使いません（Python 3 の標準機能だけ）。
"""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

# 現況の一覧（どの台風が活動中か・名前・分類・気圧など）
NHC_CURRENT = "https://www.nhc.noaa.gov/CurrentStorms.json"
# 予報点・これまでの経路（緯度経度つきのGeoJSONをくれる地図API）
IDPGIS = (
    "https://mapservices.weather.noaa.gov/tropical/rest/services/tropical/"
    "NHC_tropical_weather/MapServer"
)
OUT_PATH = Path(__file__).resolve().parent.parent / "data" / "world.json"
JST = timezone(timedelta(hours=9))
TIMEOUT = 30
USER_AGENT = "non-x2-typhoon-app/1.0 (+https://github.com/non-x2/non-x2)"

BASIN_JP = {"AL": "大西洋", "EP": "東太平洋", "CP": "中部太平洋"}

# 分類の日本語。知らない言葉が来たら英語のまま出す（勝手な創作をしないため）
CLASS_JP = {
    "TD": "熱帯低気圧",
    "STD": "亜熱帯低気圧",
    "TS": "熱帯暴風",
    "STS": "亜熱帯暴風",
    "HU": "ハリケーン",
    "MH": "ハリケーン",
    # ⚠️ 略号の PTC は Potential（たまご）。Post（温帯低気圧化）は PC。混同しないこと
    "PTC": "熱帯低気圧のたまご",
    "PC": "温帯低気圧化",
}
DVLP_JP = {
    "Tropical Depression": "熱帯低気圧",
    "Subtropical Depression": "亜熱帯低気圧",
    "Tropical Storm": "熱帯暴風",
    "Subtropical Storm": "亜熱帯暴風",
    "Hurricane": "ハリケーン",
    "Major Hurricane": "ハリケーン",
    "Post-Tropical Cyclone": "温帯低気圧化",
    "Post-tropical Cyclone": "温帯低気圧化",
    "Remnant Low": "弱まった低気圧",
    "Potential Tropical Cyclone": "熱帯低気圧のたまご",
}

KT_TO_MS = 0.514444  # ノット → メートル毎秒
NM_TO_KM = 1.852     # 海里 → キロメートル

# --- JTWC（南半球・北インド洋の担当） ---
JTWC_RSS = "https://www.metoc.navy.mil/jtwc/rss/jtwc.rss"
JTWC_PRODUCTS = "https://www.metoc.navy.mil/jtwc/products"
# 採用する海域コード。wp（北西太平洋）は気象庁、ep/cp（東・中部太平洋）はNHCの
# 担当なので、ここに入れない＝二重表示を防ぐ。
JTWC_BASINS = {"sh": "南半球", "io": "北インド洋"}
JTWC_SUBJ_JP = {
    "TROPICAL DEPRESSION": "熱帯低気圧",
    "TROPICAL STORM": "熱帯暴風",
    "TYPHOON": "台風",
    "SUPER TYPHOON": "スーパー台風",
    "HURRICANE": "ハリケーン",
}


def fetch_bytes(url: str, tries: int = 3) -> bytes:
    """URLから生データを取ってくる。何度か試して、それでもダメなら例外を投げる。"""
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as res:
                return res.read()
        except Exception as err:  # noqa: BLE001 - 何で失敗しても取り直す
            last = err
            if i < tries - 1:
                time.sleep(2**i)
    raise last


def fetch_json(url: str, tries: int = 3):
    """URLからJSONを取ってくる。"""
    return json.loads(fetch_bytes(url, tries).decode("utf-8"))


def fetch_text(url: str, tries: int = 3) -> str:
    """URLから文章を取ってくる。"""
    return fetch_bytes(url, tries).decode("utf-8", errors="replace")


def query_url(layer_id: int, extra: dict | None = None) -> str:
    """地図APIの「このレイヤーの中身をぜんぶGeoJSONでください」というURLを作る。"""
    params = {
        "where": "1=1",
        "outFields": "*",
        "f": "geojson",
        # 座標を小数2桁に丸めてもらう（約1kmの精度。地球儀に描くには十分で、軽い）
        "geometryPrecision": "2",
    }
    if extra:
        params.update(extra)
    return f"{IDPGIS}/{layer_id}/query?" + urllib.parse.urlencode(params)


def to_num(value):
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f


def to_int(value):
    """整数に（「991.0hPa」と表示されるのを防ぐ）。"""
    f = to_num(value)
    return round(f) if f is not None else None


def to_pressure(value):
    """気圧を整数に。NHCは「値なし」を 9999 という数字で送ってくるので、
    地球の気圧としてありえない値（800〜1100hPaの外）は「無し」として捨てる。"""
    p = to_int(value)
    return p if p is not None and 800 <= p <= 1100 else None


def kt_to_ms(kt):
    """風速のノットをm/sへ（気象庁の表示と単位をそろえる）。"""
    f = to_num(kt)
    return round(f * KT_TO_MS) if f and f > 0 else None


def parse_validtime(vt, base: datetime):
    """"15/1200"（日/時分・世界標準時）をISO形式へ。

    月の情報が入っていないので、前月・当月・翌月の3候補を作り、
    いまの時刻にいちばん近いものを選ぶ（予報は最大5日先・実況は少し過去のため、
    月またぎでも必ず正しい方に寄る）。
    """
    try:
        day_s, hm = str(vt).split("/")
        day, hh, mi = int(day_s), int(hm[:2]), int(hm[2:4])
    except (ValueError, AttributeError, IndexError):
        return None
    cands = []
    for delta in (-1, 0, 1):
        y, m = base.year, base.month + delta
        if m == 0:
            y, m = y - 1, 12
        elif m == 13:
            y, m = y + 1, 1
        try:
            cands.append(datetime(y, m, day, hh, mi, tzinfo=timezone.utc))
        except ValueError:
            continue  # その月にその日が無い（31日など）
    if not cands:
        return None
    best = min(cands, key=lambda d: abs((d - base).total_seconds()))
    return best.isoformat()


def category_of(props: dict) -> str:
    """予報点の発達段階を日本語にする。ハリケーンは強さのカテゴリも添える。"""
    label = DVLP_JP.get(str(props.get("tcdvlp") or "").strip(), "") or (
        CLASS_JP.get(str(props.get("stormtype") or "").strip(), "")
    )
    if not label:
        # 知らない言葉はそのまま（うそをつかない）
        label = str(props.get("tcdvlp") or props.get("stormtype") or "").strip() or "熱帯低気圧"
    ss = to_num(props.get("ssnum"))
    if label == "ハリケーン" and ss and ss >= 1:
        label += f"（カテゴリ{int(ss)}）"
    return label


def layer_map() -> dict:
    """レイヤー一覧から「EP3 → 予報点はレイヤー188」のような対応表を作る。

    番号の決め打ちはせず、毎回名前で引き直す（将来並びが変わっても壊れないように）。
    """
    info = fetch_json(f"{IDPGIS}?f=json")
    layers = info.get("layers") or []
    if not layers:
        raise ValueError("地図APIのレイヤー一覧が空でした")
    out = {}
    for lay in layers:
        name = str(lay.get("name") or "")
        parts = name.split(" ", 1)
        if len(parts) != 2:
            continue
        bin_no, kind = parts[0], parts[1]
        if kind in ("Forecast Points", "Past Track"):
            out.setdefault(bin_no, {})[kind] = lay.get("id")
    return out


def track_coords(geojson: dict) -> list:
    """経路レイヤーのGeoJSONから [緯度, 経度] の列を取り出す。"""
    pts: list[list[float]] = []
    for feat in geojson.get("features") or []:
        geom = feat.get("geometry") or {}
        gtype, coords = geom.get("type"), geom.get("coordinates") or []
        lines = []
        if gtype == "LineString":
            lines = [coords]
        elif gtype == "MultiLineString":
            lines = coords
        for line in lines:
            for xy in line:
                if len(xy) >= 2:
                    lat, lon = to_num(xy[1]), to_num(xy[0])
                    if lat is not None and lon is not None:
                        pts.append([lat, lon])
    return pts


def build_storm(entry: dict, layers: dict, now_utc: datetime) -> dict:
    """台風（ハリケーン）1個ぶんを組み立てる。途中で取れなければ例外を投げる。"""
    bin_no = str(entry.get("binNumber") or "").strip()
    lays = layers.get(bin_no) or {}
    fp_id = lays.get("Forecast Points")
    pt_id = lays.get("Past Track")

    # --- 予報点（実況 tau=0 も入っている） ---
    points = []
    if fp_id is not None:
        gj = fetch_json(query_url(fp_id))
        for feat in gj.get("features") or []:
            props = feat.get("properties") or {}
            geom = feat.get("geometry") or {}
            xy = geom.get("coordinates") or []
            if len(xy) < 2:
                continue
            tau = to_num(props.get("tau"))
            points.append(
                {
                    "hours": int(tau) if tau is not None else None,
                    "validTime": parse_validtime(props.get("validtime"), now_utc),
                    "category": category_of(props),
                    "lat": to_num(xy[1]),
                    "lon": to_num(xy[0]),
                    "windMs": kt_to_ms(props.get("maxwind")),
                    "gustMs": kt_to_ms(props.get("gust")),
                    "pressure": to_pressure(props.get("mslp")),
                }
            )
        points = [p for p in points if p["hours"] is not None and p["lat"] is not None]
        points.sort(key=lambda p: p["hours"])

    # --- これまでの経路 ---
    track = track_coords(fetch_json(query_url(pt_id))) if pt_id is not None else []

    # --- 実況（予報点の0時間目。無ければ現況一覧の位置で代用） ---
    analysis = next((p for p in points if p["hours"] == 0), None)
    if analysis is None:
        lat, lon = to_num(entry.get("latitudeNumeric")), to_num(entry.get("longitudeNumeric"))
        if lat is None or lon is None:
            raise ValueError(f"{entry.get('name')}: 位置がわかりませんでした")
        analysis = {
            "hours": 0,
            "validTime": entry.get("lastUpdate"),
            "category": CLASS_JP.get(str(entry.get("classification") or "").strip(), "熱帯低気圧"),
            "lat": lat,
            "lon": lon,
            "windMs": kt_to_ms(entry.get("intensity")),
            "gustMs": None,
            "pressure": to_pressure(entry.get("pressure")),
        }

    basin_code = bin_no[:2] if bin_no else str(entry.get("id") or "")[:2].upper()
    return {
        "id": entry.get("id"),
        "bin": bin_no,
        "name": str(entry.get("name") or "").strip(),
        "basin": BASIN_JP.get(basin_code, basin_code),
        "category": analysis["category"],
        "issue": entry.get("lastUpdate"),
        "analysis": analysis,
        "forecast": [p for p in points if p["hours"] and p["hours"] > 0],
        "track": track,
    }


# ------------------------------------------------------------------ JTWC（南半球・北インド洋）


def jtwc_category(subj_label: str, wind_kt) -> str:
    """JTWCの呼び名を日本語にする。

    JTWCは南半球・インド洋の嵐を強さによらず「TROPICAL CYCLONE」と総称することが
    あるので、そのときは風の強さで分ける（34ノット＝約17m/s、64ノット＝約33m/s。
    これはJTWC自身の区分と同じ線引き）。
    """
    label = JTWC_SUBJ_JP.get(subj_label)
    if label:
        return label
    kt = to_num(wind_kt) or 0
    if kt >= 64:
        return "サイクロン"
    if kt >= 34:
        return "熱帯暴風"
    return "熱帯低気圧"


def parse_tcw(text: str, basin_jp: str) -> dict:
    """JTWCの警報データ（JMV3.0という固定書式）を読み取る。

    3行目   : 2026081512 01C LALA 013 …  → 観測時刻・番号・名前
    T000行  : T000 178N 1541W 055 …      → 実況（緯度経度は10倍の値。178N＝北緯17.8度）
    T012行〜: 12時間後〜120時間後の予報
    R034 …  : 34ノット（約17m/s）の風がふく範囲の半径（海里・方角ごと）
    """
    head = re.search(r"^(\d{10})\s+(\S+)\s+(\S+)", text, re.M)
    if not head:
        raise ValueError("JMV3.0の見出し行が見つかりません")
    stamp, storm_no, raw_name = head.group(1), head.group(2), head.group(3)
    obs = datetime(
        int(stamp[0:4]), int(stamp[4:6]), int(stamp[6:8]), int(stamp[8:10]),
        tzinfo=timezone.utc,
    )
    name = raw_name.title() if raw_name.isalpha() else raw_name

    subj = re.search(r"SUBJ:\s+([A-Z ]+?)\s+\d+\w*\s*\(", text)
    subj_label = subj.group(1).strip() if subj else ""

    points = []
    for m in re.finditer(
        r"^T(\d{3})\s+(\d+)([NS])\s+(\d+)([EW])\s+(\d+)(.*)$", text, re.M
    ):
        tau = int(m.group(1))
        lat = int(m.group(2)) / 10 * (1 if m.group(3) == "N" else -1)
        lon = int(m.group(4)) / 10 * (1 if m.group(5) == "E" else -1)
        wind_kt = int(m.group(6))
        r34 = re.search(
            r"R034\s+(\d+)\s+NE QD\s+(\d+)\s+SE QD\s+(\d+)\s+SW QD\s+(\d+)\s+NW QD",
            m.group(7),
        )
        gale_km = None
        if r34:
            nm = max(int(r34.group(i)) for i in (1, 2, 3, 4))
            if nm > 0:
                gale_km = round(nm * NM_TO_KM)
        points.append(
            {
                "hours": tau,
                "validTime": (obs + timedelta(hours=tau)).isoformat(),
                "category": jtwc_category(subj_label if tau == 0 else "", wind_kt),
                "lat": lat,
                "lon": lon,
                "windMs": kt_to_ms(wind_kt),
                "gustMs": None,
                "pressure": None,  # JTWCは気圧を発表しない（風の強さが基準）
                "galeRadiusKm": gale_km,
            }
        )
    points.sort(key=lambda p: p["hours"])

    analysis = next((p for p in points if p["hours"] == 0), None)
    if analysis is None:
        raise ValueError("実況（T000行）が見つかりません")

    return {
        "id": f"jtwc-{storm_no.lower()}-{obs:%Y}",
        "bin": storm_no.upper(),
        "name": name,
        "basin": basin_jp,
        "category": analysis["category"],
        "issue": obs.isoformat(),
        "analysis": analysis,
        "forecast": [p for p in points if p["hours"] > 0],
        "track": [],  # JMV3.0にはこれまでの経路が入っていない（実況＋予報のみ）
    }


def build_jtwc_storms() -> list:
    """JTWCのRSSから、南半球・北インド洋の嵐だけを組み立てる。

    途中で1つでも取れなければ例外を投げる（呼び出し元で中断＝上書きしない）。
    """
    rss = fetch_text(JTWC_RSS)
    ids = []
    for m in re.finditer(r"/jtwc/products/([a-z]{2}\d{4})\.tcw", rss):
        sid = m.group(1)
        if sid[:2] in JTWC_BASINS and sid not in ids:
            ids.append(sid)
    storms = []
    for sid in ids:
        text = fetch_text(f"{JTWC_PRODUCTS}/{sid}.tcw")
        storms.append(parse_tcw(text, JTWC_BASINS[sid[:2]]))
    return storms


def main() -> int:
    now_utc = datetime.now(timezone.utc).replace(microsecond=0)
    try:
        current = fetch_json(NHC_CURRENT)
    except Exception as err:  # noqa: BLE001
        print(f"❌ 米国ハリケーンセンターの一覧が取れませんでした: {err}", file=sys.stderr)
        return 1

    storms_in = current.get("activeStorms") if isinstance(current, dict) else None
    if not isinstance(storms_in, list):
        print("❌ 一覧の形が想定と違います。ファイルは書き換えません。", file=sys.stderr)
        return 1

    # 活動中の台風があるときだけレイヤー一覧を引く（無駄な通信をしない）
    try:
        layers = layer_map() if storms_in else {}
    except Exception as err:  # noqa: BLE001
        print(f"❌ 地図APIのレイヤー一覧が取れませんでした: {err}", file=sys.stderr)
        return 1

    storms = []
    for entry in storms_in:
        try:
            storms.append(build_storm(entry, layers, now_utc))
        except Exception as err:  # noqa: BLE001
            # ⚠️ 大事な安全装置（台風ページの家訓）
            # 1個でも取れなかったら、ファイルを書き換えない。
            # 一部だけの控えを「これで全部」と見せてしまうと危ないため。
            print(
                f"❌ {entry.get('name')} の取得に失敗: {err}。"
                "古い情報のほうが安全なので、ファイルは書き換えません。",
                file=sys.stderr,
            )
            return 1

    # 南半球・北インド洋（JTWC）。こちらも1つでも失敗したら全体を書き換えない
    # （「南のサイクロンが消えた＝終わった」という誤解を作らないため）。
    try:
        storms += build_jtwc_storms()
    except Exception as err:  # noqa: BLE001
        print(
            f"❌ JTWC（南半球・北インド洋）の取得に失敗: {err}。"
            "古い情報のほうが安全なので、ファイルは書き換えません。",
            file=sys.stderr,
        )
        return 1

    payload = {
        "generatedAt": datetime.now(JST).replace(microsecond=0).isoformat(),
        "source": (
            "米国ハリケーンセンター（NHC/CPHC、https://www.nhc.noaa.gov/）＋"
            "米軍合同台風警報センター（JTWC、https://www.metoc.navy.mil/jtwc/）"
        ),
        "note": "日本周辺（北西太平洋）は気象庁が担当（latest.json）。このファイルは含みません。",
        "count": len(storms),
        "storms": storms,
    }

    # 中身が前回と同じなら書き換えない（無意味なコミットを増やさないため）。
    # ⚠️ ただし日付（generatedAt）だけは、11時間より古くなったら書き直す。
    # ページ側は「控えが12時間より古い＝確認できていない」と表示を休む決まりなので、
    # 台風0個の平和な時期に日付が止まったままだと、毎時ちゃんと確認できているのに
    # 「休んでいます」と誤解させてしまうため（書き直しても最大で1日2コミット程度）。
    if OUT_PATH.exists():
        try:
            before = json.loads(OUT_PATH.read_text(encoding="utf-8"))
            if {k: v for k, v in before.items() if k != "generatedAt"} == {
                k: v for k, v in payload.items() if k != "generatedAt"
            }:
                prev_dt = None
                try:
                    prev_dt = datetime.fromisoformat(str(before.get("generatedAt")))
                except ValueError:
                    pass
                if prev_dt and datetime.now(JST) - prev_dt < timedelta(hours=11):
                    print("✅ 発表に変わりはありませんでした（ファイルはそのまま）")
                    return 0
                print("🕐 発表は同じですが、控えの日付が古くなったので日付だけ書き直します")
        except (OSError, ValueError):
            pass

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )

    if storms:
        names = "、".join(f"{s['category']}{s['name']}（{s['basin']}）" for s in storms)
        print(f"✅ 世界の台風 {len(storms)}個ぶん保存しました: {names} → {OUT_PATH}")
    else:
        print(f"✅ いま世界（NHC担当の海）に活動中の台風はありません → {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
