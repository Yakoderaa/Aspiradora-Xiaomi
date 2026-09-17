from pathlib import Path
from io import BytesIO

import requests
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "xiaomi_robot_vacuum_e10.jpg"

# Imagen oficial publicada por Xiaomi para la página del Robot Vacuum E10.
URL = (
    "https://i02.appmifile.com/mi-com-product/fly-birds/pc/"
    "xiaomi-robot-vacuum-e10/bc5c450703d2d8faee7d609f00997da4.jpg"
)


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    response = requests.get(
        URL,
        timeout=30,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/152 Safari/537.36"
            )
        },
    )
    response.raise_for_status()
    image = Image.open(BytesIO(response.content)).convert("RGB")
    if image.width < 300 or image.height < 200:
        raise RuntimeError(
            f"La imagen oficial del E10 llegó con tamaño inesperado: {image.width}x{image.height}"
        )
    # Normalizamos a JPEG para que Pillow pueda abrirla igual en fuente y PyInstaller.
    image.save(OUT, format="JPEG", quality=92, optimize=True)
    print(f"Foto oficial E10 guardada: {OUT} ({image.width}x{image.height})")


if __name__ == "__main__":
    main()
