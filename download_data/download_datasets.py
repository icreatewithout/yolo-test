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
    "risid": "https://zenodo.org/record/15533743/files/RiSID.zip",
    # Placeholder public references; replace with latest URLs if mirrors change.
    "deepfish": "https://public.roboflow.com/ds/deepfish.zip",
    "plitter": "https://public.roboflow.com/ds/p-litter.zip",
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
    url = DATASET_URLS[dataset_name]
    zip_path = output_root / f"{dataset_name}.zip"
    extract_dir = output_root / dataset_name

    print(f"[INFO] Downloading {dataset_name} from {url}")
    download_file(url, zip_path)
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
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_root = Path(args.output)

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
