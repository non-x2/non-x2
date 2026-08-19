#!/usr/bin/env python3
"""のんラボの「進化の数字」を集計し、docs/進化レポート.md をまるごと書き出すスクリプト。

Python標準ライブラリのみ使用。外部パッケージ禁止。
実行方法: python3 tools/shinka_metrics.py
"""
from __future__ import annotations

import re
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

# リポジトリルートは、このスクリプト自身の位置（tools/の親）から求める。
# カレントディレクトリに依存しない。
REPO_ROOT = Path(__file__).resolve().parent.parent


def run_git(args: list[str]) -> str:
    """リポジトリルートを作業ディレクトリにしてgitコマンドを実行し、標準出力を返す。"""
    result = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def count_skills() -> int:
    """.claude/skills/ 直下のディレクトリ数。"""
    skills_dir = REPO_ROOT / ".claude" / "skills"
    if not skills_dir.is_dir():
        return 0
    return sum(1 for p in skills_dir.iterdir() if p.is_dir())


def list_docs() -> list[Path]:
    """docs/*.md のファイル一覧。"""
    docs_dir = REPO_ROOT / "docs"
    if not docs_dir.is_dir():
        return []
    return sorted(docs_dir.glob("*.md"))


def count_docs(docs: list[Path]) -> int:
    return len(docs)


def count_guide_docs(docs: list[Path]) -> int:
    """指示書・手順書・ガイド類の数。"""
    count = 0
    for p in docs:
        name = p.name
        if name.startswith("指示書_") or name.startswith("手順書_") or "ガイド" in name:
            count += 1
    return count


def count_work_logs(docs: list[Path]) -> int:
    """作業ログ_*.md の数。"""
    return sum(1 for p in docs if p.name.startswith("作業ログ_"))


def count_kaizen_records() -> int:
    """自己改良バックログ.md の「## 📗 改良の記録」より後にある「| 20」で始まる行の数。"""
    backlog = REPO_ROOT / "docs" / "自己改良バックログ.md"
    if not backlog.is_file():
        return 0
    text = backlog.read_text(encoding="utf-8")
    marker = "## 📗 改良の記録"
    idx = text.find(marker)
    if idx == -1:
        return 0
    after = text[idx + len(marker):]
    count = 0
    for line in after.splitlines():
        if line.startswith("| 20"):
            count += 1
    return count


def count_total_commits() -> int:
    """総コミット数。"""
    out = run_git(["rev-list", "--count", "HEAD"])
    return int(out.strip())


def count_merged_prs() -> int:
    """マージ済みPR数（推定）: git log --oneline の件名に含まれる「(#数字)」の異なり数。"""
    out = run_git(["log", "--oneline"])
    pr_numbers = set(re.findall(r"\(#(\d+)\)", out))
    return len(pr_numbers)


def is_shallow_clone() -> bool:
    """浅いクローン（履歴の一部しか持たない状態）かどうか。クラウドの部屋では通常こうなる。"""
    return (REPO_ROOT / ".git" / "shallow").is_file()


