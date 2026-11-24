import argparse
import logging
import os
import re
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


def link_fix_site(site_dir_path: str, dry_run: bool = False):
    site_dir = Path(site_dir_path)
    if not site_dir.exists():
        logging.error(f"Site directory '{site_dir}' does not exist.")
        return

    mode_label = " [DRY RUN]" if dry_run else ""
    logging.info(f"Targeting directory: {site_dir}{mode_label}")

    # ==========================================
    # PHASE 1: Fix Internal HTML Links (Case & Spaces)
    # ==========================================
    logging.info("Phase 1: Scanning and fixing HTML links...")

    link_pattern = re.compile(r'(href|src)\s*=\s*(["\'])(.*?)\2', re.IGNORECASE)

    def normalize_url(match):
        attr = match.group(1)
        quote = match.group(2)
        url = match.group(3)

        parts = urlsplit(url)

        # Skip external URLs, protocol-relative URLs (//...), data:, mailto:, tel:, javascript:, etc.
        if parts.scheme or parts.netloc or not parts.path:
            return match.group(0)

        # Only normalize the path component; leave ?query and #fragment intact
        new_path = parts.path.lower().replace("%20", "-").replace(" ", "-")
        if new_path == parts.path:
            return match.group(0)

        new_url = urlunsplit((parts.scheme, parts.netloc, new_path, parts.query, parts.fragment))
        return f"{attr}={quote}{new_url}{quote}"

    files_fixed = 0
    encodings_to_try = [
        "utf-8",
        "utf-8-sig",
        "windows-1252",
        "iso-8859-1",
        "iso-8859-15",
        "mac_roman",
        "utf-16",
    ]

    # Match .html and .htm case-insensitively, skipping hidden files/dirs
    for html_file in sorted(site_dir.rglob("*")):
        if not html_file.is_file():
            continue

        rel_path = html_file.relative_to(site_dir)
        if any(part.startswith(".") for part in rel_path.parts):
            continue

        if html_file.suffix.lower() not in (".html", ".htm"):
            continue

        original_text = None
        used_encoding = None

        for enc in encodings_to_try:
            try:
                original_text = html_file.read_text(encoding=enc)
                used_encoding = enc
                break
            except UnicodeDecodeError:
                continue

        if original_text is None:
            logging.error(f"Could not decode {rel_path} with any known encoding. Skipping.")
            continue

        try:
            new_text = link_pattern.sub(normalize_url, original_text)

            if original_text != new_text:
                if dry_run:
                    logging.info(f"[DRY RUN] Would fix links in: {rel_path} (Encoding: {used_encoding})")
                else:
                    html_file.write_text(new_text, encoding=used_encoding)
                    logging.debug(f"Fixed links in: {rel_path} (Encoding: {used_encoding})")
                files_fixed += 1
        except Exception as e:
            logging.error(f"Could not process {rel_path}: {e}")

    action = "Would modify" if dry_run else "Modified"
    logging.info(f"Phase 1 Complete: {action} internal links in {files_fixed} web files.")

    # ==========================================
    # PHASE 2: Rename Files and Folders (Case & Spaces)
    # ==========================================
    logging.info("Phase 2: Renaming files and folders to lowercase and replacing spaces...")

    paths = [
        p for p in site_dir.rglob("*")
        if not any(part.startswith(".") for part in p.relative_to(site_dir).parts)
    ]
    paths.sort(key=lambda x: len(x.parts), reverse=True)

    items_renamed = 0
    collisions = 0

    for path in paths:
        new_name = path.name.lower().replace(" ", "-")

        if path.name != new_name:
            new_path = path.parent / new_name

            # Guard against overwriting a distinct existing file (while allowing case-only renames on macOS/Windows)
            if new_path.exists() and not os.path.samefile(path, new_path):
                logging.warning(
                    f"Skipping rename '{path.relative_to(site_dir)}' -> '{new_name}': target already exists."
                )
                collisions += 1
                continue

            if dry_run:
                logging.info(f"[DRY RUN] Would rename: {path.relative_to(site_dir)} -> {new_name}")
            else:
                # Two-step rename to bypass macOS/Windows case-insensitivity bugs
                tmp_path = path.parent / f"{new_name}.tmp"
                path.rename(tmp_path)
                tmp_path.rename(new_path)
                logging.debug(f"Renamed: {path.name} -> {new_path.name}")

            items_renamed += 1

    rename_action = "Would rename" if dry_run else "Renamed"
    logging.info(f"Phase 2 Complete: {rename_action} {items_renamed} files/directories.")
    if collisions > 0:
        logging.warning(f"Skipped {collisions} rename(s) due to filename collisions.")

    if dry_run:
        logging.info("Dry run complete. No files were modified.")
    else:
        logging.info("Link fixing complete! You can now run the WARC generator.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fix HTML links and filenames (lowercase and remove spaces).")
    parser.add_argument(
        "-s", "--site-dir",
        default=os.environ.get("SITE_DIR", "/site"),
        help="Directory containing the static site files (default: /site)."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview link and filename changes without modifying any files."
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose line-by-line logging."
    )
    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    link_fix_site(args.site_dir, dry_run=args.dry_run)