#!/bin/sh
# グリモワール: 会話の最初に動く（SessionStart フック）。
# 1. 作業フォルダの近道 .grimoire を、今の版の本体へ向ける（link-shortcut.sh）。
# 2. 作業フォルダの使い方を Claude に伝える（標準出力が Claude への案内になる）。
# 初めて開いた会話では、本体の読み込みがこのフックより後になるため、このフックは動かない。
# その会話では、入力のたびに動く save-long-prompt.sh が同じことを行う。
#
# Codex からは GRIMOIRE_HOST=codex を付けて呼ぶ（hooks/codex-hooks.json）。Codex では、
# 使い方の案内を Codex 用（session-context-codex.md）にし、新しい版が届いているかも確かめる（update-check.sh）。

plugin_root="${CLAUDE_PLUGIN_ROOT:-${PLUGIN_ROOT:-}}"
CLAUDE_PLUGIN_ROOT="$plugin_root"
export CLAUDE_PLUGIN_ROOT

result="$(sh "${CLAUDE_PLUGIN_ROOT}/hooks/link-shortcut.sh" 2>/dev/null </dev/null)"
if [ "${GRIMOIRE_HOST:-}" = "codex" ]; then
  cat "${CLAUDE_PLUGIN_ROOT}/hooks/session-context-codex.md" 2>/dev/null
  if [ "$result" = "conflict" ]; then
    printf '%s\n' "【グリモワール】作業フォルダに .grimoire という名前の別の物があるため、本体への近道を作れませんでした（受講生の物なので触っていません）。この会話では、道具を python3 \"${CLAUDE_PLUGIN_ROOT}/skills/grimoire/scripts/tn_kb.py\" … の形で動かしてください。受講生には「フォルダの中の .grimoire という名前の物を別の名前に変えると、いつもの形で動くようになります」と1回だけ伝えてください。"
  fi
  sh "${CLAUDE_PLUGIN_ROOT}/hooks/update-check.sh" 2>/dev/null </dev/null
  exit 0
fi
cat "${CLAUDE_PLUGIN_ROOT}/hooks/session-context.md" 2>/dev/null
if [ "$result" = "conflict" ]; then
  printf '%s\n' "【グリモワール】作業フォルダに .grimoire という名前の別の物があるため、本体への近道を作れませんでした（受講生の物なので触っていません）。この会話では、道具を python3 \"${CLAUDE_PLUGIN_ROOT}/skills/grimoire/scripts/tn_kb.py\" … の形で動かしてください（受講生に確認が出ます）。受講生には「フォルダの中の .grimoire という名前の物を別の名前に変えると、確認なしで動くようになります」と1回だけ伝えてください。"
fi
exit 0
