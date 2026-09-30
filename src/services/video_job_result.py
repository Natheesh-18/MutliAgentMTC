"""Result type returned by the video preprocessing worker."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class VideoJobResult:
    success: bool
    retriable: bool
    message: str
    failure_code: str | None = None
