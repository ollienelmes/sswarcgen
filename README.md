# sswarcgen

`sswarcgen` is a lightweight Python utility for generating WARC (Web ARChive) files from static websites.

It uses Docker Compose to run an Apache web server alongside a Python application. The Python application discovers the static site files, retrieves them over HTTP, and writes the responses into a WARC archive.

## How it works

The application uses two Docker services:

- **web** – Apache HTTP Server serves the static website.
- **warcgen** – Python application retrieves the website files and generates the WARC archive.

The static website directory is shared between both containers. The generated archives are written to a local `data` directory.

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

## Dependencies

The Python application uses:

- [Requests](https://requests.readthedocs.io/) – HTTP requests.
- [warcio](https://github.com/webrecorder/warcio) – WARC file generation.

The Python Docker image installs these dependencies automatically.
