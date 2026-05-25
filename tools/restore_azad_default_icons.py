import os

from PIL import Image, ImageOps


def _save_png(img: Image.Image, path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img.save(path, format="PNG", optimize=True)


def main() -> None:
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    static_img = os.path.join(project_root, "static", "img")

    src = os.path.join(static_img, "azad_logo_white_on_dark.png")
    base = Image.open(src).convert("RGBA")

    favicon = ImageOps.fit(base, (32, 32), method=Image.LANCZOS)
    icon_192 = ImageOps.fit(base, (192, 192), method=Image.LANCZOS)
    icon_512 = ImageOps.fit(base, (512, 512), method=Image.LANCZOS)

    _save_png(favicon, os.path.join(static_img, "azad_favicon.png"))
    _save_png(icon_192, os.path.join(static_img, "icon-192.png"))
    _save_png(icon_512, os.path.join(static_img, "icon-512.png"))

    print("OK: Restored default icons (azad_favicon.png, icon-192.png, icon-512.png)")


if __name__ == "__main__":
    main()

