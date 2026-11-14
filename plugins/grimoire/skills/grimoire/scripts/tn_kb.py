#!/usr/bin/env python3
"""ティルナノーグのマイナレッジを操作する標準ライブラリ製 CLI。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import unicodedata
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple


KINDS: Tuple[str, ...] = ("example", "principle", "procedure", "ng", "metric")
SOURCES: Tuple[str, ...] = ("講師FB", "セミナー", "実績", "自分の手直し", "エンジン")
CONFIDENCES: Tuple[str, ...] = ("講師明言", "実測", "推測")
STATUSES: Tuple[str, ...] = ("active", "superseded")
STAGES: Tuple[str, ...] = (
    "setup",
    "threads-hook",
    "threads-body",
    "threads-cta",
    "threads-tree",
    "threads-plan",
    "note-title",
    "note-intro",
    "note-structure",
    "note-paid-line",
    "note-body",
    "note-cta",
    "launch",
    "evergreen",
    "account",
    "review",
    "voice",
)
CONFIDENCE_RANK = {name: rank for rank, name in enumerate(reversed(CONFIDENCES), start=1)}
CARD_ID_RE = re.compile(r"^C-(\d{8})-(\d{3,})$")
FORMAT_VERSION = "1"
REQUIRED_DIRS: Tuple[str, ...] = (
    "10_お手本",
    "20_講師FB",
    "30_セミナー",
    "40_実績",
    "カード",
)
REQUIRED_FILES: Dict[str, str] = {
    "00_わたしの設定.md": "",
    "索引.md": "自動生成・手で書き換えないでください。\n",
    "育成ログ.md": "",
}
FIELD_ORDER: Tuple[str, ...] = (
    "id",
    "title",
    "kind",
    "stages",
    "source",
    "source_ref",
    "said_by",
    "date",
    "confidence",
    "status",
    "superseded_by",
    "strength",
)
EXPORT_TOP_LEVEL_FILES: Tuple[str, ...] = (
    "00_わたしの設定.md",
    "索引.md",
    "育成ログ.md",
)
EXPORT_DIRECTORIES: Tuple[str, ...] = (
    "カード",
    "10_お手本",
    "20_講師FB",
    "30_セミナー",
    "40_実績",
)
SUMMARY_TITLE = "# マイナレッジ_まとめ"
SUMMARY_FILE_MARKER_RE = re.compile(r"^<!-- tirnanog:file (.+) -->$")
SUMMARY_END_MARKER = "<!-- tirnanog:end -->"


class InputError(Exception):
    """利用者が直せる入力エラー。"""


@dataclass
class Card:
    path: Path
    fields: Dict[str, str]
    body: str

    def value(self, key: str, default: str = "") -> str:
        return scalar_value(self.fields.get(key, default))

    @property
    def card_id(self) -> str:
        return self.value("id")

    @property
    def title(self) -> str:
        return self.value("title")

    @property
    def kind(self) -> str:
        return self.value("kind")

    @property
    def confidence(self) -> str:
        return self.value("confidence")

    @property
    def status(self) -> str:
        return self.value("status", "active") or "active"

    @property
    def strength(self) -> int:
        raw = self.value("strength", "1") or "1"
        try:
            value = int(raw)
        except ValueError as exc:
            raise InputError(f"{self.path}: strength は整数で書いてください（現在: {raw}）") from exc
        if value < 0:
            raise InputError(f"{self.path}: strength は0以上で書いてください（現在: {raw}）")
        return value

    @property
    def stages(self) -> List[str]:
        return parse_stages_value(self.fields.get("stages", ""), self.path)

    @property
    def date_value(self) -> date:
        raw = self.value("date")
        if not raw:
            return date.min
        return parse_iso_date(raw, f"{self.path}: date")


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


def atomic_write_text(path: Path, text: str) -> None:
    """UTF-8・LFで書き、途中失敗で元ファイルを壊さない。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: Optional[str] = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=str(path.parent),
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary.write(text)
            temporary_name = temporary.name
        os.replace(temporary_name, str(path))
        temporary_name = None
    except OSError as exc:
        raise InputError(f"ファイルを書けません: {path}（{exc}）") from exc
    finally:
        if temporary_name:
            try:
                os.unlink(temporary_name)
            except OSError:
                pass


def scalar_value(raw: str) -> str:
    """簡易 YAML の値から、表示用コメントと外側の引用符を除く。"""
    value = raw.strip()
    if value.startswith('"'):
        try:
            decoded, end = json.JSONDecoder().raw_decode(value)
        except json.JSONDecodeError:
            decoded = None
            end = 0
        remainder = value[end:].strip() if end else value
        if isinstance(decoded, str) and (not remainder or remainder.startswith("#")):
            return decoded
    if value.startswith("'"):
        match = re.fullmatch(r"'(.*)'(?:\s+#.*)?", value)
        if match:
            return match.group(1).replace("''", "'")
    return re.split(r"\s+#", value, maxsplit=1)[0].strip()


def encode_scalar(value: str) -> str:
    """コメントと誤認される値だけ JSON 互換の二重引用符で守る。"""
    if not value or value != value.strip() or re.search(r"\s+#", value) or value[0] in {'"', "'"}:
        return json.dumps(value, ensure_ascii=False)
    return value


