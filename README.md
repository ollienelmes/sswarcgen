# sswarcgen

`sswarcgen` is a lightweight Python utility for generating WARC (Web ARChive) files from static websites.

It uses Docker Compose to run an Apache web server alongside a Python application. The Python application discovers the static site files, retrieves them over HTTP, and writes the responses into a WARC archive.

## How it works

The application uses two primary Docker services:

- **web** – Apache HTTP Server serves the static website.
- **warcgen** – Python application retrieves the website files and generates the WARC archive.

There is an optional service that can be used to help reformat broken links:

- **fix-links** – An optional utility to normalize case-sensitive links before archiving.

The static website directory is shared between the containers. The generated archives are written to a local `data` directory.

## Requirements

- [Docker](https://www.docker.com/products/docker-desktop/)
- [Docker Compose](https://docs.docker.com/compose/install/) - installed by default with Docker Desktop

## Project structure

```text
sswarcgen/
├── docker-compose.yml
├── python/
│   ├── Dockerfile
│   └── main.py
├── web/
│   ├── Dockerfile
│   └── site/
│       ├── index.html
│       └── ...
└── data/
```

Place the static website you want to archive inside `web/site/`.

Generated WARC files will be saved in `data/`.

## Getting started

### 1. Build the images

```bash
docker compose build
```

You only need to run this command for the first use.

### 2. Generate the WARC archive

```bash
docker compose run --rm warcgen
```

By default, this generates: `data/WebArchive.warc.gz`

### 3. Stop the web server

```bash
docker compose down
```

## Updating Archive Data

Website files are mounted directly from `web/site/` into the containers. Changes to the static website are available immediately without rebuilding the Docker images. Simply run the WARC generator again to create an updated archive once the files have been cleared from the `web/site/` directory.

As a more concise command after the initial setup you can run a command such as below to generate the WARC file and stop the web server:

```bash
docker compose run --rm warcgen \
  --name ArchiveNameHere \
  --url https://example.com/ \
  && docker compose down
```

## Configuration

Configuration can be supplied using environment variables or command-line arguments.

| Setting | Argument | Environment variable | Default |
|---|---|---|---|
| Archive name | `-n`, `--name` | `WARC_NAME` | `WebArchive` |
| Target URL | `-u`, `--url` | `TARGET_URL` | `http://localhost` |
| Verbose logging | `-v`, `--verbose` |  | Disabled |
| WACZ file generation | `--wacz` |  | Disabled |

### Example

```bash
docker compose run --rm warcgen \
  --name ArchiveNameHere \
  --url https://example.com/ \
  -v
```

This generates:

```text
data/ArchiveNameHere.warc.gz
```

With all pages using the internal URLs:

```text
https://example.com/
```

The`-v` (or `--verbose`) flag will output a line-by-line log of every file as it is fetched and recorded. Without it, the application only prints a high-level summary of the job at startup and completion.

### Archive naming

The archive filename depends on the supplied name:

| Name supplied | Generated filename |
|---|---|
| `my_site` | `my_site_archive.warc.gz` |
| `my_site.warc` | `my_site.warc` |
| `my_site.warc.gz` | `my_site.warc.gz` |

Files ending in `.gz` are gzip-compressed.

If no file extensions are supplied in the name argument it will be by default a zipped WARC.

## Reformatting the site

Depending on how an older site's source files have been preserved, it may be necessary to make alterations to the files under `web/site/` so that the captured archive replays correctly.

### Broken internal links

If there are broken internal links, first check that the expected target files exist. If they do, the issue is often caused by case sensitivity or spaces in paths—for example, an internal link pointing to `href="About/index.html"` will fail to resolve in a WARC replayer if the file on disk is `about/index.html`.

The optional `fix-links` service resolves these issues by modifying files in `web/site/` in place: lowercasing internal link paths and filenames, and replacing spaces (` ` and `%20`) with hyphens (`-`). External URLs, `data:`/`mailto:`/`tel:`/`javascript:` links, query strings, and `#fragment` anchors are left untouched, and any rename that would overwrite an existing file is skipped with a warning.

> **Note:** `fix-links` is isolated under a Docker Compose `tools` profile, so it will not run automatically during `docker compose up`.

#### Options

| Setting | Argument | Default | Description |
|---|---|---|---|
| Dry run | `--dry-run` | Disabled | Preview link and filename changes without modifying any files. |
| Verbose logging | `-v`, `--verbose` | Disabled | Output line-by-line logs of every file updated or renamed. |
| Site directory | `-s`, `--site-dir` | `/site` | Directory containing the static site files (`SITE_DIR`). |

#### Example

Because `fix-links` edits files in place, it is good practice to preview the changes first with `--dry-run`:

```bash
docker compose run --rm fix-links --dry-run
```

## Updating the tool

If you download a newer version of `sswarcgen` or pull the latest changes via `git pull`, you must rebuild the Docker images for the updates to take effect. 

Because Docker caches your previous build, it will not automatically apply changes made within the scripts folder `python/` until you run:

```bash
docker compose build
```

## Dependencies

The Python application uses:

- [Requests](https://requests.readthedocs.io/) – HTTP requests.
- [warcio](https://github.com/webrecorder/warcio) – WARC file generation.
- [tqdm](https://github.com/tqdm/tqdm) – CLI progress bar.
- [wacz](https://github.com/webrecorder/specs) - WACZ file converter.

The Python Docker image installs these dependencies automatically.