import argparse
import io
import json
import logging
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import quote, urljoin

import requests
from tqdm import tqdm
from warcio.statusandheaders import StatusAndHeaders
from warcio.warcwriter import WARCWriter


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
        default=os.environ.get("OUTPUT_DIR", "/data"),
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
        if item.is_file():
            rel_path = item.relative_to(site_dir)
            if not any(part.startswith(".") for part in rel_path.parts):
                files.append(rel_path.as_posix())
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
    headers_list = [
        (k, v) for k, v in resp.headers.items()
        if k.lower() not in ("transfer-encoding", "content-encoding", "connection", "content-length")
    ]
    # Guarantee the Content-Length matches our downloaded payload exactly
    headers_list.append(("Content-Length", str(len(payload_bytes))))

    status_line = f"{resp.status_code} {resp.reason or ''}".strip()
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


def warc_generator(warc_name: str, domain: str, site_dir: Path, output_dir: Path, internal_host: str, verbose: bool, create_wacz: bool) -> int:
    base_domain = domain if domain.endswith("/") else f"{domain}/"
    base_internal = internal_host if internal_host.endswith("/") else f"{internal_host}/"

    if warc_name.endswith((".warc", ".warc.gz")):
        filename = warc_name
    else:
        filename = f"{warc_name}.warc.gz"

    wacz_filename = filename.removesuffix(".warc.gz").removesuffix(".warc") + ".wacz"

    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / filename
    wacz_file = output_dir / wacz_filename
    is_gzip = output_file.name.endswith(".gz")

    rel_files = get_relative_files(site_dir)
    total_files = len(rel_files)

    if not rel_files:
        logging.warning(f"No files found in {site_dir}")
        return 0

    output_file_label = wacz_file if create_wacz else output_file

    logging.info("Starting WARC generation...")
    logging.info(f"Target URL: {base_domain}")
    logging.info(f"Output File Destination: {output_file_label}")
    logging.info(f"Total files to process: {total_files}")

    records_written = 0
    failed_count = 0
    pages_list = []

    with requests.Session() as session, open(output_file, "wb") as output:
        writer = WARCWriter(output, gzip=is_gzip)

        warcinfo = writer.create_warcinfo_record(output_file.name, {
            "software": "sswarcgen",
            "format": "WARC File Format 1.1",
            "description": f"Static site archive for {base_domain}"
        })
        writer.write_record(warcinfo)
        logging.debug("Wrote warcinfo metadata record.")

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
            encoded_path = quote(rel_path, safe="/")
            internal_url = urljoin(base_internal, encoded_path)
            warc_url = urljoin(base_domain, encoded_path)

            is_html = rel_path.lower().endswith((".html", ".htm"))
            is_index = is_html and Path(rel_path).name.lower() in ("index.html", "index.htm")

            logging.debug(f"[{idx}/{total_files}] Archiving: {rel_path}")

            # For index files, only add the canonical directory URL to pages_list to avoid duplicates
            if write_url_to_warc(writer, session, internal_url, warc_url, is_page=(is_html and not is_index), pages_list=pages_list):
                records_written += 1
            else:
                failed_count += 1

            # Handle directory aliases for index files
            if is_index:
                dir_rel = Path(rel_path).parent.as_posix()
                dir_rel = "" if dir_rel == "." else f"{dir_rel}/"

                encoded_dir = quote(dir_rel, safe="/")
                dir_internal_url = urljoin(base_internal, encoded_dir)
                dir_warc_url = urljoin(base_domain, encoded_dir)

                logging.debug(f"  -> Appending directory alias response: {dir_warc_url}")

                if write_url_to_warc(writer, session, dir_internal_url, dir_warc_url, is_page=True, pages_list=pages_list):
                    records_written += 1
                else:
                    failed_count += 1

    logging.info("========================================")
    logging.info("WARC file generated.")
    logging.info(f"Processed: {total_files} files.")
    logging.info(f"Written: {records_written} response records.")
    if failed_count > 0:
        logging.warning(f"Failed: {failed_count} requests.")

    if not create_wacz:
        logging.info(f"Saved to: {output_file} ({output_file.stat().st_size / (1024 * 1024):.2f} MB)")
    else:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", encoding="utf-8", delete=False) as pf:
            pages_file = Path(pf.name)
            for page in pages_list:
                pf.write(json.dumps(page) + "\n")

        logging.info("========================================")
        logging.info("Packaging WARC into WACZ format...")
        try:
            subprocess.run(
                ["wacz", "create", "-f", str(output_file), "-o", str(wacz_file), "-p", str(pages_file)],
                check=True,
                stdout=subprocess.DEVNULL if not verbose else None
            )
            output_file.unlink()

            logging.info("WACZ created successfully. Temporary WARC deleted.")
            logging.info(f"Saved to: {wacz_file} ({wacz_file.stat().st_size / (1024 * 1024):.2f} MB)")
        except subprocess.CalledProcessError as e:
            logging.error(f"Failed to generate WACZ file (Exit code {e.returncode}).")
            logging.info(f"Retained fallback WARC file: {output_file}")
        except FileNotFoundError:
            logging.error("The 'wacz' CLI tool was not found.")
            logging.info(f"Retained fallback WARC file: {output_file}")
        finally:
            pages_file.unlink(missing_ok=True)

    return failed_count


if __name__ == "__main__":
    start_time = time.time()
    args = parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    failures = warc_generator(
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

    if failures > 0:
        sys.exit(1)