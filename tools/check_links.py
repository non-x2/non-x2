#!/usr/bin/env python3
"""👀 リンクの見張り番 — 公開ページの外部リンクが生きているか確かめる道具。

なぜ作ったか
------------
2026-08-19 に、交通ページの「🌍 世界の公式カメラサイト」18本のうち
🇳🇴 ノルウェーの1本が **404（ページが無い）** になっているのを見つけました。
向こうのサイトが作りかえられても、こちらには何の知らせも来ません。
そこで「切れていないか」を機械で見張れるようにしたのがこの道具です。

使い方
------
    python3 tools/check_links.py              # 公開ページ全部を点検
    ONLY=traffic-app python3 tools/check_links.py   # 1ページだけ点検

結果の見かた
------------
    ✅ 生きている        … そのままでOK
    ↪️ 引っ越している    … 別のURLに飛ばされる。リンクを書き換えたほうが親切
    ❌ 切れている        … 404/410。**直すべきもの**（このときだけ終了コード1）
    ⚠️ 返事が変          … 403/500など。相手側の一時的な不調かもしれない
    🌐 ここから届かない  … この部屋のネットが海外を遮断しているだけ。**切れている証拠ではない**

⚠️ 大事な考え方：「届かない」と「切れている」は違います。
   クラウドの作業部屋からは韓国・台湾などに接続できないことが分かっています。
   それを「リンク切れ」と報告すると、生きているリンクを消してしまいます。
   だからこの道具は、その2つを**はっきり分けて**表示します。

Python の標準機能だけで動きます（追加インストール不要）。
"""

import os
import re
import sys
import ssl
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# 公開しているページ（Webに出しているのはこの5つだけ）
PAGES = [
    "index.html",
    "typhoon-app/index.html",
    "bousai-app/index.html",
    "traffic-app/index.html",
    "world-livecam/index.html",
]

ROOT = Path(__file__).resolve().parent.parent
TIMEOUT = 25          # 1本あたりの待ち時間（秒）
WORKERS = 8           # 同時に確かめる本数（相手のサーバーに迷惑をかけない程度に）

# スマホのふりをする。素っ気ないUser-Agentだと門前払いする相手がいるため。
UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
      "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")

HREF = re.compile(r'href="(https?://[^"]+)"')

# 判定の記号
OK, MOVED, DEAD, ODD, UNREACHABLE = "✅", "↪️", "❌", "⚠️", "🌐"


def collect_links(pages):
    """ページごとの外部リンクを集める。同じURLは1回だけ確かめる。"""
    where = {}   # URL -> それが載っているページの一覧
    for rel in pages:
        path = ROOT / rel
        if not path.exists():
            print(f"（{rel} が見つかりません。とばします）")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for url in sorted(set(HREF.findall(text))):
            where.setdefault(url, []).append(rel)
    return where


def check(url):
    """1本のURLを確かめて (記号, 説明, 最終URL) を返す。"""
    ctx = ssl.create_default_context()
    req = urllib.request.Request(url, headers={"User-Agent": UA}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as res:
            code = res.getcode()
            final = res.geturl()
            if 200 <= code < 300:
                # 飛ばされた先が元と違うなら「引っ越し」として知らせる
                if final.rstrip("/") != url.rstrip("/"):
                    return MOVED, f"{code} → {final}", final
                return OK, str(code), final
            return ODD, str(code), final
    except urllib.error.HTTPError as e:
        if e.code in (404, 410):
            return DEAD, f"{e.code} ページが無い", url
        return ODD, f"{e.code}", url
    except Exception as e:
        # つながらない＝この部屋のネットの都合かもしれない。切れている証拠にはしない。
        return UNREACHABLE, type(e).__name__ + ": " + str(e)[:60], url


def main():
    only = os.environ.get("ONLY", "").strip()
    pages = PAGES
    if only:
        pages = [p for p in PAGES if only in p]
        if not pages:
            print(f"❌ ONLY={only} に当てはまるページがありません。選べるのは：")
            for p in PAGES:
                print("   -", p)
            return 2

    where = collect_links(pages)
    if not where:
        print("外部リンクが1本も見つかりませんでした。")
        return 0

    print(f"👀 リンクの見張り番：{len(pages)}ページ・{len(where)}本のリンクを確かめます\n")

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        results = list(pool.map(check, where.keys()))

    buckets = {OK: [], MOVED: [], DEAD: [], ODD: [], UNREACHABLE: []}
    for url, (mark, detail, _final) in zip(where.keys(), results):
        buckets[mark].append((url, detail, where[url]))

    titles = {
        DEAD:        "❌ 切れている（直すべきもの）",
        MOVED:       "↪️ 引っ越している（書き換えると親切）",
        ODD:         "⚠️ 返事が変（相手の一時的な不調かも）",
        UNREACHABLE: "🌐 この部屋から届かない（切れている証拠ではない）",
        OK:          "✅ 生きている",
    }
    for mark in (DEAD, MOVED, ODD, UNREACHABLE, OK):
        items = buckets[mark]
        if not items:
            continue
        print(f"{titles[mark]}：{len(items)}本")
        # 生きているものは数だけでよい（画面を埋めないため）
        if mark is OK:
            print()
            continue
        for url, detail, pages_of in sorted(items):
            print(f"   {url}")
            print(f"      → {detail}")
            print(f"      載っている場所: {', '.join(pages_of)}")
        print()

    dead = len(buckets[DEAD])
    if dead:
        print(f"❌ 切れているリンクが {dead} 本あります。直してください。")
        return 1
    print("✅ 切れているリンクはありませんでした。")
    if buckets[UNREACHABLE]:
        print(f"（{len(buckets[UNREACHABLE])}本は、この部屋のネットの都合で確かめられませんでした。"
              "実機やローカルで開いてみてください）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
