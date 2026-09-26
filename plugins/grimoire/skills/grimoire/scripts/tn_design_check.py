#!/usr/bin/env python3
"""
check_design.py — 設計シートと本文の点検（Python 標準機能だけで動く）

使い方:
  python3 .grimoire/scripts/tn_design_check.py <設計シート.md> [--draft <本文.md>]

見ること:
  E1 メタ表に「媒体」「読者」「採用した型」の行があり、中身が入っている
  E2 「採用した型」の ID が、このスキルの references にある型（### L1 など）である
  E3 枠の表（見出しに「枠」「中身」「理由」がそろった表。設計シートの §2 と §3）の各行に「中身」か「飛ばした理由」がある（両方空はだめ）
  E4 書き残しの印（〇〇・TODO・（ここに…）など）が残っていない（設計シートと本文。本文は【書き手が記入: 〜】の外だけを見る）
  W1 本文に、作った実績や声に見えやすい形（「〇〇さん（40代）」「月〇万円達成」など）がある → 目視で確かめる
  W2 本文に、guardrails.md の「気をつける言い回し」や、期間で結果を約束する形（「2週間で確かめられます」）がある → 目視で確かめる
  W3 表の中で、列の数が見出しの行と合わない行がある（その行は点検できていない）→ 表の中の縦線「|」を別の字に替える
  W4 選んだ型の枠（references の型の表のうち、並びの列が「順」「部」「通」の型）が、設計シートの枠の表に見当たらない・順番が違う → 目で確かめる。
     「採用した型」に「本1 S2／本2 S1」のように本ごとに書くと、本ごとに照合する。並びの表が無い型（H01〜H30・S2〜S4・M3）は照合しない（目で確かめる。点検の「情報」に出る）
  W5 媒体が X の短文なのに、本ごとの字数（全角1・半角0.5・記入欄を除く）が140字を超えている本がある → 文単位で削る
  情報: 本文の字数（空白・改行・記号を除く）と、本文に残っている【書き手が記入: 〜】の数

終了コード: 0=エラーなし（注意だけの時も0）／1=エラーあり／2=入力エラー
"""
import argparse
import os
import re
import sys
import unicodedata

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REF_DIR = os.path.join(SKILL_DIR, "references", "sales-patterns")
PLACEHOLDERS = ["〇〇", "○○", "TODO", "（ここに", "(ここに", "［ここに", "（例: ", "(例: "]
# 本文では「(例:」は教える文の中で普通に使うので見ない
DRAFT_PLACEHOLDERS = ["〇〇", "○○", "TODO", "(ここに", "[ここに"]
TESTIMONIAL = [
    re.compile(r"[ぁ-んァ-ヶー一-龥A-Za-z]{1,8}(さん|様|氏)[（(]\s*[0-9０-９]{2}代"),
    re.compile(r"月[0-9０-９,，.]+\s*万円?(を)?(達成|突破|稼)"),
    re.compile(r"(喜びの声|購入者の声|お客様の声)[:：]"),
]
CAREFUL = [
    "必ず", "絶対に", "確実に", "誰でも稼げ", "100%", "治る", "治ります", "完治", "予防できます", "必ず痩せ",
    "今すぐ", "残りわずか", "今だけ", "No.1", "業界初", "手遅れ",
]
# 期間で結果を約束する形（「2週間で確かめられます」「3日で分かります」）
PERIOD_PROMISE = re.compile(r"[0-9０-９一二三四五六七八九十]+\s*(日|週間|か月|ヶ月|カ月)(で|以内に|後には)[^。\n]{0,12}(分か|わか|確かめ|でき|変わ|身に|慣れ|効|痩せ|稼)")


def read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def known_type_ids():
    """references の見出し（### L1 …／## 2 M1 … など深さを問わない）と、冒頭の型の表（| H01 |）から型 ID を集める。"""
    ids = set()
    if not os.path.isdir(REF_DIR):
        return ids
    for name in os.listdir(REF_DIR):
        if name.endswith(".md"):
            text = read(os.path.join(REF_DIR, name))
            ids.update(re.findall(r"^#{2,4}\s+(?:[0-9]+\s+)?([A-Z]{1,2}\d{1,2})\s", text, re.M))
            ids.update(re.findall(r"^\|\s*(H\d{2})\s*\|", text, re.M))
    return ids


