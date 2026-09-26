#!/bin/sh
# グリモワール: このパソコンのこの作業フォルダに、グリモワールを「インストール済み」として登録する。
# 配布した作業フォルダの設定だけだと、Claude Code は本体を初めて開いた会話でしか読み込まない
# （フォルダに最初から入っていた設定では、インストールの記録を作らない仕様のため）。
# 登録すると、次の会話からも読み込まれ、講座が新しい版を出すと自動で新しくなる。
#
# 呼ぶ場所は2つ:
#   - プラグインのフック（save-long-prompt.sh）が `--from-hook` を付けて、入力のたびに呼ぶ（登録済みなら何もしない）
#   - フックで登録できなかった時・フォルダを移した時は、Claude が作業フォルダで `sh .grimoire/scripts/register.sh` を実行する
# 標準出力: registered（登録した）／already（登録済み）／busy（別の登録が進行中）／
#           waiting（フックから呼ばれ、前の失敗から30分たっていない）／failed: <理由>（登録できなかった）

from_hook=0
if [ "${1:-}" = "--from-hook" ]; then
  from_hook=1
fi

project_dir="${CLAUDE_PROJECT_DIR:-$PWD}"
plugins_home="${CLAUDE_CODE_PLUGIN_CACHE_DIR:-$HOME/.claude/plugins}"
data_dir="${CLAUDE_PLUGIN_DATA:-$plugins_home/data/grimoire-tirnanog}"
key="$(printf '%s' "$project_dir" | cksum | cut -d' ' -f1)"
mark="$data_dir/registered-$key"
failed_mark="$data_dir/failed-$key"
log="$data_dir/register-$key.log"
lock="$data_dir/register.lock"
installed="$plugins_home/installed_plugins.json"
cooldown_seconds=1800

# 目印があっても、インストールの記録からグリモワールが消えていたら登録し直す
if [ -e "$mark" ]; then
  if [ -f "$installed" ] && ! grep -q '"grimoire@tirnanog"' "$installed" 2>/dev/null; then
    rm -f "$mark"
  else
    echo already
    exit 0
  fi
fi

# フックからは、失敗の直後に何度も試さない（入力のたびに待たせないため）。Claude が実行した時は必ず試す
if [ "$from_hook" = 1 ] && [ -f "$failed_mark" ]; then
  last="$(cat "$failed_mark" 2>/dev/null)"
  now="$(date +%s)"
  case "$last" in
    ''|*[!0-9]*) last=0 ;;
  esac
  if [ $((now - last)) -lt "$cooldown_seconds" ]; then
    echo waiting
    exit 0
  fi
fi

mkdir -p "$data_dir" 2>/dev/null

# 同じパソコンで登録を同時に2つ走らせない（3分より古いロックは、止まった登録の残りとみなして外す）
if ! mkdir "$lock" 2>/dev/null; then
  if [ -n "$(find "$lock" -maxdepth 0 -mmin +3 2>/dev/null)" ]; then
    rmdir "$lock" 2>/dev/null
    mkdir "$lock" 2>/dev/null || { echo busy; exit 0; }
  else
    echo busy
    exit 0
  fi
fi
trap 'rmdir "$lock" 2>/dev/null' EXIT

# Claude Code 本体の場所を探す（見つかった最初の1つを使う）
#   1. Claude Code が渡す本体の場所（デスクトップアプリの Bash などで入っている）
#   2. claude コマンド（ターミナル版を入れた人）
#   3. ターミナル版の標準の置き場所
#   4. Mac のデスクトップアプリに同梱された本体（一番新しく入った版）
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

# 時間の上限つきで動かす（perl があれば。フックは60秒、Claude が実行した時は120秒）
run_limited() {
  limit="$1"
  shift
  if command -v perl >/dev/null 2>&1; then
    perl -e 'alarm shift @ARGV; exec @ARGV or exit 127' "$limit" "$@"
  else
    "$@"
  fi
}

fail() {
  date +%s >"$failed_mark" 2>/dev/null
  echo "failed: $1"
  exit 0
}

exe="$(find_claude)"
if [ -z "$exe" ]; then
  fail "Claude Code の本体が見つかりません"
fi

limit=120
if [ "$from_hook" = 1 ]; then
  limit=60
fi
if (cd "$project_dir" && run_limited "$limit" "$exe" plugin install grimoire@tirnanog --scope local) >"$log" 2>&1 </dev/null; then
  printf '%s\n' "$project_dir" >"$mark"
  rm -f "$failed_mark"
  echo registered
else
  fail "$(tail -n 1 "$log" 2>/dev/null)"
fi
exit 0
