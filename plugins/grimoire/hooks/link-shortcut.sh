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
# 標準出力: changed（作った・向け直した）／conflict（同じ名前の別の物があって作れない）。何もしなかった時は出さない。

project_dir="${CLAUDE_PROJECT_DIR:-$PWD}"
skill_dir="${CLAUDE_PLUGIN_ROOT:-}/skills/grimoire"
link="$project_dir/.grimoire"
owner_mark=".grimoire-copy-of"

if [ -z "${CLAUDE_PLUGIN_ROOT:-}" ] || [ ! -d "$skill_dir" ] || [ ! -d "$project_dir" ]; then
  exit 0
fi

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
  rm -f "$link"
elif [ -d "$link" ] && [ -f "$link/$owner_mark" ]; then
  if [ "$(cat "$link/$owner_mark" 2>/dev/null)" = "$skill_dir" ]; then
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
