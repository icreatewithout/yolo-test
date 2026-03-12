"""Auto-label river videos into YOLO format using a pretrained YOLOv8 detector."""

from __future__ import annotations

import argparse
from pathlib import Path

import cv2
from ultralytics import YOLO


def to_yolo_line(x1: float, y1: float, x2: float, y2: float, w_img: int, h_img: int, cls: int) -> str:
    x_center = ((x1 + x2) / 2) / w_img
    y_center = ((y1 + y2) / 2) / h_img
    width = (x2 - x1) / w_img
    height = (y2 - y1) / h_img
    return f"{cls} {x_center:.6f} {y_center:.6f} {width:.6f} {height:.6f}\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create pseudo-labels from a video source")
    parser.add_argument("--video", default="videos/river.mp4", help="Input video path")
    parser.add_argument("--images-dir", default="dataset/images/train", help="Output image directory")
    parser.add_argument("--labels-dir", default="dataset/labels/train", help="Output label directory")
    parser.add_argument("--interval", type=int, default=10, help="Save every N-th frame")
    parser.add_argument("--model", default="yolov8n.pt", help="YOLO model path")
    parser.add_argument("--conf", type=float, default=0.25, help="Detection confidence threshold")
    parser.add_argument("--class-id", type=int, default=0, help="Class id to write in labels")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    images_dir = Path(args.images_dir)
    labels_dir = Path(args.labels_dir)
    images_dir.mkdir(parents=True, exist_ok=True)
    labels_dir.mkdir(parents=True, exist_ok=True)

    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        raise FileNotFoundError(f"Cannot open video: {args.video}")

    model = YOLO(args.model)
    frame_index = 0
    saved = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_index % args.interval == 0:
            image_name = f"{frame_index:06d}.jpg"
            image_path = images_dir / image_name
            cv2.imwrite(str(image_path), frame)

            results = model(str(image_path), conf=args.conf)
            label_path = labels_dir / f"{frame_index:06d}.txt"
            h_img, w_img = frame.shape[:2]

            with label_path.open("w", encoding="utf-8") as file:
                for result in results:
                    boxes = result.boxes
                    if boxes is None or boxes.xyxy is None:
                        continue

                    xyxy = boxes.xyxy.cpu().numpy()
                    for x1, y1, x2, y2 in xyxy:
                        file.write(to_yolo_line(x1, y1, x2, y2, w_img, h_img, args.class_id))

            saved += 1

        frame_index += 1

    cap.release()
    print(f"[INFO] Auto-labeling complete. Saved {saved} frames.")


if __name__ == "__main__":
    main()
