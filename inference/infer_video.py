"""Run video inference with YOLOv8 + DeepSORT and display live statistics."""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

import cv2
from ultralytics import YOLO

from tracker import DeepSORT


CLASS_NAMES = {
    0: "dead_fish",
    1: "live_fish",
    2: "floating_object",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Video inference for river monitoring")
    parser.add_argument("--video", default="videos/river.mp4", help="Input video path")
    parser.add_argument("--weights", default="train/runs/detect/river_dead_fish/weights/best.pt", help="Trained YOLO weights")
    parser.add_argument("--output", default="results/output.mp4", help="Output video path")
    parser.add_argument("--conf", type=float, default=0.25, help="Confidence threshold")
    parser.add_argument("--show", action="store_true", help="Display live window")
    return parser.parse_args()


def draw_stats(frame, counts: Counter) -> None:
    y = 30
    for cls_name in ("dead_fish", "live_fish", "floating_object"):
        text = f"{cls_name}: {counts.get(cls_name, 0)}"
        cv2.putText(frame, text, (20, y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
        y += 30


def main() -> None:
    args = parse_args()
    model = YOLO(args.weights)
    tracker = DeepSORT(max_age=30)

    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        raise FileNotFoundError(f"Cannot open video: {args.video}")

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 20.0

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    writer = cv2.VideoWriter(
        str(output_path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        fps,
        (width, height),
    )

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        results = model(frame, conf=args.conf)
        detections = []
        counts = Counter()

        for result in results:
            if result.boxes is None:
                continue

            xyxy = result.boxes.xyxy.cpu().numpy()
            confs = result.boxes.conf.cpu().numpy()
            clss = result.boxes.cls.cpu().numpy().astype(int)

            for (x1, y1, x2, y2), conf, cls_id in zip(xyxy, confs, clss):
                cls_name = CLASS_NAMES.get(cls_id, str(cls_id))
                counts[cls_name] += 1
                detections.append(([x1, y1, x2 - x1, y2 - y1], float(conf), cls_name))

        tracks = tracker.update(detections, frame)

        for x1, y1, x2, y2, track_id in tracks:
            cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), (0, 255, 0), 2)
            cv2.putText(
                frame,
                f"ID:{track_id}",
                (int(x1), int(y1 - 10)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 255, 0),
                2,
            )

        draw_stats(frame, counts)
        writer.write(frame)

        if args.show:
            cv2.imshow("River Monitoring", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    cap.release()
    writer.release()
    if args.show:
        cv2.destroyAllWindows()

    print(f"[INFO] Inference completed. Video saved to: {output_path}")


if __name__ == "__main__":
    main()
