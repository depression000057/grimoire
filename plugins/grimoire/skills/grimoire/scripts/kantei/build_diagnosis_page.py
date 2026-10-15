#!/usr/bin/env python3
"""診断ページ（1枚の HTML）を作る（スピリチュアルマスタースキルズ・完全版）。

設定ファイル（JSON）から、質問→結果→「LINEでキーワードを送ってください」までの
スマホ向け診断ページを1ファイルで書き出す。外部の読み込みは使わないので、そのまま
好きな場所（UTAGE のページ・無料のホスティングなど）に置ける。公開は利用者が行う。

測る数字: 診断を始めた人・終えた人・LINEのボタンを押した人（とキーワードをコピーした人）。
設定の tracking_url に受け取り先（例: Google スプレッドシートにつないだ Apps Script の URL）を
入れると、その3つが送られる。空なら送らない。

使い方:
  python3 build_diagnosis_page.py 設定.json 出力.html
  python3 build_diagnosis_page.py 設定.json 出力.html --check   # 点検だけ
設定の見本: .grimoire/assets/kantei/diagnosis-config-sample.json
"""
import argparse
import html
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_post import SAFETY_PATTERNS  # noqa: E402


def validate(cfg: dict):
    errors, warnings = [], []
    for key in ("title", "lead", "questions", "types", "line_url"):
        if not cfg.get(key):
            errors.append(f"「{key}」が空です")
    types = cfg.get("types") or {}
    qs = cfg.get("questions") or []
    if types and not (2 <= len(types) <= 6):
        errors.append(f"結果のタイプは2〜6個にしてください（今 {len(types)} 個）")
    if qs and not (4 <= len(qs) <= 12):
        errors.append(f"質問は4〜12問にしてください（今 {len(qs)} 問。おすすめは8問）")
    if qs and len(qs) != 8:
        warnings.append(f"質問が {len(qs)} 問です（おすすめは8問）")
    for i, q in enumerate(qs, 1):
        if not q.get("q"):
            errors.append(f"質問{i}の文が空です")
        chs = q.get("choices") or []
        if len(chs) < 2:
            errors.append(f"質問{i}の選択肢が2つ未満です")
        for c in chs:
            if c.get("type") not in types:
                errors.append(f"質問{i}の選択肢「{c.get('text')}」のタイプ「{c.get('type')}」が types にありません")
    counts = {t: 0 for t in types}
    for q in qs:
        for c in q.get("choices") or []:
            if c.get("type") in counts:
                counts[c["type"]] += 1
    for t, n in counts.items():
        if n == 0:
            errors.append(f"タイプ「{t}」に当たる選択肢が1つもありません")
    keywords = []
    for t, v in types.items():
        for key in ("name", "keyword", "summary", "detail"):
            if not v.get(key):
                errors.append(f"タイプ「{t}」の「{key}」が空です")
        keywords.append(v.get("keyword"))
    if len(set(keywords)) != len(keywords):
        errors.append("タイプごとのキーワードが重なっています（LINEでタイプを分けられなくなります）")
    url = cfg.get("line_url", "")
    if url and not url.startswith("https://"):
        errors.append("line_url は https:// で始まる LINE の友だち追加URLにしてください")
    if "xxxx" in url or "example" in url:
        warnings.append("line_url が見本のままです。本物の友だち追加URLに差し替えてください")
    turl = cfg.get("tracking_url", "")
    if turl and not turl.startswith("https://"):
        errors.append("tracking_url は https:// で始めてください（使わないなら空にする）")
    if not turl:
        warnings.append("tracking_url が空です。始めた人・終えた人・LINEを押した人の数は送られません")
    blob = json.dumps(cfg, ensure_ascii=False)
    for pat, label in SAFETY_PATTERNS:
        if label.startswith("アカウント名"):
            continue
        for m in re.finditer(pat, blob):
            errors.append(f"安全ルール（{label}）: 「{m.group(0)}」")
    return errors, warnings


