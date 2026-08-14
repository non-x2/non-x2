#!/usr/bin/env python3
"""全国の道路ライブカメラの「台帳」を作る係。

やっていること（3ステップ）:

  1. 国土交通省系の公開地図データ（roads.geojson）を取ってくる
     → 全国の道路ライブカメラの「場所（緯度経度）・路線名・カメラのページ」が入っています
  2. HTMLの説明文の中から、写真のURL・ページのURL・管理者名を取り出す
  3. 写真のURLを https:// で開けるか **1台ずつ実際に試して** 確かめる
     → のんラボの公開ページは https なので、http:// のままの写真はブラウザに
       ブロックされて表示できません（「混在コンテンツ」といいます）。
       ここで確かめておけば、ページ側は「出せるカメラ」だけ写真を出せます。
  4. 緯度経度から市区町村名を調べて付ける（国土地理院）
     → 一覧に「静岡県静岡市葵区」のように出て、どこのカメラか分かるようにするため

できあがるもの:
  - traffic-app/data/livecams.json … 人が読める台帳（大もと）
  - traffic-app/index.html の中の台帳 … ページが読む用（自動で書き換えます）

    ※ ページに直接埋め込むのは、index.html を**ダブルクリックで開いたときでも**
       動くようにするためです（file:// では別ファイルの読み込みがブラウザに止められます）。

使い方（手で試すとき）:
    python3 traffic-app/scripts/fetch_livecams.py

    # 写真の確認をとばして速く作りたいとき（確認結果は前回のものを引き継ぎます）
    python3 traffic-app/scripts/fetch_livecams.py --no-verify

    # 市区町村名の調べ直しもとばす（前回の結果を引き継ぎます）
    python3 traffic-app/scripts/fetch_livecams.py --no-geocode

外部のライブラリは使いません（Python 3 の標準機能だけ）。
"""

from __future__ import annotations

import argparse
import json
import re
import ssl
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ------------------------------------------------------------------ 決まりごと

# 大もとのデータ（一般財団法人 国土技術研究センター「道路チェック地図」）
SOURCE_URL = "https://www.jice.or.jp/cms/gis/roads.geojson"
SOURCE_NAME = "国土技術研究センター（JICE）道路チェック地図"
SOURCE_PAGE = "https://www.jice.or.jp/knowledge/maps/roads"

# 緯度経度 → 市区町村（国土地理院）
REVGEO_URL = "https://mreversegeocoder.gsi.go.jp/reverse-geocoder/LonLatToAddress"
MUNI_URL = "https://maps.gsi.go.jp/js/muni.js"

APP_DIR = Path(__file__).resolve().parent.parent
OUT_PATH = APP_DIR / "data" / "livecams.json"
HTML_PATH = APP_DIR / "index.html"
JST = timezone(timedelta(hours=9))
USER_AGENT = "non-x2-traffic-app/1.0 (+https://github.com/non-x2/non-x2)"

TIMEOUT = 30          # 大もとのデータを取るときの待ち時間（秒）
IMG_TIMEOUT = 12      # 写真1枚を試すときの待ち時間（秒）
GEO_TIMEOUT = 15      # 市区町村を調べるときの待ち時間（秒）
WORKERS = 8           # 同時に試す数（相手のサーバーに負担をかけすぎない範囲で）
GEO_WORKERS = 5       # 国土地理院に同時に聞く数（控えめに）

# 写真が無いカメラに使われている「準備中」画像。これは写真として扱いません。
NO_IMAGE_MARK = "no_link.jpg"

# index.html の中の、台帳を書き込む場所の目印
EMBED_START = '<script id="livecam-data" type="application/json">'
EMBED_END = "</script>"


# ------------------------------------------------------------------ 小さな道具

def _open(url: str, timeout: int):
    """URLを開く。相手が古い設定でも読めるように、ゆるめの https 設定を用意する。"""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    ctx = ssl.create_default_context()
    # 相手（各地方整備局）のサーバーは設定が古いことがあるため、暗号の条件をゆるめる。
    # 取得するのは公開されている道路の写真だけなので、これで問題ありません。
    ctx.set_ciphers("DEFAULT@SECLEVEL=1")
    return urllib.request.urlopen(req, timeout=timeout, context=ctx)


