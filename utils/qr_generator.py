from __future__ import annotations

import base64
import io
import json
from typing import Any


def generate_qr_data_url(data: str | dict[str, Any], size: int = 120) -> str:
    """
    Build a QR image data-url (PNG base64) from string or JSON-serializable dict.
    Returns empty string on any generation failure.
    """
    try:
        import qrcode
    except Exception:
        return ""

    if data is None:
        return ""

    try:
        payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")) if isinstance(data, dict) else str(data)
    except Exception:
        payload = str(data)

    if not payload.strip():
        return ""

    try:
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=2,
        )
        qr.add_data(payload)
        qr.make(fit=True)
        image = qr.make_image(fill_color="black", back_color="white")
        if hasattr(image, "resize"):
            image = image.resize((size, size))

        output = io.BytesIO()
        image.save(output, format="PNG")
        encoded = base64.b64encode(output.getvalue()).decode("ascii")
        return f"data:image/png;base64,{encoded}"
    except Exception:
        return ""
