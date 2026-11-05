import argparse
import os
import sys
import time
from pathlib import Path
from urllib.parse import urljoin
import requests
from warcio.warcwriter import WARCWriter
from warcio.statusandheaders import StatusAndHeaders

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
    return parser.parse_args()

def get_relative_files(site_dir: Path):
    if not site_dir.exists():
        print(f"Error: Site directory '{site_dir}' does not exist.", file=sys.stderr)
        sys.exit(1)

    files = []
    for item in sorted(site_dir.rglob("*")):
        if item.is_file() and not any(part.startswith(".") for part in item.parts):
            files.append(item.relative_to(site_dir).as_posix())
    return files

def write_url_to_warc(writer, session, internal_url: str, warc_url: str) -> bool:
    try:
        resp = session.get(
            internal_url,
            headers={"Accept-Encoding": "identity"},
            stream=True,
            timeout=10
        )
    except requests.RequestException as exc:
        print(f"[!] Failed to fetch {internal_url}: {exc}", file=sys.stderr)
        return False

    headers_list = list(resp.raw.headers.items())
    status_line = f"{resp.status_code} {resp.status_reason if hasattr(resp, 'status_reason') else resp.reason}"
    http_headers = StatusAndHeaders(status_line, headers_list, protocol="HTTP/1.1")

    record = writer.create_warc_record(
        warc_url,
        "response",
        payload=resp.raw,
        http_headers=http_headers
    )
    writer.write_record(record)
    return True

def warc_generator(warc_name: str, domain: str, site_dir: Path, output_dir: Path, internal_host: str):
    base_domain = domain if domain.endswith("/") else f"{domain}/"
    base_internal = internal_host if internal_host.endswith("/") else f"{internal_host}/"

    if warc_name.endswith((".warc", ".warc.gz")):
        filename = warc_name
    else:
        filename = f"{warc_name}_archive.warc.gz"

    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / filename
    is_gzip = output_file.name.endswith(".gz")

    rel_files = get_relative_files(site_dir)
    if not rel_files:
        print(f"Warning: No files found in {site_dir}", file=sys.stderr)

    records_written = 0
    session = requests.Session()

    with open(output_file, "wb") as output:
        writer = WARCWriter(output, gzip=is_gzip)

        warcinfo = writer.create_warcinfo_record(output_file.name, {
            "software": "sswarcgen",
            "format": "WARC File Format 1.1",
            "description": f"Static site archive for {base_domain}"
        })
        writer.write_record(warcinfo)

        for rel_path in rel_files:
            internal_url = urljoin(base_internal, rel_path)
            warc_url = urljoin(base_domain, rel_path)

            if write_url_to_warc(writer, session, internal_url, warc_url):
                records_written += 1

            if rel_path == "index.html" or rel_path.endswith("/index.html"):
                dir_rel = rel_path[:-len("index.html")]
                dir_internal_url = urljoin(base_internal, dir_rel)
                dir_warc_url = urljoin(base_domain, dir_rel)
                if write_url_to_warc(writer, session, dir_internal_url, dir_warc_url):
                    records_written += 1

    print(f"{len(rel_files)} files processed ({records_written} WARC response records written)")
    print(f"Output saved to: {output_file}")

if __name__ == "__main__":
    start_time = time.time()
    args = parse_args()

    warc_generator(
        warc_name=args.name,
        domain=args.url,
        site_dir=Path(args.site_dir),
        output_dir=Path(args.output_dir),
        internal_host=args.internal_host
    )
    print(f"--- {time.time() - start_time:.2f} seconds to run ---")