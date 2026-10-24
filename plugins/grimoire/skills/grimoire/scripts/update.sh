#!/bin/sh
# グリモワール: 講座の配布元から最新の版をすぐ取ってくる（Claude Code 用）。
# 会話の最初に自動で呼ばれる（hooks/startup-update.sh。配布元に新しい版がある時だけ）。
# 受講生が「グリモワール更新」と言った時にも、Claude が呼ぶ。
# 受け取ったら、作業フォルダの近道 .grimoire を新しい版へ向け直し、今の会話から新しい版の手順書・講座の資料・道具を使えるようにする。
# 覚えたこと（マイナレッジ）と作った物（制作物）には触らない。
#
# 呼ぶ場所: 作業フォルダで Claude が `sh .grimoire/scripts/update.sh` を実行する（許可済み）。
# 待つ上限: 配布元を見に行く・受け取るのに、それぞれ GRIMOIRE_UPDATE_LIMIT 秒（既定120。会話の最初のフックからは40）。
# 標準出力: 1行目に結果。updated <前の版> <新しい版>／latest <版>（もう最新）／failed: <理由>

project_dir="${CLAUDE_PROJECT_DIR:-$PWD}"
plugins_home="${CLAUDE_CODE_PLUGIN_CACHE_DIR:-$HOME/.claude/plugins}"
installed="$plugins_home/installed_plugins.json"
limit="${GRIMOIRE_UPDATE_LIMIT:-120}"

# この道具がある版のプラグインの場所（近道 .grimoire から呼ばれても、本物の場所をたどる）
script_dir="$(cd -P "$(dirname "$0")" 2>/dev/null && pwd)"
skill_dir="${script_dir%/scripts}"
if [ -f "$skill_dir/.grimoire-copy-of" ]; then
  skill_dir="$(cat "$skill_dir/.grimoire-copy-of" 2>/dev/null)"  # 近道がコピーの時は、コピー元の場所
fi
plugin_root="${skill_dir%/skills/grimoire}"

find_claude() {
  if [ -n "${CLAUDE_CODE_EXECPATH:-}" ] && [ -x "$CLAUDE_CODE_EXECPATH" ]; then
    printf '%s\n' "$CLAUDE_CODE_EXECPATH"
    return
  fi
  found="$(command -v claude 2>/dev/null)"
  if [ -n "$found" ] && [ -x "$found" ]; then
    printf '%s\n' "$found"
    return
  fi
  if [ -x "$HOME/.local/bin/claude" ]; then
    printf '%s\n' "$HOME/.local/bin/claude"
    return
  fi
  bundled="$(ls -td "$HOME/Library/Application Support/Claude/claude-code"/*/claude.app/Contents/MacOS/claude 2>/dev/null | head -n 1)"
  if [ -n "$bundled" ] && [ -x "$bundled" ]; then
    printf '%s\n' "$bundled"
  fi
}

run_limited() {
  limit="$1"
  shift
  if command -v perl >/dev/null 2>&1; then
    perl -e 'alarm shift @ARGV; exec @ARGV or exit 127' "$limit" "$@"
  else
    "$@"
  fi
}

# このフォルダに登録されている版（installed_plugins.json の、この作業フォルダの記録）。
# Mac では plutil で読む（hooks/installed-record.sh。python3 だとコマンドライン・デベロッパ・ツールの無い Mac で画面が出るため）
current_version() {
  if [ -f "$installed" ] && [ -f "$plugin_root/hooks/installed-record.sh" ]; then
    CLAUDE_PROJECT_DIR="$project_dir" CLAUDE_CODE_PLUGIN_CACHE_DIR="$plugins_home" sh "$plugin_root/hooks/installed-record.sh" version 2>/dev/null </dev/null
  fi
}

exe="$(find_claude)"
if [ -z "$exe" ]; then
  echo "failed: Claude Code の本体が見つかりません"
  exit 0
fi

before="$(current_version)"
log="${TMPDIR:-/tmp}/grimoire-update-$$.log"
if ! (cd "$project_dir" && run_limited "$limit" "$exe" plugin marketplace update tirnanog) >"$log" 2>&1 </dev/null; then
  echo "failed: 講座の配布元を見に行けませんでした（インターネットにつながっているか確かめてください）"
  rm -f "$log"
  exit 0
fi
if ! (cd "$project_dir" && run_limited "$limit" "$exe" plugin update grimoire@tirnanog --scope local) >>"$log" 2>&1 </dev/null; then
  echo "failed: $(tail -n 1 "$log" 2>/dev/null)"
  rm -f "$log"
  exit 0
fi
rm -f "$log"
after="$(current_version)"
# 近道を、このフォルダに登録された新しい版へ向け直す（今の会話から新しい版を使うため）
if [ -n "$plugin_root" ] && [ -f "$plugin_root/hooks/link-shortcut.sh" ]; then
  (cd "$project_dir" && CLAUDE_PROJECT_DIR="$project_dir" CLAUDE_PLUGIN_ROOT="$plugin_root" GRIMOIRE_FOLLOW_INSTALLED=1 \
    sh "$plugin_root/hooks/link-shortcut.sh") >/dev/null 2>&1 </dev/null
fi
if [ -n "$after" ] && [ "$after" != "$before" ]; then
  # Claude が呼んだ時は、この結果を見て Claude が受講生に伝えるので、次の入力でフックが同じことを伝えないよう印を書く
  if [ "${GRIMOIRE_CALLER:-}" != "hook" ]; then
    data_dir="${CLAUDE_PLUGIN_DATA:-$plugins_home/data/grimoire-tirnanog}"
    key="$(printf '%s' "$project_dir" | cksum | cut -d' ' -f1)"
    mkdir -p "$data_dir" 2>/dev/null && printf '%s\n' "$after" >"$data_dir/upgrade-notified-$key" 2>/dev/null
  fi
  echo "updated ${before:-?} ${after}"
else
  echo "latest ${after:-$before}"
fi
exit 0
