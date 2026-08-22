#!/usr/bin/env python3
"""🌀 台風ページの「予備の文章（④スナップショット）」が古くなっていないか見張る道具。

■ なぜ必要か
台風ページは4段構えで中身を出します。
    ① ブラウザから気象庁へ直接（開くたび最新）
    ② data/latest.json（GitHub Actionsが毎時25分に更新）
    ③ 端末に残った前回のデータ（圏外でも出る）
    ④ 手書きのスナップショット（①②③が全部ダメなときの最後の受け皿）

①〜③は自動で新しくなりますが、**④だけは手書き**なので、
だれも直さなければ何か月でも古いまま残ります。
2026-08-22 に点検したときは、④が12日前（台風15号の話）のまま止まっていました。

この道具は「④が何日前か」を数えて、古すぎたら ❌ を出します。

■ 2つの見張り方
    1. 日付を数える（通信なし・いつでも動く）……<time id="updated-at" datetime="..."> を見る
    2. 台風の番号を照合する（通信あり・つながらなければ黙って飛ばす）
       ……気象庁がいま出している台風の番号と、④が書いている番号を見くらべる

2は「日付は新しいのに中身が古い」ような取りこぼしを拾うためのおまけです。
通信できないときは**判定しません**（つながらないことを「異常」と言い張らないため）。

■ 使い方（手で試すとき）
    python3 tools/check_typhoon_snapshot.py
    python3 tools/check_typhoon_snapshot.py --max-days 14   # 何日で古いとみなすか
    python3 tools/check_typhoon_snapshot.py --offline       # 通信せず日付だけ見る

■ 終了コード
    0 … 問題なし
    1 … ④が古い（直してほしい）

外部のライブラリは使いません（Python 3 の標準機能だけ）。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HTML = ROOT / "typhoon-app" / "index.html"
TARGET_URL = "https://www.jma.go.jp/bosai/typhoon/data/targetTc.json"
JST = timezone(timedelta(hours=9))

# 何日たったら「古い」とみなすか。台風シーズンは1週間もあれば顔ぶれが入れ替わるので7日。
DEFAULT_MAX_DAYS = 7


def read_stamp(text: str) -> datetime:
    """ヘッダーの <time id="updated-at" datetime="..."> を読み取って日時にする。"""
    m = re.search(r'<time id="updated-at" datetime="([^"]+)"', text)
    if not m:
        sys.exit('❌ typhoon-app/index.html に <time id="updated-at" datetime="..."> が見つかりません')
    raw = m.group(1)
    # 「2026-08-22T13:30+09:00」のように秒が無い書き方も受け取れるようにする
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        sys.exit(f"❌ datetime の書き方が読めません: {raw}（例：2026-08-22T13:30+09:00）")


def read_snapshot_numbers(text: str) -> list[str]:
    """④の「🌀 発生中の台風」に書いてある台風番号を取り出す。

    「すでに通過した台風」の見出しまで拾わないよう、その章の中だけを見る。
    """
    m = re.search(r"<h2>🌀 発生中の台風</h2>(.*?)</section>", text, re.S)
    if not m:
        return []
    return re.findall(r"<h3>台風(\d+)号", m.group(1))


def fetch_live_numbers(timeout: float = 20.0) -> list[str] | None:
    """気象庁がいま出している台風の番号を取ってくる。取れなければ None（＝判定しない）。"""
    req = urllib.request.Request(TARGET_URL, headers={"User-Agent": "non-x2-snapshot-check/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            data = json.loads(res.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError, TimeoutError, OSError):
        return None
    out = []
    for row in data if isinstance(data, list) else []:
        n = str(row.get("typhoonNumber") or "")
        # 「2618」→「18」。まだ番号が付いていない熱帯低気圧（例：c）は数えない
        if n[-2:].isdigit():
            out.append(str(int(n[-2:])))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="台風ページの予備の文章（④）が古くないか見張る")
    ap.add_argument("--max-days", type=int, default=DEFAULT_MAX_DAYS,
                    help=f"何日たったら古いとみなすか（既定 {DEFAULT_MAX_DAYS} 日）")
    ap.add_argument("--offline", action="store_true", help="気象庁へ通信せず、日付だけを見る")
    args = ap.parse_args()

    text = HTML.read_text(encoding="utf-8")
    stamp = read_stamp(text)
    now = datetime.now(JST)
    age_days = (now - stamp).total_seconds() / 86400

    print(f"🌀 台風ページの予備の文章（④スナップショット）の点検")
    print(f"   書かれている日時: {stamp.astimezone(JST):%Y-%m-%d %H:%M}（日本時間）")
    print(f"   いま:             {now:%Y-%m-%d %H:%M}（日本時間）")

    if age_days < -1:
        print(f"❌ 予備の文章の日時が未来になっています（{-age_days:.1f}日先）。書き間違いかもしれません。")
        return 1

    print(f"   古さ:             {age_days:.1f} 日前（{args.max_days} 日を超えたら ❌）")

    stale = age_days > args.max_days

    # ── おまけの照合：気象庁の番号と見くらべる ──────────────────────
    snap = read_snapshot_numbers(text)
    if args.offline:
        print("   （--offline なので気象庁との照合はしていません）")
    else:
        live = fetch_live_numbers()
        if live is None:
            print("   ⚠️ 気象庁につながらなかったので、番号の照合はしていません（これは異常ではありません）")
        elif not snap:
            print("   ⚠️ ④から台風番号を読み取れませんでした（章の見出しが変わったのかもしれません）")
        else:
            gone = [n for n in snap if n not in live]
            added = [n for n in live if n not in snap]
            print(f"   ④が書いている台風: {'・'.join(snap)}号")
            print(f"   気象庁のいまの台風: {'・'.join(live) + '号' if live else '（発生中の台風なし）'}")
            if gone or added:
                stale = True
                if gone:
                    print(f"   ❌ ④にあるのに気象庁にはもう無い: {'・'.join(gone)}号")
                if added:
                    print(f"   ❌ 気象庁にあるのに④に書かれていない: {'・'.join(added)}号")
            else:
                print("   ✅ 台風の顔ぶれは気象庁と一致しています")

    print()
    if stale:
        print("❌ 予備の文章（④）が古くなっています。")
        print("   ④は「気象庁にも控えにも端末にもつながらないとき」に出る最後の受け皿です。")
        print("   ふだんは見えませんが、いざというときに古い台風の話が出てしまいます。")
        print("   → Claudeに「台風ページの予備の文章を更新して」と頼んでください。")
        print("     直す場所は typhoon-app/index.html の中の次のところです：")
        print("       ・ヘッダーの <time id=\"updated-at\" datetime=\"...\">")
        print("       ・#snapshot-banner の但し書き（何日の発表か）")
        print("       ・#status-snapshot（🕐いま日本は／🌀発生中の台風／👀今後の見通し）")
        print("       ・✅すでに通過した台風／🔎情報源のリンク")
        print("       ・🗾マップの #map-static・凡例・#map-note・viewBox・aria-label")
        return 1

    print("✅ 予備の文章（④）は新しいままです。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