def fetch_source() -> dict:
    """大もとの地図データ（GeoJSON）を取ってくる。"""
    with _open(SOURCE_URL, TIMEOUT) as res:
        return json.loads(res.read().decode("utf-8"))


def tidy_road_name(name: str) -> str:
    """路線名の表記ゆれをそろえる（「国道 7号」→「国道7号」など）。"""
    name = re.sub(r"\s+", " ", (name or "").strip())
    name = re.sub(r"^国道\s+", "国道", name)
    name = re.sub(r"^(国道\d+)\s*号", r"\1号", name)
    return name


def parse_feature(feature: dict) -> dict | None:
    """地図データ1件から、必要な情報だけ取り出す。"""
    geom = feature.get("geometry") or {}
    coords = geom.get("coordinates") or []
    if geom.get("type") != "Point" or len(coords) < 2:
        return None
    try:
        lon, lat = float(coords[0]), float(coords[1])
    except (TypeError, ValueError):
        return None
    # 日本の範囲から大きく外れているものは、座標のまちがいとみなして捨てる
    if not (20.0 <= lat <= 46.5 and 122.0 <= lon <= 154.0):
        return None

    props = feature.get("properties") or {}
    desc = props.get("discription") or props.get("description") or ""

    # 写真のURL（<img src='...'>）
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
    owner = m.group(1).strip() if m else ""

    return {
        "n": tidy_road_name(props.get("title", "")),   # n = 路線名
        "y": round(lat, 6),                            # y = 緯度
        "x": round(lon, 6),                            # x = 経度
        "i": img,                                      # i = 写真のURL（後で https を確認）
        "p": page,                                     # p = カメラのページ
        "m": owner,                                    # m = 管理者
    }


def https_candidate(url: str | None) -> str | None:
    """http:// の写真URLを https:// に読み替えた候補を返す。"""
    if not url:
        return None
    if url.startswith("https://"):
        return url
    if url.startswith("http://"):
        return "https://" + url[len("http://"):]
    return None


def check_image(url: str) -> bool:
    """その写真URLが https で本当に「画像」として開けるかを確かめる。"""
    try:
        with _open(url, IMG_TIMEOUT) as res:
            if res.status != 200:
                return False
            ctype = (res.headers.get("Content-Type") or "").lower()
            if not ctype.startswith("image/"):
                return False
            # 中身が空同然のものは「表示できない」とみなす
            head = res.read(1024)
            return len(head) >= 256
    except (urllib.error.URLError, urllib.error.HTTPError, ssl.SSLError, OSError, ValueError):
        return False


# ------------------------------------------------------------------ 市区町村名を付ける

def fetch_muni_table() -> dict[str, str]:
    """自治体コード → 「都道府県＋市区町村」の対応表を取ってくる（国土地理院）。"""
    with _open(MUNI_URL, TIMEOUT) as res:
        text = res.read().decode("utf-8", errors="replace")
    table: dict[str, str] = {}
    # 例: GSI.MUNI_ARRAY["1101"] = '1,北海道,1101,札幌市　中央区';
    for code, body in re.findall(r'GSI\.MUNI_ARRAY\["(\d+)"\]\s*=\s*\'([^\']*)\'', text):
        parts = body.split(",")
        if len(parts) < 4:
            continue
        pref, muni = parts[1].strip(), parts[3].strip()
        # 「札幌市　中央区」のような全角スペースを詰めて「札幌市中央区」にする
        muni = muni.replace("　", "").replace(" ", "")
        table[code.lstrip("0") or "0"] = pref + muni
    return table


def reverse_geocode(lat: float, lon: float) -> str | None:
    """緯度経度から自治体コードを調べる。"""
    url = f"{REVGEO_URL}?lat={lat}&lon={lon}"
    try:
        with _open(url, GEO_TIMEOUT) as res:
            data = json.loads(res.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, ssl.SSLError,
            OSError, ValueError, json.JSONDecodeError):
        return None
    code = ((data or {}).get("results") or {}).get("muniCd")
    if not code:
        return None
    return str(code).lstrip("0") or "0"


