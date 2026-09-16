from pathlib import Path
import io
import urllib.request

from PIL import Image, ImageDraw

ICON_URL = "https://play-lh.googleusercontent.com/c0B5Rrg5pxwCH08jt7JlyW11eGLbERV_soQtDaHu4_FL97Xtl1SjWUyQyNFTZE_SQVBAz7qDRvKqdiUkGMlneA=w240-h480"
OUT_DIR = Path("assets")
PNG_PATH = OUT_DIR / "mi_home.png"
ICO_PATH = OUT_DIR / "mi_home.ico"


def fallback_icon():
    image = Image.new("RGBA", (512, 512), (30, 199, 151, 255))
    draw = ImageDraw.Draw(image)
    s = 2
    draw.polygon(
        [(63*s,59*s),(84*s,59*s),(120*s,76*s),(157*s,59*s),(177*s,59*s),
         (177*s,91*s),(155*s,101*s),(155*s,82*s),(120*s,98*s),(85*s,82*s),
         (85*s,128*s),(63*s,138*s)], fill="white"
    )
    draw.arc((72*s,92*s,184*s,192*s), start=20, end=160, fill="white", width=42)
    draw.line([(175*s,116*s),(174*s,143*s)], fill="white", width=42)
    return image


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    try:
        request = urllib.request.Request(ICON_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(request, timeout=20) as response:
            data = response.read()
        image = Image.open(io.BytesIO(data)).convert("RGBA")
    except Exception:
        image = fallback_icon()

    image.save(PNG_PATH, format="PNG")
    image.save(
        ICO_PATH,
        format="ICO",
        sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)],
    )
    print(f"Icono generado: {ICO_PATH}")


if __name__ == "__main__":
    main()