def rows(text):
    """表の行を「文字を揃える前」の原文で区切る（全角の｜は区切りにしない）。区切った後で各セルを揃える。"""
    out = []
    for no, raw in enumerate(text.splitlines(), 1):
        if raw.lstrip().startswith("|") and not re.match(r"^\s*\|[\s\-:|]+\|\s*$", raw):
            cells = [unicodedata.normalize("NFKC", c).strip() for c in raw.strip().strip("|").split("|")]
            out.append((no, cells))
    return out


def meta_value(text, key):
    for _, cells in rows(text):
        if len(cells) >= 2 and cells[0] == key:
            return cells[1]
    return None


def header_lines(text):
    """表の見出しの行（すぐ下が区切り線 |---| の行）の行番号の集合。セルの中の言葉で見出しと取り違えないため。"""
    lines = text.splitlines()
    out = set()
    for i in range(len(lines) - 1):
        if lines[i].lstrip().startswith("|") and re.match(r"^\s*\|[\s\-:|]+\|\s*$", lines[i + 1]):
            out.add(i + 1)
    return out


def is_slot_header(cells):
    # 枠の表だけを点検する: 見出しに「枠」「中身」「理由」の3つがそろった表（診断など、ほかの表は見ない）
    return any("枠" in c for c in cells) and any("中身" in c for c in cells) and any("理由" in c for c in cells)


def slot_table_problems(text):
    """見出しの行に「枠」「中身」「理由」を含む表を点検する。戻り値: (空の枠の一覧, 列の数が合わない行の一覧)"""
    problems, mismatched = [], []
    header = None
    last_no = None
    heads = header_lines(text)
    table_lines = {no for no, raw in enumerate(text.splitlines(), 1) if raw.lstrip().startswith("|")}
    for no, cells in rows(text):
        if last_no is not None and any(n not in table_lines for n in range(last_no + 1, no)):
            header = None  # 表が途切れたら（表でない行を挟んだら）見出しを捨てる。区切り線の行は表の一部
        last_no = no
        if no in heads:
            header = cells if is_slot_header(cells) else None
            continue
        if header is None:
            continue
        if len(cells) != len(header):
            mismatched.append((no, len(cells), len(header)))
            continue
        c_idx = next(i for i, c in enumerate(header) if "中身" in c)
        r_idx = next(i for i, c in enumerate(header) if "理由" in c)
        slot_idx = next((i for i, c in enumerate(header) if "枠" in c), 1)
        if cells[slot_idx] and not cells[c_idx] and not cells[r_idx]:
            problems.append((no, cells[slot_idx]))
    return problems, mismatched


def core(name):
    name = unicodedata.normalize("NFKC", name)
    name = re.sub(r"^本\d+\s*[-ー－]\s*", "", name)
    name = re.sub(r"[（(][^）)]*[）)]", "", name)
    # 先頭の番号（「1.」「①」）は外す。「1日目1通目」の日の数は枠の名前の一部なので残す
    name = re.sub(r"^[0-9①-⑳]+(?!\d*日目)[\s.．、]*", "", name)
    return re.sub(r"[\s「」『』]", "", name)


def card_slots(type_id):
    """references から、型 ID の見出しの直後にある表のうち「順」の列を持つ表の枠の名前を順に返す。無ければ None。"""
    for name in sorted(os.listdir(REF_DIR)):
        if not name.endswith(".md"):
            continue
        lines = read(os.path.join(REF_DIR, name)).splitlines()
        for i, line in enumerate(lines):
            if not re.match(r"^#{2,4}\s+(?:[0-9]+\s+)?%s\s" % re.escape(type_id), line):
                continue
            header, slots = None, []
            for raw in lines[i + 1:]:
                if re.match(r"^#{1,4}\s", raw):
                    break
                if not raw.lstrip().startswith("|"):
                    if header is not None and slots:
                        break
                    continue
                if re.match(r"^\s*\|[\s\-:|]+\|\s*$", raw):
                    continue
                cells = [c.strip() for c in raw.strip().strip("|").split("|")]
                if header is None:
                    # 並びの列が「順」「部」「通」の表だけを照合する（M3 のような時期の表は照合しない）
                    if cells and cells[0] in ("順", "部", "通") and len(cells) > 1:
                        header = cells
                        continue
                    return None
                slots.append(cells[1])
            return slots or None
    return None


