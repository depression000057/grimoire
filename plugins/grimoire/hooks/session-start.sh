#!/bin/sh
# グリモワール: 会話の最初に動く（SessionStart フック）。
# 1. （Claude Code だけ）講座の配布元に新しい版が出ていれば、その場で受け取る（startup-update.sh）。
#    要約の後（compact）は会話の途中なので取りに行かない。
# 2. 作業フォルダの近道 .grimoire を、今の版の本体へ向ける（link-shortcut.sh）。Claude Code では、1 で受け取った版
#    （このフォルダに登録された新しい版）があれば、そちらへ向ける。
# 3. 作業フォルダの使い方を Claude に伝える（標準出力が Claude への案内になる）。1 で新しい版へ移った時は、
#    新しい版の手順で進めることも伝える（upgrade-notice.sh）。
# 初めて開いた会話では、本体の読み込みがこのフックより後になるため、このフックは動かない。
# その会話では、入力のたびに動く save-long-prompt.sh が近道と案内を行う（本体はその時に最新の版が入る）。
# 標準入力: Claude Code が渡す JSON（source・session_id など）。
#
# Codex からは GRIMOIRE_HOST=codex を付けて呼ぶ（hooks/codex-hooks.json）。Codex では、
# 使い方の案内を Codex 用（session-context-codex.md）にし、新しい版が届いているかも確かめる（update-check.sh）。

plugin_root="${CLAUDE_PLUGIN_ROOT:-${PLUGIN_ROOT:-}}"
CLAUDE_PLUGIN_ROOT="$plugin_root"
export CLAUDE_PLUGIN_ROOT

if [ "${GRIMOIRE_HOST:-}" = "codex" ]; then
  result="$(sh "${CLAUDE_PLUGIN_ROOT}/hooks/link-shortcut.sh" 2>/dev/null </dev/null)"
  cat "${CLAUDE_PLUGIN_ROOT}/hooks/session-context-codex.md" 2>/dev/null
  if [ "$result" = "conflict" ]; then
    printf '%s\n' "【グリモワール】作業フォルダに .grimoire という名前の別の物があるため、本体への近道を作れませんでした（受講生の物なので触っていません）。この会話では、道具を python3 \"${CLAUDE_PLUGIN_ROOT}/skills/grimoire/scripts/tn_kb.py\" … の形で動かしてください。受講生には「フォルダの中の .grimoire という名前の物を別の名前に変えると、いつもの形で動くようになります」と1回だけ伝えてください。"
  fi
  sh "${CLAUDE_PLUGIN_ROOT}/hooks/update-check.sh" 2>/dev/null </dev/null
  exit 0
fi

input=""
[ -t 0 ] || input="$(cat 2>/dev/null)"
source_kind="$(printf '%s' "$input" | sed -n 's/.*"source"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n 1)"
follow=""
if [ "$source_kind" != "compact" ]; then
  case "$(sh "${CLAUDE_PLUGIN_ROOT}/hooks/startup-update.sh" 2>/dev/null </dev/null)" in
    updated*|installed*) follow=1 ;;  # 新しい版がこのフォルダに入った時だけ、登録の記録を読んで近道をそちらへ向ける
  esac
fi
result="$(GRIMOIRE_FOLLOW_INSTALLED="$follow" sh "${CLAUDE_PLUGIN_ROOT}/hooks/link-shortcut.sh" 2>/dev/null </dev/null)"
cat "${CLAUDE_PLUGIN_ROOT}/hooks/session-context.md" 2>/dev/null
if [ "$result" = "conflict" ]; then
  printf '%s\n' "【グリモワール】作業フォルダに .grimoire という名前の別の物があるため、本体への近道を作れませんでした（受講生の物なので触っていません）。この会話では、道具を python3 \"${CLAUDE_PLUGIN_ROOT}/skills/grimoire/scripts/tn_kb.py\" … の形で動かしてください（受講生に確認が出ます）。受講生には「フォルダの中の .grimoire という名前の物を別の名前に変えると、確認なしで動くようになります」と1回だけ伝えてください。"
fi
if [ "$source_kind" = "compact" ]; then
  sh "${CLAUDE_PLUGIN_ROOT}/hooks/upgrade-notice.sh" always 2>/dev/null </dev/null
else
  sh "${CLAUDE_PLUGIN_ROOT}/hooks/upgrade-notice.sh" 2>/dev/null </dev/null
fi
exit 0
