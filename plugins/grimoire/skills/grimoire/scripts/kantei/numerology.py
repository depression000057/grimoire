#!/usr/bin/env python3
"""数秘術の数字を計算する（スピリチュアルマスタースキルズ・完全版）。

計算は公開されている一般的な方法だけを使う。
- ライフパス: 生年月日の数字をすべて足し、1桁になるまで各桁を足す（11・22・33 はそこで止める）
- 誕生日数: 生まれた日を同じ方法で縮める
- 個人年: 見たい年＋生まれた月日の数字を足して1〜9にする
- 個人月: 個人年＋暦の月を足して1〜9にする
- 二人の数（相性）: 二人のライフパスを足して1〜9にする

使い方:
  python3 numerology.py 1990-05-15
  python3 numerology.py 1990/5/15 --year 2026
  python3 numerology.py 1990-05-15 --months 3          # 今月から3か月の個人月
  python3 numerology.py 1990-05-15 --months 12 --start 2027-01
  python3 numerology.py 1990-05-15 --partner 1988-11-02 # 相性
  python3 numerology.py 1990-05-15 --json
標準ライブラリだけで動く（Python 3.8 以上）。
"""
import argparse
import datetime
import json
import re
import sys

MASTER = {11, 22, 33}


def reduce_number(n: int, keep_master: bool = True) -> int:
    """各桁を足して1桁にする。keep_master なら 11・22・33 で止める。"""
    while n > 9 and not (keep_master and n in MASTER):
        n = sum(int(d) for d in str(n))
    return n


def parse_date(text: str) -> datetime.date:
    parts = re.findall(r"\d+", text)
    if len(parts) == 1 and len(parts[0]) == 8:
        s = parts[0]
        parts = [s[:4], s[4:6], s[6:]]
    if len(parts) != 3:
        raise ValueError("生年月日は 1990-05-15 の形で入れてください")
    y, m, d = (int(p) for p in parts)
    if y < 1900 or y > 2100:
        raise ValueError("西暦4桁で入れてください（例: 1990-05-15）")
    return datetime.date(y, m, d)


def life_path(date: datetime.date) -> int:
    digits = f"{date.year:04d}{date.month:02d}{date.day:02d}"
    return reduce_number(sum(int(c) for c in digits))


def birthday_number(date: datetime.date) -> int:
    return reduce_number(date.day)


def personal_year(date: datetime.date, year: int) -> int:
    digits = f"{year:04d}{date.month:02d}{date.day:02d}"
    return reduce_number(sum(int(c) for c in digits), keep_master=False)


def personal_month(date: datetime.date, year: int, month: int) -> int:
    return reduce_number(personal_year(date, year) + month, keep_master=False)


def pair_number(a: datetime.date, b: datetime.date) -> int:
    return reduce_number(life_path(a) + life_path(b), keep_master=False)


def month_series(date: datetime.date, start_year: int, start_month: int, count: int):
    out = []
    y, m = start_year, start_month
    for _ in range(count):
        out.append({"year": y, "month": m,
                    "personal_year": personal_year(date, y),
                    "personal_month": personal_month(date, y, m)})
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return out


def main(argv=None) -> int:
    today = datetime.date.today()
    ap = argparse.ArgumentParser(description="数秘術の数字を計算します")
    ap.add_argument("birthday", help="生年月日（例: 1990-05-15）")
    ap.add_argument("--year", type=int, default=today.year, help="個人年を出す年（省略すると今年）")
    ap.add_argument("--months", type=int, default=0, help="個人月を何か月分出すか（例: 3 / 12）")
    ap.add_argument("--start", default=None, help="個人月の開始年月（例: 2027-01。省略すると今月）")
    ap.add_argument("--partner", default=None, help="相性を見る相手の生年月日")
    ap.add_argument("--json", action="store_true", help="JSON で出す")
    args = ap.parse_args(argv)
    try:
        date = parse_date(args.birthday)
        partner = parse_date(args.partner) if args.partner else None
        if args.start:
            sy, sm = (int(p) for p in re.findall(r"\d+", args.start)[:2])
        else:
            sy, sm = today.year, today.month
    except (ValueError, TypeError) as e:
        print(f"エラー: {e}", file=sys.stderr)
        return 1
    if args.months < 0 or args.months > 24:
        print("エラー: --months は 1〜24 で入れてください", file=sys.stderr)
        return 1

    result = {
        "birthday": date.isoformat(),
        "life_path": life_path(date),
        "birthday_number": birthday_number(date),
        "year": args.year,
        "personal_year": personal_year(date, args.year),
    }
    if args.months:
        result["months"] = month_series(date, sy, sm, args.months)
    if partner:
        result["partner"] = {
            "birthday": partner.isoformat(),
            "life_path": life_path(partner),
            "birthday_number": birthday_number(partner),
            "pair_number": pair_number(date, partner),
        }

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    print(f"生年月日: {result['birthday']}")
    print(f"ライフパス: {result['life_path']}")
    print(f"誕生日数: {result['birthday_number']}")
    print(f"個人年（{args.year}年）: {result['personal_year']}")
    for row in result.get("months", []):
        print(f"個人月（{row['year']}年{row['month']}月）: {row['personal_month']}")
    if partner:
        p = result["partner"]
        print(f"相手の生年月日: {p['birthday']}")
        print(f"相手のライフパス: {p['life_path']}")
        print(f"相手の誕生日数: {p['birthday_number']}")
        print(f"二人の数: {p['pair_number']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