def try_unshallow() -> bool:
    """浅いクローンなら、GitHubから全履歴を取り直す。成功したら True。

    ⚠️ これが無いと数字が「増えたり減ったり」します。
    クラウドの作業部屋は毎回ちがう深さの履歴しか持たないため、
    そのまま数えると「総コミット数 85 →50」のように**後ろ向きに**書き換わり、
    成長を見るはずの進化レポートが逆走してしまいます（2026-08-17 に実際に発生）。
    全履歴を取ってから数えれば、どの部屋で実行しても同じ数字になります。

    ネットにつながらない・取得に失敗したときは False を返し、
    呼び出し側が「一部の履歴での数字です」と正直に注記します。
    """
    if not is_shallow_clone():
        return True  # もともと全履歴を持っている（ローカルなど）
    try:
        subprocess.run(
            ["git", "fetch", "--unshallow", "--quiet"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
            timeout=120,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        return False
    return not is_shallow_clone()


def daily_commit_counts(days: int = 14) -> tuple[list[tuple[str, int]], str | None]:
    """直近days日間の日別コミット数を [(表示ラベル, 件数), ...] の順（古い→新しい）で返す。
    コミットが無い日は0。
    浅いクローンでは古い日が「実際は有るのに0」に見えて誤解を招くため、
    履歴が存在する最古の日より前は表示しない。2番目の戻り値は履歴の開始日（YYYY-MM-DD）。"""
    out = run_git(["log", "--date=short", "--format=%cd"])
    counts: Counter[str] = Counter()
    dates: list[str] = []
    for line in out.splitlines():
        line = line.strip()
        if line:
            counts[line] += 1
            dates.append(line)
    oldest = min(dates) if dates else None

    today = datetime.now().date()
    start = today - timedelta(days=days - 1)
    if oldest is not None:
        oldest_date = datetime.strptime(oldest, "%Y-%m-%d").date()
        if oldest_date > start:
            start = oldest_date

    result: list[tuple[str, int]] = []
    d = start
    while d <= today:
        key = d.strftime("%Y-%m-%d")
        label = f"{d.month}/{d.day}"
        result.append((label, counts.get(key, 0)))
        d += timedelta(days=1)
    return result, oldest


def build_report(
    metrics: dict,
    daily_counts: list[tuple[str, int]],
    history_start: str | None,
    shallow: bool,
) -> str:
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    x_axis_labels = ", ".join(f'"{label}"' for label, _ in daily_counts)
    bar_values = ", ".join(str(count) for _, count in daily_counts)

    category_labels = ["スキル", "指示書等", "作業ログ", "改良回数", "マージPR"]
    category_values = [
        metrics["skills"],
        metrics["guide_docs"],
        metrics["work_logs"],
        metrics["kaizen_records"],
        metrics["merged_prs"],
    ]
    cat_x_axis = ", ".join(f'"{label}"' for label in category_labels)
    cat_bar = ", ".join(str(v) for v in category_values)

    lines = []
    lines.append(
        "> このファイルは `tools/shinka_metrics.py` が自動生成します（🔁グラフのループ）。"
        "手で編集しないでください。"
    )
    lines.append(f"> 生成日時: {now_str}")
    lines.append("")
    lines.append("# 🌱 のんラボ 進化レポート")
    lines.append("")
    lines.append("## 📊 メトリクス一覧")
    lines.append("")
    lines.append("| 項目 | 数字 |")
    lines.append("|------|------|")
    lines.append(f"| 🧩 スキル数 | {metrics['skills']} |")
    lines.append(f"| 📚 ドキュメント数 | {metrics['docs']} |")
    lines.append(f"| 📗 指示書・手順書・ガイド類 | {metrics['guide_docs']} |")
    lines.append(f"| 📝 作業ログ数 | {metrics['work_logs']} |")
    lines.append(f"| 🌱 自己改良の実施回数 | {metrics['kaizen_records']} |")
    lines.append(f"| 💾 総コミット数 | {metrics['total_commits']} |")
    lines.append(f"| 🔀 マージ済みPR数（推定） | {metrics['merged_prs']} |")
    lines.append(f"| 🌐 公開ページ数 | {metrics['public_pages']} |")
    lines.append("")
    lines.append(
        "> 🌐 公開ページ数は、公開ワークフロー（`pages-deploy.yml`）が"
        "実際に配置しているものを数えています。"
        "Webに出しているのは入口ページと各アプリだけで、"
        "作業ログ・脚本・台帳（`livecam-db/`）は公開していません。"
    )
    lines.append("")
    lines.append(f"## 📈 グラフ1: 日別コミット数（直近{len(daily_counts)}日間）")
    lines.append("")
    lines.append("```mermaid")
    lines.append("xychart-beta")
    lines.append(f'    title "日別コミット数（直近{len(daily_counts)}日間）"')
    lines.append(f"    x-axis [{x_axis_labels}]")
    lines.append('    y-axis "コミット数"')
    lines.append(f"    bar [{bar_values}]")
    lines.append("```")
    lines.append("")
    if shallow and history_start:
        lines.append(
            f"> ⚠️ **今回は全履歴を取れませんでした**（ネットにつながらない等）。"
            f"手元にある範囲（{history_start} 以降）だけで数えているので、"
            "総コミット数・マージPR数・グラフは**実際より少なめ**です。"
            "ネットにつながる場所でもう一度実行すると、正しい数字に直ります。"
        )
        lines.append("")
    lines.append("## 📈 グラフ2: カテゴリ別の数")
    lines.append("")
    lines.append("```mermaid")
    lines.append("xychart-beta")
    lines.append('    title "カテゴリ別の数"')
    lines.append(f"    x-axis [{cat_x_axis}]")
    lines.append('    y-axis "件数"')
    lines.append(f"    bar [{cat_bar}]")
    lines.append("```")
    lines.append("")
    lines.append("## 🔍 数字の見かた")
    lines.append("")
    lines.append(
        "- ここにある数字は、のんラボが「育っている証拠」です。"
        "スキルやドキュメントが増えるほど、AIと一緒にできることが増えています。"
    )
    lines.append(
        "- コミット数やPR数が増えるのは、実際に手を動かして直したり作ったりした回数です。"
        "多い＝サボらず育てている、ということです。"
    )
    lines.append(
        "- 自己改良の実施回数は、毎日すこしずつ良くする仕組み（🌱 kaizen）がちゃんと動いている証です。"
    )
    lines.append("")
    return "\n".join(lines)


def count_public_pages() -> int:
    """Webに公開しているページの数を、公開ワークフローの中身から数える。

    以前は固定値（3）でしたが、ページが増えても数字が変わらず、
    実態とズレてしまいました。公開の設定そのものを見て数えれば、
    増えても減っても自動で正しくなります。
    """
    wf = REPO_ROOT / ".github" / "workflows" / "pages-deploy.yml"
    if not wf.exists():
        return 0
    text = wf.read_text(encoding="utf-8")
    # 「cp index.html _site/」「cp -r typhoon-app _site/」のような行を数える
    return len(re.findall(r"^\s*cp\s+(?:-r\s+)?\S+\s+_site/", text, re.M))


def main() -> None:
    # ★ 数える前に、必ず全履歴を取りに行く。
    #   クラウドの作業部屋は毎回ちがう深さの履歴しか持たないため、これをしないと
    #   総コミット数・マージPR数・グラフが実行するたびに増えたり減ったりする。
    if is_shallow_clone():
        print("📥 履歴の一部しかないので、GitHubから全履歴を取り直します…")
    full_history = try_unshallow()
    if full_history:
        print("✅ 全履歴で数えます。")
    else:
        print("⚠️ 全履歴を取れませんでした（ネットにつながらない等）。手元にある範囲の数字で作ります。")

    docs = list_docs()

    metrics = {
        "skills": count_skills(),
        "docs": count_docs(docs),
        "guide_docs": count_guide_docs(docs),
        "work_logs": count_work_logs(docs),
        "kaizen_records": count_kaizen_records(),
        "total_commits": count_total_commits(),
        "merged_prs": count_merged_prs(),
        "public_pages": count_public_pages(),
    }

    daily_counts, history_start = daily_commit_counts(days=14)

    report = build_report(metrics, daily_counts, history_start, not full_history)

    out_path = REPO_ROOT / "docs" / "進化レポート.md"
    out_path.write_text(report, encoding="utf-8")

    print("✅ 進化レポート.md を生成しました。主要数字のサマリ:")
    print(f"🧩 スキル数: {metrics['skills']}")
    print(f"📚 ドキュメント数: {metrics['docs']}")
    print(f"📗 指示書・手順書・ガイド類: {metrics['guide_docs']}")
    print(f"📝 作業ログ数: {metrics['work_logs']}")
    print(f"🌱 自己改良の実施回数: {metrics['kaizen_records']}")
    print(f"💾 総コミット数: {metrics['total_commits']}")
    print(f"🔀 マージ済みPR数（推定）: {metrics['merged_prs']}")
    print(f"🌐 公開ページ数: {metrics['public_pages']}")


if __name__ == "__main__":
    main()
