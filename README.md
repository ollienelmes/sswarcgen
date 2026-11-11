# sswarcgen

`sswarcgen` is a lightweight Python utility for generating WARC (Web ARChive) files from static websites.

It uses Docker Compose to run an Apache web server alongside a Python application. The Python application discovers the static site files, retrieves them over HTTP, and writes the responses into a WARC archive.

## How it works

The application uses two primary Docker services:

- **web** – Apache HTTP Server serves the static website.
- **warcgen** – Python application retrieves the website files and generates the WARC archive.

There is an optional service that can be used to help reformat broken links:

- **case-fix-links** – An optional utility to normalize case-sensitive links before archiving.

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

In the case of certain old sites and depending on how the source files have been preserved it may be necessary to make certain alterations to the source files (under `web/site/`) to ensure that the capture archive replays correctly. To support these 

### Broken internal links

If there are broken internal links, you should first check that those expected files actually exist. If they do and it's still not working, then it may be broken due to an issue of case sensitivity. For example an internal link that points to `href="About/index.html"` will not be able to resolve within the WARC replayer if the actual file exists in `about/index.html`.

For these issues of case sensitivity you can use the `case-fix-links` tool that is included. When this service is run then it makes necessary modifications to the static site files that exist under `web/site/`.

#### Example

You can use the `-v` or `--verbose` flag to run the `case-fix-links` service to see exactly which files are being updated.

```bash
docker compose run --rm case-fix-links -v
```

After running this command you should be able to run the usual WARC generation commands. 

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