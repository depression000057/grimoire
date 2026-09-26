#!/bin/sh
# グリモワール: 会話の最初に動く（SessionStart フック）。
# 1. 作業フォルダの近道 .grimoire を、今の版の本体へ向ける（link-shortcut.sh）。
# 2. 作業フォルダの使い方を Claude に伝える（標準出力が Claude への案内になる）。
# 初めて開いた会話では、本体の読み込みがこのフックより後になるため、このフックは動かない。
# その会話では、入力のたびに動く save-long-prompt.sh が同じことを行う。

result="$(sh "${CLAUDE_PLUGIN_ROOT}/hooks/link-shortcut.sh" 2>/dev/null </dev/null)"
cat "${CLAUDE_PLUGIN_ROOT}/hooks/session-context.md" 2>/dev/null
if [ "$result" = "conflict" ]; then
  printf '%s\n' "【グリモワール】作業フォルダに .grimoire という名前の別の物があるため、本体への近道を作れませんでした（受講生の物なので触っていません）。この会話では、道具を python3 \"${CLAUDE_PLUGIN_ROOT}/skills/grimoire/scripts/tn_kb.py\" … の形で動かしてください（受講生に確認が出ます）。受講生には「フォルダの中の .grimoire という名前の物を別の名前に変えると、確認なしで動くようになります」と1回だけ伝えてください。"
fi
exit 0
