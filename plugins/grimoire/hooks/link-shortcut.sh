#!/bin/sh
# グリモワール: 作業フォルダに、本体（スキルのフォルダ）への近道 .grimoire を作る・今の版へ向け直す。
# 本体の置き場所は版ごとに変わるが、近道の名前は変わらないので、道具をいつも同じ形
# （python3 .grimoire/scripts/…）で呼べ、作業フォルダの許可の設定も1つで済む。
#
# 近道は symlink で作る。symlink が作れない環境（Windows の既定の設定など）では、本体のコピーを置き、
# 中に目印ファイル .grimoire-copy-of（コピー元の場所を1行）を入れる。
# 触るのは自分が作った近道だけ（向き先が …/skills/grimoire の symlink か、目印の入ったコピー）。
# 受講生が同じ名前で置いた物は、中身を問わず触らない。
#
# Claude Code では、会話の途中で新しい版を受け取った時（startup-update.sh・update.sh）に、その会話から
# 新しい手順書・講座の資料・道具を使えるようにする。
# - GRIMOIRE_FOLLOW_INSTALLED=1 の時（会話の最初に新しい版を受け取った時と「グリモワール更新」の後）: この作業フォルダに登録されている版
#   （installed_plugins.json の記録）が今動いている版より新しければ、そちらへ向ける
# - いつでも: 近道が今動いている版より新しい版を向いていれば、古い版へ戻さない（入力のたびのフックが戻さないように）
# Codex は今動いている版だけを見る（今までどおり）。
#
# 標準出力: changed（作った・向け直した）／conflict（同じ名前の別の物があって作れない）。何もしなかった時は出さない。

project_dir="${CLAUDE_PROJECT_DIR:-$PWD}"
skill_dir="${CLAUDE_PLUGIN_ROOT:-}/skills/grimoire"
link="$project_dir/.grimoire"
owner_mark=".grimoire-copy-of"
host="${GRIMOIRE_HOST:-claude}"

if [ -z "${CLAUDE_PLUGIN_ROOT:-}" ] || [ ! -d "$skill_dir" ] || [ ! -d "$project_dir" ]; then
  exit 0
fi

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

version_of() {
  head -n 1 "$1/VERSION" 2>/dev/null | tr -d ' \r'
}

if [ "$host" != "codex" ] && [ "${GRIMOIRE_FOLLOW_INSTALLED:-}" = "1" ]; then
  # この作業フォルダに登録されている版の本体の場所（installed-record.sh。新しい版を受け取った時だけ呼ばれる）
  recorded="$(CLAUDE_PROJECT_DIR="$project_dir" sh "${CLAUDE_PLUGIN_ROOT}/hooks/installed-record.sh" installPath 2>/dev/null </dev/null)"
  if [ -n "$recorded" ] && [ -d "$recorded/skills/grimoire" ] && [ "$recorded/skills/grimoire" != "$skill_dir" ]; then
    recorded_version="$(version_of "$recorded/skills/grimoire")"
    if [ -n "$recorded_version" ] && newer "$recorded_version" "$(version_of "$skill_dir")"; then
      skill_dir="$recorded/skills/grimoire"
    fi
  fi
fi

# 近道が向いている先（自分が作った物の時だけ）が、同じ保管場所（今動いている版と同じ …/grimoire/ の下）の、
# 向けたい先より新しい版なら 0。Codex の保管場所を向いている時は、今までどおり開いた方へ向け直す
points_to_newer() {
  [ "$host" != "codex" ] || return 1
  [ -d "$1" ] || return 1
  [ "$(dirname "${1%/skills/grimoire}")" = "$(dirname "$CLAUDE_PLUGIN_ROOT")" ] || return 1
  pointed_version="$(version_of "$1")"
  target_version="$(version_of "$skill_dir")"
  [ -n "$pointed_version" ] && [ -n "$target_version" ] && newer "$pointed_version" "$target_version"
}

make_shortcut() {
  if [ "${GRIMOIRE_LINK_MODE:-}" != "copy" ] && ln -sfn "$skill_dir" "$link" 2>/dev/null && [ -L "$link" ]; then
    return 0
  fi
  # symlink が作れなかった（または ln がコピーを作った）: 自分で作りかけた物を片づけて、目印つきのコピーにする
  rm -rf "$link" 2>/dev/null
  cp -R "$skill_dir" "$link" 2>/dev/null || return 1
  printf '%s\n' "$skill_dir" >"$link/$owner_mark"
}

if [ -L "$link" ]; then
  current="$(readlink "$link")"
  if [ "$current" = "$skill_dir" ]; then
    exit 0
  fi
  case "$current" in
    */skills/grimoire) ;;               # 前の版を向いている自分の近道
    *) echo conflict; exit 0 ;;         # 受講生が作った symlink
  esac
  if points_to_newer "$current"; then
    exit 0                              # この会話の途中で受け取った新しい版を向いている
  fi
  rm -f "$link"
elif [ -d "$link" ] && [ -f "$link/$owner_mark" ]; then
  copied_from="$(cat "$link/$owner_mark" 2>/dev/null)"
  if [ "$copied_from" = "$skill_dir" ]; then
    exit 0
  fi
  if [ -n "$copied_from" ] && points_to_newer "$copied_from"; then
    exit 0
  fi
  rm -rf "$link"                        # 前の版の、自分が作ったコピー
elif [ -e "$link" ]; then
  echo conflict
  exit 0
fi

if make_shortcut; then
  echo changed
else
  echo conflict
fi
exit 0
