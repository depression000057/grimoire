#!/usr/bin/env python3
"""Threads 投稿の点検と採点の集計（スピリチュアルマスタースキルズ）。

100点満点の7項目のうち、機械で決まる3項目（長さ10・重複10・呼びかけ5）をここで計算し、
スキルが本文の下に書いた冒頭スコア（10点満点）と判定3項目（具体性20・一次性20・読者とのつながり15）を
読み取り、冒頭スコアを全体の冒頭20点に換算して合計する。あわせて安全ルールの言葉と、日付がずれると
事故になる言葉を拾う。

投稿ファイルの書き方（1本ずつ【番号】で始める。採点の行はスキルが書く）:
  【1】型：日常のしぐさ／テーマ：金運
  （本文）
  採点: フック=8 具体=20 一次=14 読者=11

使い方:
  python3 check_post.py 投稿.md
  python3 check_post.py 投稿.md --past 過去の投稿.md
  python3 check_post.py 投稿.md --json
合格（すぐ出せる）: 合計80点以上・冒頭スコア7点以上・安全ルールの言葉0件・重複の近さ0.72未満
"""
import argparse
import difflib
import json
import re
import sys
from pathlib import Path

READY_MIN = 80
REVIEW_MIN = 64
HOOK_MIN = 7
DUP_MAX = 0.72

JUDGE_KEYS = {
    "フック": ("hook10", 10),
    "具体": ("specificity", 20),
    "一次": ("firsthand", 20),
    "読者": ("reader", 15),
}

SAFETY_PATTERNS = [
    (r"絶対(?!(?:とは|に?うまくいくとは|ではな|じゃな))|必ず叶|必ずうまく|100\s*[%％]|１００\s*[%％]|確実に|運命の人です",
     "未来の言い切り（時期と傾向の言い方に直す）"),
    (r"(?:連絡が来|復縁し|結婚し|別れ|戻ってき|臨時収入が入り)ます[。！!]", "出来事の予言（時期と傾向の言い方に直す）"),
    (r"(?:決める|決まる)のは[^。]{0,12}(?:数字|星|カード|運命)", "結果が占いで決まるという言い切り"),
    (r"不幸になる|運が落ちる|呪い|呪われ|祟り|バチが当たる|一生苦しい|二度と戻って|憑[いくか]", "不安で動かす言い方"),
    (r"努力が足りな|自己責任|引き寄せてしまった|あなたのせいで", "相談者を責める言い方"),
    (r"治ります|治る|完治|儲かる|借金が消え|病気が消え|薬を(?:やめ|止め)|受診(?:しなくて|は不要)|霊障|貯金を全部", "健康・お金の断定"),
    (r"(?:浄化|お祓い|除霊|祈祷)[^。\n]{0,30}\d[\d,，]*\s*(?:万円|円)|\d[\d,，]*\s*(?:万円|円)[^。\n]{0,30}(?:浄化|お祓い|除霊|祈祷)",
     "お祓い・浄化と金額の組み合わせ（霊感商法と受け取られる形）"),
    (r"続きはDM|続きはＤＭ|ぼかし|スルーしたら|スルーしないで|飛ばしたら|飛ばさないで", "本文を隠す・脅して引っぱる形"),
    (r"私がいないと|私だけが(?:救|助|変え)|他の占い師は偽", "依存させる言い方"),
    (r"@[A-Za-z0-9_.]{2,}", "アカウント名（@〜）"),
]

# 自己採点で使ってよい段階の点（post-scoring.md の表と同じ）
ALLOWED_STEPS = {"specificity": {4, 12, 20}, "firsthand": {5, 14, 20}, "reader": {3, 11, 15}}

TEMPORAL_TERMS = ["明日", "明朝", "明後日", "昨日", "今週", "来週", "先週",
                  "月曜", "火曜", "水曜", "木曜", "金曜", "土曜", "日曜"]

CTA_WORDS = ["コメント", "書いて", "送って", "教えて", "プロフィール", "LINE", "保存"]

JARGON = ["チャクラ", "マヤ暦", "ライフパス", "アセンション", "ツインレイ", "波動", "カルマ", "数秘"]


def split_posts(text: str):
    """【番号】で区切って (見出し, 本文, 採点dict) のリストにする。"""
    blocks = re.split(r"(?m)^(?=【\s*\d+\s*】)", text)
    posts = []
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        lines = block.splitlines()
        header = ""
        if re.match(r"^【\s*\d+\s*】", lines[0]):
            header = lines[0].strip()
            lines = lines[1:]
        judge = {}
        body_lines = []
        for line in lines:
            if re.match(r"^\s*採点\s*[:：]", line):
                for k, v in re.findall(r"(フック|具体|一次|読者)\s*=\s*(\d+)", line):
                    judge[JUDGE_KEYS[k][0]] = int(v)
                continue
            body_lines.append(line)
        body = "\n".join(body_lines).strip()
        if body:
            posts.append((header, body, judge))
    return posts


def opening_from_hook(hook10: int) -> int:
    """冒頭スコア（10点）を全体スコアの冒頭（20点）に換算する。"""
    if hook10 >= 9:
        return 20
    if hook10 >= 7:
        return 14
    if hook10 >= 5:
        return 9
    return 4


def score_length(body: str) -> int:
    n = len(body)
    if 140 <= n <= 360:
        return 10
    if 100 <= n < 140 or 360 < n <= 460:
        return 7
    if 60 <= n < 100 or 460 < n <= 520:
        return 4
    return 1


def score_cta(body: str) -> int:
    has = any(w in body for w in CTA_WORDS)
    if not has:
        return 4
    if body.startswith(("コメント", "LINE", "プロフィール")):
        return 2
    return 5


def similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio()


