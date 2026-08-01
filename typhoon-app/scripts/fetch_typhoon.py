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
OUT_PATH = Path(__file__).resolve().parent.parent / "data" / "latest.json"
JST = timezone(timedelta(hours=9))
TIMEOUT = 30
USER_AGENT = "non-x2-typhoon-app/1.0 (+https://github.com/non-x2/non-x2)"


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

    payload = {
        "generatedAt": now.isoformat(),
        "source": "気象庁（https://www.jma.go.jp/bosai/typhoon/）",
        "count": len(typhoons),
        "typhoons": typhoons,
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
