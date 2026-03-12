"""Download publicly available fish-related datasets for river monitoring.

This script uses resilient download strategies:
- candidate URL fallback
- optional Zenodo file discovery by record/search
- runtime URL override without code changes
- non-zero exit code when any selected dataset fails
"""

from __future__ import annotations

import argparse
import shutil
import sys
import zipfile
from pathlib import Path

import requests


DATASET_SPECS = {
    "risid": {
        "urls": [
            "https://zenodo.org/records/15533743/files/RiSID.zip?download=1",
            "https://zenodo.org/record/15533743/files/RiSID.zip?download=1",
        ],
        "resolver": "zenodo_risid",
    },
    "deepfish": {
        # Historical Roboflow public links frequently expire.
        "urls": [
            "https://public.roboflow.com/ds/deepfish.zip",
        ],
    },
    "plitter": {
        "urls": [
            "https://public.roboflow.com/ds/p-litter.zip",
        ],
    },
}


def download_file(url: str, destination: Path, chunk_size: int = 1024 * 1024) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    response = requests.get(url, stream=True, timeout=120)
    response.raise_for_status()

    with destination.open("wb") as file:
        for chunk in response.iter_content(chunk_size=chunk_size):
            if chunk:
                file.write(chunk)


def extract_zip(zip_path: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(output_dir)


def _collect_zenodo_urls(record_json: dict, filename_hint: str = "risid") -> list[str]:
    urls: list[str] = []
    for file_entry in record_json.get("files", []):
        key = str(file_entry.get("key", "")).lower()
        if filename_hint in key and key.endswith(".zip"):
            links = file_entry.get("links", {})
            for link_key in ("self", "download"):
                link = links.get(link_key)
                if link:
                    urls.append(str(link))
    return urls


def resolve_zenodo_risid_urls() -> list[str]:
    """Resolve RiSID zip URLs through Zenodo API for link-rot tolerance."""
    discovered: list[str] = []

    # Try direct known record first.
    endpoints = [
        "https://zenodo.org/api/records/15533743",
        "https://zenodo.org/api/records/?q=RiSID&size=5",
    ]

    for endpoint in endpoints:
        try:
            response = requests.get(endpoint, timeout=30)
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException:
            continue

        if "hits" in payload:
            for hit in payload.get("hits", {}).get("hits", []):
                discovered.extend(_collect_zenodo_urls(hit, filename_hint="risid"))
        else:
            discovered.extend(_collect_zenodo_urls(payload, filename_hint="risid"))

    # Deduplicate while keeping order.
    ordered = []
    seen = set()
    for url in discovered:
        if url not in seen:
            seen.add(url)
            ordered.append(url)
    return ordered


def _candidate_urls(dataset_name: str) -> list[str]:
    spec = DATASET_SPECS[dataset_name]
    urls = list(spec.get("urls", []))

    resolver = spec.get("resolver")
    if resolver == "zenodo_risid":
        urls.extend(resolve_zenodo_risid_urls())

    # Deduplicate while preserving order.
    merged: list[str] = []
    seen = set()
    for url in urls:
        if url not in seen:
            seen.add(url)
            merged.append(url)
    return merged


def download_dataset(dataset_name: str, output_root: Path, keep_zip: bool = False) -> None:
    candidate_urls = _candidate_urls(dataset_name)
    if not candidate_urls:
        raise requests.RequestException(
            f"No candidate URLs configured for '{dataset_name}'. "
            "Use --url-override DATASET=URL."
        )

    zip_path = output_root / f"{dataset_name}.zip"
    extract_dir = output_root / dataset_name

    last_error: Exception | None = None
    for url in candidate_urls:
        print(f"[INFO] Downloading {dataset_name} from {url}")
        try:
            download_file(url, zip_path)
            last_error = None
            break
        except requests.RequestException as exc:
            last_error = exc
            zip_path.unlink(missing_ok=True)
            print(f"[WARN] Download failed from {url}: {exc}")

    if last_error is not None:
        raise requests.RequestException(
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

    if args.clean and output_root.exists():
        print(f"[INFO] Cleaning existing directory: {output_root}")
        shutil.rmtree(output_root)

    failed: list[str] = []
    for dataset in args.datasets:
        try:
            download_dataset(dataset, output_root, keep_zip=args.keep_zip)
        except (requests.RequestException, zipfile.BadZipFile) as exc:
            failed.append(dataset)
            print(f"[ERROR] Failed to download {dataset}: {exc}")

    if failed:
        print(f"[ERROR] Dataset download failed: {', '.join(failed)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
