"""Small, dependency-free image type checks for the read-only file managers."""

from __future__ import annotations

MAX_IMAGE_BYTES = 8 * 1024 * 1024


def image_media_type(data: bytes) -> str | None:
    """Return a safe raster image MIME type, or None for unsupported data.

    SVG is intentionally not included because it can carry scripts when opened
    inline in a browser.
    """
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data.startswith(b"BM"):
        return "image/bmp"
    return None


def is_image_name(name: str) -> bool:
    lower = str(name or "").lower()
    return lower.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"))
