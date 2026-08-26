#!/usr/bin/env python3
"""🌀 台風ページの「予備の文章（④スナップショット）」の**下書き**を自動で作る道具。

■ なぜ必要か
台風ページは4段構えで中身を出します（①気象庁へ直接 → ②data/latest.json →
③端末に残った前回分 → ④手書きのスナップショット）。
このうち**④だけが手書き**で、直すところが index.html の中に15か所もあります。
2026-08-22 に更新したときは、書き落としが起きないよう置換スクリプトを
その場で1本書いて全部を1回で直しました。その手間を毎回くり返さずに済むよう、
②の `data/latest.json`（毎時25分に自動で新しくなる）から**下書きを作って画面に出す**のが
この道具です。

■ 🚧 わざと「下書き止まり」にしています（ここが肝）
ファイルは**1文字も書き換えません**。画面に出すだけです。
④は「気象庁にも控えにも端末にもつながらないとき」に出る最後の受け皿なので、
**人が目で確かめた文章**であることに意味があります。自動で流し込んでしまうと、
「誰も読んでいない文章」が最後の受け皿になってしまいます。
出てきた下書きは、必ず気象庁の発表と見くらべてから貼ってください。

■ 使い方
    python3 tools/typhoon_snapshot_draft.py            # 控え（data/latest.json）から下書きを作る
    python3 tools/typhoon_snapshot_draft.py --main 18  # 「今後の見通し」に使う台風を番号で選ぶ
    python3 tools/typhoon_snapshot_draft.py --json 別のファイル.json

■ この道具が作らないもの（＝手作業のまま残るところ）
    ・✅ すでに通過した台風 …… 過去の話なので、いまの控えには入っていません
    ・🗾 マップ（#map-static）の線 …… 座標は `tools/typhoon_map_coords.py`（別のPRで追加予定）が出します
    ・「🕐 いま日本はどうなの？」のまとめ文 …… いちばん人の言葉が要るところ
  最後にチェックリストとして画面に出しますので、消し忘れの防止にお使いください。

■ 文章の作り方
`typhoon-app/index.html` の中のJavaScript（①②のときに画面を組み立てている関数）と
**同じ言い回し**になるように写しています。そのため①②で見えている文章と、
④の下書きの文章がそろいます。

外部のライブラリは使いません（Python 3 の標準機能だけ）。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_JSON = ROOT / "typhoon-app" / "data" / "latest.json"
JST = timezone(timedelta(hours=9))
WD = "日月火水木金土"


# ── index.html の中の同名の関数と同じ動きにしてある小さな部品 ──────────────

def jst(iso: str) -> datetime | None:
    """気象庁の時刻（"2026-08-26T05:00:00+09:00"）を日本時間にする。"""
    try:
        return datetime.fromisoformat(iso).astimezone(JST)
    except (TypeError, ValueError):
        return None


def fmt_day(iso: str) -> str:
    d = jst(iso)
    return f"{d.month}月{d.day}日（{WD[(d.weekday() + 1) % 7]}）" if d else ""


def fmt_short(iso: str) -> str:
    d = jst(iso)
    if not d:
        return ""
    return f"{d.month}/{d.day} {d.hour}時" + (f"{d.minute}分" if d.minute else "")


def val(v) -> str:
    """気象庁は「値なし」を "-" で送ってくることがある（そのまま出すと画面に「-」と出る）。"""
    s = "" if v is None else str(v)
    return s if s and s != "-" else ""


def is_typhoon(t: dict) -> bool:
    """まだ番号が付いていない熱帯低気圧（番号が "b" など）を見分ける。"""
    return bool(re.fullmatch(r"[0-9]+", str(t.get("numberShort") or "")))


def tc_name(t: dict) -> str:
    if not is_typhoon(t):
        return t.get("category") or "熱帯低気圧"
    return f"台風{t['numberShort']}号" + (f"（{t['name']}）" if t.get("name") else "")


def sev_class(intensity: str | None) -> str:
    s = intensity or ""
    if "猛烈" in s:
        return "sev-violent"
    if "非常に強い" in s:
        return "sev-vstrong"
    return "sev-strong"


def strength_word(p: dict, t: dict) -> str:
    s = [x for x in (val(p.get("scale")), val(p.get("intensity"))) if x]
    if s:
        return "・".join(s)
    return val(p.get("category")) or t.get("category") or "台風"


def move_text(p: dict) -> str:
    c, sp = val(p.get("course")), val(p.get("speedKmh"))
    if not c or "不定" in c:
        return (f"で時速{sp}kmで進んでいます（進む向きは定まっていません）" if sp
                else "でほとんど停滞しています")
    return f"を{c}へ" + (f"時速{sp}kmで進行中" if sp else "ゆっくり進行中")


def km(v) -> str:
    return str(round(float(v))) if v else ""


def n(v) -> str:
    """数字を人が書くかたちにする（960.0 → 960、5.5 → 5.5）。

    JSONの数字をPythonで読むと 960.0 のように「.0」が付くことがあり、
    そのまま貼ると「中心気圧960.0hPa」という見慣れない書き方になるため。
    """
    f = float(v)
    return str(int(f)) if f == int(f) else str(f)


# ── 下書きを組み立てる ────────────────────────────────────────────

def draft_active(t: dict) -> str:
    """🌀 発生中の台風 の <li> を1つぶん作る。"""
    a = t.get("analysis") or {}
    last = (t.get("forecast") or [{}])[-1]
    tag = strength_word(a, t) if is_typhoon(t) else "台風のたまご"
    lines = [f'        <li class="status-item watch">',
             f'          <span class="tag watch">{tag}</span>',
             f"          <h3>{tc_name(t)}</h3>"]
    if a:
        body = (f"{fmt_short(a.get('validTime'))}現在、<strong>{a.get('location', '')}</strong>"
                f"{move_text(a)}。")
        # 値が無い項目があっても「、、」と句読点が重ならないよう、あるものだけ並べてつなぐ
        parts = []
        if a.get("pressure"):
            parts.append(f"中心気圧{n(a['pressure'])}hPa")
        if a.get("windMs"):
            parts.append(f"最大風速{n(a['windMs'])}m/s"
                         + (f"（最大瞬間{n(a['gustMs'])}m/s）" if a.get("gustMs") else ""))
        body += "、".join(parts)
        if is_typhoon(t):
            body += ("、" if parts else "") + f"強さは<strong>「{strength_word(a, t)}」</strong>です。"
        else:
            body += "。" if parts else ""
        if a.get("stormRadiusKm"):
            body += f"暴風域は半径およそ{km(a['stormRadiusKm'])}km、"
        if a.get("galeRadiusKm"):
            body += f"強風域は半径およそ{km(a['galeRadiusKm'])}kmです。"
        lines.append(f"          <p>{body}</p>")
    if last:
        lines.append(f"          <p>気象庁の予報では、<strong>{fmt_day(last.get('validTime'))}ごろ"
                     f"{last.get('location', '')}</strong>に進み、そのときの見込みは"
                     f"「{strength_word(last, t)}」です。</p>")
    lines.append("        </li>")
    return "\n".join(lines)


def draft_timeline(t: dict) -> str:
    """👀 今後の見通し の <li>（時系列）を作る。"""
    pts = ([t["analysis"]] if t.get("analysis") else []) + list(t.get("forecast") or [])
    out = []
    for p in pts:
        is_now = p.get("hours") == 0
        body = f"{'<strong>' if is_now else ''}{p.get('location', '')}{'</strong>' if is_now else ''}"
        body += f"{move_text(p)}。"
        parts = []
        if p.get("pressure"):
            parts.append(f"中心気圧{n(p['pressure'])}hPa")
        if p.get("windMs"):
            parts.append(f"最大風速{n(p['windMs'])}m/s")
        body += "・".join(parts)
        if p.get("circleKm"):
            body += f"。予報円の半径は約{km(p['circleKm'])}km"
        if p.get("stormRadiusKm"):
            body += f"、暴風域は半径約{km(p['stormRadiusKm'])}km"
        body += "。"
        out.append("\n".join([
            f'        <li class="tl-item {sev_class(p.get("intensity"))} '
            f'{"is-now" if is_now else "is-forecast"}">',
            '          <span class="tl-dot"></span>',
            f'          <div class="tl-head"><span class="tl-date">{fmt_short(p.get("validTime"))}'
            f'{"（実況）" if is_now else "（予報）"}</span>'
            f'<span class="tl-badge">{strength_word(p, t)}</span></div>',
            f'          <p class="tl-body">{body}</p>',
            "        </li>",
        ]))
    return "\n".join(out)


def pick_main(typhoons: list[dict], want: str | None) -> dict | None:
    """「今後の見通し」に使う台風を選ぶ。番号の指定が無ければ発表の1つめ。"""
    if not typhoons:
        return None
    if want:
        for t in typhoons:
            if str(t.get("numberShort")) == str(want).lstrip("0"):
                return t
        print(f"⚠️ 台風{want}号は控えの中に見つかりませんでした。1つめを使います。\n")
    return typhoons[0]


def main() -> int:
    ap = argparse.ArgumentParser(description="台風ページの予備の文章（④）の下書きを作る")
    ap.add_argument("--json", type=Path, default=DEFAULT_JSON, help="読み込む控えのファイル")
    ap.add_argument("--main", help="「今後の見通し」に使う台風の番号（例：18）")
    args = ap.parse_args()

    if not args.json.exists():
        sys.exit(f"❌ 控えが見つかりません: {args.json}")
    data = json.loads(args.json.read_text(encoding="utf-8"))
    typhoons = data.get("typhoons") or []
    gen = jst(data.get("generatedAt", "")) or datetime.now(JST)

    print("🌀 ④予備の文章の下書き（この道具はファイルを書き換えません）")
    # リポジトリの外のファイルを指定されても落ちないようにする
    try:
        shown = args.json.resolve().relative_to(ROOT)
    except ValueError:
        shown = args.json
    print(f"   もとにした控え: {shown}")
    print(f"   控えができた時刻: {gen:%Y-%m-%d %H:%M}（日本時間）")
    print(f"   発生中の台風: {'・'.join(tc_name(t) for t in typhoons) or '（なし）'}")
    age_h = (datetime.now(JST) - gen).total_seconds() / 3600
    if age_h > 6:
        print(f"   ⚠️ この控え自体が {age_h:.1f} 時間前のものです。"
              "先に気象庁の最新発表を確認してください。")
    print()

    if not typhoons:
        print("いま発生中の台風はありません。台風がないときの④の書き方は、")
        print("index.html の「発生中の台風はありません」向けの文面をそのままお使いください。")
        return 0

    print("─" * 70)
    print("【1】ヘッダーの日時（<time id=\"updated-at\" ...>）")
    print("─" * 70)
    print(f'<time id="updated-at" datetime="{gen:%Y-%m-%dT%H:%M}+09:00">'
          f'{gen.year}年{gen.month}月{gen.day}日</time>')
    print()

    print("─" * 70)
    print("【2】#snapshot-banner の但し書き")
    print("─" * 70)
    an = [t["analysis"] for t in typhoons if t.get("analysis", {}).get("validTime")]
    obs = fmt_short(an[0]["validTime"]) if an else ""
    print(f"気象庁が{gen.year}年{gen.month}月{gen.day}日{gen.hour}時{gen.minute:02d}分までに"
          f"発表した情報（実況はいずれも{obs}時点）をまとめたもので、自動更新はされません。")
    print()

    print("─" * 70)
    print("【3】🌀 発生中の台風（#status-snapshot の中）")
    print("─" * 70)
    for t in typhoons:
        print(draft_active(t))
    print()

    m = pick_main(typhoons, args.main)
    print("─" * 70)
    print(f"【4】👀 今後の見通し（{tc_name(m)}）")
    print("─" * 70)
    print(f"      <h2>👀 今後の見通し（{tc_name(m)}）</h2>")
    print(draft_timeline(m))
    print()

    print("─" * 70)
    print("✍️ ここからは手作業です（この道具では作れないところ）")
    print("─" * 70)
    print("  □ 🕐「いま日本はどうなの？」のまとめ文（いちばん人の言葉が要るところ）")
    print("  □ ✅「すでに通過した台風」（過去の話は控えに入っていません）")
    print("  □ 🗾 マップ #map-static の線・凡例・#map-note・aria-label")
    # 座標の道具は別のPRで入る予定なので、ある時だけ案内する（無い道具を案内しない）
    if (ROOT / "tools" / "typhoon_map_coords.py").exists():
        print("       → 座標は python3 tools/typhoon_map_coords.py 緯度 経度 ... で出せます")
    print("  □ 🔎 情報源のリンクを今回の台風のものに差し替え")
    print()
    print("  貼り終わったら、次のコマンドで古さの点検をしてください：")
    print("      python3 tools/check_typhoon_snapshot.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
