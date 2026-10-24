#!/bin/sh
# グリモワール（Claude Code だけ）: 近道 .grimoire が、今動いている版より新しい版を向いている時
# （この会話の最初か「グリモワール更新」で新しい版を受け取った時）に、新しい版の手順で進めることと、
# 受講生に1行伝えることを Claude に渡す。同じ版については1回だけ（「グリモワール更新」で受け取った時は、
# update.sh の結果で Claude が伝えるので、update.sh が「伝えた」印を先に書く）。
#
# 呼ぶ場所: session-start.sh（会話の最初）・save-long-prompt.sh（入力のたび）。
# 引数: $1 = always の時は、印があっても伝える（会話が要約されて、前に伝えたことが消えた時）。
# 標準出力: Claude への案内（伝える時だけ）。
# 案内の文の中の変数は ${…} で囲む（日本語の設定のパソコンでは、$linked） のように全角の文字が続くと変数名の一部と読まれるため）。

project_dir="${CLAUDE_PROJECT_DIR:-$PWD}"
root="${CLAUDE_PLUGIN_ROOT:-}"
data_dir="${CLAUDE_PLUGIN_DATA:-${CLAUDE_CODE_PLUGIN_CACHE_DIR:-$HOME/.claude/plugins}/data/grimoire-tirnanog}"
mode="${1:-}"

if [ -z "$root" ] || [ ! -e "$project_dir/.grimoire" ]; then
  exit 0
fi
running="$(head -n 1 "$root/skills/grimoire/VERSION" 2>/dev/null | tr -d ' \r')"
linked="$(head -n 1 "$project_dir/.grimoire/VERSION" 2>/dev/null | tr -d ' \r')"
if [ -z "$running" ] || [ -z "$linked" ]; then
  exit 0
fi
if ! awk -v a="$linked" -v b="$running" 'BEGIN {
    split(a, x, "."); split(b, y, ".")
    for (i = 1; i <= 3; i++) {
      if (x[i] + 0 > y[i] + 0) exit 0
      if (x[i] + 0 < y[i] + 0) exit 1
    }
    exit 1
  }'; then
  exit 0
fi

key="$(printf '%s' "$project_dir" | cksum | cut -d' ' -f1)"
notice="$data_dir/upgrade-notified-$key"
if [ "$mode" != "always" ] && [ "$(cat "$notice" 2>/dev/null)" = "$linked" ]; then
  exit 0
fi
mkdir -p "$data_dir" 2>/dev/null && printf '%s\n' "$linked" >"$notice" 2>/dev/null

printf '%s\n' "【グリモワール】講座の新しい版（${linked}）を受け取り、この会話から使えるようにしました（この会話を始めた時の版は ${running}）。grimoire スキルを起動した時に表示される手順は前の版のものなので、起動したら続けて .grimoire/SKILL.md を読み、そちらを今の手順として使ってください（この会話の中でまだ grimoire スキルを起動していなくても、手順は .grimoire/SKILL.md を正とする）。手順書・講座の資料・道具は、いつもどおり .grimoire/ から使います（中身はもう新しい版です）。受講生への最初の返事の最後に「グリモワールを最新の版（${linked}）にしました。」と1行伝え、.grimoire/CHANGELOG.md の一番上の内容を1〜2行で添えてください。"
exit 0
