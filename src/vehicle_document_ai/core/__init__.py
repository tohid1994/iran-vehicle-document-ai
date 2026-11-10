"""Resource limits and safe errors shared by all interfaces."""

from dataclasses import dataclass
from pathlib import Path


class DocumentError(Exception):
    """Message is a fixed public error code, never OCR text or user paths."""


@dataclass(frozen=True)
class Settings:
    model_dir: Path = Path("models")
    max_bytes: int = 10 * 1024 * 1024
    max_pixels: int = 16_000_000
    max_dimension: int = 8000
    timeout: float = 30.0
    rectify: bool = False
    deskew: bool = False
    enhance: bool = False

    def __post_init__(self):
        if self.max_bytes <= 0 or self.max_pixels <= 0 or self.timeout <= 0:
            raise ValueError("invalid_resource_limits")
