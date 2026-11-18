#!/usr/bin/env python3
"""Threads 投稿と note 原稿を機械チェックする CLI。"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


EXAGGERATIONS: Tuple[str, ...] = (
    "誰でも稼げ",
    "絶対に稼げ",
    "必ず稼げ",
    "確実に稼げ",
    "楽して稼",
    "放置で稼",
    "100%",
    "１００％",
    "月100万",
    "月収100万",
    "不労所得",
    "損しない",
    "絶対に儲か",
)
VERIFY_FACT_TERMS: Tuple[str, ...] = (
    "何年も",
    "何年間も",
    "ずっと",
    "毎日",
    "毎回",
    "いつも",
    "何度も",
    "何百",
    "何千",
    "数えきれない",
    "一番",
    "いちばん",
    "最も",
    "誰よりも",
    "みんな",
    "全員",
    "すべての人",
    "100人中",
    "0分",
    "ゼロに",
    "完全に",
    "一切",
    "二度と",
    "消えました",
    "なくなりました",
    "よく届く",
    "たくさん届く",
    "多くの人から",
    "大反響",
    "殺到",
    # 読者の声・質問の量（受け取っていない声を作りやすい言い方）
    "という声をもらう",
    "という声をいただ",
    "よく聞かれ",
    "よくいただく",
    "相談が多い",
    # 経験から出した結論の言い方（本人の経験か確かめる）
    "ちょうど真ん中でした",
    "ちょうど良かった",
    "がベストでした",
    # 読者への目安（本人の習慣を目安にしていないか。安全に関わる時は確かめ先があるか）
    "目安です",
    "を目安に",
    # 一次情報のやり方に置き換えた時の、本人のやり方としての書き方
    "私もこの方法",
)
# 公的な案内などから借りたやり方を、本人の習慣として書いた言い方（「この方法で解凍してから使うようにしていて」など）
# 語ごとの案内。一般の案内（本人の事実か確かめる）だけでは、本人の事実と確かめられた時点で残す判断になりやすい語
VERIFY_FACT_HINTS: Dict[str, str] = {
    "目安です": "読者への目安として書いていませんか。本人の習慣なら「私は〜ようにしています」と本人の習慣として書き、読者への目安にするなら公的な確かめ先を付けてください（absolute-rules.md §3）。本人の事実と確かめられても、目安の書き方のままでは残さないでください。",
    "を目安に": "読者への目安として書いていませんか。本人の習慣なら「私は〜ようにしています」と本人の習慣として書き、読者への目安にするなら公的な確かめ先を付けてください（absolute-rules.md §3）。本人の事実と確かめられても、目安の書き方のままでは残さないでください。",
    "私もこの方法": "公的な案内などから借りたやり方を、本人のやり方として書いていませんか。本人が実際にしていなければ消し、違っていたことを確かめてほしいことで本人に伝えてください（absolute-rules.md §3）。",
}
VERIFY_FACT_PATTERNS: Tuple[Tuple[str, "re.Pattern[str]"], ...] = (
    (
        "借りたやり方を本人の習慣に",
        re.compile(r"(この|その|同じ|こちらの)(方法|やり方|手順)で[^。！？!?]{0,20}ようにして"),
    ),
)
# 守りに入ってふわっとさせた言い方（absolute-rules.md §6・pipeline.md 段6c）。決まりで止めている言い方ではないので、
# 言い切れる所は言い切り、何がもらえるか・何が分かるかを具体の名前で書く。ぼかす理由が本当にある所だけ残す
FUZZY_TERMS: Tuple[str, ...] = (
    "かもしれません",
    "かもしれない",
    "気がします",
    "ではないでしょうか",
    "と言われています",
    "場合もあります",
    "人もいます",
    "少しでも",
    "参考になれば",
    "お役に立てれば",
    "いかがでしたか",
    "ヒントを",
    "きっかけに",
    "寄り添",
    "サポートします",
    "整えます",
    "豊かさ",
    "流れが変わ",
    "について話します",
    "についてお話し",
)
FIRST_PERSON_TERMS: Tuple[str, ...] = ("私", "わたし", "僕", "ぼく", "俺", "自分")
CTA_TERMS: Tuple[str, ...] = ("LINE", "公式LINE", "フォロー", "購入", "こちら", "リンク")
ACTION_CTA_TERMS: Tuple[str, ...] = ("してみてください", "やってみてください", "試してみて", "保存して", "保存しておく", "コメントで", "コメント欄")
PAID_MARKER = "---- ここから有料 ----"
SENTENCE_ENDINGS: Tuple[Tuple[str, str], ...] = (
    ("ませんでした", "でした"),
    ("だったんです", "んです"),
    ("なのです", "んです"),
    ("なんです", "んです"),
    ("んです", "んです"),
    ("でしたね", "でした"),
    ("ましたね", "ました"),
    ("ですよね", "よね"),
    ("ますよね", "よね"),
    ("だよね", "よね"),
    ("ですね", "です"),
    ("ますね", "ます"),
    ("でした", "でした"),
    ("ました", "ました"),
    ("ません", "ません"),
    ("です", "です"),
    ("ます", "ます"),
    ("よね", "よね"),
)
CONCRETE_RE = re.compile(r"[0-9０-９]|[ァ-ヶー]{3,}|円|歳|年|日|時|分|回|人|個|本")
POST_HEADING_RE = re.compile(r"^##\s*投稿")
SUBMISSION_MEMO_RE = re.compile(r"^(##\s*(提出メモ|使ったカード|企画表)|\*\*使ったカード\*\*|使ったカード\s*[:：])")
TREE_HEADING_RE = re.compile(r"^(?:###\s*ツリー|（続き）)")
HEADING_ONE_RE = re.compile(r"^#(?!#)\s+", re.MULTILINE)
HEADING_TWO_RE = re.compile(r"^##(?!#)\s+", re.MULTILINE)
HTML_COMMENT_RE = re.compile(r"<!--.*?(?:-->|\Z)", re.DOTALL)


class InputError(Exception):
    """利用者が直せる入力エラー。"""


@dataclass
class Issue:
    code: str
    message: str
    context: Dict[str, Any]

    def as_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {"code": self.code, "message": self.message}
        result.update(self.context)
        return result


@dataclass
class ThreadPart:
    text: str
    source_lines: List[Tuple[int, str]]

    @property
    def character_count(self) -> int:
        return count_without_newlines(self.text)


@dataclass
class ThreadPost:
    parts: List[ThreadPart]

    @property
    def text(self) -> str:
        return "\n".join(part.text for part in self.parts)

    @property
    def source_lines(self) -> List[Tuple[int, str]]:
        return [source_line for part in self.parts for source_line in part.source_lines]


@dataclass(frozen=True)
class VoiceSettings:
    line_break: str = ""
    emoji: str = ""
    first_person: str = ""
    note_line_break: str = ""


def eprint(message: str) -> None:
    print(message, file=sys.stderr)


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise InputError(f"ファイルが見つかりません: {path}") from exc
    except UnicodeDecodeError as exc:
        raise InputError(f"UTF-8 で読めないファイルです: {path}") from exc
    except OSError as exc:
        raise InputError(f"ファイルを読めません: {path}（{exc}）") from exc


def count_without_newlines(text: str) -> int:
    return len(text.replace("\r", "").replace("\n", ""))


def remove_html_comments(text: str) -> str:
    return HTML_COMMENT_RE.sub(lambda match: "\n" * match.group(0).count("\n"), text)


def has_source_content(lines: Sequence[Tuple[int, str]]) -> bool:
    return any(line.strip() for _, line in lines)


def trim_empty_source_lines(lines: Sequence[Tuple[int, str]]) -> List[Tuple[int, str]]:
    start = 0
    end = len(lines)
    while start < end and lines[start][1] == "":
        start += 1
    while end > start and lines[end - 1][1] == "":
        end -= 1
    return list(lines[start:end])


def split_thread_posts(text: str) -> List[ThreadPost]:
    posts_as_lines: List[List[Tuple[int, str]]] = []
    current: List[Tuple[int, str]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        # 提出メモ（使ったカード・確かめてほしいこと・企画表など）から後ろは投稿ではない
        if SUBMISSION_MEMO_RE.match(line.strip()):
            break
        if line.strip() == "---" or POST_HEADING_RE.match(line.strip()):
            if has_source_content(current):
                posts_as_lines.append(current)
            current = []
            continue
        current.append((line_number, line))
    if has_source_content(current):
        posts_as_lines.append(current)

    posts: List[ThreadPost] = []
    for post_lines in posts_as_lines:
        parts_as_lines: List[List[Tuple[int, str]]] = []
        part: List[Tuple[int, str]] = []
        for line_number, line in post_lines:
            if TREE_HEADING_RE.match(line.strip()):
                if has_source_content(part):
                    parts_as_lines.append(part)
                part = []
                continue
            part.append((line_number, line))
        if has_source_content(part):
            parts_as_lines.append(part)
        parts = []
        for source_lines in parts_as_lines:
            trimmed_lines = trim_empty_source_lines(source_lines)
            parts.append(
                ThreadPart(
                    text="\n".join(line for _, line in trimmed_lines),
                    source_lines=trimmed_lines,
                )
            )
        if parts:
            posts.append(ThreadPost(parts=parts))
    return posts


def first_content_line(post: ThreadPost) -> str:
    for line in post.parts[0].text.splitlines():
        if line.strip():
            return line.strip()
    return ""


def split_sentences(text: str) -> List[str]:
    sentences: List[str] = []
    start = 0
    for match in re.finditer(r"[。！？!?]+", text):
        sentence = text[start : match.start()].strip()
        if sentence:
            sentences.append(sentence)
        start = match.end()
    tail = text[start:].strip()
    if tail:
        sentences.append(tail)
    return sentences


def normalize_sentence_ending(sentence: str) -> str:
    cleaned = unicodedata.normalize("NFKC", sentence)
    cleaned = re.sub(r"[\s\u3000」』】）)〉》”’…・]+$", "", cleaned)
    for ending, canonical in SENTENCE_ENDINGS:
        if cleaned.endswith(ending):
            return canonical
    characters = "".join(character for character in cleaned if not unicodedata.category(character).startswith("P"))
    return characters[-2:] if len(characters) >= 2 else characters


def repeated_ending_issues(text: str, context: Dict[str, Any]) -> List[Issue]:
    sentences = split_sentences(text)
    endings = [normalize_sentence_ending(sentence) for sentence in sentences]
    issues: List[Issue] = []
    index = 0
    while index < len(endings):
        ending = endings[index]
        run_end = index + 1
        while ending and run_end < len(endings) and endings[run_end] == ending:
            run_end += 1
        run_length = run_end - index
        if ending and run_length >= 3:
            details = dict(context)
            details.update({"ending": ending, "sentence_start": index + 1, "run_length": run_length})
            issues.append(
                Issue(
                    "REPEATED_ENDING",
                    f"同じ語尾「{ending}」が{run_length}文続いています。語尾を変えてください。",
                    details,
                )
            )
        index = run_end
    return issues


def term_issues(
    text: str,
    terms: Iterable[str],
    code: str,
    message_template: str,
    context: Dict[str, Any],
) -> List[Issue]:
    issues: List[Issue] = []
    for term in terms:
        if term and term in text:
            details = dict(context)
            details["term"] = term
            issues.append(Issue(code, message_template.format(term=term), details))
    return issues


def visible_source_lines(source_lines: Sequence[Tuple[int, str]]) -> List[Tuple[int, str]]:
    if not source_lines:
        return []
    visible_text = remove_html_comments("\n".join(line for _, line in source_lines))
    visible_lines = visible_text.split("\n")
    return [
        (source_lines[index][0], line)
        for index, line in enumerate(visible_lines)
    ]


def verify_fact_review_issues(
    source_lines: Sequence[Tuple[int, str]],
    context: Dict[str, Any],
) -> List[Issue]:
    issues: List[Issue] = []
    for term in VERIFY_FACT_TERMS:
        # 「20分」の中の「0分」のように、数字の途中に当たったものは数えない
        pattern = re.compile(r"(?<![0-9０-９])" + re.escape(term)) if term[:1].isdigit() else None
        for line_number, line in source_lines:
            if pattern is not None:
                if not pattern.search(line):
                    continue
            elif term not in line:
                continue
            details = dict(context)
            details.update({"kind": "verify-fact", "line": line_number, "term": term})
            issues.append(
                Issue(
                    "VERIFY_FACT",
                    f"{line_number}行目の「{term}」: "
                    + VERIFY_FACT_HINTS.get(
                        term,
                        "本人の事実か確かめてください。設定・実績に裏付けが無ければ消すか、確かめてほしいことに回してください。",
                    ),
                    details,
                )
            )
            break
    already_flagged_lines = {
        int(issue.context["line"])
        for issue in issues
        if issue.context.get("term") == "私もこの方法"
    }
    for label, regex in VERIFY_FACT_PATTERNS:
        for line_number, line in source_lines:
            match = regex.search(line)
            if not match or line_number in already_flagged_lines:
                continue
            details = dict(context)
            details.update({"kind": "verify-fact", "line": line_number, "term": match.group(0), "pattern": label})
            issues.append(
                Issue(
                    "VERIFY_FACT",
                    f"{line_number}行目の「{match.group(0)}」: 本人が実際にしているやり方か確かめてください。"
                    "公的な案内などから借りたやり方なら、本人の習慣として書かず、確かめてほしいことに回してください。",
                    details,
                )
            )
    return sorted(issues, key=lambda issue: (int(issue.context["line"]), str(issue.context["term"])))


def fuzzy_review_issues(
    source_lines: Sequence[Tuple[int, str]],
    context: Dict[str, Any],
) -> List[Issue]:
    issues: List[Issue] = []
    for term in FUZZY_TERMS:
        for line_number, line in source_lines:
            if term not in line:
                continue
            details = dict(context)
            details.update({"kind": "fuzzy", "line": line_number, "term": term})
            issues.append(
                Issue(
                    "FUZZY",
                    f"{line_number}行目の「{term}」: 守りに入ってふわっとしていませんか。"
                    "読者が「それ何言ってるの？」「で、何がもらえるの？」とならないよう、言い切れる所は言い切り、"
                    "届く物・分かること・変化を具体の名前で書いてください（absolute-rules.md §6・pipeline.md 段6c）。"
                    "ぼかす理由が絶対ルールにある時だけ残してください。",
                    details,
                )
            )
            break
    return sorted(issues, key=lambda issue: (int(issue.context["line"]), str(issue.context["term"])))


def read_prohibited_terms(path: Optional[Path]) -> List[str]:
    if path is None:
        return []
    text = read_text(path)
    terms: List[str] = []
    inside = False
    for line in text.splitlines():
        if re.match(r"^##\s+禁止したい言葉\s*$", line.strip()):
            inside = True
            continue
        if inside and re.match(r"^#{1,6}\s+", line.strip()):
            break
        if inside:
            match = re.match(r"^\s*-\s+(.+?)\s*$", line)
            if match:
                term = match.group(1).strip()
                if term and term not in terms:
                    terms.append(term)
    return terms


def read_voice_settings(path: Optional[Path]) -> VoiceSettings:
    if path is None:
        return VoiceSettings()
    text = read_text(path)
    values: Dict[str, str] = {}
    inside = False
    for line in text.splitlines():
        stripped = line.strip()
        if re.match(r"^##(?!#)\s+声\s*$", stripped):
            inside = True
            continue
        if inside and re.match(r"^#{1,6}\s+", stripped):
            break
        if not inside:
            continue
        match = re.match(r"^\s*(?:-\s*)?(改行の癖|絵文字|一人称)\s*[:：]\s*(.*?)\s*$", line)
        if match:
            values[match.group(1)] = match.group(2).strip()
            continue
        # 「note の改行（Threads と違う時だけ…）: 段落ごと」のような行
        note_match = re.match(r"^\s*(?:-\s*)?note\s*の改行[^:：]*[:：]\s*(.*?)\s*$", line)
        if note_match:
            values["note の改行"] = note_match.group(1).strip()
    return VoiceSettings(
        line_break=values.get("改行の癖", ""),
        emoji=values.get("絵文字", ""),
        first_person=values.get("一人称", ""),
        note_line_break=values.get("note の改行", ""),
    )


QUOTED_RE = re.compile(r"「[^「」]*」|『[^『』]*』")


def count_sentences_in_line(line: str) -> int:
    """1行の中の文の数。かぎかっこの中の「？」「！」「。」は文の終わりとして数えない。"""
    outside = QUOTED_RE.sub("「」", line)
    return len(re.findall(r"[。！？]+", outside))


def is_body_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped or stripped == PAID_MARKER or re.match(r"^#{1,6}\s+", stripped):
        return False
    compact = re.sub(r"\s+", "", stripped)
    return re.fullmatch(r"(?:-{3,}|\*{3,}|_{3,})", compact) is None


def first_person_position(line: str, term: str) -> Optional[int]:
    if term == "自分":
        match = re.search(r"(?:^|[。！？!?])[\s「『（(]*自分[はが]", line)
        return match.start() if match else None
    position = line.find(term)
    return position if position >= 0 else None


# 「1文ごと」の直後にあれば、1文ごとの改行を求めていないと読む言い方
LINE_BREAK_NEGATION_RE = re.compile(
    r"(しない|せず|やめ|不要|なし|無し|必要はない|必要ない|必要ありません|必要は無い|"
    r"しなくてよい|しなくていい|しなくても|ません|行わない|分けない)"
)


def wants_line_per_sentence(value: str) -> bool:
    """声の設定が「1文ごとに改行」を求めているか。

    「1文ごと」「1文ずつ」が出てくるたびに、その直後（次の読点・句点・かっこまで）に
    否定（しない・せず など）があるかを見る。否定の無い出現が1つでもあれば求めている扱い。
    「段落でまとめる（1文ごとの改行はしない）」は求めていない、
    「段落ではなく1文ごとに改行する」「1文ごとに改行し、段落間は1行空ける」は求めている。
    """
    for match in re.finditer(r"1文(ごと|ずつ)", value):
        rest = value[match.end():]
        clause = re.split(r"[、。，．（）()]", rest, maxsplit=1)[0][:16]
        if not re.search(LINE_BREAK_NEGATION_RE, clause):
            return True
    return False


def voice_review_issues(
    source_lines: Sequence[Tuple[int, str]],
    settings: VoiceSettings,
    context: Dict[str, Any],
) -> List[Issue]:
    issues: List[Issue] = []

    if wants_line_per_sentence(settings.line_break):
        for line_number, line in source_lines:
            if not is_body_line(line):
                continue
            sentence_count = count_sentences_in_line(line)
            if sentence_count >= 2:
                details = dict(context)
                details.update(
                    {
                        "kind": "voice",
                        "line": line_number,
                        "sentence_count": sentence_count,
                    }
                )
                issues.append(
                    Issue(
                        "VOICE_LINE_BREAK",
                        f"{line_number}行目: 声の設定は1文ごとに改行です。"
                        f"この行には{sentence_count}文あります。",
                        details,
                    )
                )

    if "使わない" in settings.emoji or "ほぼ使わない" in settings.emoji:
        emoji_count = count_emoji("\n".join(line for _, line in source_lines))
        if emoji_count >= 2:
            details = dict(context)
            details.update({"kind": "voice", "emoji_count": emoji_count})
            issues.append(
                Issue(
                    "VOICE_EMOJI",
                    f"声の設定では絵文字をほぼ使わないため、{emoji_count}個ある絵文字を確認してください。",
                    details,
                )
            )

    if settings.first_person:
        configured_terms = {term for term in FIRST_PERSON_TERMS if term in settings.first_person}
        for term in FIRST_PERSON_TERMS:
            if term in configured_terms:
                continue
            first_match: Optional[Tuple[int, int]] = None
            for line_number, line in source_lines:
                position = first_person_position(line, term)
                if position is not None:
                    first_match = (line_number, position)
                    break
            if first_match is None:
                continue
            line_number, _ = first_match
            details = dict(context)
            details.update(
                {
                    "kind": "voice",
                    "line": line_number,
                    "configured": settings.first_person,
                    "actual": term,
                }
            )
            issues.append(
                Issue(
                    "VOICE_FIRST_PERSON",
                    f"{line_number}行目の一人称「{term}」が設定「{settings.first_person}」と違います。",
                    details,
                )
            )
    return issues


def is_emoji_base(character: str) -> bool:
    code = ord(character)
    return (
        0x1F1E6 <= code <= 0x1F1FF
        or 0x1F300 <= code <= 0x1FAFF
        or 0x2600 <= code <= 0x27BF
        or code in {0x00A9, 0x00AE, 0x203C, 0x2049, 0x2122, 0x2139, 0x3030, 0x303D, 0x3297, 0x3299}
    )


def count_emoji(text: str) -> int:
    """絵文字列をおおむね見た目1個として数える（外部ライブラリ不要）。"""
    count = 0
    index = 0
    regional_open = False
    while index < len(text):
        character = text[index]
        code = ord(character)
        if character in "#*0123456789" and index + 1 < len(text):
            next_index = index + 1
            if ord(text[next_index]) == 0xFE0F:
                next_index += 1
            if next_index < len(text) and ord(text[next_index]) == 0x20E3:
                count += 1
                index = next_index + 1
                regional_open = False
                continue
        if 0x1F1E6 <= code <= 0x1F1FF:
            if not regional_open:
                count += 1
                regional_open = True
            else:
                regional_open = False
            index += 1
            continue
        regional_open = False
        if is_emoji_base(character):
            count += 1
            index += 1
            while index < len(text) and ord(text[index]) in range(0x1F3FB, 0x1F400):
                index += 1
            if index < len(text) and ord(text[index]) == 0xFE0F:
                index += 1
            while index < len(text) and ord(text[index]) == 0x200D:
                index += 1
                if index < len(text) and is_emoji_base(text[index]):
                    index += 1
                    if index < len(text) and 0x1F3FB <= ord(text[index]) <= 0x1F3FF:
                        index += 1
                    if index < len(text) and ord(text[index]) == 0xFE0F:
                        index += 1
                else:
                    break
            continue
        index += 1
    return count


def first_line_review_issues(first_line: str, post_number: int) -> List[Issue]:
    issues: List[Issue] = []
    context = {"post": post_number, "line": 1}
    if len(first_line) > 40:
        issues.append(
            Issue(
                "FIRST_LINE_LONG",
                f"1行目が{len(first_line)}字です。40字以内にできるか目で確認してください。",
                dict(context, chars=len(first_line)),
            )
        )
    if not CONCRETE_RE.search(first_line):
        issues.append(
            Issue(
                "FIRST_LINE_NOT_CONCRETE",
                "1行目に数字・3字以上のカタカナ語・具体的な単位がありません。具体性を確認してください。",
                context,
            )
        )
    if (
        first_line.startswith("今日は")
        or first_line.startswith("みなさん")
        or first_line.endswith("今日は")
        or first_line.endswith("みなさん")
        or first_line.endswith("な人は聞いて")
        or first_line.endswith("な人へ")
    ):
        issues.append(
            Issue(
                "FIRST_LINE_VAGUE_PATTERN",
                "1行目が曖昧になりやすい型です。読者が続きを読みたくなる具体性を確認してください。",
                context,
            )
        )
    return issues


def check_threads(path: Path, settings: Optional[Path]) -> Tuple[Dict[str, Any], int]:
    text = read_text(path)
    posts = split_thread_posts(text)
    if not posts:
        raise InputError("検査できる投稿本文がありません。")
    prohibited = read_prohibited_terms(settings)
    voice_settings = read_voice_settings(settings)
    violations: List[Issue] = []
    reviews: List[Issue] = []
    post_summaries: List[Dict[str, Any]] = []

    for post_number, post in enumerate(posts, start=1):
        part_summaries = []
        for part_number, part in enumerate(post.parts, start=1):
            characters = part.character_count
            part_summaries.append({"part": part_number, "chars": characters})
            if characters > 500:
                violations.append(
                    Issue(
                        "PART_TOO_LONG",
                        f"投稿{post_number}のパート{part_number}が{characters}字です。500字以内でツリーに分けてください。",
                        {"post": post_number, "part": part_number, "chars": characters, "limit": 500},
                    )
                )
        first_line = first_content_line(post)
        reviews.extend(first_line_review_issues(first_line, post_number))
        context = {"post": post_number}
        visible_lines = visible_source_lines(post.source_lines)
        reviews.extend(verify_fact_review_issues(visible_lines, context))
        reviews.extend(fuzzy_review_issues(visible_lines, context))
        if settings is not None:
            reviews.extend(voice_review_issues(visible_lines, voice_settings, context))
        violations.extend(repeated_ending_issues(post.text, context))
        violations.extend(
            term_issues(
                post.text,
                EXAGGERATIONS,
                "EXAGGERATION",
                "誇大表現「{term}」が含まれています。事実に沿う表現へ直してください。",
                context,
            )
        )
        violations.extend(
            term_issues(
                post.text,
                prohibited,
                "PROHIBITED_TERM",
                "設定で禁止した言葉「{term}」が含まれています。直してください。",
                context,
            )
        )
        post_summaries.append(
            {
                "post": post_number,
                "first_line": first_line,
                "emoji_count": count_emoji(post.text),
                "parts": part_summaries,
            }
        )

    result = {
        "command": "threads",
        "file": str(path),
        "ok": not violations,
        "violations": [issue.as_dict() for issue in violations],
        "review_candidates": [issue.as_dict() for issue in reviews],
        "posts": post_summaries,
        "summary": {
            "post_count": len(posts),
            "violation_count": len(violations),
            "review_candidate_count": len(reviews),
        },
    }
    return result, 1 if violations else 0


LIST_OR_TABLE_LINE_RE = re.compile(r"^(\||[-*・]\s|\d+[.)．]\s)")


def article_sentences(text: str) -> List[str]:
    """本文を文に分ける。表の行・箇条書きの行は、句点が無くても1行を1つの単位にする。"""
    sentences: List[str] = []
    body_lines: List[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == PAID_MARKER or re.match(r"^#{1,6}\s+", stripped):
            continue
        if LIST_OR_TABLE_LINE_RE.match(stripped):
            # 表や箇条書きの行は、前後の文とつなげずに、その行だけで数える
            if body_lines:
                sentences.extend(split_sentences("\n".join(body_lines)))
                body_lines = []
            if not re.fullmatch(r"\|?[\s:|-]+\|?", stripped):  # 表の区切り行は数えない
                sentences.extend(split_sentences(stripped))
            continue
        body_lines.append(line)
    if body_lines:
        sentences.extend(split_sentences("\n".join(body_lines)))
    return sentences


def check_note(
    path: Path,
    settings: Optional[Path],
    target_chars: Optional[int],
) -> Tuple[Dict[str, Any], int]:
    original = read_text(path)
    text = remove_html_comments(original)
    prohibited = read_prohibited_terms(settings)
    voice_settings = read_voice_settings(settings)
    violations: List[Issue] = []
    reviews: List[Issue] = []

    lines = text.splitlines()
    source_lines = list(enumerate(lines, start=1))
    marker_indexes = [index for index, line in enumerate(lines) if line.strip() == PAID_MARKER]
    if marker_indexes:
        marker_index = marker_indexes[0]
        free_text = "\n".join(lines[:marker_index])
        paid_text = "\n".join(lines[marker_index + 1 :])
        has_paid_marker = True
    else:
        free_text = text
        paid_text = ""
        has_paid_marker = False
        reviews.append(
            Issue(
                "PAID_MARKER_MISSING",
                "有料ラインがありません。無料記事なら問題ありません。",
                {},
            )
        )
    free_chars = count_without_newlines(free_text)
    paid_chars = count_without_newlines(paid_text)
    total_chars = count_without_newlines("\n".join(line for line in lines if line.strip() != PAID_MARKER))

    h1_count = len(HEADING_ONE_RE.findall(text))
    h2_count = len(HEADING_TWO_RE.findall(text))
    if h1_count != 1:
        violations.append(
            Issue(
                "H1_COUNT",
                f"記事タイトル（# 見出し）は1つ必要です。現在は{h1_count}個です。",
                {"count": h1_count, "expected": 1},
            )
        )
    if h2_count < 2:
        violations.append(
            Issue(
                "H2_COUNT",
                f"章見出し（## 見出し）は2つ以上必要です。現在は{h2_count}個です。",
                {"count": h2_count, "minimum": 2},
            )
        )

    if target_chars is not None:
        if target_chars <= 0:
            raise InputError("target-chars は1以上で指定してください。")
        minimum = target_chars * 0.85
        maximum = target_chars * 1.15
        if total_chars < minimum or total_chars > maximum:
            reviews.append(
                Issue(
                    "TARGET_CHARS_OUTSIDE",
                    f"合計{total_chars}字で、目標{target_chars}字の±15%から外れています。",
                    {"chars": total_chars, "target": target_chars, "minimum": minimum, "maximum": maximum},
                )
            )

    cta_lines = [
        {"line": index, "text": line.strip()}
        for index, line in enumerate(lines, start=1)
        if any(term in line for term in CTA_TERMS)
    ]
    action_lines = [
        index
        for index, line in enumerate(lines, start=1)
        if any(term in line for term in ACTION_CTA_TERMS)
    ]
    if not cta_lines and action_lines:
        # LINE などの行き先が無い案件では、次の行動を促す一文を CTA として扱う
        reviews.append(
            Issue(
                "CTA_ACTION_ONLY",
                "LINE・フォロー・購入などの行き先の案内はありませんが、次の行動を促す文があります。"
                "行き先が無い案件ならこのままでよいか確認してください。",
                {"count": len(action_lines), "lines": action_lines[:5]},
            )
        )
    elif not cta_lines:
        violations.append(
            Issue(
                "CTA_MISSING",
                "CTA（LINE・フォロー・購入などの案内、または次の行動を促す文）がありません。案内を追加してください。",
                {"count": 0},
            )
        )
    elif len(cta_lines) == 1:
        reviews.append(
            Issue(
                "CTA_ONE_LINE",
                "CTA が1行だけです。本編途中と末尾の2段が必要か確認してください。",
                {"count": 1, "line": cta_lines[0]["line"]},
            )
        )

    for sentence_number, sentence in enumerate(article_sentences(text), start=1):
        characters = count_without_newlines(sentence)
        if characters > 60:
            reviews.append(
                Issue(
                    "LONG_SENTENCE",
                    f"{sentence_number}文目が{characters}字です。60字以内に分けられるか確認してください。",
                    {"sentence": sentence_number, "chars": characters},
                )
            )

    violations.extend(repeated_ending_issues(text, {}))
    violations.extend(
        term_issues(
            text,
            EXAGGERATIONS,
            "EXAGGERATION",
            "誇大表現「{term}」が含まれています。事実に沿う表現へ直してください。",
            {},
        )
    )
    violations.extend(
        term_issues(
            text,
            prohibited,
            "PROHIBITED_TERM",
            "設定で禁止した言葉「{term}」が含まれています。直してください。",
            {},
        )
    )
    reviews.extend(verify_fact_review_issues(source_lines, {}))
    reviews.extend(fuzzy_review_issues(source_lines, {}))
    if settings is not None:
        # note の改行は Threads と違うことがあるため、設定の「note の改行」を使う。
        # 空の時は Threads の改行の癖を note に当てはめず、確かめるよう目視候補を1件だけ出す。
        note_voice = VoiceSettings(
            line_break=voice_settings.note_line_break,
            emoji=voice_settings.emoji,
            first_person=voice_settings.first_person,
            note_line_break=voice_settings.note_line_break,
        )
        reviews.extend(voice_review_issues(source_lines, note_voice, {}))
        if not voice_settings.note_line_break and voice_settings.line_break:
            reviews.append(
                Issue(
                    "VOICE_NOTE_LINE_BREAK_UNSET",
                    "設定に「note の改行」がありません。Threads の改行の癖"
                    f"（{voice_settings.line_break}）を note にも使うか、本人に確かめてください。",
                    {"kind": "voice", "threads_line_break": voice_settings.line_break},
                )
            )

    result = {
        "command": "note",
        "file": str(path),
        "ok": not violations,
        "violations": [issue.as_dict() for issue in violations],
        "review_candidates": [issue.as_dict() for issue in reviews],
        "paid_line": {
            "present": has_paid_marker,
            "free_chars": free_chars,
            "paid_chars": paid_chars,
        },
        "headings": {"h1": h1_count, "h2": h2_count},
        "cta": {"line_count": len(cta_lines), "lines": cta_lines},
        "total_chars": total_chars,
        "summary": {
            "violation_count": len(violations),
            "review_candidate_count": len(reviews),
        },
    }
    return result, 1 if violations else 0


# --- 市場の言葉の確かめ（--market） ---
# 1行目（note は題と見出し）を句読点で分け、4字以上の句が、受講生が集めた伸びた投稿に1本も出ない時に目視候補にする。
# 集めた投稿の読み方は tn_kb.py の market-count と同じ関数を使う（本数がずれないように）。

MARKET_PHRASE_SPLIT_RE = re.compile(r"[、。！？!?\n]+")
MARKET_PHRASE_MIN_CHARS = 4
MARKET_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")


def load_market_module() -> Any:
    """同じフォルダの tn_kb.py を読む。受講生のフォルダに __pycache__ を作らない。"""
    sys.dont_write_bytecode = True
    directory = str(Path(__file__).resolve().parent)
    if directory not in sys.path:
        sys.path.insert(0, directory)
    import tn_kb  # noqa: E402

    return tn_kb


def market_phrases(line: str) -> List[str]:
    phrases: List[str] = []
    for piece in MARKET_PHRASE_SPLIT_RE.split(line):
        characters = list(piece.strip())
        # 句の前後のかっこ・記号・絵文字は外して数える
        while characters and unicodedata.category(characters[0])[0] in ("P", "S", "Z"):
            characters.pop(0)
        while characters and unicodedata.category(characters[-1])[0] in ("P", "S", "Z"):
            characters.pop()
        phrase = "".join(characters).strip()
        if len("".join(phrase.split())) >= MARKET_PHRASE_MIN_CHARS:
            phrases.append(phrase)
    return phrases


def market_targets(command: str, path: Path) -> List[Tuple[Dict[str, Any], str, str]]:
    """（場所の情報, 場所の言い方, 調べる行）の一覧。Threads は各投稿の1行目、note は題と見出し。"""
    targets: List[Tuple[Dict[str, Any], str, str]] = []
    text = read_text(path)
    if command == "threads":
        for post_number, post in enumerate(split_thread_posts(text), start=1):
            visible = visible_source_lines(post.parts[0].source_lines)
            first = next(((number, line.strip()) for number, line in visible if line.strip()), None)
            if first is not None:
                targets.append(
                    ({"post": post_number, "line": first[0]}, f"投稿{post_number}の1行目（{first[0]}行目）", first[1])
                )
        return targets
    for line_number, line in enumerate(remove_html_comments(text).splitlines(), start=1):
        match = MARKET_HEADING_RE.match(line.strip())
        if match and match.group(2).strip():
            label = "題" if len(match.group(1)) == 1 else "見出し"
            targets.append(({"line": line_number, "heading_level": len(match.group(1))}, f"{line_number}行目の{label}", match.group(2).strip()))
    return targets


def people_text(tn_kb: Any, counted: Dict[str, Any]) -> str:
    return tn_kb.authors_text(counted["authors"], int(counted["authors_unknown_posts"]))


def market_review(command: str, path: Path, directory: Path) -> Tuple[List[Issue], Dict[str, Any]]:
    tn_kb = load_market_module()
    try:
        posts, summary = tn_kb.load_market_posts(directory)
    except tn_kb.InputError as exc:
        raise InputError(str(exc)) from exc
    total = int(summary["total"])
    info: Dict[str, Any] = {"directory": str(directory), "posts": total, "checked": False}
    if total < tn_kb.MARKET_MIN_POSTS:
        info["message"] = f"集めた投稿が {total} 本（10本から確かめられます）"
        return [], info
    issues: List[Issue] = []
    phrase_count = 0
    zero_count = 0
    copy_count = 0
    for location, label, line in market_targets(command, path):
        for phrase in market_phrases(line):
            phrase_count += 1
            counted = tn_kb.count_phrase(posts, phrase)
            details = dict(location)
            details.update({"phrase": phrase, "count": counted["posts"], "market_posts": total})
            if not counted["posts"]:
                zero_count += 1
                longest = counted["longest"]
                details.update({"kind": "market", "longest": longest})
                if longest:
                    guide = (
                        f"この中で集めた投稿にある一番長い並びは「{longest['phrase']}」"
                        f"（{longest['posts']}本・{people_text(tn_kb, longest)}）です。"
                        f"その並びが市場の言い回しで、残りが題材・本人の言葉なら「形 {longest['posts']}本＋中身」と記録して残し、"
                        "そうでなければ市場にある言い方の形に直してください（market-words.md §7・pipeline.md 段6d）。"
                    )
                else:
                    guide = (
                        "4字以上の並びも0本です。市場にある言い方の形に直すか、本人の言葉・題材なら理由を1行残してください"
                        "（market-words.md §7・pipeline.md 段6d）。"
                    )
                issues.append(Issue("MARKET", f"{label}の句「{phrase}」: この句は集めた投稿（{total}本）に0本です。{guide}", details))
                continue
            # 長い句が、1〜2人（書き手が分からない時は1〜2本）の投稿にしか出ない時は、1人の文の写しに近い
            # 決まりは market-words の表と同じ（tn_kb.py の MARKET_COPY_MIN_CHARS・MARKET_COPY_MAX_PEOPLE）
            people = (counted["authors"] or 0) + int(counted["authors_unknown_posts"])
            if len(tn_kb.compact_text(phrase)) >= tn_kb.MARKET_COPY_MIN_CHARS and people <= tn_kb.MARKET_COPY_MAX_PEOPLE:
                copy_count += 1
                if counted["authors"] is None:
                    copy_amount = f"{counted['posts']}本（書き手は不明）"
                else:
                    copy_amount = f"{counted['posts']}本・{people_text(tn_kb, counted)}"
                details.update({"kind": "market-copy", "authors": counted["authors"], "authors_unknown_posts": counted["authors_unknown_posts"]})
                issues.append(
                    Issue(
                        "MARKET_COPY",
                        f"{label}の句「{phrase}」: この句は集めた投稿に {copy_amount}だけです。"
                        "1人の文の写しに近いので、3人以上が使う言い回しの形に替えるか、本人の言葉なら理由を1行残してください"
                        "（market-words.md §8）。",
                        details,
                    )
                )
    info.update({"checked": True, "phrases": phrase_count, "zero_phrases": zero_count, "copy_phrases": copy_count})
    info["message"] = (
        f"集めた投稿 {total}本で、句 {phrase_count}個を数えました（0本の句 {zero_count}個・写しに近い句 {copy_count}個）"
    )
    return issues, info


TEHON_COPY_MIN_CHARS = 12
TEHON_LENGTH_MAX_RATIO = 1.10


def compact_body_for_tehon(text: str) -> str:
    """見出し・区切り・空白を除いた本文文字列を返す。"""
    cleaned = remove_html_comments(text)
    pieces: List[str] = []
    for raw in cleaned.splitlines():
        s = raw.strip()
        if not s or s == "---" or s.startswith("#"):
            continue
        if s.startswith("## 提出メモ"):
            break
        pieces.append("".join(s.split()))
    return "".join(pieces)


def longest_common_substrings(source: str, reference: str, min_len: int = TEHON_COPY_MIN_CHARS) -> List[str]:
    """source と reference の両方に現れる min_len 文字以上の極大共通部分文字列を返す。"""
    if len(source) < min_len or len(reference) < min_len:
        return []
    found: List[str] = []
    i = 0
    while i <= len(source) - min_len:
        chunk = source[i : i + min_len]
        if chunk in reference:
            end = i + min_len
            while end < len(source) and source[i : end + 1] in reference:
                end += 1
            hit = source[i:end]
            if hit not in found:
                found.append(hit)
            i = end
        else:
            i += 1
    return found


def is_market_idiom_3plus(tn_kb: Any, market_posts: Sequence[Any], phrase: str) -> bool:
    if not market_posts:
        return False
    counted = tn_kb.count_phrase(market_posts, phrase)
    if not counted["posts"]:
        return False
    if counted["authors"] is None:
        return int(counted["posts"]) >= 3
    return int(counted["authors"]) >= 3


def tehon_review(
    command: str,
    path: Path,
    tehon_path: Path,
    market_dir: Optional[Path] = None,
) -> Tuple[List[Issue], Dict[str, Any]]:
    tehon_raw = read_text(tehon_path)
    tehon_compact = compact_body_for_tehon(tehon_raw)
    tehon_chars = len(tehon_compact)
    if tehon_chars == 0:
        raise InputError(f"手本ファイルに本文がありません: {tehon_path}")

    tn_kb: Any = None
    market_posts: Sequence[Any] = ()
    if market_dir is not None and market_dir.exists():
        tn_kb = load_market_module()
        try:
            market_posts, _ = tn_kb.load_market_posts(market_dir)
        except Exception:
            market_posts = ()

    issues: List[Issue] = []
    text = read_text(path)
    copy_hits_total = 0
    idiom_skipped = 0
    over_length_count = 0

    if command == "threads":
        posts = split_thread_posts(text)
        for post_number, post in enumerate(posts, start=1):
            post_body = "".join(
                "".join(ln.strip().split())
                for part in post.parts
                for _, ln in visible_source_lines(part.source_lines)
                if ln.strip()
            )
            post_chars = sum(
                count_without_newlines("\n".join(ln for _, ln in visible_source_lines(part.source_lines)))
                for part in post.parts
            )
            hits = longest_common_substrings(post_body, tehon_compact, TEHON_COPY_MIN_CHARS)
            for hit in hits:
                if tn_kb is not None and is_market_idiom_3plus(tn_kb, market_posts, hit):
                    idiom_skipped += 1
                    continue
                copy_hits_total += 1
                issues.append(
                    Issue(
                        "TEHON_COPY",
                        f"投稿{post_number}: 手本と{len(hit)}字一致しています（「{hit}」）。"
                        "3人以上が使う決まり文句でなければ、中身や自分の言い方に替えてください（market-words.md §6・§8）。",
                        {"post": post_number, "phrase": hit, "length": len(hit)},
                    )
                )
            limit_chars = int(tehon_chars * TEHON_LENGTH_MAX_RATIO)
            if post_chars > limit_chars:
                over_length_count += 1
                issues.append(
                    Issue(
                        "TEHON_LENGTH",
                        f"投稿{post_number}: {post_chars}字で、手本（{tehon_chars}字）の1.1倍（{limit_chars}字）を超えています。"
                        "直しで説明が増えていないか見直し、手本の字数に近づけてください（pipeline.md 段2・段8）。",
                        {"post": post_number, "chars": post_chars, "tehon_chars": tehon_chars, "limit_chars": limit_chars},
                    )
                )
    else:
        body_compact = compact_body_for_tehon(text)
        body_chars = len(body_compact)
        for hit in longest_common_substrings(body_compact, tehon_compact, TEHON_COPY_MIN_CHARS):
            if tn_kb is not None and is_market_idiom_3plus(tn_kb, market_posts, hit):
                idiom_skipped += 1
                continue
            copy_hits_total += 1
            issues.append(
                Issue(
                    "TEHON_COPY",
                    f"手本と{len(hit)}字一致しています（「{hit}」）。"
                    "3人以上が使う決まり文句でなければ、自分の言い方に替えてください（market-words.md §6・§8）。",
                    {"phrase": hit, "length": len(hit)},
                )
            )
        limit_chars = int(tehon_chars * TEHON_LENGTH_MAX_RATIO)
        if body_chars > limit_chars:
            over_length_count += 1
            issues.append(
                Issue(
                    "TEHON_LENGTH",
                    f"本文が{body_chars}字で、手本（{tehon_chars}字）の1.1倍（{limit_chars}字）を超えています。"
                    "手本の字数に近づけてください（pipeline.md 段2・段8）。",
                    {"chars": body_chars, "tehon_chars": tehon_chars, "limit_chars": limit_chars},
                )
            )

    info: Dict[str, Any] = {
        "tehon": str(tehon_path),
        "tehon_chars": tehon_chars,
        "copy_hits": copy_hits_total,
        "idiom_skipped": idiom_skipped,
        "over_length": over_length_count,
        "message": (
            f"手本（{tehon_chars}字）と照合しました（12字以上の一致 {copy_hits_total}件・"
            f"決まり文句除外 {idiom_skipped}件・字数超過 {over_length_count}件）"
        ),
    }
    return issues, info


def print_human_result(result: Dict[str, Any]) -> None:
    label = "Threads" if result["command"] == "threads" else "note"
    print(f"{label} の検査結果")
    print(f"違反（直す）: {len(result['violations'])}件")
    if result["violations"]:
        for issue in result["violations"]:
            print(f"- [{issue['code']}] {issue['message']}")
    else:
        print("- ありません")
    print(f"目視候補（人が判断）: {len(result['review_candidates'])}件")
    if result["review_candidates"]:
        for issue in result["review_candidates"]:
            print(f"- [{issue['code']}] {issue['message']}")
    else:
        print("- ありません")

    if result["command"] == "threads":
        print("投稿ごとの文字数・絵文字数:")
        for post in result["posts"]:
            parts = " / ".join(f"パート{item['part']}: {item['chars']}字" for item in post["parts"])
            print(f"- 投稿{post['post']}: {parts} / 絵文字 {post['emoji_count']}個")
    else:
        paid = result["paid_line"]
        paid_status = "あり" if paid["present"] else "なし"
        print(f"有料ライン: {paid_status}（前 {paid['free_chars']}字 / 後 {paid['paid_chars']}字）")
        print(
            f"合計: {result['total_chars']}字 / # 見出し {result['headings']['h1']}個 / "
            f"## 見出し {result['headings']['h2']}個 / CTA {result['cta']['line_count']}行"
        )
    if "market" in result:
        print(f"市場の言葉の確かめ: {result['market']['message']}")
    if "tehon" in result:
        print(f"手本との照合: {result['tehon']['message']}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Threads 投稿と note 原稿を、機械違反と目視候補に分けて検査します。"
    )
    subparsers = parser.add_subparsers(dest="command", required=True, metavar="コマンド")

    threads_parser = subparsers.add_parser("threads", help="Threads 投稿を検査する")
    threads_parser.add_argument("file", type=Path, metavar="FILE", help="検査する UTF-8 ファイル")
    threads_parser.add_argument("--settings", type=Path, help="00_わたしの設定.md")
    threads_parser.add_argument("--json", action="store_true", help="JSON で表示する")
    threads_parser.add_argument("--market", type=Path, metavar="DIR", help="マイナレッジ（集めた投稿で1行目の句を数える）")
    threads_parser.add_argument("--tehon", type=Path, metavar="FILE", help="手本にした投稿の原文ファイル（12字一致と字数比を検査する）")

    note_parser = subparsers.add_parser("note", help="note 原稿を検査する")
    note_parser.add_argument("file", type=Path, metavar="FILE", help="検査する UTF-8 ファイル")
    note_parser.add_argument("--target-chars", type=int, help="目標字数")
    note_parser.add_argument("--settings", type=Path, help="00_わたしの設定.md")
    note_parser.add_argument("--json", action="store_true", help="JSON で表示する")
    note_parser.add_argument("--market", type=Path, metavar="DIR", help="マイナレッジ（集めた投稿で題と見出しの句を数える）")
    note_parser.add_argument("--tehon", type=Path, metavar="FILE", help="手本にした記事の原文ファイル（12字一致と字数比を検査する）")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "threads":
            result, exit_code = check_threads(args.file, args.settings)
        else:
            result, exit_code = check_note(args.file, args.settings, args.target_chars)
        if args.market is not None:
            market_issues, market_info = market_review(args.command, args.file, args.market)
            result["review_candidates"].extend(issue.as_dict() for issue in market_issues)
            result["summary"]["review_candidate_count"] = len(result["review_candidates"])
            result["market"] = market_info
        if args.tehon is not None:
            tehon_issues, tehon_info = tehon_review(args.command, args.file, args.tehon, args.market)
            result["review_candidates"].extend(issue.as_dict() for issue in tehon_issues)
            result["summary"]["review_candidate_count"] = len(result["review_candidates"])
            result["tehon"] = tehon_info
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print_human_result(result)
        return exit_code
    except InputError as exc:
        eprint(f"入力エラー: {exc}")
        return 2
    except OSError as exc:
        eprint(f"入力エラー: ファイルまたはフォルダを操作できません（{exc}）")
        return 2


if __name__ == "__main__":
    sys.exit(main())
