"""Tracking wrapper built on top of deep_sort_realtime."""

from __future__ import annotations

from deep_sort_realtime.deepsort_tracker import DeepSort


class DeepSORT:
    def __init__(self, max_age: int = 30, n_init: int = 2) -> None:
        self._tracker = DeepSort(max_age=max_age, n_init=n_init)

    def update(self, detections, frame):
        """Update tracker.

        Args:
            detections: list[[x, y, w, h], conf, class_name]
            frame: current BGR frame

        Returns:
            list of [x1, y1, x2, y2, track_id]
        """
        tracks = self._tracker.update_tracks(detections, frame=frame)
        outputs = []
        for track in tracks:
            if not track.is_confirmed():
                continue
            x1, y1, x2, y2 = track.to_ltrb()
            outputs.append([x1, y1, x2, y2, track.track_id])
        return outputs
