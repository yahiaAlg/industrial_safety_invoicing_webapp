#!/usr/bin/env python3
"""
replace_from_docs.py

Sync content from docs/master_backend/<target>/<app>_<target>.py
into <app>/<target>.py at the project root.

Usage:
    python replace_from_docs.py --target models
    python replace_from_docs.py --target all
    python replace_from_docs.py --target views --dry-run
    python replace_from_docs.py --target models --app intrants
"""

import argparse
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
DOCS_DIR = PROJECT_ROOT / "docs" / "master_backend"

TARGETS = ["admin", "forms", "models", "signals", "urls", "utils", "views", "resources"]
APPS = [
    "achats",
    "clients",
    "core",
    "depenses",
    "elevage",
    "intrants",
    "production",
    "reporting",
    "stock",
]


def sync_one(app: str, target: str, dry_run: bool, backup: bool) -> bool:
    src = DOCS_DIR / target / f"{app}_{target}.py"
    dst = PROJECT_ROOT / app / f"{target}.py"

    if not src.exists():
        print(f"  [skip] no doc file: {src.relative_to(PROJECT_ROOT)}")
        return False
    if not dst.parent.exists():
        print(f"  [skip] app folder missing: {dst.parent.relative_to(PROJECT_ROOT)}")
        return False

    if dry_run:
        print(
            f"  [dry-run] {src.relative_to(PROJECT_ROOT)} -> {dst.relative_to(PROJECT_ROOT)}"
        )
        return True

    if backup and dst.exists():
        shutil.copy2(dst, dst.with_suffix(".py.bak"))

    shutil.copy2(src, dst)
    print(f"  [ok] {src.relative_to(PROJECT_ROOT)} -> {dst.relative_to(PROJECT_ROOT)}")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Sync docs/master_backend into app source files."
    )
    parser.add_argument(
        "--target",
        required=True,
        choices=TARGETS + ["all"],
        help="Which file type to sync (models, views, ... or 'all').",
    )
    parser.add_argument(
        "--app", choices=APPS, help="Limit to a single app (default: all apps)."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would happen without writing files.",
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Don't keep a .py.bak of overwritten files.",
    )
    args = parser.parse_args()

    targets = TARGETS if args.target == "all" else [args.target]
    apps = [args.app] if args.app else APPS
    backup = not args.no_backup

    if not DOCS_DIR.exists():
        sys.exit(f"docs folder not found: {DOCS_DIR}")

    total, done = 0, 0
    for target in targets:
        print(f"\n== target: {target} ==")
        for app in apps:
            total += 1
            if sync_one(app, target, args.dry_run, backup):
                done += 1

    print(f"\n{done}/{total} files synced{' (dry-run)' if args.dry_run else ''}.")


if __name__ == "__main__":
    main()
