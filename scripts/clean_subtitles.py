#!/usr/bin/env python3
"""清洗 SRT、VTT、网页转存文本或普通字幕文本。"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
from pathlib import Path

TIMESTAMP_RE = re.compile(
    r"^\s*(?:\d{1,2}:)?\d{1,2}:\d{2}[,.]\d{3}\s*-->\s*"
    r"(?:\d{1,2}:)?\d{1,2}:\d{2}[,.]\d{3}(?:\s+.*)?$"
)
TAG_RE = re.compile(r"<[^>]+>|\{\\[^}]+\}")
MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]*\)")
SPACE_RE = re.compile(r"\s+")
STAGE_DIRECTION_RE = re.compile(r"^\s*[\[(].{1,80}[\])]\s*$")
SEQUENCE_RE = re.compile(r"^\s*\d+\s*$")


def normalize_line(raw: str) -> str:
    line = html.unescape(raw.replace("\ufeff", ""))
    line = MARKDOWN_LINK_RE.sub(r"\1", line)
    line = TAG_RE.sub("", line)
    line = line.replace("&nbsp;", " ")
    line = SPACE_RE.sub(" ", line).strip()
    return line


def is_metadata(line: str) -> bool:
    upper = line.upper()
    return (
        not line
        or upper == "WEBVTT"
        or upper.startswith(("NOTE ", "STYLE", "REGION", "KIND:", "LANGUAGE:"))
        or TIMESTAMP_RE.match(line) is not None
        or SEQUENCE_RE.match(line) is not None
    )


def clean_timed_blocks(text: str) -> list[str]:
    output: list[str] = []
    blocks = re.split(r"\n\s*\n", text.replace("\r\n", "\n").replace("\r", "\n"))
    for block in blocks:
        body: list[str] = []
        for raw in block.splitlines():
            line = normalize_line(raw)
            if is_metadata(line):
                continue
            if STAGE_DIRECTION_RE.match(line) or line.strip("♪♫ ") == "":
                continue
            body.append(line)

        if not body:
            continue
        if len(body) > 1 and all(line.startswith(("- ", "– ", "— ")) for line in body):
            output.extend(line.lstrip("-–— ") for line in body)
        else:
            output.append(" ".join(body))
    return output


def clean_plain_lines(text: str) -> list[str]:
    output: list[str] = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").splitlines():
        line = normalize_line(raw)
        if is_metadata(line):
            continue
        if STAGE_DIRECTION_RE.match(line) or line.strip("♪♫ ") == "":
            continue
        if line.startswith(("Title:", "URL Source:", "Published Time:", "Markdown Content:")):
            continue
        output.append(line)
    return output


def deduplicate(lines: list[str], window: int = 4) -> tuple[list[str], int]:
    kept: list[str] = []
    removed = 0
    for line in lines:
        key = SPACE_RE.sub(" ", line).strip().casefold()
        recent = {SPACE_RE.sub(" ", item).strip().casefold() for item in kept[-window:]}
        if key in recent:
            removed += 1
            continue
        kept.append(line)
    return kept, removed


def detect_format(path: Path, text: str) -> str:
    suffix = path.suffix.lower()
    if suffix in {".srt", ".vtt"}:
        return suffix[1:]
    if "WEBVTT" in text[:200] or TIMESTAMP_RE.search(text):
        return "timed-text"
    return "plain"


def main() -> int:
    parser = argparse.ArgumentParser(description="清洗 SRT/VTT/普通字幕文本")
    parser.add_argument("input", type=Path, help="输入字幕文件")
    parser.add_argument("--output", type=Path, required=True, help="清洗后文本")
    parser.add_argument("--report", type=Path, help="JSON 清洗报告")
    parser.add_argument("--dedupe-window", type=int, default=4, help="去重回看行数")
    args = parser.parse_args()

    if not args.input.is_file():
        parser.error(f"输入文件不存在：{args.input}")
    if args.dedupe_window < 1:
        parser.error("--dedupe-window 必须大于 0")

    raw_bytes = args.input.read_bytes()
    text = raw_bytes.decode("utf-8-sig", errors="replace")
    source_format = detect_format(args.input, text)
    timed = source_format in {"srt", "vtt", "timed-text"}
    candidates = clean_timed_blocks(text) if timed else clean_plain_lines(text)
    lines, duplicate_count = deduplicate(candidates, args.dedupe_window)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

    report = {
        "input": str(args.input.resolve()),
        "output": str(args.output.resolve()),
        "source_format": source_format,
        "input_sha256": hashlib.sha256(raw_bytes).hexdigest(),
        "input_line_count": len(text.splitlines()),
        "candidate_line_count": len(candidates),
        "output_line_count": len(lines),
        "duplicates_removed": duplicate_count,
        "replacement_characters": text.count("�"),
        "warning": "清洗后文本过短，请检查字幕来源" if len(lines) < 100 else None,
    }
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
