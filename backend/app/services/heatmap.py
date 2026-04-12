"""Heatmap accumulator service — accumulates person detection positions into a heatmap grid."""

import numpy as np
import cv2


class HeatmapAccumulator:
    """Accumulates person detection positions into a heatmap grid with decay."""

    def __init__(self, grid_w: int = 64, grid_h: int = 48, decay_rate: float = 0.95):
        self._grids: dict[int, np.ndarray] = {}  # camera_id -> 2D numpy array
        self._grid_w = grid_w
        self._grid_h = grid_h
        self._total_detections: dict[int, int] = {}  # camera_id -> count
        self._decay_rate = decay_rate  # Multiply grid by this every frame (0.95 = fades in ~2 seconds)
        self._frame_count: dict[int, int] = {}  # camera_id -> frame counter

    def _ensure_grid(self, camera_id: int) -> np.ndarray:
        if camera_id not in self._grids:
            self._grids[camera_id] = np.zeros(
                (self._grid_h, self._grid_w), dtype=np.float64
            )
            self._total_detections[camera_id] = 0
        return self._grids[camera_id]

    def add_detections(
        self,
        camera_id: int,
        detections: list[dict],
        frame_w: int,
        frame_h: int,
    ):
        """Add person detections to the heatmap.

        For each person bbox, increment cells covered by the bottom half of
        the bbox (where feet are).
        """
        grid = self._ensure_grid(camera_id)

        # Apply decay every frame — heatmap fades over time
        grid *= self._decay_rate

        person_dets = [d for d in detections if d.get("object_type") == "person"]
        if not person_dets:
            return

        self._total_detections[camera_id] += len(person_dets)

        for det in person_dets:
            x1, y1, x2, y2 = det["bbox"]

            # Map full bbox to grid coords (covers entire body including head)
            gx1 = int(x1 / frame_w * self._grid_w)
            gx2 = int(x2 / frame_w * self._grid_w)
            gy1 = int(y1 / frame_h * self._grid_h)
            gy2 = int(y2 / frame_h * self._grid_h)

            # Clamp to grid bounds
            gx1 = max(0, min(gx1, self._grid_w - 1))
            gx2 = max(0, min(gx2, self._grid_w))
            gy1 = max(0, min(gy1, self._grid_h - 1))
            gy2 = max(0, min(gy2, self._grid_h))

            if gx2 > gx1 and gy2 > gy1:
                grid[gy1:gy2, gx1:gx2] += 1.0

    def get_heatmap(self, camera_id: int) -> np.ndarray:
        """Return normalized heatmap (0-1 range) for a camera.
        Uses absolute scale so values fade to zero when nobody is present."""
        grid = self._ensure_grid(camera_id)
        # Absolute scale: 10+ hits in a cell = full hot (1.0)
        # This means the heatmap actually fades when decay brings values below threshold
        return np.clip(grid / 10.0, 0.0, 1.0)

    def get_heatmap_image(
        self, camera_id: int, width: int = 640, height: int = 480
    ) -> np.ndarray:
        """Return a colored heatmap image (BGRA) using COLORMAP_JET.

        Transparent where no activity, hot colors where high activity.
        Returns a 4-channel image with alpha channel.
        """
        normalized = self.get_heatmap(camera_id)

        # Scale to 0-255 uint8
        heat_u8 = (normalized * 255).astype(np.uint8)

        # Resize to requested dimensions
        heat_resized = cv2.resize(
            heat_u8, (width, height), interpolation=cv2.INTER_LINEAR
        )

        # Apply Gaussian blur for smooth appearance
        heat_resized = cv2.GaussianBlur(heat_resized, (15, 15), 0)

        # Apply colormap (produces BGR)
        colored = cv2.applyColorMap(heat_resized, cv2.COLORMAP_JET)

        # Create alpha channel: transparent where no data, opaque where hot
        alpha = heat_resized.copy()
        # Make low values fully transparent, scale up higher values
        alpha = np.where(alpha < 5, 0, alpha).astype(np.uint8)

        # Merge BGR + Alpha into BGRA
        b, g, r = cv2.split(colored)
        bgra = cv2.merge([b, g, r, alpha])

        return bgra

    def reset(self, camera_id: int):
        """Reset heatmap for a camera."""
        if camera_id in self._grids:
            self._grids[camera_id] = np.zeros(
                (self._grid_h, self._grid_w), dtype=np.float64
            )
            self._total_detections[camera_id] = 0

    def get_stats(self, camera_id: int) -> dict:
        """Return stats: total_detections, peak_cell_value, coverage_percent."""
        grid = self._ensure_grid(camera_id)
        total_cells = self._grid_w * self._grid_h
        active_cells = int(np.count_nonzero(grid))

        return {
            "total_detections": self._total_detections.get(camera_id, 0),
            "peak_cell_value": int(grid.max()),
            "coverage_percent": round(active_cells / total_cells * 100, 1),
        }


# Singleton
heatmap_accumulator = HeatmapAccumulator()
