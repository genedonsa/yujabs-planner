"""'우리 썸네일 시안' 합성.

배경(원본 장면 또는 원본 썸네일)을 1280x720으로 꽉 채우고, 아래쪽을 검게 깔고,
회원 템플릿 PNG(투명 영역 = 배경 자리)를 덮은 뒤, 한국어 문구 두 줄을 올린다.
문구는 원본 썸네일 문구의 한국어판이고, 스타일(위치·폰트·색)만 회원 설정을 따른다.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1280, 720
ASSETS = Path(__file__).resolve().parents[1] / "assets"


@dataclass
class Style:
    position: str = "bottom"          # bottom | top
    color1: str = "#FFFFFF"           # 첫 줄
    color2: str = "#FFD21F"           # 둘째 줄(강조)
    stroke: str = "#000000"
    font_path: str = str(ASSETS / "BlackHanSans-Regular.ttf")
    max_font: int = 120
    shade: bool = True                 # 글씨 쪽을 검게 깔기


def _cover(img: Image.Image) -> Image.Image:
    img = img.convert("RGB")
    scale = max(W / img.width, H / img.height)
    img = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
    left, top = (img.width - W) // 2, 0  # 위쪽(얼굴)을 살린다
    return img.crop((left, top, left + W, top + H))


def _shade(img: Image.Image, position: str) -> Image.Image:
    grad = Image.new("L", (1, H))
    for y in range(H):
        t = y / H if position == "bottom" else 1 - y / H
        a = 0 if t < 0.35 else min(255, int((t - 0.35) / 0.3 * 245))
        grad.putpixel((0, y), a)
    black = Image.new("RGB", (W, H), "black")
    return Image.composite(black, img, grad.resize((W, H)))


def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default(size)


def _fit(draw: ImageDraw.ImageDraw, lines: list[str], style: Style, max_w: int) -> ImageFont.FreeTypeFont:
    size = style.max_font
    while size > 40:
        f = _font(style.font_path, size)
        if all(draw.textlength(l, font=f) <= max_w for l in lines):
            return f
        size -= 4
    return _font(style.font_path, size)


def compose(background: Path, line1: str, line2: str, out: Path,
            template: Path | None = None, style: Style | None = None) -> Path:
    style = style or Style()
    img = _cover(Image.open(background))
    if style.shade:
        img = _shade(img, style.position)
    if template and Path(template).exists():
        tpl = Image.open(template).convert("RGBA").resize((W, H))
        img = Image.alpha_composite(img.convert("RGBA"), tpl).convert("RGB")
    draw = ImageDraw.Draw(img)
    margin = 56
    lines = [l for l in (line1, line2) if l]
    font = _fit(draw, lines, style, W - margin * 2)
    lh = int(font.size * 1.12)
    y = H - margin - lh * len(lines) if style.position == "bottom" else margin
    for i, l in enumerate(lines):
        draw.text((margin, y + i * lh), l, font=font, fill=style.color1 if i == 0 else style.color2,
                  stroke_width=max(4, font.size // 14), stroke_fill=style.stroke)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, quality=92)
    return out