def fill_places(cams: list[dict], cache: dict[str, str], enabled: bool) -> int:
    """各カメラに市区町村名（キー "a"）を付ける。前回の結果があれば使い回す。"""
    for cam in cams:
        cam["a"] = cache.get(place_key(cam), "")

    todo = [cam for cam in cams if not cam["a"]]
    if not enabled or not todo:
        if not enabled:
            print("⏭  市区町村名の調べ直しはとばします（前回の結果を引き継ぎます）")
        return sum(1 for cam in cams if cam["a"])

    try:
        muni = fetch_muni_table()
    except Exception as exc:  # 対応表が取れなくても、他の情報は使えるので続ける
        print(f"⚠️ 自治体コードの対応表が取れませんでした（市区町村名は省略します）: {exc}", file=sys.stderr)
        return sum(1 for cam in cams if cam["a"])

    print(f"⏳ 市区町村名を調査中… {len(todo)} 件（同時 {GEO_WORKERS} 件）")
    with ThreadPoolExecutor(max_workers=GEO_WORKERS) as pool:
        codes = list(pool.map(lambda c: reverse_geocode(c["y"], c["x"]), todo))
    for cam, code in zip(todo, codes):
        if code and code in muni:
            cam["a"] = muni[code]

    return sum(1 for cam in cams if cam["a"])


def place_key(cam: dict) -> str:
    """市区町村名を覚えておくための鍵（場所が同じなら使い回せる）。"""
    return f"{cam['y']:.4f},{cam['x']:.4f}"


# ------------------------------------------------------------------ ページへの埋め込み

def to_compact(data: dict) -> dict:
    """同じ文字のくり返しをまとめて、ページに載せる用の軽い形にする。

    n=路線名 / m=管理者 / a=市区町村 / p=カメラのページ / b=写真URLの前半
    c=カメラ本体 [緯度*10万, 経度*10万, n番号, m番号, a番号, p番号, b番号, 写真URLの後半]
    """
    tables: dict[str, list[str]] = {"n": [], "m": [], "a": [], "p": [], "b": []}
    index: dict[str, dict[str, int]] = {k: {} for k in tables}

    def idx(kind: str, value: str) -> int:
        if not value:
            return -1
        if value not in index[kind]:
            index[kind][value] = len(tables[kind])
            tables[kind].append(value)
        return index[kind][value]

    rows = []
    for cam in data["cams"]:
        img = cam.get("i") or ""
        if img:
            cut = img.rfind("/") + 1
            head, tail = img[:cut], img[cut:]
        else:
            head, tail = "", ""
        rows.append([
            round(cam["y"] * 1e5),
            round(cam["x"] * 1e5),
            idx("n", cam.get("n", "")),
            idx("m", cam.get("m", "")),
            idx("a", cam.get("a", "")),
            idx("p", cam.get("p", "")),
            idx("b", head),
            tail,
        ])

    return {
        "u": data["updated"][:10],
        "n": tables["n"], "m": tables["m"], "a": tables["a"],
        "p": tables["p"], "b": tables["b"], "c": rows,
    }


def write_html_embed(data: dict) -> bool:
    """index.html の中の台帳を書き換える。"""
    if not HTML_PATH.exists():
        print(f"⚠️ {HTML_PATH} が見つからないので、ページへの埋め込みは省略します", file=sys.stderr)
        return False

    html = HTML_PATH.read_text(encoding="utf-8")
    start = html.find(EMBED_START)
    if start < 0:
        print("⚠️ index.html に台帳の目印が見つかりませんでした", file=sys.stderr)
        return False
    body_start = start + len(EMBED_START)
    end = html.find(EMBED_END, body_start)
    if end < 0:
        print("⚠️ index.html の台帳の終わりが見つかりませんでした", file=sys.stderr)
        return False

    payload = json.dumps(to_compact(data), ensure_ascii=False, separators=(",", ":"))
    # </script> が混ざると途中でページが切れてしまうので、念のため無害化する
    payload = payload.replace("</", "<\\/")

    HTML_PATH.write_text(html[:body_start] + "\n" + payload + "\n" + html[end:], encoding="utf-8")
    return True


# ------------------------------------------------------------------ 本体

