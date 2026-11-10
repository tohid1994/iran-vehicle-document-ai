"""Adapters must never fetch models or send images to external services."""

from typing import Protocol

import numpy as np

from ..schemas import TextRegion


class OCRAdapter(Protocol):
    name: str

    def recognize(self, image: np.ndarray, timeout: float) -> list[TextRegion]: ...
