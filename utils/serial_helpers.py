from __future__ import annotations


def extract_serials(line_data: dict) -> list[str]:
    """استخراج الأرقام التسلسلية من بيانات السطر (list أو str)."""
    serials = line_data.get("serials") or []
    if isinstance(serials, str):
        serials = serials.replace("\r", "\n").replace(",", "\n").split("\n")
    return [str(s).strip() for s in serials if str(s).strip()]


def validate_serials(serials: list[str], product_name: str, quantity: int):
    """التحقق من عدد السيريالات وعدم التكرار. يرفع ValueError في حال وجود خطأ."""
    if len(serials) != quantity:
        raise ValueError(
            f'⚠️ المنتج "{product_name}" يتطلب {quantity} رقم تسلسلي، '
            f"ولكن تم إدخال {len(serials)} فقط."
        )
    if len(serials) != len(set(serials)):
        raise ValueError(f'⚠️ يوجد أرقام تسلسلية مكررة للمنتج "{product_name}".')
