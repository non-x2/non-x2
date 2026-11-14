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
    🤖 機械おことわり    … 何度も調べて「機械からは断られる」と分かっているもの（下の表）
    🌐 ここから届かない  … この部屋のネットが海外を遮断しているだけ。**切れている証拠ではない**

⚠️ 大事な考え方：「届かない」と「切れている」は違います。
   クラウドの作業部屋からは韓国・台湾などに接続できないことが分かっています。
   それを「リンク切れ」と報告すると、生きているリンクを消してしまいます。
   だからこの道具は、その2つを**はっきり分けて**表示します。

🤖 「調べ済み」を覚えておく（2026-11-14 追加＝自己改良バックログの候補42）
   ⚠️ の欄に出る何本かは、**毎回おなじ顔ぶれ**です。
   そのままだと、次に見た人が**また同じリンクを一から調べ直す**ことになります。
   そこで、調べて答えが出たものは下の `KNOWN_BLOCKED` に書いておき、
   ⚠️ とは別の **🤖 枠**に分けて出すようにしました（責めない別枠）。
   「切れている」の判定（❌＝終了コード1）は**まったく変えていません**。

   📏 2026-11-14 の実測でわかったこと：
   この4本は、本物のブラウザ（Chromium）で開いても**同じ403／429**でした。
   つまり「素っ気ないUser-Agentだから断られている」のではなく、
   **クラウドの作業部屋そのものが断られている**ようです。
   だから 🤖 の説明は「ブラウザなら開ける」とは書きません（確かめられていないため）。
   のんさんのご自宅のパソコンで開けるかどうかは、**人の目で見るのがいちばん確実**です。

   ⏰ この表は**手書き**なので、放っておくと古くなります（＝候補33「時間とともに嘘になる数字」の仲間）。
   そこで、表に書いた相手の返事が変わったときは、道具のほうから
   「表を見直してください」と知らせます（黙って隠さない）。

Python の標準機能だけで動きます（追加インストール不要）。
"""

import os
import re
import sys
import ssl
import time
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# Windows（日本語）の画面でも絵文字（✅など）で落ちないよう、出力を utf-8 にそろえる
# （Linux の GitHub Actions では元から utf-8 なので変化なし）
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

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
KNOWN = "🤖"          # 調べ済み＝「機械からのアクセスは断られる」と分かっているもの

# 🤖 調べ済みのリンク（URL → いつ調べたか・どんな返事か・ひとこと）
#    ここに書いたURLが「書いてある番号と同じ返事」を返したときだけ、⚠️ ではなく 🤖 に分けます。
#    ちがう番号（例：404）になったら、ごまかさず ❌／⚠️ のほうに出ます。
KNOWN_BLOCKED = {
    "https://teideninfo.tepco.co.jp/": {
        "code": 403, "checked": "2026-11-14",
        "note": "東京電力の停電情報。403＝おことわり（ブラウザでも同じ返事でした）",
    },
    "https://traininfo.jreast.co.jp/train_info/": {
        "code": 403, "checked": "2026-11-14",
        "note": "JR東日本の運行情報。403＝おことわり（ブラウザでも同じ返事でした）",
    },
    "https://www.c-ihighway.jp/cgi/camera.cgi": {
        "code": 403, "checked": "2026-11-14",
        "note": "中日本高速のカメラ一覧。403＝おことわり（ブラウザでも同じ返事でした）",
    },
    "https://www.shutoko.jp/traffic/": {
        "code": 429, "checked": "2026-11-14",
        "note": "首都高の交通状況。429＝混みすぎ（人かどうかを確かめる画面が出ます）",
    },
}


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

    urls = list(where.keys())
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        results = list(pool.map(check, urls))

    # ⚠️ 同時にたくさんたたくと、生きているサイトでも接続を切られることがあります
    #    （実際に阪神高速・本四高速がそうなり、あとから1本ずつ試したら普通に開けました）。
    #    「届かない」と報告したものだけ、時間をおいて1本ずつ確かめ直します。
    #    ＝ 自分の測り方を先に疑う。誤って「切れている」と言わないための保険です。
    retry_idx = [i for i, r in enumerate(results) if r[0] is UNREACHABLE]
    if retry_idx:
        print(f"（{len(retry_idx)}本が届きませんでした。混み合っただけかもしれないので、"
              f"1本ずつ確かめ直します…）\n")
        for i in retry_idx:
            time.sleep(1.0)
            results[i] = check(urls[i])

    buckets = {OK: [], MOVED: [], DEAD: [], ODD: [], KNOWN: [], UNREACHABLE: []}
    stale = []   # 調べ済みの表と、きょうの返事が食い違ったもの（表の見直しをお願いする）
    for url, (mark, detail, _final) in zip(urls, results):
        known = KNOWN_BLOCKED.get(url)
        if known:
            if mark is ODD and detail.strip().startswith(str(known["code"])):
                # 表どおりの返事＝調べ済み。⚠️ ではなく責めない別枠へ
                buckets[KNOWN].append(
                    (url, f'{detail}（{known["checked"]} に調査）{known["note"]}', where[url]))
                continue
            # 表とちがう返事になった＝表が古いかもしれない。隠さず元の欄に出したうえで知らせる
            stale.append((url, mark, detail, known))
        buckets[mark].append((url, detail, where[url]))

    titles = {
        DEAD:        "❌ 切れている（直すべきもの）",
        MOVED:       "↪️ 引っ越している（書き換えると親切）",
        ODD:         "⚠️ 返事が変（相手の一時的な不調かも）",
        KNOWN:       "🤖 機械おことわり（調べ済み・直す必要はありません）",
        UNREACHABLE: "🌐 この部屋から届かない（切れている証拠ではない）",
        OK:          "✅ 生きている",
    }
    for mark in (DEAD, MOVED, ODD, KNOWN, UNREACHABLE, OK):
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

    # 表に書いた相手の返事が変わったら、黙って隠さずお知らせする（表は手書きなので古くなる）
    if stale:
        print(f"⏰ 調べ済みの表（KNOWN_BLOCKED）と返事が食い違ったリンクが {len(stale)} 本あります。"
              "表を見直してください：")
        for url, mark, detail, known in sorted(stale):
            print(f"   {url}")
            print(f"      → 表では {known['code']}（{known['checked']} に調査）／"
                  f"きょうは {mark} {detail}")
        print()

    dead = len(buckets[DEAD])
    if dead:
        print(f"❌ 切れているリンクが {dead} 本あります。直してください。")
        return 1
    print("✅ 切れているリンクはありませんでした。")
    if buckets[KNOWN]:
        print(f"（{len(buckets[KNOWN])}本は「機械おことわり」と調べ済みのものです。"
              "調べ直さなくて大丈夫です）")
    if buckets[UNREACHABLE]:
        print(f"（{len(buckets[UNREACHABLE])}本は、この部屋のネットの都合で確かめられませんでした。"
              "実機やローカルで開いてみてください）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
