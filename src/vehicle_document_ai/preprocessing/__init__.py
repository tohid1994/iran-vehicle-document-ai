"""Bounded raster decoding and opt-in image transformations."""

import io
import warnings
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from ..core import DocumentError, Settings
from ..schemas import Quality


def decode(source: bytes | str | Path, settings: Settings) -> np.ndarray:
    if isinstance(source, (str, Path)):
        with Path(source).open("rb") as stream:
            data = stream.read(settings.max_bytes + 1)
    else:
        data = source
    if not data or len(data) > settings.max_bytes:
        raise DocumentError("image_size_limit")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as im:
                if im.format not in {"JPEG", "PNG", "WEBP"}:
                    raise DocumentError("unsupported_image")
                w, h = im.size
                if w * h > settings.max_pixels or max(w, h) > settings.max_dimension:
                    raise DocumentError("image_pixel_limit")
                if w < 32 or h < 32 or getattr(im, "n_frames", 1) != 1:
                    raise DocumentError("unsupported_image")
                return np.array(ImageOps.exif_transpose(im).convert("RGB"))
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        raise DocumentError("invalid_image") from exc


def preprocess(image: np.ndarray, settings: Settings) -> tuple[np.ndarray, Quality]:
    transform = np.eye(3, dtype=float)
    operations = []
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    if settings.rectify:
        edges = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 50, 150)
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in sorted(contours, key=cv2.contourArea, reverse=True)[:5]:
            polygon = cv2.approxPolyDP(c, 0.02 * cv2.arcLength(c, True), True)
            if len(polygon) != 4 or not cv2.isContourConvex(polygon):
                continue
            if cv2.contourArea(polygon) < gray.size * 0.45:
                continue
            points = polygon.reshape(4, 2).astype(np.float32)
            sums, diffs = points.sum(axis=1), np.diff(points, axis=1).ravel()
            ordered = points[[sums.argmin(), diffs.argmin(), sums.argmax(), diffs.argmax()]]
            if len(np.unique(ordered, axis=0)) != 4:
                continue
            tl, tr, br, bl = ordered
            w = int(max(np.linalg.norm(tr - tl), np.linalg.norm(br - bl)))
            h = int(max(np.linalg.norm(bl - tl), np.linalg.norm(br - tr)))
            if min(w, h) < 32:
                continue
            target = np.float32([[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]])
            transform = cv2.getPerspectiveTransform(ordered, target)
            image = cv2.warpPerspective(image, transform, (w, h), borderValue=(255, 255, 255))
            operations.append("perspective_rectification")
            break
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    if settings.deskew:
        lines = cv2.HoughLinesP(
            cv2.Canny(gray, 50, 150),
            1,
            np.pi / 180,
            threshold=80,
            minLineLength=gray.shape[1] // 5,
            maxLineGap=15,
        )
        angles = (
            []
            if lines is None
            else [np.degrees(np.arctan2(y2 - y1, x2 - x1)) for x1, y1, x2, y2 in lines[:, 0]]
        )
        angles = [a for a in angles if abs(a) < 10]
        if len(angles) >= 4:
            angle = float(np.median(angles))
            if 0.5 < abs(angle) < 8:
                h, w = gray.shape
                affine = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1)
                image = cv2.warpAffine(image, affine, (w, h), borderValue=(255, 255, 255))
                transform = np.vstack([affine, [0, 0, 1]]) @ transform
                operations.append("small_angle_deskew")
    from ..layout.legacy import align_legacy

    image, alignment, alignment_operations = align_legacy(image)
    transform = alignment @ transform
    operations.extend(alignment_operations)
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    contrast, brightness = float(gray.std()), float(gray.mean())
    blur = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    issues = []
    if blur < 70:
        issues.append("possible_blur")
    if brightness < 50 or brightness > 240:
        issues.append("poor_exposure")
    if contrast < 25:
        issues.append("low_contrast")
    if settings.enhance and contrast < 25:
        lab = cv2.cvtColor(image, cv2.COLOR_RGB2LAB)
        lab[:, :, 0] = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(lab[:, :, 0])
        image = cv2.cvtColor(lab, cv2.COLOR_LAB2RGB)
        operations.append("conditional_clahe")
    return image, Quality(
        width=image.shape[1],
        height=image.shape[0],
        blurVariance=blur,
        brightness=brightness,
        contrast=contrast,
        warnings=issues,
        operations=operations,
        originalToProcessed=transform.tolist(),
    )