PAGE = """<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
:root{--bg:#fbf8f3;--card:#ffffff;--ink:#2b2522;--sub:#6b625c;--accent:#7a4fa3;--accent-ink:#ffffff;--line:#06c755;--border:#e8e0d6}
@media (prefers-color-scheme: dark){:root{--bg:#1c1a1f;--card:#262329;--ink:#f1ece6;--sub:#b8aea6;--accent:#b28ad6;--accent-ink:#1c1a1f;--border:#3a353e}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"Hiragino Sans","Noto Sans JP",sans-serif;line-height:1.8}
main{max-width:560px;margin:0 auto;padding:24px 16px 48px}
.card{background:var(--card);border:1px solid var(--border);border-radius:16px;padding:24px 20px;margin-top:16px}
h1{font-size:1.35rem;line-height:1.5;margin:8px 0 12px}
h2{font-size:1.15rem;margin:0 0 12px}
p{margin:0 0 12px}
.sub{color:var(--sub);font-size:.9rem}
.btn{display:block;width:100%;border:0;border-radius:12px;padding:14px 16px;font-size:1rem;font-weight:700;cursor:pointer;margin-top:12px;text-align:center;text-decoration:none}
.primary{background:var(--accent);color:var(--accent-ink)}
.choice{background:transparent;color:var(--ink);border:1.5px solid var(--border);font-weight:500;text-align:left}
.choice:hover,.choice:focus{border-color:var(--accent)}
.line{background:var(--line);color:#fff}
.bar{height:6px;background:var(--border);border-radius:3px;overflow:hidden;margin-bottom:16px}
.bar>i{display:block;height:100%;background:var(--accent);width:0}
.kw{display:flex;gap:8px;align-items:center;justify-content:center;border:2px dashed var(--accent);border-radius:12px;padding:12px;font-size:1.3rem;font-weight:700;margin:12px 0}
.hidden{display:none}
.note{font-size:.8rem;color:var(--sub);margin-top:20px}
</style>
</head>
<body>
<main>
  <section id="top" class="card">
    <p class="sub" id="author"></p>
    <h1 id="title"></h1>
    <p id="lead"></p>
    <p class="sub" id="count"></p>
    <button class="btn primary" id="start">診断をはじめる</button>
  </section>
  <section id="quiz" class="card hidden">
    <div class="bar"><i id="progress"></i></div>
    <p class="sub" id="qno"></p>
    <h2 id="qtext"></h2>
    <div id="choices"></div>
  </section>
  <section id="result" class="card hidden">
    <p class="sub">あなたの診断結果</p>
    <h1 id="rname"></h1>
    <p id="rsummary"></p>
    <p id="rdetail"></p>
    <p id="rtip"></p>
    <div class="card" style="margin-top:20px">
      <h2>この続きの詳しい鑑定結果は、LINEでお届けしています</h2>
      <p>下のボタンで友だち追加をして、このキーワードを送ってください。</p>
      <div class="kw"><span id="kw"></span></div>
      <button class="btn choice" id="copy" style="text-align:center">キーワードをコピーする</button>
      <a class="btn line" id="linebtn" href="#" target="_blank" rel="noopener">LINEで詳しい結果を受け取る</a>
    </div>
    <button class="btn choice" id="retry" style="text-align:center">もう一度診断する</button>
  </section>
  <p class="note" id="disclaimer"></p>
</main>
<script type="application/json" id="cfg">__CONFIG__</script>
<script>
(function(){
  var cfg = JSON.parse(document.getElementById('cfg').textContent);
  var typeKeys = Object.keys(cfg.types);
  var $ = function(id){ return document.getElementById(id); };
  var i = 0, score = {}, last = null, sessionId = Math.random().toString(36).slice(2);
  function track(ev, extra){
    try { var k = 'diag_' + ev; localStorage.setItem(k, String(1 + Number(localStorage.getItem(k) || 0))); } catch (e) {}
    if (!cfg.tracking_url) return;
    var body = JSON.stringify(Object.assign({event: ev, session: sessionId, page: cfg.title, ts: new Date().toISOString()}, extra || {}));
    try {
      if (navigator.sendBeacon) { navigator.sendBeacon(cfg.tracking_url, new Blob([body], {type: 'text/plain'})); }
      else { fetch(cfg.tracking_url, {method: 'POST', body: body, mode: 'no-cors', keepalive: true}); }
    } catch (e) {}
  }
  $('title').textContent = cfg.title;
  $('lead').textContent = cfg.lead;
  $('author').textContent = cfg.author || '';
  $('count').textContent = '質問は' + cfg.questions.length + '問・1分ほどで終わります';
  $('disclaimer').textContent = cfg.disclaimer || '';
  function show(id){ ['top','quiz','result'].forEach(function(s){ $(s).classList.toggle('hidden', s !== id); }); window.scrollTo(0,0); }
  function render(){
    var q = cfg.questions[i];
    $('qno').textContent = '質問 ' + (i + 1) + ' / ' + cfg.questions.length;
    $('progress').style.width = (i / cfg.questions.length * 100) + '%';
    $('qtext').textContent = q.q;
    var box = $('choices'); box.innerHTML = '';
    q.choices.forEach(function(c){
      var b = document.createElement('button');
      b.className = 'btn choice'; b.textContent = c.text;
      b.onclick = function(){ score[c.type] = (score[c.type] || 0) + 1; last = c.type; i++; if (i < cfg.questions.length) { render(); } else { finish(); } };
      box.appendChild(b);
    });
  }
  function finish(){
    var best = null, bestN = -1;
    typeKeys.forEach(function(t){ var n = score[t] || 0; if (n > bestN || (n === bestN && t === last)) { best = t; bestN = n; } });
    var r = cfg.types[best];
    $('rname').textContent = r.name;
    $('rsummary').textContent = r.summary;
    $('rdetail').textContent = r.detail;
    $('rtip').textContent = r.tip || '';
    $('kw').textContent = r.keyword;
    $('linebtn').href = cfg.line_url;
    $('linebtn').onclick = function(){ track('line_click', {type: best}); };
    $('copy').onclick = function(){
      track('keyword_copy', {type: best});
      try { navigator.clipboard.writeText(r.keyword); $('copy').textContent = 'コピーしました'; } catch (e) { $('copy').textContent = 'キーワード：' + r.keyword; }
    };
    track('finish', {type: best});
    show('result');
  }
  $('start').onclick = function(){ i = 0; score = {}; last = null; track('start'); show('quiz'); render(); };
  $('retry').onclick = function(){ show('top'); };
})();
</script>
</body>
</html>
"""


def build(cfg: dict) -> str:
    data = json.dumps(cfg, ensure_ascii=False).replace("</", "<\\/")
    return PAGE.replace("__TITLE__", html.escape(cfg["title"])).replace("__CONFIG__", data)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="診断ページを作る")
    ap.add_argument("config")
    ap.add_argument("output", nargs="?")
    ap.add_argument("--check", action="store_true", help="点検だけして書き出さない")
    args = ap.parse_args(argv)
    try:
        cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"エラー: 設定ファイルを読めません: {e}", file=sys.stderr)
        return 2
    errors, warnings = validate(cfg)
    for w in warnings:
        print(f"注意: {w}")
    if errors:
        for e in errors:
            print(f"直してください: {e}", file=sys.stderr)
        return 1
    if args.check or not args.output:
        print("点検OK（書き出すには出力ファイル名を付けて実行）")
        return 0
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build(cfg), encoding="utf-8")
    print(f"書き出しました: {out}（質問{len(cfg['questions'])}問・結果{len(cfg['types'])}タイプ）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
