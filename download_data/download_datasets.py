"""Download publicly available fish-related datasets for river monitoring.

Resilience features:
- multi-candidate URL fallback
- Zenodo API discovery for renamed/moved records
- runtime --url-override without code edits
- proxy scope control for better throughput
- non-zero exit code when any selected dataset fails
"""

from __future__ import annotations

import argparse
import shutil
import sys
import zipfile
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter


DATASET_SPECS = {
    "risid": {
        "urls": [
            "https://zenodo.org/records/15533743/files/RiSID.zip?download=1",
            "https://zenodo.org/record/15533743/files/RiSID.zip?download=1",
        ],
        "resolver": "zenodo_search",
        "queries": ["RiSID", '"river" fish dataset'],
        "filename_hints": ["risid"],
    },
    "deepfish": {
        "urls": [
            "https://public.roboflow.com/ds/deepfish.zip",
        ],
        "resolver": "zenodo_search",
        "queries": ["DeepFish dataset", "deepfish fish detection"],
        "filename_hints": ["deepfish"],
    },
    "plitter": {
        "urls": [
            "https://public.roboflow.com/ds/p-litter.zip",
        ],
        "resolver": "zenodo_search",
        "queries": ["pLitter dataset", "river litter dataset"],
        "filename_hints": ["litter", "plitter"],
    },
}


class DatasetDownloadError(RuntimeError):
    """Raised when a dataset cannot be downloaded from any candidate source."""


def build_session(proxy: str | None, use_proxy: bool, pool_size: int) -> requests.Session:
    session = requests.Session()
    adapter = HTTPAdapter(pool_connections=pool_size, pool_maxsize=pool_size)
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    if use_proxy and proxy:
        session.proxies.update({"http": proxy, "https": proxy})
    return session


def pick_sessions(proxy: str, proxy_scope: str, pool_size: int) -> tuple[requests.Session, requests.Session, str]:
    """Return (api_session, download_session, human_readable_mode)."""
    if proxy_scope == "off":
        direct = build_session(proxy=None, use_proxy=False, pool_size=pool_size)
        return direct, direct, "proxy disabled (all direct)"

    if proxy_scope == "api-only":
        api_session = build_session(proxy=proxy, use_proxy=True, pool_size=pool_size)
        download_session = build_session(proxy=None, use_proxy=False, pool_size=pool_size)
        return api_session, download_session, "API via proxy, file download direct"

    # all
    proxied = build_session(proxy=proxy, use_proxy=True, pool_size=pool_size)
    return proxied, proxied, f"all requests via proxy {proxy}"


