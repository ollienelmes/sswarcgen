import argparse
import os
import re
import logging
from pathlib import Path

def link_fix_site(site_dir_path):
    site_dir = Path(site_dir_path)
    if not site_dir.exists():
        logging.error(f"Site directory '{site_dir}' does not exist.")
        return

    logging.info(f"Targeting directory: {site_dir}")
    
    # ==========================================
    # PHASE 1: Fix Internal HTML Links (Case & Spaces)
    # ==========================================
    logging.info("Phase 1: Scanning and fixing HTML links...")
    
    link_pattern = re.compile(r'(href|src)\s*=\s*(["\'])(.*?)\2', re.IGNORECASE)

    def normalize_url(match):
        attr = match.group(1)
        quote = match.group(2)
        url = match.group(3)
        
        # Only modify internal links
        if not url.lower().startswith(('http://', 'https://', 'mailto:')):
            # Lowercase and replace both literal spaces and %20 with hyphens
            url = url.lower().replace('%20', '-').replace(' ', '-')
            
        return f'{attr}={quote}{url}{quote}'

    files_fixed = 0
    encodings_to_try = [
        "utf-8", 
        "utf-8-sig", 
        "windows-1252", 
        "iso-8859-1", 
        "iso-8859-15", 
        "mac_roman", 
        "utf-16"
    ]
    
    # Scan for both .html and .htm extensions
    for ext in ("*.html", "*.htm"):
        for html_file in site_dir.rglob(ext):
            
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
                logging.error(f"Could not decode {html_file.name} with any known encoding. Skipping.")
                continue

            try:
                new_text = link_pattern.sub(normalize_url, original_text)
                
                if original_text != new_text:
                    html_file.write_text(new_text, encoding=used_encoding)
                    logging.debug(f"Fixed links in: {html_file.relative_to(site_dir)} (Encoding: {used_encoding})")
                    files_fixed += 1
            except Exception as e:
                logging.error(f"Could not process {html_file.name}: {e}")

    logging.info(f"Phase 1 Complete: Modified internal links in {files_fixed} web files.")
    
    # ==========================================
    # PHASE 2: Rename Files and Folders (Case & Spaces)
    # ==========================================
    logging.info("Phase 2: Renaming files and folders to lowercase and replacing spaces...")
    
    paths = list(site_dir.rglob("*"))
    paths.sort(key=lambda x: len(x.parts), reverse=True)

    items_renamed = 0
    for path in paths:
        # Calculate the new name: lowercase AND spaces replaced with hyphens
        new_name = path.name.lower().replace(' ', '-')
        
        if path.name != new_name:
            new_path = path.parent / new_name
            
            # The Two-Step Rename: Bypass macOS/Windows case-insensitivity bugs
            tmp_path = path.parent / f"{new_name}.tmp"
            path.rename(tmp_path)          # Step 1: Rename to .tmp
            tmp_path.rename(new_path)      # Step 2: Rename to final lowercase/hyphenated
            
            logging.debug(f"Renamed: {path.name} -> {new_path.name}")
            items_renamed += 1

    logging.info(f"Phase 2 Complete: Renamed {items_renamed} files/directories.")
    logging.info("Link fixing complete! You can now run the WARC generator.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fix HTML links and filenames (lowercase and remove spaces).")
    parser.add_argument(
        "-s", "--site-dir",
        default=os.environ.get("SITE_DIR", "/site"),
        help="Directory containing the static site files (default: /site)."
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
    
    link_fix_site(args.site_dir)