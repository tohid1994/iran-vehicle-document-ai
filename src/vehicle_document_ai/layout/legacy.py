"""Guarded regional profile for the older registration form with a copper VIN grid.

Coordinates are relative to a DETECTED grid, not photo pixels. This profile has
only been evaluated on one supplied document; it is not a universal layout model.
It contains no vehicle, plate, owner or identifier values.
"""

import cv2
import numpy as np

from ..schemas import Box

# Relative to grid width and top-left. Regions contain values, not their labels.
# Canonical value windows of this printed form, expressed relative to its VIN grid.
# The reference geometry is layout-only; no document values are stored here.
_REFERENCE_GRID = (491, 694, 923)
_REFERENCE_WINDOWS = {
    "vehicle.brand": (1090, 520, 1320, 568),
    "vehicle.model": (670, 520, 900, 568),
    "vehicle.year": (454, 523, 583, 574),
    "vehicle.color": (40, 524, 320, 573),
    "vehicle.fuelType": (725, 584, 840, 625),
    "vehicle.vehicleType": (1380, 521, 1630, 566),
    "vehicle.engineNumber": (1210, 640, 1460, 687),
    "vehicle.chassisNumber": (430, 640, 830, 690),
    "owner.fullName": (920, 832, 1220, 892),
    "owner.nationalId": (320, 1048, 590, 1105),
    "vehicle.plate": (220, 1165, 556, 1226),
    "vehicle.vin": (435, 701, 1412, 745),
}
VALUE_REGIONS = {
    key: (
        (x1 - _REFERENCE_GRID[0]) / _REFERENCE_GRID[2],
        (y1 - _REFERENCE_GRID[1]) / _REFERENCE_GRID[2],
        (x2 - _REFERENCE_GRID[0]) / _REFERENCE_GRID[2],
        (y2 - _REFERENCE_GRID[1]) / _REFERENCE_GRID[2],
    )
    for key, (x1, y1, x2, y2) in _REFERENCE_WINDOWS.items()
}


def detect_grid(image: np.ndarray) -> Box | None:
    h, w = image.shape[:2]
    rgb = image.astype(np.int16)
    copper = ((rgb[:, :, 0] - rgb[:, :, 1] > 12) & (rgb[:, :, 0] - rgb[:, :, 2] > 18)).astype(
        np.uint8
    ) * 255
    copper = cv2.morphologyEx(copper, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    contours, _ = cv2.findContours(copper, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    matches = []
    for c in contours:
        x, y, width, height = cv2.boundingRect(c)
        if not (width > w * 0.3 and 12 < width / max(height, 1) < 24 and y < h * 0.6):
            continue
        # Repeated upright separators distinguish a VIN grid from a ribbon or rule.
        roi = copper[y : y + height, x : x + width]
        peaks = np.flatnonzero((roi > 0).sum(axis=0) > height * 0.65)
        groups = np.split(peaks, np.flatnonzero(np.diff(peaks) > 2) + 1)
        centers = [float(g.mean()) for g in groups if len(g)]
        if not 15 <= len(centers) <= 19:
            continue
        gaps = np.diff(centers)
        if gaps.std() / gaps.mean() > 0.30:
            continue
        matches.append(Box(x=x, y=y, width=width, height=height))
    return matches[0] if len(matches) == 1 else None


def value_boxes(grid: Box, image: np.ndarray) -> dict[str, Box]:
    h, w = image.shape[:2]
    boxes = {}
    for field, (x1, y1, x2, y2) in VALUE_REGIONS.items():
        left, right = round(grid.x + x1 * grid.width), round(grid.x + x2 * grid.width)
        top, bottom = round(grid.y + y1 * grid.width), round(grid.y + y2 * grid.width)
        # A partial photograph is not sufficient to apply the whole form profile.
        if min(left, top) < 0 or right > w or bottom > h:
            return {}
        boxes[field] = Box(x=left, y=top, width=right - left, height=bottom - top)
    return boxes


def align_legacy(image):
    """Canonical scale/origin only for a uniquely detected legacy grid."""
    original_h, original_w = image.shape[:2]
    choices = []
    for turns in range(4):
        candidate = np.rot90(image, turns).copy() if turns else image
        grid = detect_grid(candidate)
        if grid:
            choices.append((turns, candidate, grid))
    if len(choices) != 1:
        return image, np.eye(3), []
    turns, candidate, grid = choices[0]
    matrices = [
        np.eye(3),
        np.array([[0, 1, 0], [-1, 0, original_w - 1], [0, 0, 1]]),
        np.array([[-1, 0, original_w - 1], [0, -1, original_h - 1], [0, 0, 1]]),
        np.array([[0, -1, original_h - 1], [1, 0, 0], [0, 0, 1]]),
    ]
    if turns == 0 and (grid.x, grid.y, grid.width) == _REFERENCE_GRID:
        return image, np.eye(3), []
    scale = _REFERENCE_GRID[2] / grid.width
    matrix = np.array(
        [
            [scale, 0, _REFERENCE_GRID[0] - grid.x * scale],
            [0, scale, _REFERENCE_GRID[1] - grid.y * scale],
            [0, 0, 1],
        ],
        float,
    )
    candidate = cv2.warpAffine(
        candidate, matrix[:2], (1844, 2644), flags=cv2.INTER_CUBIC, borderValue=(255, 255, 255)
    )
    return candidate, matrix @ matrices[turns], ["legacy_grid_scale_origin_alignment"]
