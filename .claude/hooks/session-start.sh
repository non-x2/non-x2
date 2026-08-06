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

# 使える型のお知らせ（毎回1行だけ）
echo "- 🧰 型: /handoff（引き継ぎを作る）/ /bunsan（手分けする）/ /git-guide（Git）"

# --- ② クラウドのときだけ、道具をそろえる ---
# ローカル（自分のPC）では勝手にインストールしない。環境を汚さないため。
if [ "${CLAUDE_CODE_REMOTE:-}" = "true" ]; then
  echo "- ☁️ ここはクラウド（使い捨ての部屋）。**プッシュしないと消えます**"
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
fi

exit 0
