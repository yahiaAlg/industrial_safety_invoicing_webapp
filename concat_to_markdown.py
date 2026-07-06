#!/usr/bin/env python3
"""
Concatenates a folder of Python files into a single master Markdown file.

Usage:
    # Using a preset default
    python concat_to_markdown.py --default urls
    python concat_to_markdown.py --default views
    python concat_to_markdown.py --default models

    # Manual
    python concat_to_markdown.py docs/master_backend/urls/
    python concat_to_markdown.py docs/master_backend/urls/ --output docs/urls/master_urls.md
    python concat_to_markdown.py docs/master_backend/ --recursive

    # List available defaults
    python concat_to_markdown.py --list-defaults
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

# ── Default schema ─────────────────────────────────────────────────────────────
# Edit these to match your project's folder structure.
# Each key: (input_folder, output_file)  — both relative to where you run the script.
DEFAULTS: dict[str, tuple[str, str]] = {
    "urls": ("docs/master_backend/urls", "docs/master_backend/urls/master_urls.md"),
    "views": ("docs/master_backend/views", "docs/master_backend/views/master_views.md"),
    "models": (
        "docs/master_backend/models",
        "docs/master_backend/models/master_models.md",
    ),
    "forms": ("docs/master_backend/forms", "docs/master_backend/forms/master_forms.md"),
    "serializers": (
        "docs/master_backend/serializers",
        "docs/master_backend/serializers/master_serializers.md",
    ),
    "admin": ("docs/master_backend/admin", "docs/master_backend/admin/master_admin.md"),
    "signals": (
        "docs/master_backend/signals",
        "docs/master_backend/signals/master_signals.md",
    ),
    "utils": ("docs/master_backend/utils", "docs/master_backend/utils/master_utils.md"),
    "tasks": ("docs/master_backend/tasks", "docs/master_backend/tasks/master_tasks.md"),
    "filters": (
        "docs/master_backend/filters",
        "docs/master_backend/filters/master_filters.md",
    ),
    "permissions": (
        "docs/master_backend/permissions",
        "docs/master_backend/permissions/master_permissions.md",
    ),
}
# ───────────────────────────────────────────────────────────────────────────────

TYPE_SUFFIXES = {
    "urls",
    "views",
    "models",
    "forms",
    "admin",
    "admins",
    "serializers",
    "signals",
    "utils",
    "utility",
    "utilities",
    "tasks",
    "permissions",
    "filters",
    "validators",
    "mixins",
    "managers",
    "middleware",
    "apps",
    "tests",
    "helpers",
}


def filename_to_header(stem: str) -> str:
    parts = stem.split("_")
    suffix_parts = []
    for part in reversed(parts):
        if part.lower() in TYPE_SUFFIXES:
            suffix_parts.insert(0, part)
        else:
            break
    if suffix_parts:
        app_parts = parts[: len(parts) - len(suffix_parts)]
        app_name = " ".join(p.capitalize() for p in app_parts) if app_parts else stem
        type_name = " ".join(p.capitalize() for p in suffix_parts)
        return f"{app_name} — {type_name}"
    return " ".join(p.capitalize() for p in parts)


def collect_files(folder: Path, pattern: str, recursive: bool) -> list[Path]:
    glob = folder.rglob if recursive else folder.glob
    return sorted(f for f in glob(pattern) if f.is_file())


def build_markdown(files: list[Path], title: str) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        f"# {title}",
        f"\n> Generated: {now} — {len(files)} file(s)\n",
        "---\n",
    ]
    for filepath in files:
        header = filename_to_header(filepath.stem)
        source = filepath.read_text(encoding="utf-8", errors="replace")
        lines += [
            f"## {header}",
            f"\n`{filepath.name}`\n",
            "```python",
            source.rstrip(),
            "```\n",
            "---\n",
        ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Concat a folder of .py files into a master Markdown file.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "folder",
        nargs="?",
        type=Path,
        default=None,
        help="Folder containing the .py files",
    )
    parser.add_argument(
        "--default",
        metavar="TYPE",
        choices=list(DEFAULTS.keys()),
        help=f"Use a preset config. Choices: {', '.join(DEFAULTS)}",
    )
    parser.add_argument(
        "--list-defaults",
        action="store_true",
        help="Print all available --default presets and exit",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output .md path (overrides --default output)",
    )
    parser.add_argument(
        "--title",
        default=None,
        help="Document title (default: derived from folder name)",
    )
    parser.add_argument(
        "--pattern", default="*.py", help="Glob pattern (default: *.py)"
    )
    parser.add_argument(
        "--recursive", action="store_true", help="Search subfolders recursively"
    )
    args = parser.parse_args()

    # ── --list-defaults ──
    if args.list_defaults:
        print("Available --default presets:\n")
        for key, (folder, output) in DEFAULTS.items():
            print(f"  --default {key:<14}  {folder}  →  {output}")
        sys.exit(0)

    # ── Resolve folder + output ──
    if args.default:
        default_folder, default_output = DEFAULTS[args.default]
        folder = Path(default_folder).resolve()
        output = args.output or Path(default_output)
    elif args.folder:
        folder = args.folder.resolve()
        output = args.output or folder / f"{folder.name}_master.md"
    else:
        parser.error("Provide a folder argument or use --default <type>")

    if not folder.is_dir():
        print(f"Error: folder not found: {folder}", file=sys.stderr)
        print(
            "Tip: check your DEFAULTS paths at the top of this script.", file=sys.stderr
        )
        sys.exit(1)

    files = collect_files(folder, args.pattern, args.recursive)
    if not files:
        print(f"No files matching '{args.pattern}' in {folder}.", file=sys.stderr)
        sys.exit(1)

    title = args.title or f"{folder.name.replace('_', ' ').title()} — Master Reference"

    print(f"[{args.default or folder.name}]  {len(files)} file(s)  →  {output}\n")
    for f in files:
        print(f"  {f.name:<45}  {filename_to_header(f.stem)}")

    markdown = build_markdown(files, title)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(markdown, encoding="utf-8")
    print(f"\n✔  Written → {output}  ({len(markdown):,} chars)")


if __name__ == "__main__":
    main()
