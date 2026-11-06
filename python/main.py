import argparse
import os
import sys
import time
import logging
import subprocess
import json
import io
from pathlib import Path
from urllib.parse import urljoin
import requests
from warcio.warcwriter import WARCWriter
from warcio.statusandheaders import StatusAndHeaders
from tqdm import tqdm

def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate a WARC archive from a static site."
    )
    parser.add_argument(
        "-n", "--name",
        default=os.environ.get("WARC_NAME", "WebArchive"),
        help="Name for the WARC file (e.g. 'my_archive.warc.gz')."
    )
    parser.add_argument(
        "-u", "--url",
        default=os.environ.get("TARGET_URL", "http://localhost"),
        help="Target base URL used for WARC-Target-URIs (e.g., 'https://omeka.warburg.sas.ac.uk/')."
    )
    parser.add_argument(
        "-s", "--site-dir",
        default=os.environ.get("SITE_DIR", "/site"),
        help="Directory containing the static site files (default: /site)."
    )
    parser.add_argument(
        "-o", "--output-dir",
        default=os.environ.get("OUTPUT_DIR", '/data'),
        help="Directory to write the output WARC file (default: /data)."
    )
    parser.add_argument(
        "--internal-host",
        default=os.environ.get("INTERNAL_HOST", "http://web/"),
        help="Internal HTTP server URL serving the static site."
    )
    parser.add_argument(
        "--wacz",
        action="store_true",
        help="Package into a WACZ file and delete the intermediate WARC."
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose line-by-line logging."
    )
    return parser.parse_args()

def get_relative_files(site_dir: Path):
    if not site_dir.exists():
        logging.error(f"Site directory '{site_dir}' does not exist.")
        sys.exit(1)

    files = []
    for item in sorted(site_dir.rglob("*")):
        if item.is_file() and not any(part.startswith(".") for part in item.parts):
            files.append(item.relative_to(site_dir).as_posix())
    return files

def write_url_to_warc(writer, session, internal_url: str, warc_url: str, is_page: bool, pages_list: list) -> bool:
    try:
        # Fetch the entire payload into memory to guarantee byte length accuracy
        resp = session.get(
            internal_url,
            headers={"Accept-Encoding": "identity"},
            timeout=10
        )
    except requests.RequestException as exc:
        logging.error(f"Failed to fetch {internal_url}: {exc}")
        return False

    payload_bytes = resp.content

    # Strip hop-by-hop headers that break WARC replay indexing
    headers_list = []
    for k, v in resp.headers.items():
        if k.lower() not in ("transfer-encoding", "content-encoding", "connection"):
            headers_list.append((k, v))
            
    # Guarantee the Content-Length matches our downloaded payload exactly
    headers_list = [h for h in headers_list if h[0].lower() != "content-length"]
    headers_list.append(("Content-Length", str(len(payload_bytes))))

    status_line = f"{resp.status_code} {resp.status_reason if hasattr(resp, 'status_reason') else resp.reason}"
    http_headers = StatusAndHeaders(status_line, headers_list, protocol="HTTP/1.1")

    record = writer.create_warc_record(
        warc_url,
        "response",
        payload=io.BytesIO(payload_bytes),
        length=len(payload_bytes),
        http_headers=http_headers
    )
    writer.write_record(record)
    
    # If this is designated as an HTML page, add it to our WACZ pages index
    if is_page and resp.status_code == 200:
        pages_list.append({"url": warc_url, "title": warc_url})
        
    return True

