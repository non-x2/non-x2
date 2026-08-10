#!/bin/bash
# のんラボ セッション開始フック
# 新しいセッションが始まったときに自動で走ります。
#  ① 今どうなっているか（ブランチ・保存忘れ・直近の作業）を表示
#  ② クラウドのときだけ、道具（Pythonの部品）を自動でそろえる
#
# ※ 途中で失敗してもセッションは普通に始まります（set -e は使わない方針）

set -uo pipefail

cd "${CLAUDE_PROJECT_DIR:-.}" 2>/dev/null || exit 0

echo "📍 のんラボ：いまの状態"

# --- ① 状態の表示（クラウド・ローカル共通）---
branch="$(git branch --show-current 2>/dev/null)"
echo "- ブランチ: ${branch:-（不明）}"

if [ -n "$(git status --porcelain 2>/dev/null)" ]; then
  echo "- ⚠️ 保存していない変更があります（コミット＆プッシュを忘れずに）"
else
  echo "- 作業中の変更なし（きれいな状態）"
fi

echo "- 直近の作業:"
git log --oneline -3 2>/dev/null | sed 's/^/    /'

# 押し忘れているコミットがあれば知らせる（クラウドは消えるため）
ahead="$(git rev-list --count '@{u}..HEAD' 2>/dev/null)"
[ -n "$ahead" ] && [ "$ahead" != "0" ] && echo "- ⚠️ まだプッシュしていないコミットが ${ahead} 個あります"

latest_log="$(ls -1 docs/作業ログ_*.md 2>/dev/null | sort | tail -1)"
if [ -n "$latest_log" ]; then
  echo "- 最新の作業ログ: $latest_log"
  # 💰 トークン節約のいちばんの近道：
  #    続きをやるとき、リポジトリ全体を調べさせない。作業ログ1枚で足りる。
  echo "- 💰 続きをやるなら **まず「$latest_log」だけ読む**こと"
  echo "     （リポジトリ全体を調べる必要はありません。これが節約のいちばんの近道）"
fi

# 🧠 共有メモリ（ローカル⇄クラウド共通の記憶）を読む合図
[ -f docs/共有メモリ.md ] && echo "- 🧠 共有メモリ: docs/共有メモリ.md も必ず読むこと（ローカル⇄クラウド共通の記憶）"

# 使える型のお知らせ（毎回1行だけ）
echo "- 🧰 型: /handoff（引き継ぎを作る）/ /bunsan（手分けする）/ /git-guide（Git）"

# --- ② クラウドのときだけ、道具をそろえる ---
# ローカル（自分のPC）では勝手にインストールしない。環境を汚さないため。
if [ "${CLAUDE_CODE_REMOTE:-}" = "true" ]; then
  echo "- ☁️ ここはクラウド（使い捨ての部屋）。**プッシュしないと消えます**"
  # 🔒 個人の記憶（非公開リポ）を自動で読む合図（ルールの本体はCLAUDE.mdに記載）
  echo "- 🔒 個人の記憶: 非公開リポ non-x2/kioku-sync も add_repo で追加して docs/共有メモリ.md を**頼まれなくても自動で読む**こと"
  if [ -f excel-jan-barcode/requirements.txt ]; then
    if python3 -m pip install --quiet --break-system-packages \
         -r excel-jan-barcode/requirements.txt 2>/dev/null; then
      echo "- 🏷 バーコードExcelツール: すぐ実行できます"
    else
      echo "- 🏷 バーコードExcelツール: 部品の準備に失敗（手動なら pip3 install -r excel-jan-barcode/requirements.txt）"
    fi
  fi
else
  echo "- 💻 ここはローカル（あなたのPC）。ファイルはそのまま残ります"

  # --- ③ ローカルのときだけ：GitHubの最新（共有メモリなど）を自動で見に行く ---
  # 自動で取り込むのは安全なときだけ：mainブランチ・保存していない変更なし・早送りできる場合。
  # それ以外は「最新にして」と頼んでもらう案内だけ出す（勝手に壊さない）。
  if command -v timeout >/dev/null 2>&1; then
    fetch_cmd="timeout 10 git fetch origin main --quiet"
  else
    fetch_cmd="git fetch origin main --quiet"   # macOSなどtimeoutが無い環境
  fi
  if $fetch_cmd 2>/dev/null; then
    behind="$(git rev-list --count HEAD..origin/main 2>/dev/null)"
    if [ -n "$behind" ] && [ "$behind" != "0" ]; then
      if [ "$branch" = "main" ] && [ -z "$(git status --porcelain 2>/dev/null)" ] \
         && git merge --ff-only --quiet origin/main 2>/dev/null; then
        echo "- 🔄 GitHubの新しい更新 ${behind}件を自動で取り込みました（🧠共有メモリも最新）"
      else
        echo "- ⚠️ GitHubに新しい更新が ${behind}件あります。「最新にして」と頼んでください"
      fi
    else
      echo "- ✅ GitHubと同期済み（🧠共有メモリも最新です）"
    fi
  else
    echo "- 📡 GitHubに接続できません（オフライン？）。メモは手元の分を使います"
  fi
fi

exit 0
