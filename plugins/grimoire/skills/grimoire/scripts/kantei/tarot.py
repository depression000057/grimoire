#!/usr/bin/env python3
"""タロットを引く（スピリチュアルマスタースキルズ・完全版）。

78枚（大アルカナ22枚・小アルカナ56枚）から重ならずに引き、正位置・逆位置を決める。
カードの読みは references/tarot-meanings.md（自分の言葉で書いた一般的な読み）を使う。
利用者が自分で実物のカードを引いた時は、この道具を使わずに引いたカードを教えてもらう。

使い方:
  python3 tarot.py                    # 1枚
  python3 tarot.py --spread 3         # 3枚（過去・現在・これから）
  python3 tarot.py --spread 3 --labels 状況,壁,助言
  python3 tarot.py --spread 3 --seed 42   # 同じ結果を出し直す時
  python3 tarot.py --majors-only --json
"""
import argparse
import json
import random
import sys

MAJORS = [
    "0 愚者", "1 魔術師", "2 女教皇", "3 女帝", "4 皇帝", "5 教皇", "6 恋人", "7 戦車",
    "8 力", "9 隠者", "10 運命の輪", "11 正義", "12 吊るされた男", "13 死神", "14 節制",
    "15 悪魔", "16 塔", "17 星", "18 月", "19 太陽", "20 審判", "21 世界",
]
SUITS = ["ワンド", "カップ", "ソード", "ペンタクル"]
RANKS = ["エース", "2", "3", "4", "5", "6", "7", "8", "9", "10", "ペイジ", "ナイト", "クイーン", "キング"]
DEFAULT_LABELS = {1: ["今のあなたへ"], 3: ["過去", "現在", "これから"],
                  5: ["今の状況", "気持ちの奥", "壁", "助言", "流れの向き"]}


def deck(majors_only: bool):
    cards = [{"name": m, "arcana": "大アルカナ"} for m in MAJORS]
    if not majors_only:
        cards += [{"name": f"{s}の{r}", "arcana": "小アルカナ", "suit": s, "rank": r}
                  for s in SUITS for r in RANKS]
    return cards


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="タロットを引きます")
    ap.add_argument("--spread", type=int, default=1, choices=[1, 3, 5])
    ap.add_argument("--labels", default=None, help="位置の名前をカンマ区切りで（枚数と同じ数）")
    ap.add_argument("--seed", type=int, default=None, help="同じ結果を出し直すための番号")
    ap.add_argument("--majors-only", action="store_true", help="大アルカナ22枚だけで引く")
    ap.add_argument("--no-reversed", action="store_true", help="逆位置を使わない")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    labels = args.labels.split(",") if args.labels else DEFAULT_LABELS[args.spread]
    if len(labels) != args.spread:
        print(f"エラー: 位置の名前は {args.spread} 個にしてください", file=sys.stderr)
        return 1
    rng = random.Random(args.seed) if args.seed is not None else random.SystemRandom()
    picked = rng.sample(deck(args.majors_only), args.spread)
    out = []
    for label, card in zip(labels, picked):
        reversed_ = False if args.no_reversed else rng.random() < 0.5
        out.append({"position": label.strip(), **card, "reversed": reversed_})
    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0
    for row in out:
        pos = "逆位置" if row["reversed"] else "正位置"
        print(f"{row['position']}: {row['name']}（{pos}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
