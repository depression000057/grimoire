#!/usr/bin/env python3
"""note 統合稿から貼り付け用テキストを作る CLI。"""

from __future__ import annotations

import argparse
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple


PAID_MARKER = "---- ここから有料 ----"
VISIBLE_PAID_MARKER = "━━━━ ここから有料（note の画面で有料ラインを入れる位置） ━━━━"
HTML_COMMENT_RE = re.compile(r"<!--.*?(?:-->|\Z)", re.DOTALL)
CONTENT_TOKEN_RE = re.compile(
    r"<!--.*?(?:-->|\Z)|^(#{1,6})\s+([^\r\n]+?)\s*$",
    re.DOTALL | re.MULTILINE,
)


class InputError(Exception):
    """利用者が直せる入力エラー。"""


@dataclass
class Placeholder:
    heading_number: int
    heading: str
    content: str


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


def comment_content(comment: str) -> str:
    inner = comment[4:-3] if comment.endswith("-->") else comment[4:]
    return " ".join(inner.strip().split())


def find_placeholders(text: str) -> List[Placeholder]:
    placeholders: List[Placeholder] = []
    heading_number = 0
    current_heading = ""
    for match in CONTENT_TOKEN_RE.finditer(text):
        token = match.group(0)
        if token.startswith("<!--"):
            content = comment_content(token)
            if content.startswith("ここに"):
                placeholders.append(Placeholder(heading_number, current_heading, content))
            continue
        heading_number += 1
        current_heading = f"{match.group(1)} {match.group(2).strip()}"
    return placeholders


def remove_comments_and_memos(text: str, preserve_placeholders: bool = False) -> str:
    def replace_comment(match: re.Match[str]) -> str:
        content = comment_content(match.group(0))
        if preserve_placeholders and content.startswith("ここに"):
            return f"【{content}】"
        return ""

    without_comments = HTML_COMMENT_RE.sub(replace_comment, text)
    kept_lines = [
        line
        for line in without_comments.splitlines()
        if not line.lstrip().startswith("> 制作メモ") and not line.lstrip().startswith("<!--")
    ]
    return "\n".join(kept_lines)


def collapse_blank_lines(text: str) -> str:
    result: List[str] = []
    blank_count = 0
    for line in text.splitlines():
        if line.strip() == "":
            blank_count += 1
            if blank_count <= 2:
                result.append("")
        else:
            blank_count = 0
            result.append(line.rstrip())
    while result and result[0] == "":
        result.pop(0)
    while result and result[-1] == "":
        result.pop()
    return "\n".join(result)


def split_paid_content(text: str) -> Tuple[str, str, bool]:
    lines = text.splitlines()
    marker_index = next((index for index, line in enumerate(lines) if line.strip() == PAID_MARKER), None)
    if marker_index is None:
        return "\n".join(lines), "", False
    free = "\n".join(lines[:marker_index])
    paid_lines = [line for line in lines[marker_index + 1 :] if line.strip() != PAID_MARKER]
    return free, "\n".join(paid_lines), True


def with_final_newline(text: str) -> str:
    return text + "\n" if text else ""


def make_outputs(source_text: str) -> Tuple[str, str, str, bool, List[Placeholder]]:
    placeholders = find_placeholders(source_text)
    cleaned = remove_comments_and_memos(source_text)
    confirmation_text = remove_comments_and_memos(source_text, preserve_placeholders=True)
    free, paid, has_marker = split_paid_content(cleaned)
    confirmation_free, confirmation_paid, confirmation_has_marker = split_paid_content(confirmation_text)
    free = collapse_blank_lines(free)
    paid = collapse_blank_lines(paid)
    confirmation_free = collapse_blank_lines(confirmation_free)
    confirmation_paid = collapse_blank_lines(confirmation_paid)
    if confirmation_has_marker:
        pieces = [confirmation_free, VISIBLE_PAID_MARKER, confirmation_paid]
        full = "\n\n".join(piece for piece in pieces if piece != "")
    else:
        full = confirmation_free
    full = collapse_blank_lines(full)
    return (
        with_final_newline(free),
        with_final_newline(paid),
        with_final_newline(full),
        has_marker,
        placeholders,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="note 統合稿から、無料部分・有料部分・確認用全文を UTF-8 で書き出します。"
    )
    parser.add_argument("input", type=Path, metavar="統合稿.md", help="元になる UTF-8 の Markdown ファイル")
    parser.add_argument("--outdir", type=Path, help="出力先フォルダ（省略時は入力ファイルと同じ場所）")
    parser.add_argument(
        "--settings",
        type=Path,
        help="00_わたしの設定.md（禁止したい言葉も含めて機械チェックする時に渡す）",
    )
    parser.add_argument(
        "--no-check",
        action="store_true",
        help="書き出す前の機械チェック（tn_check.py note）を行わない。チェックを別に済ませた時だけ使う",
    )
    return parser


def note_violations(path: Path, settings: Optional[Path]) -> Optional[List[dict]]:
    """同じフォルダの tn_check.py で note の違反を調べる。tn_check.py が無ければ None。"""
    import importlib.util

    checker_path = Path(__file__).with_name("tn_check.py")
    if not checker_path.is_file():
        return None
    spec = importlib.util.spec_from_file_location("tn_check_for_paste", checker_path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclass が自分のモジュールを探せるように先に登録する
    spec.loader.exec_module(module)
    result, _ = module.check_note(path, settings, None)
    return list(result.get("violations", []))


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        source = read_text(args.input)
        if not args.no_check:
            violations = note_violations(args.input, args.settings)
            if violations is None:
                print("注意: tn_check.py が見つからないため、書き出す前の機械チェックを行えませんでした。")
            elif violations:
                print("機械チェックの違反が残っているため、貼り付け用を書き出しませんでした。先に直してください:")
                for issue in violations:
                    print(f"- [{issue.get('code')}] {issue.get('message')}")
                return 1
        free, paid, full, has_marker, placeholders = make_outputs(source)
        outdir = args.outdir or args.input.parent
        if outdir.exists() and not outdir.is_dir():
            raise InputError(f"出力先がフォルダではありません: {outdir}")
        outdir.mkdir(parents=True, exist_ok=True)
        outputs = {
            outdir / "貼り付け_無料部分.txt": free,
            outdir / "貼り付け_有料部分.txt": paid,
            outdir / "貼り付け_全文_確認用.txt": full,
        }
        for path, content in outputs.items():
            atomic_write_text(path, content)
        if not has_marker:
            print("注意: 有料ラインがないため、全文を無料部分として書き出しました。")
        print("貼り付け用ファイルを書き出しました:")
        for path in outputs:
            print(f"- {path}")
        if placeholders:
            print("本人が公開前に埋める枠:")
            for placeholder in placeholders:
                if placeholder.heading_number:
                    location = f"見出し{placeholder.heading_number}（{placeholder.heading}）の下"
                else:
                    location = "最初の見出しより前"
                print(f"- {location}: {placeholder.content}")
            print("公開前に、確認用ファイルの【】の場所を埋めてください")
        return 0
    except InputError as exc:
        eprint(f"入力エラー: {exc}")
        return 2
    except OSError as exc:
        eprint(f"入力エラー: ファイルまたはフォルダを操作できません（{exc}）")
        return 2


if __name__ == "__main__":
    sys.exit(main())
