#!/bin/sh
# グリモワール（Claude Code だけ）: 会話の最初に、講座の配布元に新しい版が出ていないかを確かめ、
# 出ていればその場で受け取る（skills/grimoire/scripts/update.sh）。受け取った版へ近道 .grimoire を向け直し、
# その会話から新しい版を使えるようにするのは、呼び出し元の session-start.sh。
#
# Claude Code 本体の自動更新（autoUpdate）だけだと、新しい版は会話を始めてから裏で届き、次の会話から切り替わる。
# 講座が勉強会の資料を足した直後でも、開いたその会話で使えるようにするために、ここで先に取りに行く。
#
# 配布元の版は hooks/update-source.txt の1行目の URL から読む（build_dist.py が書く。試験では GRIMOIRE_UPDATE_URL で差し替える）。
# つながらない時は数秒であきらめる（会話を待たせないため）。受け取れなくても、Claude Code 本体の自動更新が裏で届ける。
# 新しい版が無いふだんの会話では、curl とシェルの比べだけで終える（登録の記録は読まない）。
# 標準出力: updated <前の版> <新しい版>（受け取った）／installed <版>（裏の自動更新がもう受け取っていた）／
#   latest <版>／failed: <理由>。確かめられなかった時は何も出さない。

root="${CLAUDE_PLUGIN_ROOT:-}"
project_dir="${CLAUDE_PROJECT_DIR:-$PWD}"
if [ -z "$root" ]; then
  exit 0
fi
url="${GRIMOIRE_UPDATE_URL:-$(head -n 1 "$root/hooks/update-source.txt" 2>/dev/null | tr -d ' \r')}"
if [ -z "$url" ] || ! command -v curl >/dev/null 2>&1; then
  exit 0
fi

is_version() {
  printf '%s\n' "$1" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+$'
}

# $1 が $2 より新しい版なら 0
newer() {
  awk -v a="$1" -v b="$2" 'BEGIN {
    split(a, x, "."); split(b, y, ".")
    for (i = 1; i <= 3; i++) {
      if (x[i] + 0 > y[i] + 0) exit 0
      if (x[i] + 0 < y[i] + 0) exit 1
    }
    exit 1
  }'
}

latest="$(curl -fsS --max-time "${GRIMOIRE_CHECK_SECONDS:-3}" "$url" 2>/dev/null | head -n 1 | tr -d ' \r')"
if ! is_version "$latest"; then
  exit 0
fi

# このフォルダが今持っている版: 今動いている版と、近道が向いている版（前の会話の途中で受け取った版）の新しい方
have="$(head -n 1 "$root/skills/grimoire/VERSION" 2>/dev/null | tr -d ' \r')"
linked="$(head -n 1 "$project_dir/.grimoire/VERSION" 2>/dev/null | tr -d ' \r')"
if is_version "$linked" && { ! is_version "$have" || newer "$linked" "$have"; }; then
  have="$linked"
fi
if is_version "$have" && ! newer "$latest" "$have"; then
  echo "latest $have"
  exit 0
fi

# 新しい版がある: 裏の自動更新がもう受け取っていれば、取りに行かずにそちらを使う
recorded="$(CLAUDE_PROJECT_DIR="$project_dir" sh "$root/hooks/installed-record.sh" version 2>/dev/null </dev/null)"
if is_version "$recorded" && ! newer "$latest" "$recorded" && { ! is_version "$have" || newer "$recorded" "$have"; }; then
  echo "installed $recorded"
  exit 0
fi

GRIMOIRE_CALLER=hook GRIMOIRE_UPDATE_LIMIT="${GRIMOIRE_UPDATE_LIMIT:-40}" sh "$root/skills/grimoire/scripts/update.sh" </dev/null 2>/dev/null
exit 0