def build(verify: bool = True, geocode: bool = True) -> dict:
    print(f"⏳ 大もとのデータを取得中… {SOURCE_URL}")
    raw = fetch_source()
    features = raw.get("features") or []
    if not features:
        raise RuntimeError("大もとのデータが空でした（相手のサイトの不調かもしれません）")

    cams: list[dict] = []
    for feature in features:
        cam = parse_feature(feature)
        if cam and cam["n"]:
            cams.append(cam)
    print(f"✅ カメラ {len(cams)} 台の情報を読み取りました")

    # 前回の結果（写真の確認・市区町村名を使い回すため）
    #   前に「開けた」と分かっている写真URLの一覧と、場所ごとの市区町村名
    known_ok: set[str] = set()
    place_cache: dict[str, str] = {}
    if OUT_PATH.exists():
        try:
            old = json.loads(OUT_PATH.read_text(encoding="utf-8"))
            for cam in old.get("cams", []):
                if cam.get("i"):
                    known_ok.add(cam["i"])
                if cam.get("a"):
                    place_cache[place_key(cam)] = cam["a"]
        except (json.JSONDecodeError, OSError, KeyError):
            pass

    # 写真URLを https に読み替えて、実際に開けるか確かめる
    targets = [(idx, https_candidate(cam["i"])) for idx, cam in enumerate(cams)]
    checkable = [(idx, url) for idx, url in targets if url]

    if verify:
        print(f"⏳ 写真 {len(checkable)} 件が https で開けるか確認中（同時 {WORKERS} 件）…")
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            results = list(pool.map(lambda t: check_image(t[1]), checkable))
        ok_map = {idx: ok for (idx, _), ok in zip(checkable, results)}
    else:
        print("⏭  写真の確認はとばします（前回の結果を引き継ぎます）")
        ok_map = {idx: (url in known_ok) for idx, url in checkable}

    shown = 0
    for idx, cam in enumerate(cams):
        url = https_candidate(cam["i"])
        if url and ok_map.get(idx):
            cam["i"] = url
            shown += 1
        else:
            # 写真が出せないカメラは、ページへのリンクだけ残す
            cam["i"] = None

    print(f"📷 写真をその場で出せるカメラ: {shown} 台 / ページのみ: {len(cams) - shown} 台")

    placed = fill_places(cams, place_cache, geocode)
    print(f"🗾 市区町村名が付いたカメラ: {placed} 台")

    # 空っぽの項目は載せない（ファイルを軽くするため）
    for cam in cams:
        for key in ("i", "p", "m", "a"):
            if not cam.get(key):
                cam.pop(key, None)

    return {
        "updated": datetime.now(JST).isoformat(timespec="seconds"),
        "source": {"name": SOURCE_NAME, "page": SOURCE_PAGE, "data": SOURCE_URL},
        "count": len(cams),
        "withImage": shown,
        "withPlace": placed,
        "cams": cams,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="道路ライブカメラの台帳を作ります")
    parser.add_argument(
        "--no-verify",
        action="store_true",
        help="写真が開けるかの確認をとばす（速いかわりに前回の結果を使います）",
    )
    parser.add_argument(
        "--no-geocode",
        action="store_true",
        help="市区町村名の調べ直しをとばす（前回の結果を使います）",
    )
    args = parser.parse_args()

    try:
        data = build(verify=not args.no_verify, geocode=not args.no_geocode)
    except Exception as exc:  # 取得に失敗したら、今ある台帳は上書きしない（安全装置）
        print(f"⚠️ 取得に失敗したので、今ある台帳はそのままにします: {exc}", file=sys.stderr)
        return 1

    # 安全装置: 台数が極端に少ないときは、こわれたデータで上書きしない
    if data["count"] < 500:
        print(
            f"⚠️ カメラが {data['count']} 台しか読めませんでした（いつもは1400台前後）。"
            "こわれたデータで上書きしないため中止します。",
            file=sys.stderr,
        )
        return 1

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    size_kb = OUT_PATH.stat().st_size / 1024
    print(f"💾 保存しました: {OUT_PATH}（{size_kb:.0f} KB）")

    if write_html_embed(data):
        html_kb = HTML_PATH.stat().st_size / 1024
        print(f"💾 ページにも埋め込みました: {HTML_PATH}（{html_kb:.0f} KB）")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
