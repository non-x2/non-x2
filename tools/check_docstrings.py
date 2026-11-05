#!/usr/bin/env python3
"""👀 tools/ の道具のdocstringに書かれた「出力例」が、実際の出力とズレていないか照合する見張り番。

■ なぜ必要か
docstringの出力例は手で書くので、道具の中身を直したときにうっかり
書き換え忘れて実際の出力とズレることがある（例：typhoon_map_coords.py で発生。
自己改良バックログの候補17で発見・修正した）。この道具は、docstring中の
コマンド例を実際に実行して、書かれている出力例と一致するかを機械的に照合する。

■ 使い方
    python3 tools/check_docstrings.py
    npm run check:docstrings   （同じもの）
        （対象は下の TARGETS リストに書かれた道具だけ）

■ 伏せ字（◯）も照合できる（2026-11-06 追加＝自己改良バックログの候補52）
道具の出力例には、数が入る場所を **「◯個」「◯枚」のような伏せ字**にしてあるものがある
（`check_map.py` が代表。道具や自動実行が増えるたびに実数が変わるので、
  実数を書くと時間とともに嘘になる＝候補33の仲間）。
そういう出力例は「文字がぴったり同じか」では照合できないので、この道具は
**ひと続きの ◯（○・〇）を「なんらかの数」として扱う**。
    例）出力例「✅ tools/ の◯個の道具は、…」
        実際の出力「✅ tools/ の10個の道具は、…」 → ✅ 一致とみなす
    例）出力例「… ◯◯◯◯-◯◯-◯◯ で合っています」 → 「2026-08-22」に当てはまる
※ 伏せ字が無い出力例は、いままでどおり**文字がぴったり同じか**で照合する（動きは変わらない）。

■ 出力例をdocstringから直接読む（2026-11-06 追加＝候補52）
TARGETS に `"docstring_heading": "■ 出力例"` と書くと、その道具のdocstringの
その見出しの下から **✅・❌・⏭ で始まる行**を読み取って、そのまま期待値にする。
手で書き写さないので、**書き写しのズレ**が起きない（候補21の一歩目）。
手で期待値を並べたいとき（コマンドの引数を変えて試したいときなど）は、
いままでどおり `"expected_lines"` に書けばよい。

■ 「どちらかが出ればOK」も書ける（2026-11-06 追加＝候補52）
手元の環境によって出る行が変わる照合もある（例：`check_map.py` のフックの文法点検は、
bash が見つからない素のWindowsでは「⏭ …飛ばしました」と出る）。
そういうときは出力例の次の行に **「または 」で始める行**を書くと、
どちらか一方が出ていれば ✅ とみなす（出ない行を責めて**嘘の❌**を出さないため）。

外部のライブラリは使いません（Python 3 の標準機能だけ）。
"""

from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
from pathlib import Path

# Windows（日本語）の画面でも絵文字（✅など）で落ちないよう、出力を utf-8 にそろえる
# （Linux の GitHub Actions では元から utf-8 なので変化なし）
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parent.parent

# 伏せ字（数が入る場所）に使われる文字。ひと続きで「なんらかの数」1つぶんとして扱う。
PLACEHOLDER_RUN = re.compile("[◯○〇]+")
# 出力例の行だと分かる先頭の目印（説明の地の文を期待値と間違えないため）
OUTPUT_MARKS = ("✅", "❌", "⏭")
# 「どちらかが出ればOK」をつなぐ目印
ALT_PREFIX = "または "

# 照合したいコマンド例を登録する。
#   tool              : 走らせる道具（リポジトリの根っこから見た場所）
#   label             : 報告に出す呼び名
#   args              : 渡す引数（無いときは []）
#   expected_lines    : 期待する出力（手で書く方式）
#   docstring_heading : docstringのこの見出しの下から期待値を読み取る方式（上のどちらか一方）
TARGETS = [
    {
        "tool": "tools/typhoon_map_coords.py",
        "label": "順方向（緯度経度→x,y）",
        "args": ["24.5", "132.0", "26.0", "135.4"],
        "expected_lines": [
            "24.5,132.0 → x=101.4,y=278.1",
            "26.0,135.4 → x=136.0,y=261.3",
        ],
    },
    {
        "tool": "tools/typhoon_map_coords.py",
        "label": "逆方向（x,y→緯度経度）",
        "args": ["--xy", "101.4", "278.1", "136.0", "261.3"],
        "expected_lines": [
            "x=101.4,y=278.1 → 24.5,132.0",
            "x=136.0,y=261.3 → 26.0,135.4",
        ],
    },
    {
        # 🗺 構成表の見張り番。出力例は伏せ字（◯）入りなので、docstringから直接読み取る。
        "tool": "tools/check_map.py",
        "label": "照合の結果",
        "args": [],
        "docstring_heading": "■ 出力例",
    },
]


