#!/bin/sh
# グリモワール: 受講生が何か入力するたびに動く（UserPromptSubmit フック）。
# 1. チャットに貼られた長い文を、原文のまま作業フォルダに保存する（Claude が長い原文を書き写さなくても
#    取り込めるようにするため。短い入力は保存しない）。後の処理が時間切れになっても残るように、最初に行う。
# 2. 近道 .grimoire がまだ無い・古い時は作り直して、使い方の案内も渡す（link-shortcut.sh）。
#    初めて開いた会話では本体の読み込みが会話の最初のフックより後になり、session-start.sh が動かないため。
# 3. このパソコンへの登録がまだなら、登録する（skills/grimoire/scripts/register.sh。登録済みなら何もしない）。
# 標準入力: Claude Code が渡す JSON（prompt・session_id など）。標準出力: Claude に渡す案内（必要な時だけ）。

THRESHOLD_BYTES=4000  # 日本語でおよそ1,300字。講師の添削とセミナーの一部を一緒に貼ると超える長さ
project_dir="${CLAUDE_PROJECT_DIR:-$PWD}"
inbox="$project_dir/ティルナノーグ_マイナレッジ/_受け取り"
data_dir="${CLAUDE_PLUGIN_DATA:-${CLAUDE_CODE_PLUGIN_CACHE_DIR:-$HOME/.claude/plugins}/data/grimoire-tirnanog}"

tmp_file="$(mktemp 2>/dev/null || echo "${TMPDIR:-/tmp}/grimoire-prompt-$$.json")"
cat >"$tmp_file" || { rm -f "$tmp_file"; exit 0; }
session_id="$(sed -n 's/.*"session_id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$tmp_file" 2>/dev/null | head -n 1)"

# 1. 長い文の保存
saved=""
size=$(wc -c <"$tmp_file" | tr -d ' ')
if [ "${size:-0}" -ge "$THRESHOLD_BYTES" ] && mkdir -p "$inbox" 2>/dev/null; then
  stamp="$(date +%Y%m%d-%H%M%S)"
  saved="$inbox/$stamp.json"
  if [ -e "$saved" ]; then
    saved="$inbox/$stamp-$$.json"
  fi
  mv "$tmp_file" "$saved" 2>/dev/null || saved=""
fi
rm -f "$tmp_file" 2>/dev/null

# 2. 近道
case "$(sh "${CLAUDE_PLUGIN_ROOT}/hooks/link-shortcut.sh" 2>/dev/null </dev/null)" in
  changed)
    cat "${CLAUDE_PLUGIN_ROOT}/hooks/session-context.md" 2>/dev/null
    ;;
  conflict)
    # 同じ会話の中では1回だけ伝える
    key="$(printf '%s' "$project_dir" | cksum | cut -d' ' -f1)"
    notice="$data_dir/conflict-notified-$key"
    if [ -z "$session_id" ] || [ "$(cat "$notice" 2>/dev/null)" != "$session_id" ]; then
      mkdir -p "$data_dir" 2>/dev/null && printf '%s\n' "$session_id" >"$notice" 2>/dev/null
      printf '%s\n' "【グリモワール】作業フォルダに .grimoire という名前の別の物があるため、本体への近道を作れませんでした（受講生の物なので触っていません）。この会話では、道具を python3 \"${CLAUDE_PLUGIN_ROOT}/skills/grimoire/scripts/tn_kb.py\" … の形で動かしてください（受講生に確認が出ます）。受講生には「フォルダの中の .grimoire という名前の物を別の名前に変えると、確認なしで動くようになります」と1回だけ伝えてください。"
    fi
    ;;
esac

# 3. 登録
case "$(sh "${CLAUDE_PLUGIN_ROOT}/skills/grimoire/scripts/register.sh" --from-hook 2>/dev/null </dev/null)" in
  registered)
    printf '%s\n' "【グリモワール】このパソコンのこの作業フォルダに、グリモワールを登録しました。次の会話からもそのまま使え、講座が新しい版を出すと自動で新しくなります。受講生への返事の最後に、このことを1行で伝えてください。"
    ;;
  failed*)
    printf '%s\n' "【グリモワール・最優先】このパソコンへの登録がまだです（登録しないと、次の会話からグリモワールが動きません）。今の依頼に答える前に、受講生に「グリモワールをこのパソコンに登録します」と一言伝えてから、作業フォルダで sh .grimoire/scripts/register.sh を1回だけ実行してください。registered か already と出たら、今の依頼に進み、返事の最後に「このパソコンに登録しました」と1行伝えてください。failed と出たら（インターネットにつながっていない時など）、今の依頼はそのまま進め、返事の最後に「インターネットにつながった状態で、もう一度話しかけてください」と1行伝えてください。"
    ;;
esac

# 1 の結果の案内
if [ -n "$saved" ]; then
  printf '%s\n' "【グリモワール】今の入力は長い文だったので、原文をそのまま次のファイルに保存しました: $saved 。中身が素材（文字起こし・講師の添削・資料・投稿の数字など）なら、この文を書き写さず、python3 .grimoire/scripts/tn_kb.py add-source ティルナノーグ_マイナレッジ --kind <種類> --prompt-json <このファイル> で取り込んでください（grimoire の references/modes/4_grow.md §11）。ふつうの依頼（投稿や note の注文など）なら、このファイルは使わなくてよい。"
fi
exit 0
