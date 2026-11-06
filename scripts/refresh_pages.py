#!/usr/bin/env python3
"""把最新网页模板刷新到 docs 中已有的所有剧集。"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="刷新已发布剧集的 AnkiEnglish 网页模板")
    parser.add_argument("--docs-dir", type=Path, required=True, help="仓库中的 docs 目录")
    parser.add_argument("--templates", type=Path, help="模板目录")
    args = parser.parse_args()

    docs_dir = args.docs_dir.resolve()
    templates = (args.templates or Path(__file__).resolve().parent.parent / "templates").resolve()
    required = ["index.html", "app.js", "styles.css", "catalog.html", "catalog.js"]
    missing = [name for name in required if not (templates / name).is_file()]
    if missing:
        parser.error(f"缺少模板：{', '.join(missing)}")

    episodes_root = docs_dir / "episodes"
    if not episodes_root.is_dir():
        parser.error(f"剧集目录不存在：{episodes_root}")

    refreshed: list[str] = []
    for data_file in sorted(episodes_root.glob("*/*/data/cards.json")):
        episode_dir = data_file.parent.parent
        for name in ("index.html", "app.js", "styles.css"):
            shutil.copy2(templates / name, episode_dir / name)
        refreshed.append(str(episode_dir.relative_to(docs_dir)))

    docs_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(templates / "catalog.html", docs_dir / "index.html")
    shutil.copy2(templates / "catalog.js", docs_dir / "catalog.js")
    shutil.copy2(templates / "styles.css", docs_dir / "styles.css")
    (docs_dir / ".nojekyll").touch()

    print(json.dumps({"docs_dir": str(docs_dir), "refreshed_count": len(refreshed), "episodes": refreshed}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