def to_pattern(expected: str) -> re.Pattern[str]:
    """出力例の1行を、照合に使う当てはめ（ひと続きの◯＝なんらかの数）に直す。

    ⚠️ 照合は行まるごと（fullmatch）で見る。伏せ字が無い出力例なら
       「文字がぴったり同じか」とまったく同じ厳しさになる（うしろに文字を
       足されたのを見逃さないため）。
    """
    parts: list[str] = []
    last = 0
    for run in PLACEHOLDER_RUN.finditer(expected):
        parts.append(re.escape(expected[last : run.start()]))
        parts.append(r"\d+")
        last = run.end()
    parts.append(re.escape(expected[last:]))
    return re.compile("".join(parts))


def to_groups(expected_lines: list[str]) -> list[list[str]]:
    """「または …」の行を、直前の行の仲間（どちらかが出ればOK）にまとめる。"""
    groups: list[list[str]] = []
    for line in expected_lines:
        if line.startswith(ALT_PREFIX) and groups:
            groups[-1].append(line[len(ALT_PREFIX) :].strip())
        else:
            groups.append([line])
    return groups


def docstring_examples(tool: str, heading: str) -> list[str]:
    """道具のdocstringの `heading` の下から、出力例の行だけを読み取る。"""
    source = (REPO_ROOT / tool).read_text(encoding="utf-8")
    doc = ast.get_docstring(ast.parse(source)) or ""
    found: list[str] = []
    inside = False
    for raw in doc.splitlines():
        line = raw.strip()
        if not inside:
            inside = line.startswith(heading)
            continue
        if not line:
            break          # 空行＝その節の終わり
        if line.startswith("■"):
            break          # 次の見出し
        if line.startswith(OUTPUT_MARKS) or line.startswith(ALT_PREFIX):
            found.append(line)
    return found


def run_tool(tool: str, args: list[str]) -> list[str]:
    # Windows（日本語）では子の出力が cp932 になり、utf-8 で読むと絵文字で落ちる（候補97）。
    # 子にも親にも utf-8 を指定して、どの手元でも同じ文字で受け渡す（Linux では元から同じ）。
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / tool), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        cwd=REPO_ROOT,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def expected_for(target: dict) -> list[str]:
    """その対象の期待値（手書き／docstring読み取り）を返す。読めなければ空。"""
    if "expected_lines" in target:
        return list(target["expected_lines"])
    return docstring_examples(target["tool"], target["docstring_heading"])


def main() -> int:
    ok = True
    for target in TARGETS:
        where = f"{target['tool']}（{target['label']}）"
        expected_lines = expected_for(target)
        if not expected_lines:
            ok = False
            heading = target.get("docstring_heading", "")
            print(f"❌ {where}: docstringの「{heading}」から出力例を読み取れませんでした（見出しが消えた？）")
            continue
        actual_lines = run_tool(target["tool"], target["args"])
        for group in to_groups(expected_lines):
            # どれが当たったかまで表示する（「または」の行で当たったときに分かるように）
            matched = next(
                (one for one in group for line in actual_lines if to_pattern(one).fullmatch(line)),
                None,
            )
            if matched is not None:
                note = "" if matched == group[0] else "（「または」の行で一致）"
                print(f"✅ {where}: 「{matched}」は実際の出力と一致{note}")
            else:
                ok = False
                print(f"❌ {where}: 「{group[0]}」が実際の出力に見つかりません")
                for alt in group[1:]:
                    print(f"   （「{alt}」も出ていません）")
                print(f"   実際の出力: {actual_lines}")
    if ok:
        print("\n✅ すべての出力例が実際の出力と一致しています。")
        return 0
    print("\n❌ docstringの出力例が実際の出力とズレています。該当箇所を直してください。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
