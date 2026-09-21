"""
TAILOR24 — QR Code Service
Generates stable, human-readable garment QR identifiers.
Format: GRT-T24-000000123
No QR image binary is stored in MongoDB.
"""
from __future__ import annotations

import io
import re

import qrcode
from qrcode.image.pil import PilImage


QR_PREFIX = "GRT-T24-"
QR_PATTERN = re.compile(r"^GRT-T24-\d{9}$")


def generate_qr_value(sequence: int) -> str:
    """Return a stable, unique QR identifier string for a garment."""
    return f"{QR_PREFIX}{sequence:09d}"


def is_valid_qr_value(value: str) -> bool:
    """Return True if value matches the GRT-T24-XXXXXXXXX format."""
    return bool(QR_PATTERN.match(value))


def generate_qr_image_bytes(qr_value: str) -> bytes:
    """
    Generate a PNG QR-code image for the given value.
    Returns raw PNG bytes — caller decides where to store them
    (object storage, not MongoDB).
    """
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(qr_value)
    qr.make(fit=True)
    img: PilImage = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
