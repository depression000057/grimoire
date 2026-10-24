#!/bin/sh
# グリモワール（Claude Code だけ）: この作業フォルダの登録の記録（installed_plugins.json の grimoire@tirnanog）から、値を1つ読む。
# 引数: $1 = installPath か version。標準出力: その値（記録が無ければ何も出さない）。
# この作業フォルダの記録（scope local・projectPath が同じ）を先に、無ければ scope user の記録を使う。
#
# Mac では最初から入っている plutil で読む。python3 を呼ぶと、コマンドライン・デベロッパ・ツールが無い Mac では
# 入れ方の画面が出るため（2.5.0 までのフックは python3 を呼んでいなかった）。plutil が無い時（Windows など）だけ python3 を使う。
#
# 呼ぶ場所: link-shortcut.sh・startup-update.sh・skills/grimoire/scripts/update.sh（どれも新しい版がある時だけ）。

field="$1"
project_dir="${CLAUDE_PROJECT_DIR:-$PWD}"
file="${CLAUDE_CODE_PLUGIN_CACHE_DIR:-$HOME/.claude/plugins}/installed_plugins.json"
if [ -z "$field" ] || [ ! -f "$file" ]; then
  exit 0
fi

if [ -x /usr/bin/plutil ]; then
  key="plugins.grimoire@tirnanog"
  i=0
  user_value=""
  while scope="$(/usr/bin/plutil -extract "$key.$i.scope" raw -o - "$file" 2>/dev/null)"; do
    if [ "$scope" = "local" ]; then
      if [ "$(/usr/bin/plutil -extract "$key.$i.projectPath" raw -o - "$file" 2>/dev/null)" = "$project_dir" ]; then
        printf '%s\n' "$(/usr/bin/plutil -extract "$key.$i.$field" raw -o - "$file" 2>/dev/null)"
        exit 0
      fi
    elif [ "$scope" = "user" ] && [ -z "$user_value" ]; then
      user_value="$(/usr/bin/plutil -extract "$key.$i.$field" raw -o - "$file" 2>/dev/null)"
    fi
    i=$((i + 1))
  done
  if [ -n "$user_value" ]; then
    printf '%s\n' "$user_value"
  fi
  exit 0
fi

command -v python3 >/dev/null 2>&1 || exit 0
python3 - "$file" "$project_dir" "$field" <<'PY' 2>/dev/null
import json, sys
try:
    entries = json.load(open(sys.argv[1], encoding="utf-8")).get("plugins", {}).get("grimoire@tirnanog", [])
except Exception:
    entries = []
local = [e for e in entries if e.get("scope") == "local" and e.get("projectPath") == sys.argv[2]]
user = [e for e in entries if e.get("scope") == "user"]
for entry in local + user:
    print(entry.get(sys.argv[3], ""))
    break
PY
exit 0
