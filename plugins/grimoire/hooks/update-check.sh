#!/bin/sh
# グリモワール（Codex だけ）: 講座が出した新しい版が、このパソコンに届いているかを確かめる。
# Codex は新しい会話を始める時に配布元から新しい版を取ってくるが、公式の説明には自動更新の記述が無く、
# 届かない環境もありうる。届いていない時だけ、受講生に伝える案内を Codex のモデルに渡す。
# 更新の命令はここでは実行しない（受講生が頼んだ時だけ、モデルが実行する）。
#
# 呼ぶ場所: session-start.sh（GRIMOIRE_HOST=codex の時だけ）。
# 配布元の版の読み先: プラグインの hooks/update-source.txt の1行目（build_dist.py が書く）。
#   試験では GRIMOIRE_UPDATE_URL で差し替える。
# 標準出力: 案内（届いていない状態が2回続いた時だけ。同じ版の案内は1日1回まで）。
# 案内の文の中の変数は ${…} で囲む（日本語の設定のパソコンでは、$latest） のように全角の文字が続くと変数名の一部と読まれるため）。

root="${PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-}}"
data_dir="${PLUGIN_DATA:-${CLAUDE_PLUGIN_DATA:-${CODEX_HOME:-$HOME/.codex}/plugins/data/grimoire-tirnanog}}"
marketplace="tirnanog"
interval="${GRIMOIRE_UPDATE_INTERVAL:-21600}"  # 配布元を見に行く間隔（秒）。6時間
notice_interval=86400                          # 同じ版の案内を出す間隔（秒）。1日

if [ -z "$root" ]; then
  exit 0
fi
installed="$(head -n 1 "$root/skills/grimoire/VERSION" 2>/dev/null | tr -d ' \r')"
url="${GRIMOIRE_UPDATE_URL:-$(head -n 1 "$root/hooks/update-source.txt" 2>/dev/null | tr -d ' \r')}"
if [ -z "$installed" ] || [ -z "$url" ]; then
  exit 0
fi
mkdir -p "$data_dir" 2>/dev/null || exit 0

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

now="$(date +%s)"
latest_file="$data_dir/update-latest"
stamp=0
latest=""
if [ -f "$latest_file" ]; then
  read -r stamp latest <"$latest_file" 2>/dev/null
fi
case "$stamp" in
  ''|*[!0-9]*) stamp=0 ;;
esac
if [ $((now - stamp)) -ge "$interval" ] && command -v curl >/dev/null 2>&1; then
  fetched="$(curl -fsS --max-time 4 "$url" 2>/dev/null | head -n 1 | tr -d ' \r')"
  if is_version "$fetched"; then
    latest="$fetched"
  fi
  # 読めなかった時も時刻だけは残す（つながらないパソコンで、会話のたびに待たせないため）
  printf '%s %s\n' "$now" "$latest" >"$latest_file" 2>/dev/null
fi

behind_file="$data_dir/update-behind"
if ! is_version "$latest" || ! newer "$latest" "$installed"; then
  rm -f "$behind_file" 2>/dev/null
  exit 0
fi

# 新しい会話を始めた直後は、取ってくる途中のことがある。2回続けて古いままの時だけ案内する
behind_version=""
count=0
if [ -f "$behind_file" ]; then
  read -r behind_version count <"$behind_file" 2>/dev/null
fi
case "$count" in
  ''|*[!0-9]*) count=0 ;;
esac
if [ "$behind_version" != "$latest" ]; then
  count=0
fi
count=$((count + 1))
printf '%s %s\n' "$latest" "$count" >"$behind_file" 2>/dev/null
if [ "$count" -lt 2 ]; then
  exit 0
fi

notified_file="$data_dir/update-notified"
notified_version=""
notified_at=0
if [ -f "$notified_file" ]; then
  read -r notified_version notified_at <"$notified_file" 2>/dev/null
fi
case "$notified_at" in
  ''|*[!0-9]*) notified_at=0 ;;
esac
if [ "$notified_version" = "$latest" ] && [ $((now - notified_at)) -lt "$notice_interval" ]; then
  exit 0
fi
printf '%s %s\n' "$latest" "$now" >"$notified_file" 2>/dev/null

printf '%s\n' "【グリモワール】講座から新しい版（${latest}）が出ていますが、このパソコンのグリモワールは ${installed} のままです（新しい会話を始めても届いていません）。今の依頼にはこのまま答え、返事の最後に次の2行を受講生に伝えてください。1行目「グリモワールの新しい版（${latest}）が出ています。Codex をいったん終了して開き直し、新しい会話で話しかけてください。」2行目「それでも変わらない時は、ターミナルで次の1行を実行してください: codex plugin marketplace upgrade ${marketplace}」。この命令は自分からは実行しない（受講生がはっきり「更新して」と頼んだ時だけ実行し、確認が出たら受講生に許可してもらう）。"
exit 0
