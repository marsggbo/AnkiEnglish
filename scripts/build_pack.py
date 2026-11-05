#!/usr/bin/env python3
"""校验 AnkiEnglish 词条并生成 CSV、Anki 文件与静态网页。"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import re
import shutil
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CSV_FIELDS = [
    "id", "show", "episode", "term", "ipa", "definition_zh", "scene_sentence",
    "scene_translation_zh", "everyday_example", "everyday_translation_zh", "level",
    "category", "register", "review_status", "source_name", "source_url",
]
CARD_FIELDS = [
    "term", "ipa", "definition_zh", "scene_sentence", "scene_translation_zh",
    "everyday_example", "everyday_translation_zh", "level", "category", "register",
    "review_status", "notes",
]
ALLOWED_LEVELS = {"B2", "C1", "待复核"}
ALLOWED_CATEGORIES = {
    "phrasal verb", "idiom", "collocation", "slang", "word", "sentence pattern",
}


def slugify(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return value or "show"


def episode_code(season: Any, episode: Any) -> str:
    try:
        season_number = int(season)
        episode_number = int(episode)
    except (TypeError, ValueError) as exc:
        raise ValueError("metadata.season 和 metadata.episode 必须是整数") from exc
    if season_number < 1 or episode_number < 1:
        raise ValueError("season 和 episode 必须大于 0")
    return f"S{season_number:02d}E{episode_number:02d}"


def canonical(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    value = value.translate(str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"', "…": "..."}))
    value = re.sub(r"[^\w']+", " ", value, flags=re.UNICODE)
    return re.sub(r"\s+", " ", value).strip()


def mark_review(card: dict[str, Any], reason: str, warnings: list[dict[str, Any]], index: int) -> None:
    card["review_status"] = "待复核"
    notes = str(card.get("notes", "")).strip()
    if reason not in notes:
        card["notes"] = f"{notes}；{reason}".strip("；")
    warnings.append({"card": index, "term": card.get("term", ""), "reason": reason})


def stable_id(show: str, episode: str, card: dict[str, Any]) -> str:
    raw = "\x1f".join([show, episode, str(card.get("term", "")), str(card.get("scene_sentence", ""))])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def html_block(card: dict[str, Any], front: bool) -> str:
    esc = lambda key: html.escape(str(card.get(key, "")), quote=True)
    if front:
        return (
            f'<div class="term"><strong>{esc("term")}</strong> '
            f'<span class="ipa">{esc("ipa")}</span></div>'
            f'<div class="scene">{esc("scene_sentence")}</div>'
        )
    status = "" if card.get("review_status") == "已核验" else '<div><strong>⚠ 待复核</strong></div>'
    return (
        f'<div class="definition">{esc("definition_zh")}</div>'
        f'<div class="translation">剧中译文：{esc("scene_translation_zh")}</div>'
        f'<hr><div class="example">日常例句：{esc("everyday_example")}</div>'
        f'<div class="translation">{esc("everyday_translation_zh")}</div>'
        f'<div class="meta">{esc("level")} · {esc("category")} · {esc("register")}</div>{status}'
    )


def write_review_csv(path: Path, cards: list[dict[str, Any]], metadata: dict[str, Any], episode: str) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for card in cards:
            writer.writerow({
                "id": card["id"],
                "show": metadata["show"],
                "episode": episode,
                "term": card["term"],
                "ipa": card["ipa"],
                "definition_zh": card["definition_zh"],
                "scene_sentence": card["scene_sentence"],
                "scene_translation_zh": card["scene_translation_zh"],
                "everyday_example": card["everyday_example"],
                "everyday_translation_zh": card["everyday_translation_zh"],
                "level": card["level"],
                "category": card["category"],
                "register": card["register"],
                "review_status": card["review_status"],
                "source_name": metadata.get("source_name", "待复核"),
                "source_url": metadata.get("source_url", ""),
            })


def write_anki_csv(path: Path, cards: list[dict[str, Any]], show: str, episode: str) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write("#separator:Comma\n")
        handle.write("#html:true\n")
        handle.write("#notetype:Basic\n")
        handle.write(f"#deck:AnkiEnglish::{show}\n")
        handle.write("#columns:Front,Back,Tags\n")
        handle.write("#tags column:3\n")
        writer = csv.writer(handle, quoting=csv.QUOTE_ALL, lineterminator="\n")
        for card in cards:
            tags = " ".join([
                "AnkiEnglish", slugify(show), episode.lower(), card["level"].lower(),
                card["category"].replace(" ", "-").lower(),
            ])
            writer.writerow([html_block(card, True), html_block(card, False), tags])


def main() -> int:
    parser = argparse.ArgumentParser(description="构建 AnkiEnglish 学习包")
    parser.add_argument("--input", type=Path, required=True, help="词条 JSON")
    parser.add_argument("--transcript", type=Path, required=True, help="清洗后的字幕")
    parser.add_argument("--output-dir", type=Path, required=True, help="输出目录")
    parser.add_argument("--templates", type=Path, help="网页模板目录")
    parser.add_argument("--expected-count", type=int, default=50)
    parser.add_argument("--daily-new-limit", type=int, default=10)
    parser.add_argument("--desired-retention", type=float, default=0.90)
    parser.add_argument("--strict", action="store_true", help="任何校验警告都返回失败")
    args = parser.parse_args()

    if not args.input.is_file() or not args.transcript.is_file():
        parser.error("--input 和 --transcript 必须指向存在的文件")
    if args.expected_count < 1 or args.daily_new_limit < 1:
        parser.error("数量参数必须大于 0")
    if not 0.7 <= args.desired_retention <= 0.99:
        parser.error("--desired-retention 必须在 0.70 到 0.99 之间")

    templates = args.templates or Path(__file__).resolve().parent.parent / "templates"
    required_templates = ["index.html", "app.js", "styles.css"]
    missing_templates = [name for name in required_templates if not (templates / name).is_file()]
    if missing_templates:
        parser.error(f"缺少网页模板：{', '.join(missing_templates)}")

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    metadata = payload.get("metadata")
    raw_cards = payload.get("cards")
    if not isinstance(metadata, dict) or not isinstance(raw_cards, list):
        parser.error("输入 JSON 必须包含 metadata 对象和 cards 数组")
    if not str(metadata.get("show", "")).strip():
        parser.error("metadata.show 不能为空")

    show = str(metadata["show"]).strip()
    episode = episode_code(metadata.get("season"), metadata.get("episode"))
    transcript_text = args.transcript.read_text(encoding="utf-8-sig", errors="replace")
    transcript_canonical = canonical(transcript_text)
    warnings: list[dict[str, Any]] = []
    cards: list[dict[str, Any]] = []
    seen_terms: set[str] = set()
    seen_sentences: set[str] = set()

    for index, raw_card in enumerate(raw_cards, start=1):
        if not isinstance(raw_card, dict):
            warnings.append({"card": index, "term": "", "reason": "词条不是对象，已跳过"})
            continue
        card = {field: str(raw_card.get(field, "")).strip() for field in CARD_FIELDS}
        card["review_status"] = card["review_status"] or "已核验"

        for field in CARD_FIELDS[:-2]:
            if not card[field]:
                card[field] = "待复核"
                mark_review(card, f"缺少字段 {field}", warnings, index)
        if card["level"] not in ALLOWED_LEVELS:
            mark_review(card, f"难度等级异常：{card['level']}", warnings, index)
            card["level"] = "待复核"
        if card["category"] not in ALLOWED_CATEGORIES:
            mark_review(card, f"类别异常：{card['category']}", warnings, index)

        term_key = canonical(card["term"])
        sentence_key = canonical(card["scene_sentence"])
        if not sentence_key or sentence_key not in transcript_canonical:
            mark_review(card, "剧中原句未在清洗字幕中匹配", warnings, index)
        if term_key in seen_terms:
            mark_review(card, "词条重复", warnings, index)
        if sentence_key in seen_sentences:
            mark_review(card, "剧中原句重复", warnings, index)
        seen_terms.add(term_key)
        seen_sentences.add(sentence_key)
        card["id"] = stable_id(show, episode, card)
        cards.append(card)

    if len(cards) != args.expected_count:
        warnings.append({
            "card": None,
            "term": "",
            "reason": f"词条数量为 {len(cards)}，预期 {args.expected_count}",
        })

    args.output_dir.mkdir(parents=True, exist_ok=True)
    site_dir = args.output_dir / "site"
    data_dir = site_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    metadata = {
        **metadata,
        "show": show,
        "season": int(metadata["season"]),
        "episode": int(metadata["episode"]),
        "episode_code": episode,
        "show_slug": slugify(show),
    }
    settings = {
        "daily_new_limit": args.daily_new_limit,
        "desired_retention": args.desired_retention,
        "scheduler": "FSRS-7",
        "ts_fsrs_version": "6.0.0",
    }
    deck = {"metadata": metadata, "settings": settings, "cards": cards}
    built_at = datetime.now(timezone.utc).isoformat()
    manifest = {
        "schema_version": 1,
        "built_at": built_at,
        "metadata": metadata,
        "settings": settings,
        "card_count": len(cards),
        "review_required_count": sum(card["review_status"] == "待复核" for card in cards),
        "levels": dict(Counter(card["level"] for card in cards)),
        "categories": dict(Counter(card["category"] for card in cards)),
        "warnings": warnings,
    }

    review_csv = args.output_dir / "cards.csv"
    anki_csv = args.output_dir / f"anki-{slugify(show)}-{episode}.csv"
    write_review_csv(review_csv, cards, metadata, episode)
    write_anki_csv(anki_csv, cards, show, episode)
    (args.output_dir / "cards.json").write_text(json.dumps(deck, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest_path = args.output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (data_dir / "cards.json").write_text(json.dumps(deck, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    downloads_dir = site_dir / "downloads"
    downloads_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(review_csv, downloads_dir / "cards.csv")
    shutil.copy2(anki_csv, downloads_dir / "anki.csv")
    shutil.copy2(manifest_path, downloads_dir / "manifest.json")
    for name in required_templates:
        shutil.copy2(templates / name, site_dir / name)

    summary = {
        "output_dir": str(args.output_dir.resolve()),
        "cards_csv": str(review_csv.resolve()),
        "anki_csv": str(anki_csv.resolve()),
        "site": str(site_dir.resolve()),
        "card_count": len(cards),
        "review_required_count": manifest["review_required_count"],
        "warning_count": len(warnings),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 2 if args.strict and warnings else 0


if __name__ == "__main__":
    raise SystemExit(main())
