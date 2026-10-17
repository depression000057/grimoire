#!/bin/sh
# グリモワール: 受講生が「グリモワール更新」と言った時に、講座の配布元から最新の版をすぐ取ってくる（Claude Code 用）。
# ふだんは話しかけると自動で届く（最大10分ほど）。これは待たずに今すぐ取りに行くための道具。
# 覚えたこと（マイナレッジ）と作った物（制作物）には触らない。
#
# 呼ぶ場所: 作業フォルダで Claude が `sh .grimoire/scripts/update.sh` を実行する（許可済み）。
# 標準出力: 1行目に結果。updated <前の版> <新しい版>／latest <版>（もう最新）／failed: <理由>
#   新しい版になった時は、新しい会話を開くと使えることを受講生に伝える（今の会話は前の版のまま）。

project_dir="${CLAUDE_PROJECT_DIR:-$PWD}"
plugins_home="${CLAUDE_CODE_PLUGIN_CACHE_DIR:-$HOME/.claude/plugins}"
installed="$plugins_home/installed_plugins.json"

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

# このフォルダに登録されている版（installed_plugins.json の、この作業フォルダの記録）
current_version() {
  if [ -f "$installed" ] && command -v python3 >/dev/null 2>&1; then
    python3 - "$installed" "$project_dir" <<'PY' 2>/dev/null
import json, sys
data = json.load(open(sys.argv[1]))
for entry in data.get("plugins", {}).get("grimoire@tirnanog", []):
    if entry.get("projectPath") == sys.argv[2] or entry.get("scope") in ("user",):
        print(entry.get("version", ""))
        break
PY
  fi
}

exe="$(find_claude)"
if [ -z "$exe" ]; then
  echo "failed: Claude Code の本体が見つかりません"
  exit 0
fi

before="$(current_version)"
log="${TMPDIR:-/tmp}/grimoire-update-$$.log"
if ! (cd "$project_dir" && run_limited 120 "$exe" plugin marketplace update tirnanog) >"$log" 2>&1 </dev/null; then
  echo "failed: 講座の配布元を見に行けませんでした（インターネットにつながっているか確かめてください）"
  rm -f "$log"
  exit 0
fi
if ! (cd "$project_dir" && run_limited 120 "$exe" plugin update grimoire@tirnanog --scope local) >>"$log" 2>&1 </dev/null; then
  echo "failed: $(tail -n 1 "$log" 2>/dev/null)"
  rm -f "$log"
  exit 0
fi
rm -f "$log"
after="$(current_version)"
if [ -n "$after" ] && [ "$after" != "$before" ]; then
  echo "updated ${before:-?} ${after}"
else
  echo "latest ${after:-$before}"
fi
exit 0