def design_slot_names(raw_text):
    names, header = [], None
    heads = header_lines(raw_text)
    for no, cells in rows(raw_text):
        if no in heads:
            header = cells if is_slot_header(cells) else None
            continue
        if header and len(cells) == len(header):
            # §3 の抜けやすい枠（5-1〜5-4）は型の枠ではないので、W4 の照合に入れない
            if re.match(r"^5-\d", cells[0]):
                continue
            idx = next((i for i, c in enumerate(header) if "枠" in c), 1)
            if cells[idx]:
                names.append(cells[idx])
    return names


def post_prefix(name):
    m = re.match(r"^\s*本\s*(\d+)\s*[-ー－]", unicodedata.normalize("NFKC", name))
    return int(m.group(1)) if m else None


def check_sequence(tid, slots, design_names, label=""):
    warnings = []
    design = [core(n) for n in design_names]
    positions = []
    for s in slots:
        c = core(s)
        key = c[:8]
        pos = next((i for i, d in enumerate(design) if key and (key in d or (d and d[:8] in c))), None)
        if pos is None:
            warnings.append("W4 %s型 %s の枠「%s」が設計シートの枠の表に見当たらない（名前を言い換えた時は無視してよい。「採用した型」の欄に、選ばなかった型の番号を書いていないかも確かめる）" % (label, tid, s[:30]))
        else:
            positions.append(pos)
    if positions != sorted(positions):
        warnings.append("W4 %s型 %s の枠の順番が、設計シートでは型と違う" % (label, tid))
    return warnings


def slot_coverage(chosen_text, ids, raw_text):
    """選んだ型の枠が設計シートにそろっているか。「採用した型」に「本1 S2／本2 S1」のように本ごとに書いてあれば、本ごとに照合する。"""
    warnings = []
    names = design_slot_names(raw_text)
    per_post = re.findall(r"本\s*(\d+)\s*[:：]?\s*([A-Z]{1,2}\d{1,2})", unicodedata.normalize("NFKC", chosen_text))
    if per_post:
        for num, tid in per_post:
            slots = card_slots(tid)
            if not slots:
                continue
            group = [n for n in names if post_prefix(n) == int(num)]
            warnings.extend(check_sequence(tid, slots, group, label="本%s の" % num))
        return warnings
    for tid in ids:
        slots = card_slots(tid)
        if slots:
            warnings.extend(check_sequence(tid, slots, names))
    return warnings


def post_lengths(draft):
    """本文が「## 本1」「## 2日目1通目」のように本ごと・1通ごとに分かれていれば、それぞれの字数（全角1・半角0.5）を返す。"""
    parts = re.split(r"^##\s*(本\s*\d+|\d+\s*日目\s*\d+\s*通目).*$", draft, flags=re.M)
    out = []
    for i in range(1, len(parts) - 1, 2):
        body = re.sub(r"<!--.*?-->", "", parts[i + 1], flags=re.S)
        body = re.sub(r"【書き手が記入[^】]*】", "", body)
        body = re.sub(r"\s", "", body)
        out.append((re.sub(r"\s", "", parts[i]), sum(0.5 if ord(ch) < 128 else 1 for ch in body)))
    return out