def first_line_notes(body: str):
    first = body.splitlines()[0].strip() if body else ""
    notes = []
    if re.match(r"^(おはよう|こんにちは|こんばんは|はじめまして)", first):
        notes.append("1行目が挨拶で始まっている")
    if re.match(r"^(私は|わたしは|僕は)", first):
        notes.append("1行目の主語が自分になっている（読者か他の人を主語に）")
    hit = [w for w in JARGON if w in first]
    if hit:
        notes.append("1行目に説明なしの専門用語: " + "・".join(hit))
    if len(first) > 60:
        notes.append(f"1行目が長い（{len(first)}字。35〜45字が目安）")
    return first, notes


def check(posts, past_texts):
    results = []
    bodies = [b for _, b, _ in posts]
    for i, (header, body, judge) in enumerate(posts):
        others = past_texts + [b for j, b in enumerate(bodies) if j != i]
        dup = max((similarity(body, o) for o in others), default=0.0)
        mech = {
            "length": score_length(body),
            "duplicate": max(0, round(10 - dup * 10)),
            "cta": score_cta(body),
        }
        safety = []
        for pat, label in SAFETY_PATTERNS:
            for m in re.finditer(pat, body):
                safety.append(f"{label}: 「{m.group(0)}」")
        temporal = [t for t in TEMPORAL_TERMS if t in body]
        first, notes = first_line_notes(body)
        missing = [k for k, (key, _) in JUDGE_KEYS.items() if key not in judge]
        total = None
        status = "採点の行が足りない"
        if "hook10" in judge:
            judge["opening"] = opening_from_hook(judge["hook10"])
        if not missing:
            total = sum(mech.values()) + sum(judge[k] for k in ("opening", "specificity", "firsthand", "reader"))
            if safety:
                status = "書き直し（安全ルール）"
            elif dup >= DUP_MAX:
                status = "書き直し（似た投稿がある）"
            elif judge["hook10"] < HOOK_MIN:
                status = "冒頭を直す（冒頭スコア7点未満）"
            elif total >= READY_MIN:
                status = "合格（出せる）"
            elif total >= REVIEW_MIN:
                status = "手直し（64〜79点）"
            else:
                status = "書き直し（64点未満）"
        over = [k for k, (key, mx) in JUDGE_KEYS.items() if judge.get(key, 0) > mx]
        off_step = [k for k, (key, _) in JUDGE_KEYS.items()
                    if key in ALLOWED_STEPS and key in judge and judge[key] not in ALLOWED_STEPS[key]]
        if over:
            status = "採点の値が上限を超えている: " + "・".join(over)
            total = None
        elif off_step:
            status = "採点の値が表の段階と違う（具体20/12/4・一次20/14/5・読者15/11/3）: " + "・".join(off_step)
            total = None
        results.append({
            "no": i + 1, "header": header, "chars": len(body), "first_line": first,
            "mechanical": mech, "judge": judge, "missing_judge": missing,
            "duplicate_ratio": round(dup, 2), "total": total, "status": status,
            "safety": safety, "temporal": temporal, "first_line_notes": notes,
        })
    return results


def print_report(results):
    print("| # | 字数 | 冒頭(10) | 冒頭20 | 具体20 | 一次20 | 読者15 | 長さ10 | 重複10 | 呼びかけ5 | 合計 | 判定 |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in results:
        j, m = r["judge"], r["mechanical"]
        g = lambda k: str(j[k]) if k in j else "-"
        total = str(r["total"]) if r["total"] is not None else "-"
        print(f"| {r['no']} | {r['chars']} | {g('hook10')} | {g('opening')} | {g('specificity')} | {g('firsthand')} | "
              f"{g('reader')} | {m['length']} | {m['duplicate']} | {m['cta']} | {total} | {r['status']} |")
    for r in results:
        notes = []
        if r["missing_judge"]:
            notes.append("採点の行に無い項目: " + "・".join(r["missing_judge"]))
        notes += ["安全: " + s for s in r["safety"]]
        if r["temporal"]:
            notes.append("日付の言葉（予約投稿なら日付とずれないか確認）: " + "・".join(r["temporal"]))
        notes += ["冒頭: " + n for n in r["first_line_notes"]]
        if r["duplicate_ratio"] >= 0.5:
            notes.append(f"似た投稿との近さ {r['duplicate_ratio']}（0.72以上は書き直し）")
        if notes:
            print(f"\n【{r['no']}】")
            for n in notes:
                print(f"- {n}")
    ok = sum(1 for r in results if r["status"].startswith("合格"))
    print(f"\n合格 {ok} / {len(results)} 本（合格の条件: 合計{READY_MIN}点以上・冒頭スコア{HOOK_MIN}点以上・安全ルールの言葉0件・重複0.72未満）")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Threads 投稿の点検と採点の集計")
    ap.add_argument("posts", help="投稿ファイル（【1】【2】…で区切る）")
    ap.add_argument("--past", action="append", default=[], help="過去の投稿ファイル（重複の確認用・何個でも）")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    path = Path(args.posts)
    if not path.exists():
        print(f"エラー: ファイルが見つかりません: {path}", file=sys.stderr)
        return 2
    posts = split_posts(path.read_text(encoding="utf-8"))
    if not posts:
        print("エラー: 投稿が見つかりません。1本ずつ【1】【2】…で始めてください", file=sys.stderr)
        return 2
    past = []
    for p in args.past:
        pp = Path(p)
        if not pp.exists():
            print(f"エラー: 比べる投稿のファイルが見つかりません: {pp}（無いなら --past から外してください）", file=sys.stderr)
            return 2
        past += [b for _, b, _ in split_posts(pp.read_text(encoding="utf-8"))]
    results = check(posts, past)
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        print_report(results)
    return 0


if __name__ == "__main__":
    sys.exit(main())
