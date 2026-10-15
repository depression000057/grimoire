#!/usr/bin/env python3
"""週次の振り返り表を作る（スピリチュアルマスタースキルズ・完全版）。

利用者が Threads のインサイトから写した数字（CSV）を読み、伸びた投稿・伸びなかった投稿・
型ごとの平均・導線の数字をまとめた Markdown を出す。数字は利用者の実数だけを使う。

CSV の見出し（.grimoire/assets/kantei/weekly-posts-template.csv と同じ）:
  date,type,theme,first_line,views,likes,replies,reposts
  （views が空の行は反応率を計算しない）

使い方:
  python3 weekly_report.py 投稿の数字.csv
  python3 weekly_report.py 投稿の数字.csv --from 2026-09-22 --to 2026-09-28
  python3 weekly_report.py 投稿の数字.csv --profile 1200 --diag-start 80 --diag-finish 52 --line-click 30 --line-add 24 --paid 2
"""
import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path


def num(v):
    try:
        return float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def rate(a, b):
    if a is None or not b:
        return None
    return a / b


def pct(x):
    return "-" if x is None else f"{x * 100:.1f}%"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="週次の振り返り表を作る")
    ap.add_argument("csv")
    ap.add_argument("--from", dest="date_from", default=None)
    ap.add_argument("--to", dest="date_to", default=None)
    for k in ("profile", "diag-start", "diag-finish", "line-click", "line-add", "paid"):
        ap.add_argument(f"--{k}", type=float, default=None)
    args = ap.parse_args(argv)
    path = Path(args.csv)
    if not path.exists():
        print(f"エラー: ファイルが見つかりません: {path}", file=sys.stderr)
        return 2
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    need = {"date", "type", "first_line", "views", "likes", "replies"}
    if not rows or not need.issubset(rows[0].keys()):
        print("エラー: 見出しは date,type,theme,first_line,views,likes,replies,reposts にしてください", file=sys.stderr)
        return 2
    posts = []
    for r in rows:
        d = (r.get("date") or "").strip()
        if args.date_from and d < args.date_from:
            continue
        if args.date_to and d > args.date_to:
            continue
        views, likes, replies, reposts = (num(r.get(k)) for k in ("views", "likes", "replies", "reposts"))
        react = sum(x for x in (likes, replies, reposts) if x is not None)
        posts.append({"date": d, "type": (r.get("type") or "未分類").strip(), "theme": (r.get("theme") or "").strip(),
                      "first": (r.get("first_line") or "").strip()[:40], "views": views, "likes": likes or 0,
                      "replies": replies or 0, "react": react, "rate": rate(react, views)})
    if not posts:
        print("エラー: 期間内の投稿がありません", file=sys.stderr)
        return 2
    dates = sorted(p["date"] for p in posts)
    total_views = sum(p["views"] or 0 for p in posts)
    print(f"# 週次の振り返り（{dates[0]}〜{dates[-1]}）\n")
    print(f"- 投稿数: {len(posts)}本")
    print(f"- 閲覧の合計: {int(total_views):,}")
    print(f"- いいねの合計: {int(sum(p['likes'] for p in posts)):,}／返信の合計: {int(sum(p['replies'] for p in posts)):,}")
    rated = [p for p in posts if p["rate"] is not None]
    key = (lambda p: p["rate"]) if len(rated) >= 3 else (lambda p: p["likes"])
    pool = rated if len(rated) >= 3 else posts
    label = "反応率（いいね＋返信＋再投稿÷閲覧）" if len(rated) >= 3 else "いいね数（閲覧の数字が3本未満のため）"
    ranked = sorted(pool, key=key, reverse=True)
    print(f"\n## 伸びた投稿トップ3（{label}の順）\n")
    print("| 日付 | 型 | 1行目 | 閲覧 | いいね | 返信 | 反応率 |\n|---|---|---|---|---|---|---|")
    for p in ranked[:3]:
        print(f"| {p['date']} | {p['type']} | {p['first']} | {int(p['views'] or 0):,} | {int(p['likes'])} | {int(p['replies'])} | {pct(p['rate'])} |")
    print("\n## 伸びなかった投稿ワースト3\n")
    print("| 日付 | 型 | 1行目 | 閲覧 | いいね | 返信 | 反応率 |\n|---|---|---|---|---|---|---|")
    for p in ranked[-3:][::-1]:
        print(f"| {p['date']} | {p['type']} | {p['first']} | {int(p['views'] or 0):,} | {int(p['likes'])} | {int(p['replies'])} | {pct(p['rate'])} |")
    by_type = defaultdict(list)
    for p in posts:
        by_type[p["type"]].append(p)
    print("\n## 型ごとの平均\n")
    print("| 型 | 本数 | 平均閲覧 | 平均いいね | 平均返信 | 平均反応率 |\n|---|---|---|---|---|---|")
    for t, ps in sorted(by_type.items(), key=lambda kv: -sum(x["likes"] for x in kv[1]) / len(kv[1])):
        vs = [x["views"] for x in ps if x["views"] is not None]
        rs = [x["rate"] for x in ps if x["rate"] is not None]
        print(f"| {t} | {len(ps)} | {int(sum(vs) / len(vs)) if vs else '-'} | {sum(x['likes'] for x in ps) / len(ps):.1f} | "
              f"{sum(x['replies'] for x in ps) / len(ps):.1f} | {pct(sum(rs) / len(rs)) if rs else '-'} |")
    steps = [("プロフィールを見た人", args.profile), ("診断を始めた人", args.diag_start), ("診断を終えた人", args.diag_finish),
             ("LINEのボタンを押した人", args.line_click), ("LINEに登録した人", args.line_add), ("有料鑑定を申し込んだ人", args.paid)]
    if any(v is not None for _, v in steps):
        print("\n## 導線の数字（前の段から次の段へ進んだ割合）\n")
        print("| 段階 | 人数 | 前の段から |\n|---|---|---|")
        prev = None
        for name, v in steps:
            if v is None:
                continue
            print(f"| {name} | {int(v)} | {pct(rate(v, prev)) if prev else '-'} |")
            prev = v
        if args.diag_start and args.diag_finish is not None and args.diag_finish == 0:
            print("\n注意: 診断を始めた人がいるのに、終えた人が0人です。最後のボタンや送信先がつながっているか確かめてください。")
    print("\n## 来週やること（スキルが上の表から書く）\n\n- 伸びた型：\n- やめる言い方：\n- 導線で直す所：")
    return 0


if __name__ == "__main__":
    sys.exit(main())
