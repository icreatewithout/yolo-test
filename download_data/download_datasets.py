"""Download publicly available fish-related datasets for river monitoring.

Example:
    python download_data/download_datasets.py --datasets risid
    python download_data/download_datasets.py --datasets risid deepfish
"""

from __future__ import annotations

import argparse
import shutil
import zipfile
from pathlib import Path

import requests


DATASET_URLS = {
    # Some hosting providers periodically change record/file paths. We keep
    # multiple candidates and try them in order.
    "risid": [
        "https://zenodo.org/record/15533743/files/RiSID.zip",
        "https://zenodo.org/records/15533743/files/RiSID.zip",
    ],
    # Placeholder public references; replace with latest URLs if mirrors change.
    "deepfish": ["https://public.roboflow.com/ds/deepfish.zip"],
    "plitter": ["https://public.roboflow.com/ds/p-litter.zip"],
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


def download_dataset(dataset_name: str, output_root: Path, keep_zip: bool = False) -> None:
    candidate_urls = DATASET_URLS[dataset_name]
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
        choices=sorted(DATASET_URLS.keys()),
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

        if dataset not in DATASET_URLS:
            raise ValueError(f"Unknown dataset in --url-override: '{dataset}'")

        if not url:
            raise ValueError(f"Empty URL for --url-override '{item}'")

        DATASET_URLS[dataset] = [url]


def main() -> None:
    args = parse_args()
    output_root = Path(args.output)

    apply_url_overrides(args.url_override)

    if args.clean and output_root.exists():
        print(f"[INFO] Cleaning existing directory: {output_root}")
        shutil.rmtree(output_root)

    for dataset in args.datasets:
        try:
            download_dataset(dataset, output_root, keep_zip=args.keep_zip)
        except requests.RequestException as exc:
            print(f"[ERROR] Failed to download {dataset}: {exc}")
        except zipfile.BadZipFile as exc:
            print(f"[ERROR] Corrupted zip for {dataset}: {exc}")


if __name__ == "__main__":
    main()