def parse_iso_date(value: str, label: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise InputError(f"{label} は YYYY-MM-DD で書いてください（現在: {value}）") from exc


def validate_header_text(value: str, label: str) -> str:
    if not value.strip():
        raise InputError(f"{label} は空にできません。")
    if "\n" in value or "\r" in value:
        raise InputError(f"{label} は1行で入力してください。")
    return value.strip()


def parse_stages_argument(raw: str) -> List[str]:
    stages: List[str] = []
    for item in raw.split(","):
        stage = item.strip()
        if stage and stage not in stages:
            stages.append(stage)
    if not stages:
        raise InputError("stages を1つ以上、カンマ区切りで指定してください。")
    invalid = [stage for stage in stages if stage not in STAGES]
    if invalid:
        raise vocabulary_error("stages", invalid, STAGES)
    return stages


def parse_stages_value(raw: str, path: Path) -> List[str]:
    value = scalar_value(raw)
    if not (value.startswith("[") and value.endswith("]")):
        raise InputError(f"{path}: stages は [a, b] の1行リストで書いてください。")
    inner = value[1:-1].strip()
    if not inner:
        return []
    stages = [scalar_value(item) for item in inner.split(",")]
    invalid = [stage for stage in stages if stage not in STAGES]
    if invalid:
        raise vocabulary_error(f"{path}: stages", invalid, STAGES)
    return stages


def vocabulary_error(label: str, invalid: Sequence[str], allowed: Sequence[str]) -> InputError:
    bad = "、".join(invalid)
    choices = "、".join(allowed)
    return InputError(f"{label} に使えない値があります: {bad}\n使える値: {choices}")


def parse_card(path: Path) -> Card:
    text = read_text(path)
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise InputError(f"{path}: 先頭の frontmatter 開始行（---）がありません。")
    closing = None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            closing = index
            break
    if closing is None:
        raise InputError(f"{path}: frontmatter の終了行（---）がありません。")

    fields: Dict[str, str] = {}
    for line_number, line in enumerate(lines[1:closing], start=2):
        if not line.strip():
            continue
        if ":" not in line:
            raise InputError(f"{path}:{line_number}: frontmatter は「項目: 値」で書いてください。")
        key, value = line.split(":", 1)
        key = key.strip()
        if not key:
            raise InputError(f"{path}:{line_number}: frontmatter の項目名が空です。")
        if key in fields:
            raise InputError(f"{path}:{line_number}: frontmatter の項目「{key}」が重複しています。")
        fields[key] = value.strip()

    body = "\n".join(lines[closing + 1 :]).strip("\n")
    card = Card(path=path, fields=fields, body=body)
    validate_card(card)
    return card


def validate_card(card: Card) -> None:
    for required in FIELD_ORDER:
        if required not in card.fields:
            raise InputError(f"{card.path}: frontmatter の「{required}」がありません。")
    for required in ("id", "title", "kind", "stages", "source", "source_ref", "said_by", "date", "confidence", "status", "strength"):
        if not card.value(required):
            raise InputError(f"{card.path}: frontmatter の「{required}」が空です。")
    if not CARD_ID_RE.fullmatch(card.card_id):
        raise InputError(f"{card.path}: id は C-YYYYMMDD-NNN 形式で書いてください。")
    if card.kind not in KINDS:
        raise vocabulary_error(f"{card.path}: kind", [card.kind], KINDS)
    source = card.value("source")
    if source not in SOURCES:
        raise vocabulary_error(f"{card.path}: source", [source], SOURCES)
    if card.confidence not in CONFIDENCES:
        raise vocabulary_error(f"{card.path}: confidence", [card.confidence], CONFIDENCES)
    if card.status not in STATUSES:
        raise vocabulary_error(f"{card.path}: status", [card.status], STATUSES)
    card.stages
    card.strength
    card.date_value


def serialize_card(card: Card) -> str:
    ordered_keys: List[str] = []
    for key in FIELD_ORDER:
        if key in card.fields:
            ordered_keys.append(key)
    ordered_keys.extend(key for key in card.fields if key not in ordered_keys)
    header = ["---"]
    header.extend(f"{key}: {card.fields[key]}" for key in ordered_keys)
    header.append("---")
    text = "\n".join(header) + "\n"
    if card.body:
        text += "\n" + card.body.rstrip("\n") + "\n"
    return text


def write_card(card: Card) -> None:
    atomic_write_text(card.path, serialize_card(card))


def cards_directory(root: Path) -> Path:
    return root / "カード"


def load_cards(root: Path) -> List[Card]:
    directory = cards_directory(root)
    if not directory.exists():
        return []
    if not directory.is_dir():
        raise InputError(f"カードの保存先がフォルダではありません: {directory}")
    cards = [parse_card(path) for path in sorted(directory.glob("*.md"), key=lambda item: item.name)]
    seen: Dict[str, Path] = {}
    for card in cards:
        if card.path.stem != card.card_id:
            raise InputError(f"ファイル名とカード内の id が一致しません: {card.path}")
        if card.card_id in seen:
            raise InputError(f"同じカードIDが複数あります: {card.card_id}（{seen[card.card_id]} / {card.path}）")
        seen[card.card_id] = card.path
    return cards


def card_by_id(root: Path, card_id: str) -> Card:
    if not CARD_ID_RE.fullmatch(card_id):
        raise InputError("カードIDは C-YYYYMMDD-NNN 形式で指定してください。")
    path = cards_directory(root) / f"{card_id}.md"
    card = parse_card(path)
    if card.card_id != card_id:
        raise InputError(f"ファイル名とカード内の id が一致しません: {path}")
    return card


def card_sort_key(card: Card) -> Tuple[int, int, int, str]:
    return (
        -card.strength,
        -CONFIDENCE_RANK[card.confidence],
        -card.date_value.toordinal(),
        card.card_id,
    )


def sort_cards(cards: Iterable[Card]) -> List[Card]:
    return sorted(cards, key=card_sort_key)


def copy_template(template: Path, destination: Path) -> Tuple[int, List[Path]]:
    created = 0
    skipped: List[Path] = []
    if template.is_symlink():
        raise InputError(f"テンプレートにシンボリックリンクは使えません: {template}")
    for source in sorted(template.rglob("*"), key=lambda item: item.as_posix()):
        relative = source.relative_to(template)
        target = destination / relative
        if source.is_symlink():
            raise InputError(f"テンプレートにシンボリックリンクは使えません: {source}")
        if source.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        if target.exists():
            skipped.append(target)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(str(source), str(target))
        except OSError as exc:
            raise InputError(f"テンプレートをコピーできません: {source} → {target}（{exc}）") from exc
        created += 1
    return created, skipped


def command_init(args: argparse.Namespace) -> int:
    root: Path = args.directory
    if root.exists() and not root.is_dir():
        raise InputError(f"作成先がフォルダではありません: {root}")
    root.mkdir(parents=True, exist_ok=True)

    explicit_template = args.template is not None
    template = args.template or (Path(__file__).resolve().parent.parent / "assets" / "my-knowledge-template")
    created = 0
    skipped: List[Path] = []
    if template.exists():
        if not template.is_dir():
            raise InputError(f"テンプレートがフォルダではありません: {template}")
        copied, skipped = copy_template(template, root)
        created += copied
    elif explicit_template:
        raise InputError(f"指定したテンプレートが見つかりません: {template}")
    else:
        print(f"警告: 雛形が見つからないため、最小構成を作ります: {template}")

    for directory_name in REQUIRED_DIRS:
        directory = root / directory_name
        if not directory.exists():
            directory.mkdir(parents=True, exist_ok=True)
            created += 1
        elif not directory.is_dir():
            raise InputError(f"必要なフォルダと同名のファイルがあります: {directory}")

    format_path = root / ".tirnanog-format"
    if not format_path.exists():
        atomic_write_text(format_path, FORMAT_VERSION + "\n")
        created += 1
    elif not format_path.is_file():
        raise InputError(f"形式ファイルが通常のファイルではありません: {format_path}")

    for filename, initial_text in REQUIRED_FILES.items():
        path = root / filename
        if not path.exists():
            atomic_write_text(path, initial_text)
            created += 1
        elif not path.is_file():
            raise InputError(f"必要なファイルと同名のフォルダがあります: {path}")

    for path in skipped:
        print(f"スキップ（既存ファイルを保持）: {path}")
    print(f"マイナレッジを準備しました: {root}（新規 {created} 件、スキップ {len(skipped)} 件）")
    return 0


def next_card_id(root: Path, card_date: date) -> str:
    prefix = f"C-{card_date.strftime('%Y%m%d')}-"
    highest = 0
    directory = cards_directory(root)
    if directory.exists():
        for path in directory.glob(f"{prefix}*.md"):
            match = CARD_ID_RE.fullmatch(path.stem)
            if match:
                highest = max(highest, int(match.group(2)))
    return f"{prefix}{highest + 1:03d}"


def command_add_card(args: argparse.Namespace) -> int:
    if args.kind not in KINDS:
        raise vocabulary_error("kind", [args.kind], KINDS)
    if args.source not in SOURCES:
        raise vocabulary_error("source", [args.source], SOURCES)
    if args.confidence not in CONFIDENCES:
        raise vocabulary_error("confidence", [args.confidence], CONFIDENCES)
    stages = parse_stages_argument(args.stages)
    card_date = parse_iso_date(args.card_date, "date") if args.card_date else date.today()
    title = validate_header_text(args.title, "title")
    source_ref = validate_header_text(args.source_ref, "source-ref")
    said_by = validate_header_text(args.said_by, "said-by")
    if args.body_file is not None and str(args.body_file) == "-":
        # 一時ファイルを作らずに、標準入力（heredoc など）から本文を受け取る
        body = sys.stdin.read()
    elif args.body_file is not None:
        body = read_text(args.body_file)
    else:
        body = args.body
    if body is None:
        raise InputError("body または body-file のどちらかを指定してください。")

    directory = cards_directory(args.directory)
    directory.mkdir(parents=True, exist_ok=True)
    card_id = next_card_id(args.directory, card_date)
    path = directory / f"{card_id}.md"
    fields: Dict[str, str] = {
        "id": card_id,
        "title": encode_scalar(title),
        "kind": args.kind,
        "stages": f"[{', '.join(stages)}]",
        "source": args.source,
        "source_ref": encode_scalar(source_ref),
        "said_by": encode_scalar(said_by),
        "date": card_date.isoformat(),
        "confidence": args.confidence,
        "status": "active",
        "superseded_by": '""',
        "strength": "1",
    }
    write_card(Card(path=path, fields=fields, body=body.strip("\n")))
    print(f"カードを書きました: {path}")
    print(f"ID: {card_id}")
    return 0


def normalized_characters(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text)
    return "".join(
        character
        for character in normalized
        if unicodedata.category(character)[:1] in {"L", "M", "N"}
    )


def bigrams(text: str) -> Set[str]:
    normalized = normalized_characters(text)
    if not normalized:
        return set()
    if len(normalized) == 1:
        return {normalized}
    return {normalized[index : index + 2] for index in range(len(normalized) - 1)}


def jaccard(left: Set[str], right: Set[str]) -> float:
    union = left | right
    if not union:
        return 0.0
    return len(left & right) / len(union)


def command_similar(args: argparse.Namespace) -> int:
    if args.top <= 0:
        raise InputError("top は1以上で指定してください。")
    query = bigrams(args.text)
    if not query:
        raise InputError("text には文字を入力してください。")
    scored = []
    for card in load_cards(args.directory):
        if card.status != "active":
            continue
        score = jaccard(query, bigrams(card.title + card.body))
        scored.append((score, card))
    scored.sort(key=lambda item: (-item[0], item[1].card_id))
    results = [
        {"id": card.card_id, "score": round(score, 2), "title": card.title}
        for score, card in scored[: args.top]
    ]
    if args.json:
        print(json.dumps({"results": results}, ensure_ascii=False, indent=2))
    elif results:
        for result in results:
            print(f"{result['id']}  {result['score']:.2f}  {result['title']}")
    else:
        print("似た active カードはありません。")
    return 0


def append_source(body: str, source_ref: str) -> str:
    entry = f"- {date.today().isoformat()} {source_ref}"
    lines = body.splitlines()
    heading_index = next((index for index, line in enumerate(lines) if line.strip() == "## 出典"), None)
    if heading_index is None:
        if lines and lines[-1].strip():
            lines.append("")
        lines.extend(["## 出典", "", entry])
        return "\n".join(lines).strip("\n")

    insert_at = len(lines)
    for index in range(heading_index + 1, len(lines)):
        if re.match(r"^##\s+", lines[index]):
            insert_at = index
            break
    if insert_at > heading_index + 1 and lines[insert_at - 1].strip() == "":
        insert_at -= 1
    lines.insert(insert_at, entry)
    return "\n".join(lines).strip("\n")


def command_strengthen(args: argparse.Namespace) -> int:
    source_ref = validate_header_text(args.source_ref, "source-ref")
    if args.confidence is not None and args.confidence not in CONFIDENCES:
        raise vocabulary_error("confidence", [args.confidence], CONFIDENCES)
    card = card_by_id(args.directory, args.card_id)
    card.fields["strength"] = str(card.strength + 1)
    if args.confidence is not None:
        # 新しい出典で確かさが上がった時だけ変える（下げる方向の変更は supersede で新しいカードにする）
        if CONFIDENCE_RANK[args.confidence] < CONFIDENCE_RANK[card.confidence]:
            raise InputError(
                f"確かさを「{card.confidence}」から「{args.confidence}」へ下げることはできません。"
                "内容が変わった時は新しいカードを作って supersede してください。"
            )
        card.fields["confidence"] = args.confidence
    card.body = append_source(card.body, source_ref)
    write_card(card)
    suffix = f"・確かさ「{card.fields['confidence']}」" if args.confidence is not None else ""
    print(f"強さを {card.strength} にしました{suffix}: {card.card_id}")
    return 0


def command_supersede(args: argparse.Namespace) -> int:
    if args.old_id == args.new_id:
        raise InputError("旧カードと更新先に同じIDは指定できません。")
    old_card = card_by_id(args.directory, args.old_id)
    card_by_id(args.directory, args.new_id)
    old_card.fields["status"] = "superseded"
    old_card.fields["superseded_by"] = args.new_id
    write_card(old_card)
    print(f"{args.old_id} を更新済みにしました。更新先: {args.new_id}")
    return 0


def index_line(card: Card) -> str:
    return f"- {card.card_id} {card.title}（{card.kind}・強さ{card.strength}）"


def build_index_text(cards: Sequence[Card]) -> str:
    lines = [
        "# 索引",
        "",
        "自動生成・手で書き換えないでください。カードの本文は `カード/<id>.md` にあります。",
        "",
    ]
    active = [card for card in cards if card.status == "active"]
    if not active:
        lines.append("まだカードがありません。講師のフィードバックやセミナーの文字起こしを AI に渡すと、ここにカードが並びます。")
        lines.append("")
    for stage in STAGES:
        stage_cards = sort_cards(card for card in active if stage in card.stages)
        if not stage_cards:
            continue
        lines.append(f"## {stage}")
        lines.extend(index_line(card) for card in stage_cards)
        lines.append("")

    superseded = sort_cards(card for card in cards if card.status == "superseded")
    if superseded:
        lines.append("## 更新済み（読まない）")
        for card in superseded:
            destination = card.value("superseded_by")
            suffix = f" → {destination}" if destination else ""
            lines.append(index_line(card) + suffix)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def command_index(args: argparse.Namespace) -> int:
    cards = load_cards(args.directory)
    path = args.directory / "索引.md"
    atomic_write_text(path, build_index_text(cards))
    print(f"索引を作り直しました: {path}（カード {len(cards)} 枚）")
    return 0


def table_cell(value: str) -> str:
    return " ".join(value.replace("|", "\\|").splitlines()).strip()


def append_log_row(existing: str, row: str) -> str:
    lines = existing.splitlines()
    header_index = next(
        (
            index
            for index, line in enumerate(lines)
            if all(label in line for label in ("日付", "取り込んだもの", "新規", "強化", "更新", "次に変わること"))
            and line.lstrip().startswith("|")
        ),
        None,
    )
    if header_index is None:
        if lines and lines[-1].strip():
            lines.append("")
        lines.extend(
            [
                "# 育成ログ",
                "",
                "| 日付 | 取り込んだもの | 新規 | 強化 | 更新 | 次に変わること |",
                "|---|---|---:|---:|---:|---|",
                row,
            ]
        )
        return "\n".join(lines).rstrip() + "\n"

    insert_at = header_index + 1
    while insert_at < len(lines) and lines[insert_at].lstrip().startswith("|"):
        insert_at += 1
    lines.insert(insert_at, row)
    return "\n".join(lines).rstrip() + "\n"


def command_log(args: argparse.Namespace) -> int:
    for label, value in (
        ("new", args.new_count),
        ("strengthened", args.strengthened_count),
        ("superseded", args.superseded_count),
    ):
        if value < 0:
            raise InputError(f"{label} は0以上で指定してください。")
    path = args.directory / "育成ログ.md"
    existing = read_text(path) if path.exists() else ""
    row = (
        f"| {date.today().isoformat()} | {table_cell(args.input_text)} | {args.new_count} | "
        f"{args.strengthened_count} | {args.superseded_count} | {table_cell(args.next_text)} |"
    )
    atomic_write_text(path, append_log_row(existing, row))
    print(f"育成ログに追記しました: {path}")
    return 0


def command_select(args: argparse.Namespace) -> int:
    if args.stage not in STAGES:
        raise vocabulary_error("stage", [args.stage], STAGES)
    if args.limit <= 0:
        raise InputError("limit は1以上で指定してください。")
    selected = sort_cards(
        card for card in load_cards(args.directory) if card.status == "active" and args.stage in card.stages
    )[: args.limit]
    results = [
        {"id": card.card_id, "title": card.title, "path": str(card.path)}
        for card in selected
    ]
    if args.json:
        print(json.dumps({"stage": args.stage, "results": results}, ensure_ascii=False, indent=2))
    elif results:
        for result in results:
            print(f"{result['id']}  {result['title']}  {result['path']}")
    else:
        print(f"{args.stage} の active カードはありません。")
    return 0


def recent_log_rows(path: Path) -> List[str]:
    if not path.exists():
        return []
    rows = []
    for line in read_text(path).splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        if "取り込んだもの" in stripped or re.fullmatch(r"\|[\s:|\-]+\|", stripped):
            continue
        rows.append(stripped)
    return rows[-5:]


def command_status(args: argparse.Namespace) -> int:
    cards = load_cards(args.directory)
    status_counts = Counter(card.status for card in cards)
    kind_counts = Counter(card.kind for card in cards)
    stage_counts: Counter[str] = Counter()
    for card in cards:
        for stage in card.stages:
            stage_counts[stage] += 1

    print(f"カード総数: {len(cards)}")
    print(f"状態: active {status_counts['active']} / superseded {status_counts['superseded']}")
    print("kind 別:")
    for kind in KINDS:
        print(f"- {kind}: {kind_counts[kind]}")
    print("stage 別:")
    for stage in STAGES:
        print(f"- {stage}: {stage_counts[stage]}")
    print("育成ログ（直近5行）:")
    rows = recent_log_rows(args.directory / "育成ログ.md")
    if rows:
        for row in rows:
            print(row)
    else:
        print("（まだありません）")
    return 0


def command_migrate(args: argparse.Namespace) -> int:
    root: Path = args.directory
    if root.exists() and not root.is_dir():
        raise InputError(f"マイナレッジの場所がフォルダではありません: {root}")
    root.mkdir(parents=True, exist_ok=True)
    path = root / ".tirnanog-format"
    if not path.exists():
        atomic_write_text(path, FORMAT_VERSION + "\n")
        print(f"形式ファイルを作りました: {path}（版 {FORMAT_VERSION}）")
        return 0
    current = read_text(path).strip()
    if current == FORMAT_VERSION:
        print(f"形式は最新です（版 {FORMAT_VERSION}）。")
        return 0
    raise InputError(
        f"形式の版「{current or '空'}」には、このスクリプトはまだ対応していません。"
        f" ファイルを上書きせず停止しました: {path}"
    )


def export_source_files(root: Path) -> List[Path]:
    if not root.exists():
        raise InputError(f"マイナレッジのフォルダが見つかりません: {root}")
    if not root.is_dir():
        raise InputError(f"マイナレッジの場所がフォルダではありません: {root}")

    sources: List[Path] = []
    for filename in EXPORT_TOP_LEVEL_FILES:
        source = root / filename
        if source.is_symlink():
            raise InputError(f"まとめるファイルにシンボリックリンクは使えません: {source}")
        if not source.is_file():
            raise InputError(f"まとめる必須ファイルが見つかりません: {source}")
        sources.append(source)

    for directory_name in EXPORT_DIRECTORIES:
        directory = root / directory_name
        if directory.is_symlink():
            raise InputError(f"まとめるフォルダにシンボリックリンクは使えません: {directory}")
        if not directory.exists():
            continue
        if not directory.is_dir():
            raise InputError(f"まとめる場所がフォルダではありません: {directory}")
        for source in sorted(directory.glob("*.md"), key=lambda item: item.name):
            if source.is_symlink():
                raise InputError(f"まとめるファイルにシンボリックリンクは使えません: {source}")
            if source.is_file():
                sources.append(source)
    return sources


def command_export(args: argparse.Namespace) -> int:
    root: Path = args.directory
    sources = export_source_files(root)
    format_path = root / ".tirnanog-format"
    format_version = read_text(format_path).strip()
    if format_version != FORMAT_VERSION:
        raise InputError(
            f"形式の版「{format_version or '空'}」には、このスクリプトはまだ対応していません: {format_path}"
        )

    card_count = sum(1 for source in sources if source.parent.name == "カード")
    header = (
        f"{SUMMARY_TITLE}\n\n"
        f"- 生成日: {date.today().isoformat()}\n"
        f"- 形式の版: {format_version}\n"
        f"- カード件数: {card_count}\n\n"
        "このファイルを丸ごとプロジェクトに入れてください。中身は手で書き換えても大丈夫です\n\n"
    )
    sections: List[str] = []
    for source in sources:
        relative = source.relative_to(root).as_posix()
        content = read_text(source)
        sections.append(f"<!-- tirnanog:file {relative} -->\n{content}\n{SUMMARY_END_MARKER}\n")

    output: Path = args.out or (root.parent / "マイナレッジ_まとめ.md")
    if output.exists() and output.is_dir():
        raise InputError(f"出力先がフォルダです: {output}")
    atomic_write_text(output, header + "".join(sections))
    print(f"マイナレッジを1ファイルにまとめました: {output}")
    print(f"収録: {len(sources)}ファイル（カード {card_count}件）")
    return 0


def summary_error(line_number: int, detail: str) -> InputError:
    return InputError(f"まとめファイルの区切りが壊れています（{line_number}行目）: {detail}")


def safe_summary_path(raw: str, line_number: int) -> Path:
    if raw != raw.strip() or not raw or "\x00" in raw:
        raise summary_error(line_number, "ファイルの相対パスを正しく書いてください。")
    normalized = raw.replace("\\", "/")
    posix_path = PurePosixPath(normalized)
    windows_path = PureWindowsPath(raw)
    if posix_path.is_absolute() or windows_path.is_absolute() or bool(windows_path.drive):
        raise summary_error(line_number, f"絶対パスは使えません: {raw}")
    if not posix_path.parts or any(part in ("", ".", "..") for part in posix_path.parts):
        raise summary_error(line_number, f"パスに . や .. は使えません: {raw}")
    return Path(*posix_path.parts)


def parse_summary(text: str) -> List[Tuple[Path, str, int]]:
    entries: List[Tuple[Path, str, int]] = []
    seen_paths: Set[str] = set()
    current_path: Optional[Path] = None
    current_line = 0
    content_lines: List[str] = []
    seen_first_marker = False

    for line_number, line in enumerate(text.splitlines(keepends=True), start=1):
        marker_text = line.rstrip("\r\n").strip()
        file_match = SUMMARY_FILE_MARKER_RE.fullmatch(marker_text)
        if current_path is None:
            if file_match:
                current_path = safe_summary_path(file_match.group(1), line_number)
                key = current_path.as_posix().casefold()
                if key in seen_paths:
                    raise summary_error(line_number, f"同じパスが2回あります: {current_path.as_posix()}")
                seen_paths.add(key)
                current_line = line_number
                content_lines = []
                seen_first_marker = True
                continue
            if marker_text == SUMMARY_END_MARKER:
                raise summary_error(line_number, "対応する tirnanog:file がありません。")
            if marker_text.startswith("<!-- tirnanog:file") or marker_text.startswith("<!-- tirnanog:end"):
                raise summary_error(line_number, "区切り行の書式が正しくありません。")
            if seen_first_marker and marker_text:
                raise summary_error(line_number, "ファイルの区切りの外に文字があります。")
            continue

        if marker_text == SUMMARY_END_MARKER:
            content = "".join(content_lines)
            if not content.endswith("\n"):
                raise summary_error(line_number, "tirnanog:end の前の改行がありません。")
            entries.append((current_path, content[:-1], current_line))
            current_path = None
            current_line = 0
            content_lines = []
            continue
        if file_match:
            raise summary_error(line_number, f"{current_line}行目から始まるファイルの tirnanog:end がありません。")
        if marker_text.startswith("<!-- tirnanog:file") or marker_text.startswith("<!-- tirnanog:end"):
            raise summary_error(line_number, "区切り行の書式が正しくありません。")
        content_lines.append(line)

    if current_path is not None:
        raise summary_error(current_line, "この行から始まるファイルの tirnanog:end がありません。")
    if not entries:
        raise summary_error(1, "tirnanog:file の区切りが1つもありません。")
    return entries


def import_target(root: Path, relative: Path, line_number: int) -> Path:
    target = root.joinpath(*relative.parts)
    root_resolved = root.resolve()
    target_resolved = target.resolve(strict=False)
    try:
        target_resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise summary_error(line_number, f"フォルダの外へは書き込めません: {relative.as_posix()}") from exc
    return target


def command_import(args: argparse.Namespace) -> int:
    entries = parse_summary(read_text(args.file))
    root: Path = args.directory
    if root.exists() and not root.is_dir():
        raise InputError(f"書き戻し先がフォルダではありません: {root}")
    root.mkdir(parents=True, exist_ok=True)

    targets = [
        (import_target(root, relative, line_number), relative, content)
        for relative, content, line_number in entries
    ]
    skipped: List[Path] = []
    written = 0
    for target, relative, content in targets:
        if target.exists() or target.is_symlink():
            if target.is_dir():
                raise InputError(f"ファイルの書き戻し先と同名のフォルダがあります: {target}")
            if not args.overwrite:
                skipped.append(relative)
                continue
        atomic_write_text(target, content)
        written += 1

    for relative in skipped:
        print(f"スキップ（既存ファイルを保持）: {relative.as_posix()}")
    print(
        f"マイナレッジを書き戻しました: {root}"
        f"（書き込み {written} 件、スキップ {len(skipped)} 件）"
    )
    return 0


# --- 大量の素材の取り込み（add-source・ingest-status・ingest-done） ---

SOURCE_KIND_DIRS: Dict[str, str] = {
    "seminar": "30_セミナー",
    "feedback": "20_講師FB",
    "results": "40_実績",
    "sample": "10_お手本",
}
SOURCE_SUFFIXES: Tuple[str, ...] = (".txt", ".md", ".srt", ".vtt")
SOURCE_ID_RE = re.compile(r"^S-(\d{8})-(\d{3,})$")
INGEST_STATE_FILE = "取り込み状況.json"
DEFAULT_PART_CHARS = 12000
MIN_PART_CHARS = 2000
MAX_SOURCE_BYTES = 50 * 1024 * 1024
SUBTITLE_TIME_RE = re.compile(
    r"^\s*(\d{1,2}:)?\d{1,2}:\d{2}[.,]\d{1,3}\s*-->\s*(\d{1,2}:)?\d{1,2}:\d{2}[.,]\d{1,3}.*$"
)
SUBTITLE_TAG_RE = re.compile(r"</?[^>]{1,40}>")


def read_source_text(path: Path) -> str:
    """文字起こしのファイルを読む。UTF-8（BOM つき可）で読めなければ Shift_JIS（cp932）で読む。"""
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise InputError(f"ファイルを読めません: {path}（{exc}）") from exc
    if size > MAX_SOURCE_BYTES:
        raise InputError(f"ファイルが大きすぎます（50MB まで）: {path}")
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise InputError(f"ファイルを読めません: {path}（{exc}）") from exc
    for encoding in ("utf-8-sig", "cp932"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise InputError(f"文字のファイルとして読めません（UTF-8 か Shift_JIS にしてください）: {path}")


def clean_subtitles(text: str) -> str:
    """字幕（.srt・.vtt）を、キュー（空行で区切られたかたまり）ごとに読み、本文の行だけを残す。

    時刻の行（00:00:01,000 --> …）と、その直前にあるキューの番号・識別子だけを除く。
    本文の行は、数字だけの行（「100」「2026」など）でも残す。WEBVTT の見出しと NOTE・STYLE・REGION のかたまりは除く。
    同じ行が続けてくり返される時（自動字幕によくある）は1行にまとめる。
    """
    lines: List[str] = []
    blocks = re.split(r"\n\s*\n", text.replace("\r\n", "\n").replace("\r", "\n"))
    first_block = True
    for block in blocks:
        raw_lines = [line.strip() for line in block.split("\n") if line.strip()]
        if not raw_lines:
            continue
        is_first, first_block = first_block, False
        head = raw_lines[0]
        time_index = next((index for index, line in enumerate(raw_lines) if SUBTITLE_TIME_RE.match(line)), None)
        # 時刻の行があるかたまりは、識別子が何で始まっても字幕のキューとして読む
        if time_index is None:
            if is_first and head.startswith("WEBVTT"):
                continue  # ファイル先頭の見出し
            if head.split(" ")[0] in ("NOTE", "STYLE", "REGION"):
                continue
        body = raw_lines if time_index is None else raw_lines[time_index + 1 :]
        for line in body:
            if line.startswith("Kind:") or line.startswith("Language:"):
                continue
            cleaned = SUBTITLE_TAG_RE.sub("", line).strip()
            if not cleaned or (lines and lines[-1] == cleaned):
                continue
            lines.append(cleaned)
    return "\n".join(lines) + ("\n" if lines else "")


def normalize_source_text(path: Path, text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if path.suffix.lower() in (".srt", ".vtt"):
        text = clean_subtitles(text)
    return text.strip("\n") + "\n"


def split_source_parts(text: str, part_chars: int) -> List[str]:
    """段落の区切り（空行）→文の終わり（。！？）→行の終わりの順で、part_chars 字以内に区切る。"""
    parts: List[str] = []
    rest = text
    while len(rest) > part_chars:
        window = rest[:part_chars]
        cut = window.rfind("\n\n")
        if cut < part_chars // 2:
            cut = max(window.rfind("。"), window.rfind("！"), window.rfind("？"))
            cut = cut + 1 if cut >= part_chars // 2 else -1
        if cut < part_chars // 2:
            newline = window.rfind("\n")
            cut = newline if newline >= part_chars // 2 else part_chars
        piece = rest[:cut].strip("\n")
        if piece:
            parts.append(piece + "\n")
        rest = rest[cut:].lstrip("\n")
    if rest.strip():
        parts.append(rest.strip("\n") + "\n")
    return parts


def safe_title(text: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|\n\r\t]+', "_", text).strip(" ._")
    return cleaned[:60] or "素材"


def load_ingest_state(root: Path) -> Dict[str, object]:
    path = root / INGEST_STATE_FILE
    if not path.exists():
        return {"format": 1, "sources": []}
    try:
        state = json.loads(read_text(path))
    except json.JSONDecodeError as exc:
        raise InputError(f"取り込み状況のファイルが壊れています（手で直さず、講座のサポートへ）: {path}（{exc}）") from exc
    if not isinstance(state, dict) or not isinstance(state.get("sources"), list):
        raise InputError(f"取り込み状況のファイルの形が違います: {path}")
    return state


def save_ingest_state(root: Path, state: Dict[str, object]) -> None:
    atomic_write_text(root / INGEST_STATE_FILE, json.dumps(state, ensure_ascii=False, indent=2) + "\n")


def next_source_id(state: Dict[str, object], source_date: date) -> str:
    prefix = f"S-{source_date.strftime('%Y%m%d')}-"
    highest = 0
    for source in state["sources"]:  # type: ignore[index]
        match = SOURCE_ID_RE.fullmatch(str(source.get("id", "")))
        if match and source["id"].startswith(prefix):
            highest = max(highest, int(match.group(2)))
    return f"{prefix}{highest + 1:03d}"


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    for number in range(2, 1000):
        candidate = path.with_name(f"{path.stem}_{number}{path.suffix}")
        if not candidate.exists():
            return candidate
    raise InputError(f"同じ名前のファイルが多すぎます: {path}")


def read_prompt_json(path: Path) -> str:
    """フック（save-long-prompt.sh）が保存した JSON から、受講生が貼った文（prompt）を取り出す。"""
    try:
        payload = json.loads(read_source_text(path))
    except json.JSONDecodeError as exc:
        raise InputError(f"保存された長文のファイルが JSON として読めません: {path}（{exc}）") from exc
    prompt = payload.get("prompt") if isinstance(payload, dict) else None
    if not isinstance(prompt, str) or not prompt.strip():
        raise InputError(f"保存された長文のファイルに、貼られた文（prompt）がありません: {path}")
    return prompt


def collect_source_files(files: Sequence[Path], from_dir: Optional[Path]) -> Tuple[List[Path], List[Path]]:
    selected: List[Path] = []
    skipped: List[Path] = []
    for path in files:
        if not path.is_file():
            raise InputError(f"ファイルが見つかりません: {path}")
        (selected if path.suffix.lower() in SOURCE_SUFFIXES else skipped).append(path)
    if from_dir is not None:
        if not from_dir.is_dir():
            raise InputError(f"フォルダが見つかりません: {from_dir}")
        for path in sorted(from_dir.rglob("*"), key=lambda item: item.as_posix()):
            # 「.」で始まる隠しファイルと、「_」で始まる案内のファイル（_ここに文字起こしを置く.txt など）は取り込まない
            if path.is_file() and not path.name.startswith((".", "_")):
                (selected if path.suffix.lower() in SOURCE_SUFFIXES else skipped).append(path)
    if not selected:
        raise InputError("取り込める文字のファイル（.txt・.md・.srt・.vtt）がありません。")
    return selected, skipped


def command_add_source(args: argparse.Namespace) -> int:
    root: Path = args.directory
    if not (root / "カード").is_dir():
        raise InputError(f"マイナレッジが見つかりません（先に init）: {root}")
    if args.kind not in SOURCE_KIND_DIRS:
        raise vocabulary_error("kind", [args.kind], tuple(SOURCE_KIND_DIRS))
    if args.part_chars < MIN_PART_CHARS:
        raise InputError(f"part-chars は{MIN_PART_CHARS}以上で指定してください。")
    source_date = parse_iso_date(args.source_date, "date") if args.source_date else date.today()
    prompt_files: List[Path] = []
    for path in args.prompt_jsons or []:
        if not path.is_file():
            raise InputError(f"ファイルが見つかりません: {path}")
        prompt_files.append(path)
    if prompt_files and not (args.files or args.from_dir):
        files, skipped = [], []
    else:
        files, skipped = collect_source_files(args.files or [], args.from_dir)
    files = [*files, *prompt_files]
    if args.title and len(files) > 1:
        raise InputError("--title は、ファイルが1つの時だけ使えます（複数の時はファイル名が題名になります）。")

    state = load_ingest_state(root)
    kind_dir = root / SOURCE_KIND_DIRS[args.kind]
    known_hashes = {
        str(item.get("sha256")): str(item.get("id"))
        for item in state["sources"]  # type: ignore[union-attr]
        if item.get("sha256")
    }
    added = []
    already: List[Dict[str, str]] = []
    for path in files:
        if path in prompt_files:
            text = normalize_source_text(path, read_prompt_json(path))
        else:
            text = normalize_source_text(path, read_source_text(path))
        if not text.strip():
            skipped.append(path)
            continue
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if digest in known_hashes and not args.allow_duplicate:
            # 同じ中身は取り込み済み（前の呼び出し、または今回の呼び出しの中で）。カードが二重にできないように飛ばす
            already.append({"file": str(path), "id": known_hashes[digest]})
            continue
        default_title = f"チャットに貼られた文_{path.stem}" if path in prompt_files else path.stem
        title = safe_title(args.title or default_title)
        source_id = next_source_id(state, source_date)
        destination = unique_path(kind_dir / f"{source_date.isoformat()}_{title}.md")
        parts = split_source_parts(text, args.part_chars)
        parts_dir = destination.with_name(f"{destination.stem}_分割")
        header = (
            "from: 未記入（講師名・セミナー名が分かれば書き足す）\n"
            f"date: {source_date.isoformat()}\n"
            f"about: {title}\n"
            "target: なし\n"
            f"source_id: {source_id}\n"
            f"original_file: {path.name}\n"
            f"chars: {len(text)}\n"
            f"parts: {len(parts)}\n\n"
        )
        atomic_write_text(destination, header + text)
        part_entries = []
        for number, part in enumerate(parts, start=1):
            part_path = parts_dir / f"part-{number:03d}.md"
            atomic_write_text(
                part_path,
                f"<!-- {source_id} {title} 区切り {number}/{len(parts)}（原文: {destination.name}） -->\n\n{part}",
            )
            part_entries.append(
                {
                    "n": number,
                    "path": part_path.relative_to(root).as_posix(),
                    "chars": len(part),
                    "done": False,
                    "cards": [],
                    "note": "",
                    "done_at": "",
                }
            )
        entry = {
            "id": source_id,
            "sha256": digest,
            "kind": args.kind,
            "title": title,
            "date": source_date.isoformat(),
            "path": destination.relative_to(root).as_posix(),
            "original_file": path.name,
            "chars": len(text),
            "parts": part_entries,
            "added_at": datetime.now().replace(microsecond=0).isoformat(),
        }
        state["sources"].append(entry)  # type: ignore[union-attr]
        save_ingest_state(root, state)
        known_hashes[digest] = source_id
        added.append(entry)

    result = {
        "added": [
            {"id": item["id"], "title": item["title"], "path": item["path"], "chars": item["chars"], "parts": len(item["parts"])}
            for item in added
        ],
        "skipped": [str(path) for path in skipped],
        "already_ingested": already,
        "total_parts": sum(len(item["parts"]) for item in added),
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for item in result["added"]:
            print(f"{item['id']}  {item['title']}  {item['chars']}字・{item['parts']}区切り  {item['path']}")
        if skipped:
            print("取り込めなかったファイル（文字のファイルではない・空）:")
            for path in skipped:
                print(f"- {path}")
        if already:
            print("取り込み済みなので飛ばしたファイル（同じ中身がすでにあります。もう一度取り込む時は --allow-duplicate）:")
            for item in already:
                print(f"- {item['file']}（{item['id']}）")
        print(f"区切りは合計 {result['total_parts']} 個です。`ingest-status` で次に読む区切りを確かめてください。")
    return 0


def ingest_summary(state: Dict[str, object]) -> List[Dict[str, object]]:
    rows = []
    for source in state["sources"]:  # type: ignore[union-attr]
        parts = source.get("parts", [])
        done = [part for part in parts if part.get("done")]
        pending = [part for part in parts if not part.get("done")]
        rows.append(
            {
                "id": source["id"],
                "title": source["title"],
                "kind": source["kind"],
                "parts_done": len(done),
                "parts_total": len(parts),
                "cards": sorted({card for part in parts for card in part.get("cards", [])}),
                "next_part": pending[0]["n"] if pending else None,
                "next_path": pending[0]["path"] if pending else None,
            }
        )
    return rows


def command_ingest_status(args: argparse.Namespace) -> int:
    state = load_ingest_state(args.directory)
    rows = ingest_summary(state)
    remaining = sum(row["parts_total"] - row["parts_done"] for row in rows)  # type: ignore[operator]
    if args.json:
        print(json.dumps({"sources": rows, "remaining_parts": remaining}, ensure_ascii=False, indent=2))
        return 0
    if not rows:
        print("取り込み中の素材はありません。")
        return 0
    for row in rows:
        mark = "済" if row["next_part"] is None else f"次は区切り{row['next_part']}（{row['next_path']}）"
        print(f"{row['id']}  {row['title']}  {row['parts_done']}/{row['parts_total']}  カード{len(row['cards'])}枚  {mark}")
    print(f"残りの区切り: {remaining}")
    return 0


def command_ingest_done(args: argparse.Namespace) -> int:
    root: Path = args.directory
    state = load_ingest_state(root)
    source = next((item for item in state["sources"] if item["id"] == args.source_id), None)  # type: ignore[union-attr]
    if source is None:
        raise InputError(f"取り込み中の素材が見つかりません: {args.source_id}（`ingest-status` で id を確かめてください）")
    part = next((item for item in source["parts"] if item["n"] == args.part), None)
    if part is None:
        raise InputError(f"{args.source_id} に区切り {args.part} はありません（全部で {len(source['parts'])}）。")
    cards = [card.strip() for card in (args.cards or "").split(",") if card.strip()]
    for card_id in cards:
        if not CARD_ID_RE.fullmatch(card_id):
            raise InputError(f"カードの id の形が違います: {card_id}")
        card_by_id(root, card_id)
    part["done"] = True
    part["cards"] = sorted(set(part.get("cards", [])) | set(cards))
    part["note"] = args.note or part.get("note", "")
    part["done_at"] = datetime.now().replace(microsecond=0).isoformat()
    save_ingest_state(root, state)
    pending = [item for item in source["parts"] if not item["done"]]
    if pending:
        print(f"{args.source_id} の区切り {args.part} を済みにしました。次は区切り {pending[0]['n']}（{pending[0]['path']}）。")
    else:
        print(f"{args.source_id}「{source['title']}」は全部の区切りが済みました。育成ログに1行足してください（`log`）。")
    return 0


# --- 市場の投稿（market-add・market-count・market-words） ---
# 受講生がリサーチで集めた、伸びている他人の投稿を原文のまま手元に置き、言葉を数える。
# 外には送らない。カード化の取り込み待ち（取り込み状況.json）にも入れない。

MARKET_DIR_NAME = "50_市場の投稿"
KANTEI_DIR_NAME = "鑑定"
KANTEI_COLLECTED_NAME = "集めた投稿.md"
MARKET_WORDS_FILE = "市場の言葉.md"
MARKET_MIN_POSTS = 10  # これより少ないと、言葉の表と MARKET の確かめはしない
MARKET_PHRASE_MIN_POSTS = 3  # よく出る言い回しとして数える下限（何本の投稿に出るか）
MARKET_GRAM_MIN = 2
MARKET_GRAM_MAX = 12
MARKET_ENDING_MAX = 6
MARKET_ENDING_TOP = 15
MARKET_FILE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_(\d{2,})\.md$")
MARKET_HEADER_PREFIX = "<!-- tirnanog:market"
MARKET_NUMBER_HEAD_RE = re.compile(r"^(?:#{1,6}\s*)?【\s*[0-9０-９]+\s*】")
MARKET_SEPARATOR_LINE = "---"
# ファイルの題などの見出し（「# 集めた投稿」）。投稿の文としては数えず、区切りとして扱う。「#金運」のような空白なしのタグは見出しではない
MARKET_HEADING_RE = re.compile(r"^#{1,6}\s+\S")
# 書き手の行: 行全体が @ で始まり、空白を含まない40字までの名前（@ふく江・2日 の「・」より後ろは捨てる）。
# 行の途中の @ や、名前の後ろに文が続く行（@名前 ありがとう）は書き手にしない
MARKET_AUTHOR_HANDLE_RE = re.compile(r"^@([^\s@・·|｜]{1,40})\s*(?:[・·|｜].*)?$")
MARKET_AUTHOR_LABEL_RE = re.compile(r"^(?:書き手|投稿者)\s*[:：]\s*(.+)$")
# いいね・コメントの数だけの行（案内で数字も一緒に貼ってもらうため）。言葉の数えに入れない
MARKET_METRIC_LINE_RE = re.compile(
    r"^(?:(?:いいね|コメント|リポスト|再投稿|引用|シェア|返信|閲覧|表示回数|保存)\s*[:：]?\s*"
    r"[0-9][0-9.,万千kK]*\s*(?:件|回|人)?[\s・/|、,]*)+$"
)
MARKET_NUMBER_ONLY_RE = re.compile(r"^[0-9][0-9.,]*$")
HTML_COMMENT_BLOCK_RE = re.compile(r"<!--.*?(?:-->|\Z)", re.DOTALL)
MARKET_SENTENCE_SPLIT_RE = re.compile(r"[。！？!?\n]+")
SMALL_KANA = set("ぁぃぅぇぉっゃゅょゎゕゖァィゥェォッャュョヮヵヶ")
# 並びの頭・お尻で見る助詞1字
MARKET_PARTICLES = set("のはでにをがともへや")
# 漢字の後ろに来ても、言葉の切れ目と見なすかな（助詞・助動詞の頭）
MARKET_BREAK_KANA = set("のはでにをがともへやかよねなだじ")
# 2字以上の漢字・カタカナの後ろの「し・す・さ・せ」は、する言葉（冷凍して）の切れ目と見なす
MARKET_SURU_KANA = set("しすさせ")
MARKET_COVER_RATIO = 0.8  # 長い並びが、短い並びの本数のこの割合以上を占めたら、短い並びは落とす
MARKET_LONGEST_MIN = 4  # 0本の句に添える「一番長い並び」の下限の字数
MARKET_COPY_MIN_CHARS = 12  # これ以上の長さの句が1〜2人の投稿にしか出ない時は「1人の文の写しに近い」（tn_check の MARKET_COPY と同じ）
MARKET_COPY_MAX_PEOPLE = 2
# よく出る言い回しから落とす、意味を持たない並び（助詞・助動詞のつながり）。大事な言葉を落とさないよう小さくしておく
MARKET_STOP_GRAMS: Set[str] = {
    "ている", "ていた", "ていて", "ています", "ていました", "てる", "てた",
    "している", "していた", "しています", "して", "した", "する", "します", "しました",
    "いる", "いた", "います", "いました", "ある", "あった", "あります", "ありました",
    "なる", "なった", "なります", "ない", "なく", "なくて", "ません", "ませんでした",
    "です", "でした", "ます", "ました", "ので", "から", "けど", "けれど", "って", "という", "といった",
    "として", "について", "には", "では", "とは", "のは", "のが", "のを", "のに", "のも", "のです", "なんです",
    "こと", "ことが", "ことを", "ことは", "もの", "ため", "よう", "ように", "それ", "これ", "あれ",
    "その", "この", "あの", "それは", "これは", "たら", "れば", "まで", "より", "など", "だけ", "でも", "ても",
    "にも", "との", "への", "でいる", "じゃない", "ではない", "かった", "なかった", "った",
}


@dataclass
class MarketPost:
    text: str  # 本文（書き手の行・数字だけの行を外した行。NFC にそろえた）
    lines: List[str]
    author: str
    source: str
    compact: str = ""

    def __post_init__(self) -> None:
        if not self.compact:
            self.compact = compact_text(self.text)

    @property
    def first_line(self) -> str:
        return self.lines[0] if self.lines else ""


def nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text)


def compact_text(text: str) -> str:
    """全角・半角の空白と改行を外し、NFC にそろえる（句を文字のまま比べるため）。"""
    return "".join(character for character in nfc(text) if not character.isspace())


def find_child(parent: Path, name: str) -> Optional[Path]:
    """名前が NFC・NFD のどちらで保存されていても見つける。無ければ None。"""
    direct = parent / name
    if direct.exists():
        return direct
    if not parent.is_dir():
        return None
    wanted = nfc(name)
    try:
        for child in parent.iterdir():
            if nfc(child.name) == wanted:
                return child
    except OSError:
        return None
    return None


def require_knowledge_directory(root: Path) -> None:
    if not root.is_dir():
        raise InputError(f"マイナレッジのフォルダが見つかりません: {root}")


def strip_market_header(text: str) -> str:
    """保存した時の頭書き（HTML のコメント）を外す。行の数は変えない。"""
    return HTML_COMMENT_BLOCK_RE.sub(lambda match: "\n" * match.group(0).count("\n"), text)


def split_market_blocks(text: str) -> Tuple[List[List[str]], bool]:
    """貼られた文を投稿ごとの行に分ける。区切りは `---` だけの行・【番号】で始まる行・空行2つ以上
    （ほかに、ファイルの題などの「# 」で始まる見出しの行も、文として数えずに区切りにする）。

    空行が1つだけの所では区切らない（投稿の中の段落）。【番号】の行は次の投稿の先頭で、番号を外して
    残った文があれば、それを投稿の1行目にする。返り値は（投稿ごとの行の一覧, 区切りが1つでもあったか）。
    """
    blocks: List[List[str]] = []
    current: List[str] = []
    blank_run = 0
    found_separator = False

    def flush() -> None:
        nonlocal current
        while current and not current[-1].strip():
            current.pop()
        while current and not current[0].strip():
            current.pop(0)
        if current:
            blocks.append(current)
        current = []

    for raw_line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        stripped = raw_line.strip()
        if stripped == MARKET_SEPARATOR_LINE:
            flush()
            found_separator = True
            blank_run = 0
            continue
        head = MARKET_NUMBER_HEAD_RE.match(stripped)
        if head:
            flush()
            found_separator = True
            blank_run = 0
            rest = stripped[head.end() :].strip()
            if rest:
                current.append(rest)
            continue
        if MARKET_HEADING_RE.match(stripped):
            flush()
            found_separator = True
            blank_run = 0
            continue
        if not stripped:
            blank_run += 1
            current.append("")
            continue
        if blank_run >= 2 and any(line.strip() for line in current):
            flush()
            found_separator = True
        blank_run = 0
        current.append(raw_line.rstrip())
    flush()
    return blocks, found_separator


def market_post_from_block(block: Sequence[str], source: str) -> Optional[MarketPost]:
    """投稿1本の行から、書き手の行（@名前・書き手:）と数字だけの行を外す。本文が残らなければ None。"""
    author = ""
    lines: List[str] = []
    for raw_line in block:
        line = nfc(raw_line).strip()
        if not line:
            if lines:
                lines.append("")
            continue
        handle = MARKET_AUTHOR_HANDLE_RE.match(line)
        label = MARKET_AUTHOR_LABEL_RE.match(line)
        if handle is not None or label is not None:
            if not author:
                found = handle.group(1) if handle is not None else label.group(1)  # type: ignore[union-attr]
                author = found.strip().lstrip("@")
            continue
        folded = unicodedata.normalize("NFKC", line)
        if MARKET_METRIC_LINE_RE.match(folded) or MARKET_NUMBER_ONLY_RE.match(folded):
            continue
        lines.append(line)
    while lines and not lines[-1]:
        lines.pop()
    if not lines:
        return None
    return MarketPost(text="\n".join(lines), lines=[line for line in lines if line], author=author, source=source)


def market_files(root: Path) -> List[Path]:
    folder = find_child(root, MARKET_DIR_NAME)
    if folder is None or not folder.is_dir():
        return []
    files = [
        path
        for path in folder.iterdir()
        if path.is_file() and path.suffix.lower() == ".md" and not path.name.startswith((".", "_"))
    ]
    return sorted(files, key=lambda item: nfc(item.name))


def kantei_collected_file(root: Path) -> Optional[Path]:
    kantei = find_child(root, KANTEI_DIR_NAME)
    if kantei is None or not kantei.is_dir():
        return None
    path = find_child(kantei, KANTEI_COLLECTED_NAME)
    return path if path is not None and path.is_file() else None


def is_market_text(text: str) -> bool:
    """market-add で保存した形（頭に <!-- tirnanog:market … --> の行）か。"""
    return text.lstrip("\ufeff \t\r\n").startswith(MARKET_HEADER_PREFIX)


def market_posts_from_text(text: str, source: str) -> List[MarketPost]:
    """ファイル1つ分の文を、頭書き・書き手の行・数だけの行を外して、投稿ごとに分ける。"""
    blocks, _ = split_market_blocks(strip_market_header(text))
    return [post for post in (market_post_from_block(block, source) for block in blocks) if post is not None]


def load_market_posts(root: Path) -> Tuple[List[MarketPost], Dict[str, int]]:
    """`50_市場の投稿/*.md` と `鑑定/集めた投稿.md` を読む（どちらも無ければ0本）。

    空白を外した中身が同じ投稿は1本にまとめる（同じ投稿を2か所に置いても、本数がふくらまないように）。
    """
    require_knowledge_directory(root)
    folder_paths = market_files(root)
    sources: List[Tuple[Path, str]] = [(path, f"{MARKET_DIR_NAME}/{nfc(path.name)}") for path in folder_paths]
    kantei = kantei_collected_file(root)
    if kantei is not None:
        sources.append((kantei, f"{KANTEI_DIR_NAME}/{KANTEI_COLLECTED_NAME}"))
    posts: List[MarketPost] = []
    seen: Set[str] = set()
    counts = {"folder_posts": 0, "kantei_posts": 0, "duplicates": 0}
    for path, label in sources:
        for post in market_posts_from_text(read_source_text(path), label):
            if post.compact in seen:
                counts["duplicates"] += 1
                continue
            seen.add(post.compact)
            posts.append(post)
            counts["kantei_posts" if path == kantei else "folder_posts"] += 1
    summary = {"total": len(posts), "folder_files": len(folder_paths), **counts}
    return posts, summary


def market_summary_text(summary: Dict[str, int]) -> str:
    detail = [f"{MARKET_DIR_NAME} {summary['folder_posts']}本（{summary['folder_files']}ファイル）"]
    if summary["kantei_posts"]:
        detail.append(f"{KANTEI_DIR_NAME}/{KANTEI_COLLECTED_NAME} {summary['kantei_posts']}本")
    text = f"集めた投稿: {summary['total']}本（{'・'.join(detail)}"
    if summary["duplicates"]:
        text += f"。同じ投稿 {summary['duplicates']}本は1本として数えました"
    return text + "）"


def phrase_hits(posts: Sequence[MarketPost], needle: str) -> Dict[str, object]:
    hits = [post for post in posts if needle in post.compact]
    authors = {post.author for post in hits if post.author}
    return {
        "posts": len(hits),
        "authors": len(authors) if authors else None,
        "authors_unknown_posts": sum(1 for post in hits if not post.author),
        "hits": hits,
    }


def longest_found_part(posts: Sequence[MarketPost], needle: str) -> Optional[Dict[str, object]]:
    """句の中で、集めた投稿に出る一番長い並び（4字以上）。同じ長さなら本数の多い物。無ければ None。"""
    for size in range(len(needle) - 1, MARKET_LONGEST_MIN - 1, -1):
        best: Optional[Dict[str, object]] = None
        for start in range(0, len(needle) - size + 1):
            part = needle[start : start + size]
            found = phrase_hits(posts, part)
            if found["posts"] and (best is None or int(found["posts"]) > int(best["posts"])):  # type: ignore[arg-type]
                best = {"phrase": part, **found}
        if best is not None:
            # 端の句読点・かっこは外して数え直す（「母から教わった、」→「母から教わった」）
            trimmed = str(best["phrase"])
            while trimmed and unicodedata.category(trimmed[0])[0] in ("P", "S", "Z"):
                trimmed = trimmed[1:]
            while trimmed and unicodedata.category(trimmed[-1])[0] in ("P", "S", "Z"):
                trimmed = trimmed[:-1]
            if trimmed != best["phrase"] and len(trimmed) >= MARKET_LONGEST_MIN:
                best = {"phrase": trimmed, **phrase_hits(posts, trimmed)}
            best.pop("hits")
            return best
    return None


def count_phrase(posts: Sequence[MarketPost], phrase: str) -> Dict[str, object]:
    """句を文字のまま探す（空白・改行は無視）。出る投稿の本数・書き手の人数・例を1つ返す。

    0本の時は、句の中で集めた投稿に出る一番長い並び（4字以上）を longest に入れる（市場の形＋中身の句を見分けるため）。
    """
    needle = compact_text(phrase)
    if not needle:
        raise InputError("--phrase が空です（空白だけの句は数えられません）。")
    found = phrase_hits(posts, needle)
    hits: List[MarketPost] = found.pop("hits")  # type: ignore[assignment]
    example = ""
    if hits:
        post = hits[0]
        example = next((line for line in post.lines if needle in compact_text(line)), "")
        if not example:
            # 句が改行をまたいで出る時は「その句を含む1行」が無いので、またいだ所の前後を空白なしでつないで例にする
            position = post.compact.find(needle)
            example = post.compact[max(0, position - 10) : position + len(needle) + 10]
    return {
        "phrase": phrase,
        **found,
        "example": example,
        "longest": None if hits else longest_found_part(posts, needle),
    }


def authors_text(count: Optional[int], unknown: int) -> str:
    if count is None:
        return "人数は不明"
    if unknown:
        return f"{count}人以上（書き手が分からない投稿 {unknown}本）"
    return f"{count}人"


def next_market_path(folder: Path, today: date) -> Path:
    prefix = today.isoformat()
    highest = 0
    if folder.is_dir():
        for path in folder.iterdir():
            match = MARKET_FILE_RE.match(nfc(path.name))
            if match and match.group(1) == prefix:
                highest = max(highest, int(match.group(2)))
    return folder / f"{prefix}_{highest + 1:02d}.md"


def read_market_input(args: argparse.Namespace) -> Tuple[str, str]:
    if args.prompt_json is not None:
        if not args.prompt_json.is_file():
            raise InputError(f"ファイルが見つかりません: {args.prompt_json}")
        return read_prompt_json(args.prompt_json), "チャットに貼られた文"
    path: Path = args.file if args.file is not None else args.text_file
    if str(path) == "-":
        # 一時ファイルを作らずに、標準入力（heredoc など）から受け取る
        data = sys.stdin.buffer.read()
        for encoding in ("utf-8-sig", "cp932"):
            try:
                return data.decode(encoding), "標準入力"
            except UnicodeDecodeError:
                continue
        raise InputError("標準入力を文字として読めません（UTF-8 にしてください）。")
    if not path.is_file():
        raise InputError(f"ファイルが見つかりません: {path}")
    return read_source_text(path), path.name


def header_value(text: str) -> str:
    # 頭書きのコメントが途中で閉じないよう、改行をつなぎ「--」を全角にする
    return " ".join(text.split()).replace("--", "－－")


def command_market_add(args: argparse.Namespace) -> int:
    root: Path = args.directory
    cards = find_child(root, "カード")
    if cards is None or not cards.is_dir():
        raise InputError(f"マイナレッジが見つかりません（先に init）: {root}")
    raw_text, origin = read_market_input(args)
    text = raw_text.replace("\r\n", "\n").replace("\r", "\n").strip("\n")
    if not text.strip():
        raise InputError("貼られた文が空です。")
    blocks, found_separator = split_market_blocks(strip_market_header(text))
    saved_posts = [post for post in (market_post_from_block(block, "") for block in blocks) if post is not None]
    if not saved_posts:
        raise InputError("投稿の本文が見つかりません（書き手の行や数字だけでした）。")

    folder = find_child(root, MARKET_DIR_NAME) or (root / MARKET_DIR_NAME)
    digest = hashlib.sha256(compact_text(strip_market_header(text)).encode("utf-8")).hexdigest()
    for existing in market_files(root):
        body = strip_market_header(read_source_text(existing))
        if hashlib.sha256(compact_text(body).encode("utf-8")).hexdigest() == digest:
            print(f"同じ中身がすでに保存されているので、保存しませんでした: {existing}")
            _, summary = load_market_posts(root)
            print(market_summary_text(summary))
            return 0

    today = date.today()
    destination = next_market_path(folder, today)
    header = f"{MARKET_HEADER_PREFIX} date: {today.isoformat()} from: {header_value(origin)}"
    note = header_value(args.note or "")
    if note:
        header += f" note: {note}"
    header += " -->\n\n"
    atomic_write_text(destination, header + text + "\n")

    _, summary = load_market_posts(root)
    print(f"市場の投稿を保存しました: {destination}（{len(saved_posts)}本）")
    if not found_separator:
        print("区切り（--- だけの行・【番号】で始まる行・空行2つ以上）が見つからなかったので、全体を1本の投稿として保存しました。")
    print(market_summary_text(summary))
    if summary["total"] < MARKET_MIN_POSTS:
        print(f"あと {MARKET_MIN_POSTS - summary['total']} 本集めると、市場の言葉を数えて確かめられます（10本から）。")
    else:
        print("`market-words` で市場の言葉の表を作り直せます。")
    return 0


def zero_phrase_text(item: Dict[str, object]) -> str:
    """0本の句の後ろに付ける（ ）の中身。"""
    longest = item.get("longest")
    if not longest:
        return "4字以上の並びも0本"
    who = authors_text(longest["authors"], int(longest["authors_unknown_posts"]))  # type: ignore[index,arg-type]
    return f"この中で集めた投稿にある一番長い並び: 「{longest['phrase']}」{longest['posts']}本・{who}"  # type: ignore[index]


def command_market_count(args: argparse.Namespace) -> int:
    posts, summary = load_market_posts(args.directory)
    results = [count_phrase(posts, phrase) for phrase in args.phrases]
    if args.json:
        payload = {"total_posts": summary["total"], "sources": summary, "phrases": results}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    print(market_summary_text(summary))
    if summary["total"] < MARKET_MIN_POSTS:
        print(f"集めた投稿が {summary['total']} 本なので、本数は目安です（10本から確かめられます）。")
    for item in results:
        if item["posts"] == 0:
            print(f"- 「{item['phrase']}」: 0本（{zero_phrase_text(item)}）")
            continue
        who = authors_text(item["authors"], int(item["authors_unknown_posts"]))  # type: ignore[arg-type]
        print(f"- 「{item['phrase']}」: {item['posts']}本・{who}（例: {item['example']}）")
    return 0


def market_segments(text: str) -> List[str]:
    """文字（かな・漢字・英字）と数字の続きだけを取り出す。空白・句読点・かっこ・絵文字で切る。"""
    segments: List[str] = []
    current: List[str] = []
    for character in text:
        category = unicodedata.category(character)
        if category[0] in ("L", "N") or category == "Mn":
            current.append(character)
            continue
        if current:
            segments.append("".join(current))
            current = []
    if current:
        segments.append("".join(current))
    return segments


def is_hiragana(character: str) -> bool:
    return "\u3041" <= character <= "\u309f"


def character_kind(character: str) -> str:
    if "\u3041" <= character <= "\u309f":
        return "hiragana"
    if "\u30a1" <= character <= "\u30ff" or character == "ー":
        return "katakana"
    if unicodedata.category(character) == "Nd":
        return "digit"
    if unicodedata.category(character).startswith("L") and unicodedata.name(character, "").startswith("CJK"):
        return "kanji"
    if character.isascii() and character.isalpha():
        return "latin"
    return "other"


def ends_inside_word(gram: str, following: str) -> bool:
    """並びのお尻が、言葉の途中で切れているか（「冷凍し|て」「3パターンで回|して」「考え|る」）。"""
    if not following:
        return False
    last = gram[-1]
    last_kind = character_kind(last)
    next_kind = character_kind(following)
    if last_kind in ("kanji", "katakana", "digit", "latin") and next_kind == last_kind:
        return True  # 漢字・カタカナ・数字・英字の続きの途中
    if next_kind != "hiragana":
        return False
    if last_kind == "hiragana":
        return True  # かなの続きの途中（送り仮名・活用の途中）
    if following in MARKET_BREAK_KANA:
        return False
    if last_kind in ("kanji", "katakana"):
        run = 0
        for character in reversed(gram):
            if character_kind(character) != last_kind:
                break
            run += 1
        if (run >= 2 or last_kind == "katakana") and following in MARKET_SURU_KANA:
            return False  # 「冷凍して」「コメントして」の、する言葉の切れ目
        return True  # 漢字1字の後ろの送り仮名（回して・考える）
    return False


def starts_inside_word(gram: str, preceding: str) -> bool:
    """並びの頭が、言葉の途中から始まっているか（「月|曜の朝」「とだ|けコメント」）。"""
    if not preceding:
        return False
    kind = character_kind(gram[0])
    if kind in ("kanji", "katakana", "digit", "latin") and character_kind(preceding) == kind:
        return True
    if kind != "hiragana" or gram[0] in MARKET_PARTICLES:
        return False
    # かなの続きの途中（前のかなが助詞でない時）か、漢字の後ろの送り仮名から始まる（「早|い人」）
    preceding_kind = character_kind(preceding)
    return (preceding_kind == "hiragana" and preceding not in MARKET_PARTICLES) or preceding_kind == "kanji"


def is_noise_gram(gram: str, ending_words: Sequence[str] = ()) -> bool:
    if gram in MARKET_STOP_GRAMS:
        return True
    if gram[0] in SMALL_KANA or gram[0] in "ーん":
        return True  # 言葉の途中から始まる並び
    if all(unicodedata.category(character) == "Nd" for character in gram):
        return True  # 数字だけ
    hiragana_only = all(is_hiragana(character) for character in gram)
    if hiragana_only and len(gram) < 4:
        return True  # 漢字・カタカナを含まない並びは4字以上だけ残す
    if gram[0] == "を" or (gram[0] in MARKET_PARTICLES and len(gram) > 1 and not is_hiragana(gram[1])):
        return True  # 助詞1字で始まる並び（「の3」「と魚に下味を付けて」）
    if len(gram) == 2 and gram[-1] in MARKET_PARTICLES:
        return True  # 助詞1字で終わる2字の並び（「曜の」「人は」「分で」）
    if hiragana_only and any(gram in ending or ending in gram for ending in ending_words):
        return True  # 文末の形の表に出る物と、その一部だけの並び（「てください」「ださい」）
    return False


def frequent_grams(posts: Sequence[MarketPost], ending_words: Sequence[str] = ()) -> List[Tuple[str, Set[int]]]:
    """3本以上の投稿に出る 2〜12字の並びから、意味の無い並びを落とした物。

    落とす物: 落とす語の一覧・助詞1字で始まる並びと助詞1字で終わる2字の並び・ひらがなだけの3字以下・
    文末の形の表に出る物・上限の12字で切れた並び・言葉の途中で始まる／終わる並び（出る所の半分を超える時）・
    長い並びに含まれる短い並び（長い方が、短い方の本数の8割以上に出る時）。
    """
    occurrences: Dict[str, Set[int]] = {}
    post_segments = [market_segments(post.text) for post in posts]
    for index, segments in enumerate(post_segments):
        grams: Set[str] = set()
        for segment in segments:
            length = len(segment)
            for size in range(MARKET_GRAM_MIN, min(MARKET_GRAM_MAX, length) + 1):
                for start in range(0, length - size + 1):
                    grams.add(segment[start : start + size])
        for gram in grams:
            occurrences.setdefault(gram, set()).add(index)
    frequent = {gram: ids for gram, ids in occurrences.items() if len(ids) >= MARKET_PHRASE_MIN_POSTS}

    # 出る所ごとに、言葉の途中で切れているかを数える（3本以上に出る並びだけ）
    seen_count: Dict[str, int] = {}
    inside_count: Dict[str, int] = {}
    whole_segments: Set[str] = set()
    for segments in post_segments:
        for segment in segments:
            whole_segments.add(segment)
            length = len(segment)
            for size in range(MARKET_GRAM_MIN, min(MARKET_GRAM_MAX, length) + 1):
                for start in range(0, length - size + 1):
                    gram = segment[start : start + size]
                    if gram not in frequent:
                        continue
                    preceding = segment[start - 1] if start > 0 else ""
                    following = segment[start + size] if start + size < length else ""
                    seen_count[gram] = seen_count.get(gram, 0) + 1
                    if ends_inside_word(gram, following) or starts_inside_word(gram, preceding):
                        inside_count[gram] = inside_count.get(gram, 0) + 1

    valid: Dict[str, Set[int]] = {}
    for gram, ids in frequent.items():
        if is_noise_gram(gram, ending_words):
            continue
        if len(gram) >= MARKET_GRAM_MAX and gram not in whole_segments:
            continue  # 上限の12字で切れた並び
        if inside_count.get(gram, 0) * 2 > seen_count.get(gram, 1):
            continue  # 言葉の途中で始まる・終わる所が半分を超える
        valid[gram] = ids

    # 1語に助詞が1字付いただけの並び（「献立は」「台所に」）は、1語の方があれば落とす。
    # 先に落とすのは、助詞の付いた方が1語の方を覆って消さないようにするため。
    # 中に助詞がある並び（「月曜の朝15分で」）は1語ではないので、助詞の付いた形のまま残す
    valid = {
        gram: ids
        for gram, ids in valid.items()
        if not (
            len(gram) > 2
            and gram[-1] in MARKET_PARTICLES
            and gram[:-1] in valid
            and not any(character in MARKET_PARTICLES for character in gram[:-1])
        )
    }
    # 長い並びに含まれる短い並びは、長い方が短い方の本数の8割以上に出る時に落とす
    cover: Dict[str, int] = {}
    for longer, ids in valid.items():
        for size in range(MARKET_GRAM_MIN, len(longer)):
            for start in range(0, len(longer) - size + 1):
                part = longer[start : start + size]
                if part in valid and len(ids) > cover.get(part, 0):
                    cover[part] = len(ids)
    kept = [
        (gram, ids)
        for gram, ids in valid.items()
        if cover.get(gram, 0) < MARKET_COVER_RATIO * len(ids)
    ]
    kept.sort(key=lambda item: (-len(item[1]), -len(item[0]), item[0]))
    return kept


def people_count(posts: Sequence[MarketPost], ids: Iterable[int]) -> int:
    """書き手の人数。書き手が分からない投稿は1本を1人と数える（多めに見積もる）。"""
    chosen = [posts[index] for index in ids]
    return len({post.author for post in chosen if post.author}) + sum(1 for post in chosen if not post.author)


def is_copy_like(posts: Sequence[MarketPost], ids: Iterable[int], phrase: str) -> bool:
    return len(compact_text(phrase)) >= MARKET_COPY_MIN_CHARS and people_count(posts, ids) <= MARKET_COPY_MAX_PEOPLE


def edge_trimmed(text: str) -> str:
    characters = list(text.strip())
    while characters and unicodedata.category(characters[0])[0] in ("P", "S", "Z"):
        characters.pop(0)
    while characters and unicodedata.category(characters[-1])[0] in ("P", "S", "Z"):
        characters.pop()
    return "".join(characters)


def select_grams(
    grams: Sequence[Tuple[str, Set[int]]], top: int, posts: Sequence[MarketPost]
) -> List[Tuple[str, Set[int], List[str]]]:
    """上位の言い回しを選ぶ。同じ投稿の組の、同じ文（。！？で切った所）から出る並び（1つの決まり文句の切れ端）は
    1行にまとめ、その文の中で切れ端を全部覆う所を、原文のまま見せる（「献立は、焼く・煮る・炒めるの3パターンで回してください」）。

    返り値は（見せる言い回し, 出る投稿, まとめた並び）の一覧。
    """
    groups: List[Dict[str, object]] = []
    for gram, ids in grams:
        line = next(
            (sentence for sentence in MARKET_SENTENCE_SPLIT_RE.split(example_line(posts, ids, gram)) if gram in sentence),
            "",
        )
        group = next((item for item in groups if item["ids"] == ids and item["line"] == line), None)
        if group is not None:
            group["members"].append(gram)  # type: ignore[union-attr]
            continue
        groups.append({"ids": ids, "line": line, "members": [gram]})
    selected: List[Tuple[str, Set[int], List[str]]] = []
    for group in groups:
        if len(selected) >= top:
            break
        members: List[str] = group["members"]  # type: ignore[assignment]
        line = str(group["line"])
        display = members[0]
        if len(members) > 1 and line:
            positions = [(line.find(member), line.find(member) + len(member)) for member in members if member in line]
            if positions:
                display = edge_trimmed(line[min(start for start, _ in positions) : max(end for _, end in positions)])
        if is_copy_like(posts, group["ids"], display):  # type: ignore[arg-type]
            continue  # 1人の文の写しに近い長い行は、表に載せない（tn_check の MARKET_COPY に止められるため）
        selected.append((display, group["ids"], members))  # type: ignore[arg-type]
    return selected


def sentence_ending(sentence: str) -> str:
    """文の終わりのかな（〜してください・〜です など）。漢字・カタカナで終わる時は空を返す。"""
    characters = list(sentence.rstrip())
    while characters and unicodedata.category(characters[-1])[0] not in ("L", "N"):
        characters.pop()
    tail: List[str] = []
    while characters and ("ぁ" <= characters[-1] <= "ゟ" or characters[-1] == "ー"):
        tail.insert(0, characters.pop())
    return "".join(tail)


def frequent_endings(posts: Sequence[MarketPost]) -> Tuple[List[Tuple[str, Set[int], str]], Set[int]]:
    """文末のかな（2〜6字）が何本の投稿に出るか。同じ本数の長い終わり方に含まれる短い物は落とす。"""
    occurrences: Dict[str, Set[int]] = {}
    examples: Dict[str, str] = {}
    noun_endings: Set[int] = set()
    for index, post in enumerate(posts):
        for sentence in MARKET_SENTENCE_SPLIT_RE.split(post.text):
            sentence = sentence.strip()
            if not sentence:
                continue
            tail = sentence_ending(sentence)
            if not tail:
                if any(unicodedata.category(character)[0] in ("L", "N") for character in sentence):
                    noun_endings.add(index)
                continue
            for size in range(2, min(MARKET_ENDING_MAX, len(tail)) + 1):
                ending = tail[-size:]
                occurrences.setdefault(ending, set()).add(index)
                examples.setdefault(ending, sentence)
    counts = {ending: len(ids) for ending, ids in occurrences.items()}
    covered = {
        longer[1:]
        for longer, count in counts.items()
        if len(longer) > 2 and counts.get(longer[1:]) == count
    }
    # 1字短い終わり方の半分に届かない長い物（「〜べてください」など、動詞の送り仮名まで入った物）は落とす
    thin = {
        ending
        for ending, count in counts.items()
        if len(ending) > 2 and count * 2 < counts.get(ending[1:], 0)
    }
    kept = [
        (ending, ids, examples[ending])
        for ending, ids in occurrences.items()
        if len(ids) >= 2 and ending not in covered and ending not in thin
    ]
    kept.sort(key=lambda item: (-len(item[1]), -len(item[0]), item[0]))
    return kept[:MARKET_ENDING_TOP], noun_endings


def ids_authors_text(posts: Sequence[MarketPost], ids: Iterable[int]) -> str:
    chosen = [posts[index] for index in ids]
    authors = {post.author for post in chosen if post.author}
    unknown = sum(1 for post in chosen if not post.author)
    if not authors:
        return "不明"
    return f"{len(authors)}人" + (f"＋不明{unknown}本" if unknown else "")


def example_line(posts: Sequence[MarketPost], ids: Set[int], gram: str) -> str:
    for index in sorted(ids):
        for line in posts[index].lines:
            if gram in line:
                return line
    return ""


def build_market_words_text(posts: Sequence[MarketPost], summary: Dict[str, int], top: int) -> Tuple[str, int]:
    endings, noun_endings = frequent_endings(posts)
    grams = select_grams(frequent_grams(posts, [ending for ending, _, _ in endings]), top, posts)
    lines = [
        "# 市場の言葉",
        "",
        f"- 作った日: {date.today().isoformat()}",
        f"- {market_summary_text(summary)}",
        "- この表は道具が数えた物。手で言葉を足さない（集めた投稿が増えたら `market-words` で作り直す）",
        "",
        f"## よく出る言い回し（{MARKET_PHRASE_MIN_POSTS}本以上の投稿に出る {MARKET_GRAM_MIN}〜{MARKET_GRAM_MAX}字の並び・上位{top}）",
        "",
        "同じ投稿の同じ文から出る並び（1つの決まり文句の切れ端）は、その文の原文のまま1行にまとめています。",
        "",
    ]
    if grams:
        lines.extend(["| 言い回し | 本数 | 書き手 | 例（その並びを含む1行） |", "|---|---:|---|---|"])
        for display, ids, members in grams:
            lines.append(
                f"| {table_cell(display)} | {len(ids)} | {ids_authors_text(posts, ids)} | "
                f"{table_cell(example_line(posts, ids, members[0]))} |"
            )
    else:
        lines.append(f"{MARKET_PHRASE_MIN_POSTS}本以上の投稿に出る言い回しは、まだありません。")

    first_lines: Dict[str, List[int]] = {}
    for index, post in enumerate(posts):
        first_lines.setdefault(compact_text(post.first_line), []).append(index)

    def first_line_key(item: Tuple[str, List[int]]) -> Tuple[int, int, int]:
        key, ids = item
        best = max((len(gram_ids) for _, gram_ids, members in grams if any(member in key for member in members)), default=0)
        return (-len(ids), -best, ids[0])

    lines.extend(
        [
            "",
            "## 1行目の一覧（原文のまま）",
            "",
            "同じ1行目の本数が多い順、次に、本数の多い言い回しが入っている順に並べています。",
            "",
            "| 1行目（原文） | 同じ1行目の本数 | 入っているよく出る言い回し |",
            "|---|---:|---|",
        ]
    )
    for key, ids in sorted(first_lines.items(), key=first_line_key):
        contained = " ／ ".join(display for display, _, members in grams if any(member in key for member in members))
        lines.append(f"| {table_cell(posts[ids[0]].first_line)} | {len(ids)} | {table_cell(contained)} |")

    lines.extend(["", "## 文末の形（上位）", "", "| 終わり方 | 本数 | 例 |", "|---|---:|---|"])
    for ending, ids, example in endings:
        lines.append(f"| 〜{table_cell(ending)} | {len(ids)} | {table_cell(example)} |")
    if len(noun_endings) >= 2:
        lines.append(f"| （漢字・カタカナの言葉で終わる） | {len(noun_endings)} | |")
    return "\n".join(lines).rstrip() + "\n", len(grams)


def command_market_words(args: argparse.Namespace) -> int:
    root: Path = args.directory
    if args.top < 1:
        raise InputError("--top は1以上で指定してください。")
    posts, summary = load_market_posts(root)
    if summary["total"] < MARKET_MIN_POSTS:
        # 表は作らず、前に作った表も書き換えない
        print(f"集めた投稿が {summary['total']} 本なので、表はまだ作れません（10本から）。")
        return 0
    text, gram_count = build_market_words_text(posts, summary, args.top)
    output = args.out if args.out is not None else (find_child(root, MARKET_WORDS_FILE) or root / MARKET_WORDS_FILE)
    atomic_write_text(output, text)
    print(f"市場の言葉の表を書きました: {output}（集めた投稿 {summary['total']}本・よく出る言い回し {gram_count}個）")
    return 0


def add_directory_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("directory", type=Path, metavar="DIR", help="マイナレッジのフォルダ")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="ティルナノーグのマイナレッジを安全に作成・検索・更新します。"
    )
    subparsers = parser.add_subparsers(dest="command", required=True, metavar="コマンド")

    init_parser = subparsers.add_parser("init", help="マイナレッジの雛形を作る")
    add_directory_argument(init_parser)
    init_parser.add_argument("--template", type=Path, help="雛形フォルダ（省略時は同梱の雛形）")
    init_parser.set_defaults(handler=command_init)

    add_parser = subparsers.add_parser("add-card", help="知見カードを1枚追加する")
    add_directory_argument(add_parser)
    add_parser.add_argument("--title", required=True, help="カードの題名")
    add_parser.add_argument("--kind", required=True, help="知見の種類")
    add_parser.add_argument("--stages", required=True, help="使う工程（カンマ区切り）")
    add_parser.add_argument("--source", required=True, help="情報源")
    add_parser.add_argument("--source-ref", required=True, help="情報源のファイルや場所")
    add_parser.add_argument("--said-by", required=True, help="発言者")
    add_parser.add_argument("--confidence", required=True, help="確かさ")
    body_group = add_parser.add_mutually_exclusive_group(required=True)
    body_group.add_argument("--body", help="カード本文")
    body_group.add_argument("--body-file", type=Path, help="カード本文を読む UTF-8 ファイル（- なら標準入力から読む）")
    add_parser.add_argument("--date", dest="card_date", help="日付（YYYY-MM-DD、省略時は今日）")
    add_parser.set_defaults(handler=command_add_card)

    similar_parser = subparsers.add_parser("similar", help="似た active カードを探す")
    add_directory_argument(similar_parser)
    similar_parser.add_argument("--text", required=True, help="比べたい文章")
    similar_parser.add_argument("--top", type=int, default=5, help="表示件数（既定: 5）")
    similar_parser.add_argument("--json", action="store_true", help="JSON で表示する")
    similar_parser.set_defaults(handler=command_similar)

    strengthen_parser = subparsers.add_parser("strengthen", help="カードを強化して出典を足す")
    add_directory_argument(strengthen_parser)
    strengthen_parser.add_argument("card_id", metavar="ID", help="強化するカードID")
    strengthen_parser.add_argument("--source-ref", required=True, help="追加する出典のパス")
    strengthen_parser.add_argument(
        "--confidence",
        help="新しい出典で確かさが上がった時の値（講師明言／実測／推測。下げる変更は不可）",
    )
    strengthen_parser.set_defaults(handler=command_strengthen)

    supersede_parser = subparsers.add_parser("supersede", help="古いカードを更新済みにする")
    add_directory_argument(supersede_parser)
    supersede_parser.add_argument("old_id", metavar="OLD", help="古いカードID")
    supersede_parser.add_argument("--by", dest="new_id", required=True, help="更新先のカードID")
    supersede_parser.set_defaults(handler=command_supersede)

    index_parser = subparsers.add_parser("index", help="索引を作り直す")
    add_directory_argument(index_parser)
    index_parser.set_defaults(handler=command_index)

    log_parser = subparsers.add_parser("log", help="育成ログに1行足す")
    add_directory_argument(log_parser)
    log_parser.add_argument("--input", dest="input_text", required=True, help="取り込んだもの")
    log_parser.add_argument("--new", dest="new_count", type=int, required=True, help="新規カード数")
    log_parser.add_argument(
        "--strengthened", dest="strengthened_count", type=int, required=True, help="強化したカード数"
    )
    log_parser.add_argument(
        "--superseded", dest="superseded_count", type=int, required=True, help="更新済みにしたカード数"
    )
    log_parser.add_argument("--next", dest="next_text", required=True, help="次に変わること")
    log_parser.set_defaults(handler=command_log)

    select_parser = subparsers.add_parser("select", help="工程に合う active カードを選ぶ")
    add_directory_argument(select_parser)
    select_parser.add_argument("--stage", required=True, help="使う工程")
    select_parser.add_argument("--limit", type=int, default=12, help="最大件数（既定: 12）")
    select_parser.add_argument("--json", action="store_true", help="JSON で表示する")
    select_parser.set_defaults(handler=command_select)

    status_parser = subparsers.add_parser("status", help="カード数と直近ログを表示する")
    add_directory_argument(status_parser)
    status_parser.set_defaults(handler=command_status)

    migrate_parser = subparsers.add_parser("migrate", help="マイナレッジ形式の版を確認する")
    add_directory_argument(migrate_parser)
    migrate_parser.set_defaults(handler=command_migrate)

    export_parser = subparsers.add_parser("export", help="マイナレッジを1ファイルにまとめる")
    add_directory_argument(export_parser)
    export_parser.add_argument(
        "--out",
        type=Path,
        help="出力ファイル（省略時は親フォルダのマイナレッジ_まとめ.md）",
    )
    export_parser.set_defaults(handler=command_export)

    import_parser = subparsers.add_parser("import", help="まとめファイルをマイナレッジに書き戻す")
    import_parser.add_argument("file", type=Path, metavar="FILE", help="マイナレッジ_まとめ.md")
    add_directory_argument(import_parser)
    import_parser.add_argument("--overwrite", action="store_true", help="既存ファイルを上書きする")
    import_parser.set_defaults(handler=command_import)

    add_source_parser = subparsers.add_parser("add-source", help="長い原文（文字起こしなど）をファイルのまま取り込み、区切りに分ける")
    add_directory_argument(add_source_parser)
    add_source_parser.add_argument("--kind", required=True, help="seminar／feedback／results／sample")
    add_source_parser.add_argument("--file", dest="files", type=Path, action="append", help="取り込むファイル（複数可）")
    add_source_parser.add_argument("--from-dir", type=Path, help="このフォルダの中の文字のファイルを全部取り込む")
    add_source_parser.add_argument(
        "--prompt-json",
        dest="prompt_jsons",
        type=Path,
        action="append",
        help="チャットに貼られた長い文を、フックが保存した JSON（_受け取り/*.json）から取り込む（複数可）",
    )
    add_source_parser.add_argument("--title", help="題名（ファイルが1つの時だけ。省略時はファイル名）")
    add_source_parser.add_argument("--date", dest="source_date", help="日付（YYYY-MM-DD。セミナーの日が分かればその日。省略時は今日）")
    add_source_parser.add_argument("--part-chars", type=int, default=DEFAULT_PART_CHARS, help=f"1つの区切りの字数（既定: {DEFAULT_PART_CHARS}）")
    add_source_parser.add_argument("--allow-duplicate", action="store_true", help="取り込み済みと同じ中身でも、もう一度取り込む")
    add_source_parser.add_argument("--json", action="store_true", help="JSON で表示する")
    add_source_parser.set_defaults(handler=command_add_source)

    ingest_status_parser = subparsers.add_parser("ingest-status", help="取り込み中の素材と、次に読む区切りを表示する")
    add_directory_argument(ingest_status_parser)
    ingest_status_parser.add_argument("--json", action="store_true", help="JSON で表示する")
    ingest_status_parser.set_defaults(handler=command_ingest_status)

    ingest_done_parser = subparsers.add_parser("ingest-done", help="区切りを読み終えたことと、作ったカードを記録する")
    add_directory_argument(ingest_done_parser)
    ingest_done_parser.add_argument("source_id", metavar="ID", help="素材の id（S-YYYYMMDD-NNN）")
    ingest_done_parser.add_argument("--part", type=int, required=True, help="区切りの番号")
    ingest_done_parser.add_argument("--cards", help="この区切りから作った・強化したカードの id（カンマ区切り。無ければ省略）")
    ingest_done_parser.add_argument("--note", help="メモ（例: 雑談だけでカード無し）")
    ingest_done_parser.set_defaults(handler=command_ingest_done)

    market_add_parser = subparsers.add_parser(
        "market-add", help="集めた他人の投稿を、原文のまま 50_市場の投稿 に保存する（カードにはしない）"
    )
    add_directory_argument(market_add_parser)
    market_input = market_add_parser.add_mutually_exclusive_group(required=True)
    market_input.add_argument("--file", type=Path, help="貼られた投稿の入った UTF-8 ファイル")
    market_input.add_argument(
        "--prompt-json",
        type=Path,
        help="チャットに貼られた長い文を、フックが保存した JSON（_受け取り/*.json）から読む",
    )
    market_input.add_argument("--text-file", type=Path, help="投稿の入ったファイル（- なら標準入力から読む）")
    market_add_parser.add_argument("--note", help="一言メモ（例: 金運で検索・コメントが多い順）")
    market_add_parser.set_defaults(handler=command_market_add)

    market_count_parser = subparsers.add_parser("market-count", help="句が、集めた投稿の何本に出るかを数える")
    add_directory_argument(market_count_parser)
    market_count_parser.add_argument("--phrase", dest="phrases", action="append", required=True, help="数える句（複数可）")
    market_count_parser.add_argument("--json", action="store_true", help="JSON で表示する")
    market_count_parser.set_defaults(handler=command_market_count)

    market_words_parser = subparsers.add_parser("market-words", help="集めた投稿から、市場の言葉の表（市場の言葉.md）を作る")
    add_directory_argument(market_words_parser)
    market_words_parser.add_argument("--top", type=int, default=40, help="よく出る言い回しの表示件数（既定: 40）")
    market_words_parser.add_argument("--out", type=Path, help="出力ファイル（省略時はマイナレッジの 市場の言葉.md）")
    market_words_parser.set_defaults(handler=command_market_words)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except InputError as exc:
        eprint(f"入力エラー: {exc}")
        return 2
    except OSError as exc:
        eprint(f"入力エラー: ファイルまたはフォルダを操作できません（{exc}）")
        return 2


if __name__ == "__main__":
    sys.exit(main())
