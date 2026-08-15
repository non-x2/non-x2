#!/usr/bin/env python3
"""どの情報源でも共通で使う「道具箱」。

ここには「取ってくる」「写真が https で見られるか確かめる」「緯度経度から市区町村名を出す」
といった、情報源によらず必要になる作業だけを置いています。

情報源ごとの読み取り方（JICE用・自治体用…）は `sources/` の別ファイルに分けています。

外部のライブラリは使いません（Python 3 の標準機能だけ）。
"""

from __future__ import annotations

import json
import re
import ssl
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta, timezone

JST = timezone(timedelta(hours=9))
USER_AGENT = "non-x2-livecam-db/1.0 (+https://github.com/non-x2/non-x2)"

TIMEOUT = 30          # データを取ってくるときの待ち時間（秒）
IMG_TIMEOUT = 12      # 写真1枚を試すときの待ち時間（秒）
GEO_TIMEOUT = 15      # 市区町村を調べるときの待ち時間（秒）
WORKERS = 8           # 写真を同時に試す数（相手のサーバーに負担をかけすぎない範囲で）
GEO_WORKERS = 5       # 国土地理院に同時に聞く数（控えめに）

# 緯度経度 → 市区町村（国土地理院）
REVGEO_URL = "https://mreversegeocoder.gsi.go.jp/reverse-geocoder/LonLatToAddress"
MUNI_URL = "https://maps.gsi.go.jp/js/muni.js"

# 日本のだいたいの範囲（ここから外れる座標はまちがいとみなす）
JP_BOUNDS = (20.0, 46.6, 122.0, 154.0)  # 南, 北, 西, 東


# ------------------------------------------------------------------ 通信

def open_url(url: str, timeout: int = TIMEOUT):
    """URLを開く。相手が古い設定でも読めるように、ゆるめの https 設定を用意する。"""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    ctx = ssl.create_default_context()
    # 相手（各地方整備局など）のサーバーは設定が古いことがあるため、暗号の条件をゆるめる。
    # 取得するのは公開されている道路・河川の写真だけなので、これで問題ありません。
    ctx.set_ciphers("DEFAULT@SECLEVEL=1")
    return urllib.request.urlopen(req, timeout=timeout, context=ctx)


def fetch_json(url: str, timeout: int = TIMEOUT):
    """JSON（GeoJSONを含む）を取ってくる。"""
    with open_url(url, timeout) as res:
        return json.loads(res.read().decode("utf-8"))


def fetch_text(url: str, timeout: int = TIMEOUT, encoding: str = "utf-8") -> str:
    """文字データを取ってくる。"""
    with open_url(url, timeout) as res:
        return res.read().decode(encoding, errors="replace")


# ------------------------------------------------------------------ 写真URLの確認
#
# ここがこの台帳のいちばん大事な部分です。
#
# 全国のライブカメラの写真URLは、ほとんどが http://（暗号化なし）で公開されています。
# 一方 のんラボの公開ページは https:// なので、http:// の写真をそのまま出そうとすると
# ブラウザが「混在コンテンツ」として問答無用でブロックします。
#
# そこで https:// に読み替えて **1台ずつ実際に開いてみて**、
# ちゃんと画像が返ってくるものだけを「ページ内で見られる写真」として記録します。

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
        with open_url(url, IMG_TIMEOUT) as res:
            if res.status != 200:
                return False
            ctype = (res.headers.get("Content-Type") or "").lower()
            if not ctype.startswith("image/"):
                return False
            # 中身が空同然のものは「表示できない」とみなす
            return len(res.read(1024)) >= 256
    except (urllib.error.URLError, urllib.error.HTTPError, ssl.SSLError, OSError, ValueError):
        return False


def verify_images(cams: list[dict], known_ok: set[str], enabled: bool = True) -> int:
    """各カメラの `img` を https で開けるか確かめ、開けないものは None にする。

    `known_ok` に入っている（前回開けた）URLは、確認をとばす指定のときに再利用します。
    """
    targets = [(i, https_candidate(c.get("img"))) for i, c in enumerate(cams)]
    checkable = [(i, u) for i, u in targets if u]

    if enabled:
        print(f"⏳ 写真 {len(checkable)} 件が https で開けるか確認中（同時 {WORKERS} 件）…")
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            results = list(pool.map(lambda t: check_image(t[1]), checkable))
        ok_map = {i: ok for (i, _), ok in zip(checkable, results)}
    else:
        print("⏭  写真の確認はとばします（前回の結果を引き継ぎます）")
        ok_map = {i: (u in known_ok) for i, u in checkable}

    shown = 0
    for i, cam in enumerate(cams):
        url = https_candidate(cam.get("img"))
        if url and ok_map.get(i):
            cam["img"] = url
            shown += 1
        else:
            # 写真が出せないカメラは、公式ページへのリンクだけ残す（存在ごと消さない）
            cam["img"] = None
    return shown


