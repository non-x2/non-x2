#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""📝 会話の文字起こしツール（のんラボ）

Claude Code が自動で残している会話の記録ファイル（.jsonl）を読み取り、
読みやすい Markdown の「文字起こし」に変換して docs/会話ログ/ に保存します。

使い方（ふつうはこれだけ）:
    python3 tools/kaiwa_mojiokoshi.py

  → いま作業中のプロジェクトの一番新しい会話を文字起こしして
    docs/会話ログ/会話ログ_YYYY-MM-DD_HHMM.md に保存します。

オプション:
    --list            会話ファイルの一覧を表示するだけ（保存しない）
    --file PATH       文字起こしする .jsonl ファイルを直接指定する
    --out PATH        保存先ファイルを指定する（省略時は docs/会話ログ/ に自動命名）
    --tools           Claudeが使った道具（コマンド実行など）も1行ずつ載せる
    --stdout          ファイルに保存せず画面に表示するだけ

しくみ:
  Claude Code はやり取りを ~/.claude/projects/<プロジェクト名>/<会話ID>.jsonl に
  自動保存しています（クラウドもローカルのデスクトップアプリも同じ形式）。
  このツールはそれを読むだけなので、会話の内容を「思い出しながら書き直す」ときの
  抜け・言い換えがなく、トークン（AIの利用量）もほぼ使いません。

注意:
  ⚠️ このリポジトリは public（GitHub上で誰でも閲覧可）です。
     文字起こしをコミット＆プッシュすると会話の内容が公開されます。
     個人情報などが含まれていないか、プッシュ前に必ず中身を確認してください。

Python の追加インストールは不要（標準機能のみで動きます）。
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

JST = timezone(timedelta(hours=9), "JST")

# 画面に長々と出さないための上限（本文は削らない。道具の表示だけ短くする）
TOOL_HINT_MAX = 80


def find_project_dir(cwd: Path) -> Path | None:
    """いまの作業フォルダに対応する ~/.claude/projects/ の中のフォルダを探す。"""
    # Claude Code はパスの記号を「-」に置き換えたフォルダ名で保存している
    # 例: /home/user/non-x2 → -home-user-non-x2
    encoded = re.sub(r"[^A-Za-z0-9]", "-", str(cwd))
    base = Path.home() / ".claude" / "projects"
    candidate = base / encoded
    if candidate.is_dir():
        return candidate
    # 見つからないときは、いちばん最近使われたプロジェクトフォルダで代用
    if base.is_dir():
        dirs = [d for d in base.iterdir() if d.is_dir()]
        if dirs:
            return max(dirs, key=lambda d: d.stat().st_mtime)
    return None


