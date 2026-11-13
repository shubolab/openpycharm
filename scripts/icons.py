"""Generate the product's geometric icon assets; no reference art is used."""
from io import BytesIO
from pathlib import Path
import subprocess
import tempfile
from product import ROOT


def image(size=1024):
    from PIL import Image, ImageDraw
    canvas = Image.new("RGBA", (size, size))
    pixels = canvas.load()
    for y in range(size):
        for x in range(size):
            t = (x + y) / (2 * size)
            pixels[x, y] = (int(37 + 20*t), int(199 - 75*t), int(183 + 53*t), 255)
    mask = Image.new("L", (size, size))
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size-1, size-1), radius=size*28/128, fill=255)
    canvas.putalpha(mask)
    draw = ImageDraw.Draw(canvas)
    scale = size / 128
    points = lambda values: [(int(x*scale), int(y*scale)) for x, y in values]
    for values in (((28,38),(55,38),(55,70),(28,70),(28,38)),
                   ((78,89),(78,38),(100,38),(100,60),(78,60)), ((28,90),(55,90))):
        draw.line(points(values), fill="#101820", width=max(1,int(10*scale)), joint="curve")
    return canvas


def resources():
    icon = image()
    buffer = BytesIO()
    icon.save(buffer, format="PNG")
    # Splash is intentionally minimal and contains only original product art.
    from PIL import Image, ImageDraw, ImageFont
    splash = Image.new("RGB", (800, 500), "#1e1f22")
    splash.paste(icon.resize((128,128)), (64,64), icon.resize((128,128)))
    draw = ImageDraw.Draw(splash)
    font_path = Path("/System/Library/Fonts/Supplemental/Arial.ttf")
    if not font_path.exists():
        font_path = Path("C:/Windows/Fonts/arial.ttf")
    font = ImageFont.truetype(str(font_path), 48) if font_path.exists() else ImageFont.load_default(size=48)
    small = ImageFont.truetype(str(font_path), 20) if font_path.exists() else ImageFont.load_default(size=20)
    draw.text((64,230), "OpenPyCharm", font=font, fill="#f0f1f3")
    draw.text((64,300), "An open Python IDE", font=small, fill="#a8abb3")
    splash_buffer = BytesIO()
    splash.save(splash_buffer, format="PNG")
    svg = (ROOT / "product/icon.svg").read_bytes()
    return {"pycharm_core_logo.png": splash_buffer.getvalue(),
            **{name: svg for name in ("pycharm-ce.svg", "pycharm-ce_16.svg", "pycharm-ce-eap.svg", "pycharm-ce-eap_16.svg")}}


def mac_icon(contents):
    with tempfile.TemporaryDirectory(prefix="openpycharm-icon-") as directory:
        iconset = Path(directory) / "openpycharm.iconset"
        iconset.mkdir()
        original = image()
        for size in (16,32,128,256,512):
            original.resize((size,size)).save(iconset / f"icon_{size}x{size}.png")
            original.resize((size*2,size*2)).save(iconset / f"icon_{size}x{size}@2x.png")
        subprocess.run(["iconutil", "--convert", "icns", "--output", str(contents / "Resources/openpycharm.icns"), str(iconset)], check=True)