# ------------------------------------------------------------------ 市区町村名

def fetch_muni_table() -> dict[str, str]:
    """自治体コード → 「都道府県＋市区町村」の対応表を取ってくる（国土地理院）。"""
    text = fetch_text(MUNI_URL)
    table: dict[str, str] = {}
    # 例: GSI.MUNI_ARRAY["1101"] = '1,北海道,1101,札幌市　中央区';
    for code, body in re.findall(r'GSI\.MUNI_ARRAY\["(\d+)"\]\s*=\s*\'([^\']*)\'', text):
        parts = body.split(",")
        if len(parts) < 4:
            continue
        pref, muni = parts[1].strip(), parts[3].strip()
        muni = muni.replace("　", "").replace(" ", "")  # 「札幌市　中央区」→「札幌市中央区」
        table[code.lstrip("0") or "0"] = pref + muni
    return table


def _reverse_geocode_once(lat: float, lon: float) -> str | None:
    """その1点だけで自治体コードを調べる（見つからなければ None）。"""
    try:
        data = fetch_json(f"{REVGEO_URL}?lat={lat}&lon={lon}", GEO_TIMEOUT)
    except (urllib.error.URLError, urllib.error.HTTPError, ssl.SSLError,
            OSError, ValueError, json.JSONDecodeError):
        return None
    code = ((data or {}).get("results") or {}).get("muniCd")
    return (str(code).lstrip("0") or "0") if code else None


# 少しずらして試す位置（度）。0.003度 ≒ 330m、0.006度 ≒ 660m、0.012度 ≒ 1.3km。
# 近いところから順に試し、見つかった時点で打ち切ります
# （ふつうのカメラは最初の1回で決まるので、通信が増えるのは水の上のカメラだけです）。
def _ring(step: float) -> tuple:
    """ある距離の東西南北＋斜めの8方向。"""
    d = step * 0.7  # 斜めは少し内側にして、同じくらいの距離にそろえる
    return ((step, 0.0), (-step, 0.0), (0.0, step), (0.0, -step),
            (d, d), (d, -d), (-d, d), (-d, -d))


_NUDGES = ((0.0, 0.0),) + _ring(0.003) + _ring(0.006) + _ring(0.012)


def reverse_geocode(lat: float, lon: float) -> str | None:
    """緯度経度から自治体コードを調べる。

    ⚠️ 川や海の上に立っているカメラ（橋の上・河口・港など）は、
    その点に自治体の区域が無く、国土地理院が空の答えを返します。
    そのときは **少しずつずらした近くの点** を順に試して、最初に見つかったものを使います。
    """
    for dlat, dlon in _NUDGES:
        code = _reverse_geocode_once(lat + dlat, lon + dlon)
        if code:
            return code
    return None


def place_key(lat: float, lon: float) -> str:
    """市区町村名を覚えておくための鍵（同じ場所なら使い回せる）。"""
    return f"{lat:.4f},{lon:.4f}"


def fill_places(cams: list[dict], cache: dict[str, str], enabled: bool = True) -> int:
    """各カメラに市区町村名（`place`）を付ける。前回の結果があれば使い回す。"""
    for cam in cams:
        if not cam.get("place"):
            cam["place"] = cache.get(place_key(cam["lat"], cam["lon"]), "")

    todo = [c for c in cams if not c.get("place")]
    if not enabled or not todo:
        if not enabled and todo:
            print("⏭  市区町村名の調べ直しはとばします（前回の結果を引き継ぎます）")
        return sum(1 for c in cams if c.get("place"))

    try:
        muni = fetch_muni_table()
    except Exception as exc:  # 対応表が取れなくても他は使えるので続ける
        print(f"⚠️ 自治体コードの対応表が取れませんでした（市区町村名は省略）: {exc}", file=sys.stderr)
        return sum(1 for c in cams if c.get("place"))

    print(f"⏳ 市区町村名を調査中… {len(todo)} 件（同時 {GEO_WORKERS} 件）")
    with ThreadPoolExecutor(max_workers=GEO_WORKERS) as pool:
        codes = list(pool.map(lambda c: reverse_geocode(c["lat"], c["lon"]), todo))
    for cam, code in zip(todo, codes):
        if code and code in muni:
            cam["place"] = muni[code]

    return sum(1 for c in cams if c.get("place"))


# ------------------------------------------------------------------ そのほか

def in_japan(lat: float, lon: float) -> bool:
    """日本のだいたいの範囲に入っているか（座標のまちがい除け）。"""
    s, n, w, e = JP_BOUNDS
    return s <= lat <= n and w <= lon <= e


def tidy(text: str | None) -> str:
    """余分な空白をそろえる。"""
    return re.sub(r"\s+", " ", (text or "").strip())
