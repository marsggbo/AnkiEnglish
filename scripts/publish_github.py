#!/usr/bin/env python3
"""把 AnkiEnglish 学习包增量发布到 GitHub Pages。"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def run(command: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, check=check, text=True, capture_output=True)


def gh_json(command: list[str], check: bool = True) -> tuple[subprocess.CompletedProcess[str], dict[str, Any] | None]:
    result = run(["gh", *command], check=check)
    try:
        return result, json.loads(result.stdout) if result.stdout.strip() else None
    except json.JSONDecodeError:
        return result, None


def copy_site(pack_dir: Path, docs_dir: Path, manifest: dict[str, Any], templates: Path) -> tuple[Path, dict[str, Any]]:
    metadata = manifest["metadata"]
    show_slug = metadata["show_slug"]
    episode_code = metadata["episode_code"]
    target = docs_dir / "episodes" / show_slug / episode_code
    target.mkdir(parents=True, exist_ok=True)
    shutil.copytree(pack_dir / "site", target, dirs_exist_ok=True)

    docs_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(templates / "catalog.html", docs_dir / "index.html")
    shutil.copy2(templates / "catalog.js", docs_dir / "catalog.js")
    shutil.copy2(templates / "styles.css", docs_dir / "styles.css")

    catalog_path = docs_dir / "catalog.json"
    if catalog_path.is_file():
        try:
            catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"现有 docs/catalog.json 不是有效 JSON：{exc}") from exc
    else:
        catalog = {"schema_version": 1, "episodes": []}

    item = {
        "show": metadata["show"],
        "show_slug": show_slug,
        "season": metadata["season"],
        "episode": metadata["episode"],
        "episode_code": episode_code,
        "card_count": manifest["card_count"],
        "review_required_count": manifest["review_required_count"],
        "source_name": metadata.get("source_name", "待复核"),
        "source_url": metadata.get("source_url", ""),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "url": f"episodes/{show_slug}/{episode_code}/",
    }
    episodes = [
        entry for entry in catalog.get("episodes", [])
        if not (entry.get("show_slug") == show_slug and entry.get("episode_code") == episode_code)
    ]
    episodes.append(item)
    episodes.sort(key=lambda entry: (entry.get("show", "").casefold(), entry.get("season", 0), entry.get("episode", 0)))
    catalog = {"schema_version": 1, "episodes": episodes}
    catalog_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (docs_dir / ".nojekyll").touch()
    return target, item


def configure_pages(repo: str, branch: str) -> str:
    _, existing = gh_json(["api", f"repos/{repo}/pages"], check=False)
    method = "PUT" if existing else "POST"
    result, payload = gh_json([
        "api", "--method", method, f"repos/{repo}/pages",
        "-f", f"source[branch]={branch}", "-f", "source[path]=/docs",
    ], check=False)
    if result.returncode != 0:
        raise RuntimeError(f"仓库已推送，但 Pages 配置失败：{result.stderr.strip()}")
    if payload and payload.get("html_url"):
        return str(payload["html_url"])
    _, page = gh_json(["api", f"repos/{repo}/pages"], check=False)
    if page and page.get("html_url"):
        return str(page["html_url"])
    return ""


def main() -> int:
    parser = argparse.ArgumentParser(description="发布 AnkiEnglish 学习包到 GitHub Pages")
    parser.add_argument("--pack-dir", type=Path, required=True)
    parser.add_argument("--repo", required=True, help="OWNER/REPO")
    parser.add_argument("--branch", default="main")
    parser.add_argument("--create-public", action="store_true")
    parser.add_argument("--confirm-publish", action="store_true", help="确认执行外部写入")
    parser.add_argument("--skip-pages", action="store_true", help="仅推送内容，跳过 Pages API 配置")
    parser.add_argument("--keep-workdir", action="store_true", help="失败时保留临时克隆")
    args = parser.parse_args()

    if not args.confirm_publish:
        parser.error("发布会写入 GitHub；取得用户明确授权后再传 --confirm-publish")
    if "/" not in args.repo or args.repo.startswith("/") or args.repo.endswith("/"):
        parser.error("--repo 必须是 OWNER/REPO")

    pack_dir = args.pack_dir.resolve()
    manifest_path = pack_dir / "manifest.json"
    site_dir = pack_dir / "site"
    if not manifest_path.is_file() or not site_dir.is_dir():
        parser.error("学习包必须包含 manifest.json 和 site/ 目录")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    templates = Path(__file__).resolve().parent.parent / "templates"
    for name in ("catalog.html", "catalog.js", "styles.css"):
        if not (templates / name).is_file():
            parser.error(f"缺少模板：{templates / name}")

    auth = run(["gh", "auth", "status"], check=False)
    if auth.returncode != 0:
        raise SystemExit("GitHub CLI 尚未登录。请先运行 gh auth login；不要在聊天中发送 token。")

    view, repo_info = gh_json(["repo", "view", args.repo, "--json", "nameWithOwner,isPrivate,url"], check=False)
    created = False
    if view.returncode != 0:
        if not args.create_public:
            raise SystemExit("目标仓库不存在或不可访问。取得创建公开仓库授权后使用 --create-public。")
        create = run([
            "gh", "repo", "create", args.repo, "--public", "--add-readme",
            "--description", "AnkiEnglish learning decks and GitHub Pages",
        ], check=False)
        if create.returncode != 0:
            raise SystemExit(f"创建仓库失败：{create.stderr.strip()}")
        created = True
    elif repo_info and repo_info.get("isPrivate"):
        print("警告：目标仓库是私有仓库；Pages 可用性取决于 GitHub 套餐。")

    temp_root = Path(tempfile.mkdtemp(prefix="ankienglish-publish-"))
    workdir = temp_root / "repo"
    try:
        clone = run(["gh", "repo", "clone", args.repo, str(workdir)], check=False)
        if clone.returncode != 0:
            raise RuntimeError(f"克隆仓库失败：{clone.stderr.strip()}")

        remote_branch = run(["git", "rev-parse", "--verify", f"origin/{args.branch}"], cwd=workdir, check=False)
        if remote_branch.returncode == 0:
            run(["git", "checkout", "-B", args.branch, f"origin/{args.branch}"], cwd=workdir)
        else:
            run(["git", "checkout", "-b", args.branch], cwd=workdir)

        target, item = copy_site(pack_dir, workdir / "docs", manifest, templates)
        run(["git", "add", "docs"], cwd=workdir)
        diff = run(["git", "diff", "--cached", "--quiet"], cwd=workdir, check=False)
        if diff.returncode == 1:
            run(["git", "config", "user.name", "AnkiEnglish Bot"], cwd=workdir)
            run(["git", "config", "user.email", "ankienglish@users.noreply.github.com"], cwd=workdir)
            message = f"Add {item['show']} {item['episode_code']} learning deck"
            run(["git", "commit", "-m", message], cwd=workdir)
            push = run(["git", "push", "origin", args.branch], cwd=workdir, check=False)
            if push.returncode != 0:
                raise RuntimeError(f"推送失败，未执行强推：{push.stderr.strip()}")
        elif diff.returncode != 0:
            raise RuntimeError("无法检查 Git 暂存区状态")

        pages_url = "" if args.skip_pages else configure_pages(args.repo, args.branch)
        episode_url = f"{pages_url.rstrip('/')}/{item['url']}" if pages_url else ""
        print(json.dumps({
            "repo": args.repo,
            "created": created,
            "branch": args.branch,
            "published_path": str(target.relative_to(workdir)),
            "pages_configured": not args.skip_pages,
            "pages_url": pages_url,
            "episode_url": episode_url,
        }, ensure_ascii=False, indent=2))
        return 0
    except Exception:
        if args.keep_workdir:
            print(f"临时克隆保留在：{workdir}")
            temp_root = None  # type: ignore[assignment]
        raise
    finally:
        if temp_root is not None:
            shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
