#!/usr/bin/env python3
"""全国の道路の「いまの交通量」を取ってくる係。

データの出どころは、国土交通省の「交通量API」（JARTIC 交通量オープンデータ）です。
全国の高速道路・一般国道にある常時観測点（約1,000か所）が、
「5分間に何台の車が通ったか」を数えています。

やっていること（3ステップ）:

  1. いちばん新しい5分間の交通量を全国ぶん取ってくる
     （観測から届くまで約20分の遅れがあるので、20分前から順に探します）
  2. くらべる相手として「1週間前の同じ時刻」の交通量も取ってくる
     → ページ側で「いつもより車が多い／少ない」を色分けするため。
       ※このAPIには速度が入っていないため「渋滞かどうか」は分かりません。
       台数を先週と比べるのが、うそをつかない見せ方の限界です。
  3. traffic-app/data/road_status.json（5分値のスナップショット）と
     traffic-app/data/road_points.json（観測点の台帳：場所・市区町村名）を書き出す

安全装置（トラブル解決記録 T12 の教訓）:
  - いまの交通量が取れなかったら、ファイルを**いっさい書き換えずに**終了コード1で終わります。
    （古い情報が残るほうが、まちがった「データなし」よりも安全）
  - 「1週間前」だけ取れなかったときは、比較なし（null）として正直に記録します。

使い方（手で試すとき）:
    python3 traffic-app/scripts/fetch_road_status.py

    # 観測点の台帳の市区町村名を調べ直すとき（毎週の自動実行が使います）
    python3 traffic-app/scripts/fetch_road_status.py --rebuild-points

外部のライブラリは使いません（Python 3 の標準機能だけ）。

出典：このスクリプトが取るデータは
「国土交通省API機能による交通量(参考値)」です（利用規約に沿って出典を明記しています）。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ------------------------------------------------------------------ 決まりごと

# 交通量API（国土交通省／JARTIC 交通量オープンデータ）
# ※JARTIC_API_BASE は「わざと失敗させるテスト」用の差し替え口です。ふだんは触りません。
API_BASE = os.environ.get("JARTIC_API_BASE", "https://api.jartic-open-traffic.org/geoserver")
TYPE_NAME = "t_travospublic_measure_5m"  # 5分間交通量
SOURCE_NOTE = "国土交通省API機能による交通量(参考値)を加工して作成"

# 緯度経度 → 市区町村（国土地理院。ライブカメラ台帳と同じやり方）
REVGEO_URL = "https://mreversegeocoder.gsi.go.jp/reverse-geocoder/LonLatToAddress"
MUNI_URL = "https://maps.gsi.go.jp/js/muni.js"

APP_DIR = Path(__file__).resolve().parent.parent
STATUS_PATH = APP_DIR / "data" / "road_status.json"
POINTS_PATH = APP_DIR / "data" / "road_points.json"

JST = timezone(timedelta(hours=9))
USER_AGENT = "non-x2-traffic-app/1.0 (+https://github.com/non-x2/non-x2)"

TIMEOUT = 90          # APIの待ち時間（秒）。全国分は1MB近くあるので長めに
GEO_TIMEOUT = 15      # 市区町村を調べるときの待ち時間（秒）
GEO_WORKERS = 5       # 国土地理院に同時に聞く数（控えめに）
RETRY = 2             # 通信に失敗したときの再試行の回数
DELAY_MIN = 20        # 観測からデータが届くまでの遅れ（分）。公式の説明どおり
SEARCH_BACK = 12      # 見つからないとき、5分ずつ何回さかのぼるか（12回=1時間）
MIN_FEATURES = 300    # これより件数が少なかったら「取得失敗」とみなす
                      # （ふだんは全国で1,000件前後。半分以下しか来ないのは異常）

# 日本全体を囲む範囲（経度・緯度）
BBOX = "122,24,146,46"


# ------------------------------------------------------------------ 小さな道具

def _open(url: str, timeout: int):
    """URLを開く。"""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    ctx = ssl.create_default_context()
    return urllib.request.urlopen(req, timeout=timeout, context=ctx)


def fetch_json(url: str, timeout: int = TIMEOUT) -> dict | None:
    """URLからJSONを取ってくる。失敗したら少し待って再試行し、それでもだめなら None。"""
    for attempt in range(RETRY + 1):
        try:
            with _open(url, timeout) as res:
                return json.loads(res.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, ssl.SSLError,
                OSError, ValueError, json.JSONDecodeError) as exc:
            if attempt < RETRY:
                wait = 3 * (attempt + 1)
                print(f"  ↻ 通信に失敗しました。{wait}秒待って再試行します（{exc}）", file=sys.stderr)
                time.sleep(wait)
            else:
                print(f"  ✗ 通信に失敗しました: {exc}", file=sys.stderr)
    return None


def build_url(timecode: str) -> str:
    """交通量APIのURLを組み立てる。

    しぼりこみ（cql_filter）の書き方の注意:
      - 項目名（道路種別など）は**クォートで囲まない**こと。囲むとエラーになります（実測で確認）。
      - 時間コードは省略できません（省略すると応答が大きすぎてエラーになります）。
    """
    cql = (
        f"(道路種別=1 OR 道路種別=3) AND 時間コード={timecode} "
        f"AND BBOX(ジオメトリ,{BBOX},'EPSG:4326')"
    )
    query = urllib.parse.urlencode({
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeNames": TYPE_NAME,
        "srsName": "EPSG:4326",
        "outputFormat": "application/json",
        "exceptions": "application/json",
        "cql_filter": cql,
    })
    return f"{API_BASE}?{query}"


def timecode_of(dt: datetime) -> str:
    """日時 → 時間コード（YYYYMMDDHHMM、5分きざみ）。"""
    return dt.strftime("%Y%m%d%H%M")


def floor5(dt: datetime) -> datetime:
    """5分きざみに切り捨てる。"""
    return dt.replace(minute=dt.minute - dt.minute % 5, second=0, microsecond=0)


def parse_timecode(code: str) -> datetime:
    """時間コード → 日時（日本時間）。"""
    return datetime.strptime(code, "%Y%m%d%H%M").replace(tzinfo=JST)


# ------------------------------------------------------------------ 交通量の取り出し

def direction_volume(props: dict, side: str) -> int | None:
    """片方向（上り or 下り）の台数を数える。機器の故障・欠測のときは None。"""
    for flag in ("停電", "ループ異常", "超音波異常", "欠測"):
        if str(props.get(f"{side}・{flag}", "0")) == "1":
            return None
    total = 0
    for kind in ("小型交通量", "大型交通量", "車種判別不能交通量"):
        value = props.get(f"{side}・{kind}")
        if isinstance(value, (int, float)) and value >= 0:
            total += int(value)
    return total


def collect(payload: dict) -> dict[str, dict]:
    """APIの応答から、観測点コードごとの情報を取り出す。"""
    points: dict[str, dict] = {}
    for feature in payload.get("features") or []:
        props = feature.get("properties") or {}
        code = props.get("常時観測点コード")
        if code is None:
            continue
        geom = feature.get("geometry") or {}
        coords = geom.get("coordinates") or []
        # MultiPoint（[[経度, 緯度]]）と Point（[経度, 緯度]）のどちらでも読めるように
        if coords and isinstance(coords[0], (list, tuple)):
            coords = coords[0]
        if len(coords) < 2:
            continue
        try:
            lon, lat = float(coords[0]), float(coords[1])
        except (TypeError, ValueError):
            continue
        if not (20.0 <= lat <= 46.5 and 122.0 <= lon <= 154.0):
            continue
        points[str(code)] = {
            "lat": lat,
            "lon": lon,
            "type": str(props.get("道路種別", "3")),
            "up": direction_volume(props, "上り"),
            "dn": direction_volume(props, "下り"),
        }
    return points


def fetch_latest() -> tuple[str, dict[str, dict]] | None:
    """いちばん新しい5分値を探して取ってくる。見つからなければ None。"""
    start = floor5(datetime.now(JST) - timedelta(minutes=DELAY_MIN))
    for step in range(SEARCH_BACK + 1):
        code = timecode_of(start - timedelta(minutes=5 * step))
        print(f"⏳ {code} の交通量を取得中…")
        payload = fetch_json(build_url(code))
        if payload is None:
            continue
        points = collect(payload)
        if len(points) >= MIN_FEATURES:
            print(f"✅ {code} の交通量: {len(points)} 地点")
            return code, points
        print(f"  … {code} はまだ {len(points)} 地点でした（そろっていないので、5分さかのぼります）")
    return None


# ------------------------------------------------------------------ 観測点の台帳

def load_points_file() -> dict:
    """観測点の台帳を読み込む（まだ無ければ空の台帳）。"""
    try:
        return json.loads(POINTS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {"u": "", "m": [], "p": []}


def merge_points(ledger: dict, latest: dict[str, dict]) -> tuple[dict, int]:
    """台帳に、新しく見つかった観測点を足す（すでにある観測点はそのまま）。"""
    munis: list[str] = list(ledger.get("m") or [])
    rows: list[list] = [list(r) for r in (ledger.get("p") or [])]
    known = {str(r[0]) for r in rows}
    added = 0
    for code, info in latest.items():
        if code in known:
            continue
        rows.append([int(code), round(info["lat"] * 1e5), round(info["lon"] * 1e5),
                     int(info["type"]), -1])
        added += 1
    rows.sort(key=lambda r: r[0])
    return {"u": ledger.get("u") or "", "m": munis, "p": rows}, added


def fill_munis(ledger: dict) -> int:
    """台帳のうち、市区町村名がまだ無い観測点を国土地理院で調べて埋める。"""
    todo = [r for r in ledger["p"] if r[4] < 0]
    if not todo:
        print("✅ 市区町村名はすべて埋まっています")
        return 0
    try:
        with _open(MUNI_URL, TIMEOUT) as res:
            text = res.read().decode("utf-8", errors="replace")
    except Exception as exc:
        print(f"⚠️ 自治体コードの対応表が取れませんでした（今回は市区町村名を省略）: {exc}", file=sys.stderr)
        return 0
    table: dict[str, str] = {}
    # 例: GSI.MUNI_ARRAY["1101"] = '1,北海道,1101,札幌市　中央区';
    for code, body in re.findall(r'GSI\.MUNI_ARRAY\["(\d+)"\]\s*=\s*\'([^\']*)\'', text):
        parts = body.split(",")
        if len(parts) < 4:
            continue
        muni = parts[3].replace("　", "").replace(" ", "")
        table[code.lstrip("0") or "0"] = parts[1].strip() + muni

    def lookup(row: list) -> str | None:
        url = f"{REVGEO_URL}?lat={row[1] / 1e5}&lon={row[2] / 1e5}"
        data = fetch_json(url, GEO_TIMEOUT)
        code = ((data or {}).get("results") or {}).get("muniCd")
        if not code:
            return None
        return table.get(str(code).lstrip("0") or "0")

    print(f"⏳ 市区町村名を調査中… {len(todo)} 地点（同時 {GEO_WORKERS} 件）")
    with ThreadPoolExecutor(max_workers=GEO_WORKERS) as pool:
        names = list(pool.map(lookup, todo))

    index = {name: i for i, name in enumerate(ledger["m"])}
    filled = 0
    for row, name in zip(todo, names):
        if not name:
            continue
        if name not in index:
            index[name] = len(ledger["m"])
            ledger["m"].append(name)
        row[4] = index[name]
        filled += 1
    print(f"✅ 市区町村名を {filled}/{len(todo)} 地点ぶん埋めました")
    return filled


# ------------------------------------------------------------------ 書き出し

def write_json(path: Path, data: dict) -> None:
    """JSONを書き出す（途中で失敗しても壊れたファイルが残らないよう、いったん別名で書く）。"""
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(data, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    tmp.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description="道路の交通量データを取ってくる係")
    parser.add_argument("--rebuild-points", action="store_true",
                        help="観測点台帳の市区町村名を調べ直す（毎週の自動実行用）")
    args = parser.parse_args()

    # 1. いちばん新しい5分値
    latest = fetch_latest()
    if latest is None:
        print("✗ 交通量が取得できませんでした。ファイルは書き換えずに終わります（安全のため）。",
              file=sys.stderr)
        return 1
    timecode, current = latest

    # 2. くらべる相手：1週間前の同じ時刻
    basecode = timecode_of(parse_timecode(timecode) - timedelta(days=7))
    print(f"⏳ 1週間前（{basecode}）の交通量を取得中…")
    base_payload = fetch_json(build_url(basecode))
    base = collect(base_payload) if base_payload else {}
    if base:
        print(f"✅ 1週間前の交通量: {len(base)} 地点")
    else:
        print("⚠️ 1週間前のデータが取れませんでした。今回は「比較なし」で記録します。", file=sys.stderr)

    # 3. 観測点の台帳を育てる（新しい観測点が増えていたら足す）
    ledger, added = merge_points(load_points_file(), current)
    if added:
        print(f"➕ 新しい観測点を {added} 地点、台帳に足しました")
    if args.rebuild_points:
        fill_munis(ledger)
        ledger["u"] = datetime.now(JST).isoformat(timespec="seconds")
        write_json(POINTS_PATH, ledger)
        print(f"💾 {POINTS_PATH.name} を書き出しました（{len(ledger['p'])} 地点）")
    elif added or not POINTS_PATH.exists():
        ledger["u"] = ledger["u"] or datetime.now(JST).isoformat(timespec="seconds")
        write_json(POINTS_PATH, ledger)
        print(f"💾 {POINTS_PATH.name} を書き出しました（{len(ledger['p'])} 地点）")

    # 4. スナップショットを書き出す（同じ観測時刻ならそのまま＝無駄なコミットを増やさない）
    try:
        old = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        old = {}
    same_time = old.get("timecode") == timecode
    adds_base = bool(base) and not old.get("basecode")  # 前回は比較なしだったが今回は取れた、なら書き直す
    if same_time and not adds_base:
        print("⏭ 観測時刻が前回と同じなので、スナップショットはそのままにします。")
        return 0

    status = {
        "generated": datetime.now(JST).isoformat(timespec="seconds"),
        "timecode": timecode,
        "basecode": basecode if base else None,
        "note": SOURCE_NOTE,
        "points": {
            code: [info["up"], info["dn"],
                   (base.get(code) or {}).get("up"), (base.get(code) or {}).get("dn")]
            for code, info in sorted(current.items())
        },
    }
    write_json(STATUS_PATH, status)
    print(f"💾 {STATUS_PATH.name} を書き出しました（観測 {timecode}／{len(current)} 地点）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