def download_file(
    session: requests.Session,
    url: str,
    destination: Path,
    chunk_size: int,
    timeout: int,
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    response = session.get(url, stream=True, timeout=timeout)
    response.raise_for_status()

    with destination.open("wb") as file:
        for chunk in response.iter_content(chunk_size=chunk_size):
            if chunk:
                file.write(chunk)


def extract_zip(zip_path: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(output_dir)


def _collect_zenodo_zip_links(record_json: dict, filename_hints: list[str]) -> list[str]:
    hints = [hint.lower() for hint in filename_hints]
    urls: list[str] = []

    for file_entry in record_json.get("files", []):
        key = str(file_entry.get("key", "")).lower()
        if not key.endswith(".zip"):
            continue

        if hints and not any(hint in key for hint in hints):
            continue

        links = file_entry.get("links", {})
        for link_key in ("download", "self"):
            link = links.get(link_key)
            if link:
                urls.append(str(link))

    return urls


def resolve_zenodo_search_urls(
    session: requests.Session,
    queries: list[str],
    filename_hints: list[str],
    api_timeout: int,
) -> list[str]:
    discovered: list[str] = []

    for query in queries:
        endpoint = "https://zenodo.org/api/records/"
        params = {"q": query, "size": 10, "sort": "mostrecent"}
        try:
            response = session.get(endpoint, params=params, timeout=api_timeout)
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException:
            continue

        for hit in payload.get("hits", {}).get("hits", []):
            links = _collect_zenodo_zip_links(hit, filename_hints=filename_hints)
            if links:
                discovered.extend(links)
                continue
            discovered.extend(_collect_zenodo_zip_links(hit, filename_hints=[]))

    merged: list[str] = []
    seen = set()
    for url in discovered:
        if url not in seen:
            seen.add(url)
            merged.append(url)
    return merged


def _candidate_urls(
    api_session: requests.Session,
    dataset_name: str,
    api_timeout: int,
    skip_discovery: bool,
) -> list[str]:
    spec = DATASET_SPECS[dataset_name]
    urls = list(spec.get("urls", []))

    if not skip_discovery and spec.get("resolver") == "zenodo_search":
        urls.extend(
            resolve_zenodo_search_urls(
                session=api_session,
                queries=list(spec.get("queries", [])),
                filename_hints=list(spec.get("filename_hints", [])),
                api_timeout=api_timeout,
            )
        )

    merged: list[str] = []
    seen = set()
    for url in urls:
        if url not in seen:
            seen.add(url)
            merged.append(url)
    return merged


def download_dataset(
    api_session: requests.Session,
    download_session: requests.Session,
    dataset_name: str,
    output_root: Path,
    keep_zip: bool,
    chunk_size: int,
    download_timeout: int,
    api_timeout: int,
    skip_discovery: bool,
) -> None:
    candidate_urls = _candidate_urls(api_session, dataset_name, api_timeout, skip_discovery)
    if not candidate_urls:
        raise DatasetDownloadError(
            f"No candidate URLs configured for '{dataset_name}'. "
            "Use --url-override DATASET=URL."
        )

    zip_path = output_root / f"{dataset_name}.zip"
    extract_dir = output_root / dataset_name

    last_error: Exception | None = None
    for url in candidate_urls:
        print(f"[INFO] Downloading {dataset_name} from {url}")
        try:
            download_file(
                session=download_session,
                url=url,
                destination=zip_path,
                chunk_size=chunk_size,
                timeout=download_timeout,
            )
            last_error = None
            break
        except requests.RequestException as exc:
            last_error = exc
            zip_path.unlink(missing_ok=True)
            print(f"[WARN] Download failed from {url}: {exc}")

    if last_error is not None:
        raise DatasetDownloadError(
            f"All candidate URLs failed for '{dataset_name}'. "
            "Use --url-override to provide a verified direct download URL."
        ) from last_error

    print(f"[INFO] Extracting {zip_path} -> {extract_dir}")
    extract_zip(zip_path, extract_dir)

    if not keep_zip:
        zip_path.unlink(missing_ok=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download open datasets for river dead-fish monitoring")
    parser.add_argument(
        "--datasets",
        nargs="+",
        default=["risid"],
        choices=sorted(DATASET_SPECS.keys()),
        help="Dataset aliases to download",
    )
    parser.add_argument("--output", default="dataset/raw", help="Output directory for raw downloads")
    parser.add_argument("--keep-zip", action="store_true", help="Keep downloaded zip archives")
    parser.add_argument("--clean", action="store_true", help="Remove output directory before download")
    parser.add_argument(
        "--url-override",
        action="append",
        default=[],
        metavar="DATASET=URL",
        help="Override download URL, e.g. --url-override risid=https://.../RiSID.zip",
    )
    parser.add_argument(
        "--proxy",
        default="http://127.0.0.1:7890",
        help="HTTP/HTTPS proxy URL, default: http://127.0.0.1:7890",
    )
    parser.add_argument(
        "--proxy-scope",
        choices=["all", "api-only", "off"],
        default="api-only",
        help="Proxy usage mode: all=everything via proxy, api-only=API via proxy + file direct, off=disable proxy",
    )
    parser.add_argument(
        "--print-candidates",
        action="store_true",
        help="Print resolved candidate URLs and exit (for debugging broken sources)",
    )
    parser.add_argument("--chunk-size-mb", type=int, default=4, help="Download stream chunk size in MB (default 4)")
    parser.add_argument("--download-timeout", type=int, default=120, help="Download request timeout seconds")
    parser.add_argument("--api-timeout", type=int, default=30, help="Zenodo API request timeout seconds")
    parser.add_argument("--pool-size", type=int, default=16, help="HTTP connection pool size")
    parser.add_argument("--skip-discovery", action="store_true", help="Skip Zenodo discovery to reduce startup latency")
    return parser.parse_args()


def apply_url_overrides(overrides: list[str]) -> None:
    for item in overrides:
        if "=" not in item:
            raise ValueError(f"Invalid --url-override '{item}'. Expected DATASET=URL format.")

        dataset, url = item.split("=", 1)
        dataset = dataset.strip()
        url = url.strip()

        if dataset not in DATASET_SPECS:
            raise ValueError(f"Unknown dataset in --url-override: '{dataset}'")

        if not url:
            raise ValueError(f"Empty URL for --url-override '{item}'")

        DATASET_SPECS[dataset]["urls"] = [url]


def main() -> None:
    args = parse_args()
    output_root = Path(args.output)

    apply_url_overrides(args.url_override)

    api_session, download_session, mode = pick_sessions(args.proxy, args.proxy_scope, args.pool_size)
    print(f"[INFO] Proxy mode: {mode}")

    if args.print_candidates:
        for dataset in args.datasets:
            print(f"[{dataset}] candidate URLs:")
            for idx, url in enumerate(
                _candidate_urls(api_session, dataset, args.api_timeout, args.skip_discovery),
                start=1,
            ):
                print(f"  {idx}. {url}")
        return

    if args.clean and output_root.exists():
        print(f"[INFO] Cleaning existing directory: {output_root}")
        shutil.rmtree(output_root)

    failed: list[str] = []
    for dataset in args.datasets:
        try:
            download_dataset(
                api_session=api_session,
                download_session=download_session,
                dataset_name=dataset,
                output_root=output_root,
                keep_zip=args.keep_zip,
                chunk_size=args.chunk_size_mb * 1024 * 1024,
                download_timeout=args.download_timeout,
                api_timeout=args.api_timeout,
                skip_discovery=args.skip_discovery,
            )
        except (requests.RequestException, zipfile.BadZipFile, DatasetDownloadError) as exc:
            failed.append(dataset)
            print(f"[ERROR] Failed to download {dataset}: {exc}")

    if failed:
        print(f"[ERROR] Dataset download failed: {', '.join(failed)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