def warc_generator(warc_name: str, domain: str, site_dir: Path, output_dir: Path, internal_host: str, verbose: bool, create_wacz: bool):
    base_domain = domain if domain.endswith("/") else f"{domain}/"
    base_internal = internal_host if internal_host.endswith("/") else f"{internal_host}/"

    if warc_name.endswith((".warc", ".warc.gz")):
        filename = warc_name
    else:
        filename = f"{warc_name}.warc.gz"

    wacz_filename = filename.replace(".warc.gz", "").replace(".warc", "") + ".wacz"

    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / filename
    is_gzip = output_file.name.endswith(".gz")

    rel_files = get_relative_files(site_dir)
    total_files = len(rel_files)
    
    if not rel_files:
        logging.warning(f"No files found in {site_dir}")
        return

    if create_wacz:
        output_file_label = output_dir / (filename.replace(".warc.gz", "").replace(".warc", "") + ".wacz")
    else:
        output_file_label = output_file

    logging.info(f"Starting WARC generation...")
    logging.info(f"Target URL: {base_domain}")
    logging.info(f"Output File Destination: {output_file_label}")
    logging.info(f"Total files to process: {total_files}")

    records_written = 0
    session = requests.Session()
    
    # Keep track of entry points for the WACZ menu
    pages_list = []

    with open(output_file, "wb") as output:
        writer = WARCWriter(output, gzip=is_gzip)

        warcinfo = writer.create_warcinfo_record(output_file.name, {
            "software": "sswarcgen",
            "format": "WARC File Format 1.1",
            "description": f"Static site archive for {base_domain}"
        })
        writer.write_record(warcinfo)
        logging.debug("Wrote warcinfo metadata record.")

        # Wrap the loop with a tqdm progress bar
        progress_iterator = tqdm(
            enumerate(rel_files, start=1), 
            total=total_files, 
            disable=verbose, 
            desc="Archiving files", 
            unit="file",
            leave=False,
            bar_format="{l_bar}{bar:30}{r_bar}"
        )

        for idx, rel_path in progress_iterator:
            internal_url = urljoin(base_internal, rel_path)
            warc_url = urljoin(base_domain, rel_path)
            
            is_html = rel_path.lower().endswith((".html", ".htm"))

            logging.debug(f"[{idx}/{total_files}] Archiving: {rel_path}")

            if write_url_to_warc(writer, session, internal_url, warc_url, is_page=is_html, pages_list=pages_list):
                records_written += 1

            # Handle directory aliases for index files
            if is_html and Path(rel_path).name.lower() in ("index.html", "index.htm"):
                dir_rel = str(Path(rel_path).parent)
                if dir_rel == ".":
                    dir_rel = ""
                else:
                    dir_rel += "/"

                dir_internal_url = urljoin(base_internal, dir_rel)
                dir_warc_url = urljoin(base_domain, dir_rel)

                logging.debug(f"  -> Appending directory alias response: {dir_warc_url}")

                if write_url_to_warc(writer, session, dir_internal_url, dir_warc_url, is_page=True, pages_list=pages_list):
                    records_written += 1

    logging.info("========================================")
    logging.info(f"WARC file generated.")
    logging.info(f"Processed: {total_files} files.")
    logging.info(f"Written: {records_written} response records.")

    if not create_wacz:
        logging.info(f"Saved to: {output_file} ({output_file.stat().st_size / (1024 * 1024):.2f} MB)")
    else:
        wacz_file = output_dir / wacz_filename
        
        # Write the pages.jsonl file to inject into the WACZ
        pages_file = output_dir / "pages.jsonl"
        with open(pages_file, "w", encoding="utf-8") as pf:
            for page in pages_list:
                pf.write(json.dumps(page) + "\n")
                
        logging.info("========================================")
        logging.info(f"Packaging WARC into WACZ format...")
        try:
            # Generate the WACZ using the explicit pages index
            subprocess.run(
                ["wacz", "create", "-f", str(output_file), "-o", str(wacz_file), "-p", str(pages_file)],
                check=True,
                stdout=subprocess.DEVNULL if not verbose else None
            )
            # Delete the intermediate files
            output_file.unlink()
            pages_file.unlink()
            
            logging.info(f"WACZ created successfully. Temporary WARC deleted.")
            logging.info(f"Saved to: {wacz_file} ({wacz_file.stat().st_size / (1024 * 1024):.2f} MB)")
        except subprocess.CalledProcessError as e:
            logging.error(f"Failed to generate WACZ file (Exit code {e.returncode}).")
            logging.info(f"Retained fallback WARC file: {output_file}")
        except FileNotFoundError:
            logging.error("The 'wacz' CLI tool was not found.")
            logging.info(f"Retained fallback WARC file: {output_file}")


if __name__ == "__main__":
    start_time = time.time()
    args = parse_args()

    # Set log level based on verbose flag
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    warc_generator(
        warc_name=args.name,
        domain=args.url,
        site_dir=Path(args.site_dir),
        output_dir=Path(args.output_dir),
        internal_host=args.internal_host,
        verbose=args.verbose,
        create_wacz=args.wacz
    )
    
    elapsed = time.time() - start_time
    logging.info(f"Total execution time: {elapsed:.2f} seconds")