def visible_chars(text):
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    text = re.sub(r"^\s*#+\s*", "", text, flags=re.M)
    return len(re.sub(r"[\s|*_`>#\-]", "", text))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("design")
    ap.add_argument("--draft")
    a = ap.parse_args()
    if not os.path.isfile(a.design):
        print("設計シートが無い: %s" % a.design, file=sys.stderr)
        return 2
    raw_text = read(a.design)
    text = unicodedata.normalize("NFKC", raw_text)
    errors, warnings, infos = [], [], []

    for key in ("媒体", "読者", "採用した型"):
        v = meta_value(raw_text, key)
        if not v:
            errors.append("E1 メタ表に「%s」の行が無いか空" % key)
    medium = unicodedata.normalize("NFKC", meta_value(raw_text, "媒体") or "")
    chosen = meta_value(raw_text, "採用した型") or ""
    ids = re.findall(r"(?<![A-Za-z0-9])([A-Z]{1,2}\d{1,2})(?![0-9])", chosen)
    known = known_type_ids()
    if chosen and not ids:
        errors.append("E2 「採用した型」に型の ID（L1・B1 など）が無い: %s" % chosen)
    for tid in ids:
        if tid not in known:
            errors.append("E2 references に無い型 ID: %s（使える ID: %s）" % (tid, ", ".join(sorted(known))))
    w4 = slot_coverage(chosen, [t for t in ids if t in known], raw_text)
    warnings.extend(w4)
    checked = sorted(set(t for t in ids if t in known and card_slots(t)))
    passed = [t for t in checked if not any((" %s の" % t) in w for w in w4)]
    if passed:
        infos.append("型 %s は枠の照合（W4）をして、型の枠が順番どおりそろっていた" % ", ".join(passed))
    unchecked = sorted(set(t for t in ids if t in known and not card_slots(t)))
    if unchecked:
        infos.append("型 %s は並びの表が無いので、枠の照合（W4）をしていない。枠は目で確かめる" % ", ".join(unchecked))
    empty_slots, mismatched = slot_table_problems(raw_text)
    for no, slot in empty_slots:
        errors.append("E3 L%d 枠「%s」に中身も飛ばした理由も無い" % (no, slot))
    for no, got, want in mismatched:
        warnings.append("W3 L%d 列の数が見出しと合わない（%d 列／見出しは %d 列）。この行は点検できていない。セルの中の「|」を別の字に替える" % (no, got, want))
    for no, line in enumerate(text.splitlines(), 1):
        for p in PLACEHOLDERS:
            if p in line:
                errors.append("E4 L%d 書き残しの印「%s」: %s" % (no, p, line.strip()[:60]))

    if a.draft:
        if not os.path.isfile(a.draft):
            print("本文が無い: %s" % a.draft, file=sys.stderr)
            return 2
        draft = unicodedata.normalize("NFKC", read(a.draft))
        for no, line in enumerate(draft.splitlines(), 1):
            outside = re.sub(r"【書き手が記入[^】]*】", "", line)
            for p in DRAFT_PLACEHOLDERS:
                if p in outside:
                    errors.append("E4 本文 L%d 書き残しの印「%s」: %s" % (no, p, line.strip()[:60]))
            # 注意（W1・W2）も書き残し（E4）と同じく、【書き手が記入: 〜】の外だけを見る
            for rx in TESTIMONIAL:
                m = rx.search(outside)
                if m:
                    warnings.append("W1 L%d 作った実績や声に見えやすい形「%s」→ 事実か確かめる" % (no, m.group(0)))
            m = PERIOD_PROMISE.search(outside)
            if m:
                warnings.append("W2 L%d 期間で結果を約束する形「%s」→ 依頼にある事実でなければ記入欄にする（guardrails.md）" % (no, m.group(0)))
            for w in CAREFUL:
                if w in outside:
                    warnings.append("W2 L%d 気をつける言い回し「%s」→ guardrails.md §5 を見る: %s" % (no, w, line.strip()[:60]))
        blanks = len(re.findall(r"【書き手が記入", draft))
        infos.append("本文の字数（空白・改行・記号を除く）: %d 字／記入欄を除くと %d 字" % (visible_chars(draft), visible_chars(re.sub(r"【書き手が記入[^】]*】", "", draft))))
        # 字数は文字の形をそろえる前の本文で数える（全角の「？」を半角の0.5字にしないため）
        for num, length in post_lengths(read(a.draft)):
            if "X" in medium.upper() and "短文" in medium and length > 140:
                warnings.append("W5 %s が %s 字で、X の短文の上限（全角140字）を超えている → 同じことの言い換えを文単位で削る" % (num, ("%.1f" % length).rstrip("0").rstrip(".")))
            infos.append("%s の字数（全角1・半角0.5・記入欄を除く）: %s 字" % (num, ("%.1f" % length).rstrip("0").rstrip(".")))
        if "---- ここから有料 ----" in draft:
            free, paid = draft.split("---- ここから有料 ----", 1)
            strip = lambda s: re.sub(r"【書き手が記入[^】]*】", "", s)
            infos.append("有料ラインより前（無料部分）: %d 字／記入欄を除くと %d 字・後（有料部分）: %d 字／記入欄を除くと %d 字" % (visible_chars(free), visible_chars(strip(free)), visible_chars(paid), visible_chars(strip(paid))))
        infos.append("本文に残っている【書き手が記入】: %d か所（公開前に全部埋める）" % blanks)

    for e in errors:
        print("エラー  " + e)
    for w in warnings:
        print("注意    " + w)
    for i in infos:
        print("情報    " + i)
    print("結果: エラー %d 件・注意 %d 件（型 %s）" % (len(errors), len(warnings), ", ".join(ids) or "—"))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