def list_transcripts(project_dir: Path) -> list[Path]:
    """会話ファイルを新しい順に並べて返す。"""
    files = sorted(
        project_dir.glob("*.jsonl"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return files


def jst_str(iso: str | None, fmt: str = "%H:%M") -> str:
    """'2026-08-10T01:44:55.650Z' → 日本時間の文字列（読めない時は空文字）。"""
    if not iso:
        return ""
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.astimezone(JST).strftime(fmt)
    except ValueError:
        return ""


def tool_hint(block: dict) -> str:
    """道具の呼び出しを1行の短い説明にする。"""
    name = block.get("name", "?")
    inp = block.get("input") or {}
    hint = ""
    if isinstance(inp, dict):
        # わかりやすい代表項目があればそれを使う
        for key in ("description", "file_path", "pattern", "command", "prompt", "query"):
            v = inp.get(key)
            if isinstance(v, str) and v.strip():
                hint = v.strip().splitlines()[0]
                break
    if len(hint) > TOOL_HINT_MAX:
        hint = hint[: TOOL_HINT_MAX - 1] + "…"
    return f"{name}（{hint}）" if hint else name


def clean_user_text(text: str) -> str | None:
    """のんさんの発言として載せる文章に整える。システム由来のものは None で除外。"""
    t = text.strip()
    if not t:
        return None
    # スラッシュコマンド実行や中断などの機械的なメッセージは会話ではないので省く
    if t.startswith("<") and ("command-name" in t or "system-reminder" in t or "local-command" in t):
        return None
    if t.startswith("Caveat:"):
        return None
    # スキル（型）の説明文がシステムから自動で入ることがあるので、会話としては省く
    if t.startswith("Base directory for this skill:"):
        return None
    if "[Request interrupted" in t:
        return None
    return t


def transcribe(jsonl_path: Path, include_tools: bool) -> tuple[str, dict]:
    """会話ファイル1つを Markdown の文字起こしにする。(本文, 情報) を返す。"""
    turns: list[tuple[str, str, str]] = []  # (誰, 時刻, 本文)
    first_ts = last_ts = None
    n_user = n_assistant = 0

    with open(jsonl_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue  # 壊れた行は飛ばす（全体を止めない）

            if d.get("isSidechain"):
                continue  # 助手（サブエージェント）とのやり取りは本編ではないので省く
            t = d.get("type")
            if t not in ("user", "assistant"):
                continue

            ts = d.get("timestamp")
            msg = d.get("message") or {}
            content = msg.get("content")

            texts: list[str] = []
            tools: list[str] = []
            if isinstance(content, str):
                texts.append(content)
            elif isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    bt = block.get("type")
                    if bt == "text":
                        texts.append(block.get("text", ""))
                    elif bt == "tool_use" and include_tools:
                        tools.append(tool_hint(block))
                    # thinking（考え中のメモ）と tool_result（道具の出力）は
                    # 文字起こしには載せない：会話の本文だけを残すため

            if t == "user":
                for x in texts:
                    cleaned = clean_user_text(x)
                    if cleaned:
                        turns.append(("🙋 のんさん", jst_str(ts), cleaned))
                        n_user += 1
                        first_ts = first_ts or ts
                        last_ts = ts
            else:  # assistant
                body = "\n\n".join(x.strip() for x in texts if x.strip())
                if body:
                    turns.append(("🤖 Claude", jst_str(ts), body))
                    n_assistant += 1
                    first_ts = first_ts or ts
                    last_ts = ts
                for tl in tools:
                    turns.append(("🔧 道具", jst_str(ts), tl))

    date_str = jst_str(first_ts, "%Y-%m-%d") or datetime.now(JST).strftime("%Y-%m-%d")
    span = ""
    if first_ts and last_ts:
        span = f"{jst_str(first_ts)}〜{jst_str(last_ts)}（日本時間）"

    lines = [
        f"# 💬 会話の文字起こし — {date_str}",
        "",
        f"> 記録元: `{jsonl_path.name}`",
        f"> 時間帯: {span}　発言数: のんさん {n_user}回 / Claude {n_assistant}回",
        "",
        "---",
        "",
    ]
    for who, when, body in turns:
        stamp = f"（{when}）" if when else ""
        if who == "🔧 道具":
            lines.append(f"> 🔧 {body}")
            lines.append("")
        else:
            lines.append(f"## {who} {stamp}")
            lines.append("")
            lines.append(body)
            lines.append("")

    info = {"date": date_str, "first_ts": first_ts, "n_user": n_user, "n_assistant": n_assistant}
    return "\n".join(lines).rstrip() + "\n", info


def main() -> int:
    ap = argparse.ArgumentParser(
        description="会話の記録(.jsonl)を読みやすい文字起こしMarkdownに変換して保存します。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--list", action="store_true", help="会話ファイルの一覧を表示するだけ")
    ap.add_argument("--file", type=Path, help="文字起こしする .jsonl を直接指定")
    ap.add_argument("--out", type=Path, help="保存先ファイル（省略時は docs/会話ログ/ に自動命名）")
    ap.add_argument("--tools", action="store_true", help="Claudeが使った道具も1行ずつ載せる")
    ap.add_argument("--stdout", action="store_true", help="保存せず画面に表示するだけ")
    args = ap.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    project_dir = find_project_dir(Path.cwd())

    if args.file:
        target = args.file
        if not target.is_file():
            print(f"❌ ファイルが見つかりません: {target}")
            return 1
    else:
        if not project_dir:
            print("❌ 会話の記録フォルダ（~/.claude/projects/）が見つかりませんでした。")
            print("   Claude Code で会話したことのある端末で実行してください。")
            return 1
        files = list_transcripts(project_dir)
        if not files:
            print(f"❌ 会話ファイルが1つもありません: {project_dir}")
            return 1
        if args.list:
            print(f"📂 {project_dir} の会話ファイル（新しい順）:")
            for p in files:
                mtime = datetime.fromtimestamp(p.stat().st_mtime, JST).strftime("%Y-%m-%d %H:%M")
                size_kb = p.stat().st_size / 1024
                print(f"  - {p.name}（最終更新 {mtime}・{size_kb:.0f}KB）")
            print("\n特定の会話を選ぶには: python3 tools/kaiwa_mojiokoshi.py --file <上のパス>")
            return 0
        target = files[0]  # いちばん新しい会話

    md, info = transcribe(target, include_tools=args.tools)

    if info["n_user"] == 0 and info["n_assistant"] == 0:
        print(f"⚠️ この記録には会話の本文が見つかりませんでした: {target.name}")
        return 1

    if args.stdout:
        print(md)
        return 0

    if args.out:
        out_path = args.out
    else:
        stamp = jst_str(info["first_ts"], "%Y-%m-%d_%H%M") or datetime.now(JST).strftime("%Y-%m-%d_%H%M")
        out_dir = repo_root / "docs" / "会話ログ"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"会話ログ_{stamp}.md"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md, encoding="utf-8")
    rel = os.path.relpath(out_path, Path.cwd())
    print(f"✅ 文字起こしを保存しました: {rel}")
    print(f"   のんさん {info['n_user']}回 / Claude {info['n_assistant']}回 の発言を記録")
    print("⚠️ このリポジトリは public です。コミット＆プッシュすると内容が公開されるので、")
    print("   個人情報が入っていないか確認してからプッシュしてください。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
