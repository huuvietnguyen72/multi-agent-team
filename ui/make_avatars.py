"""Vẽ 6 ảnh đại diện cho tin nhắn của từng role vào public/avatars/ (chạy tay một lần, cần Pillow):

    python ui/make_avatars.py
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
ROLES = {  # tên tác giả viết thường -> (chữ, màu nền); màu giống bản thiết kế
    "pm": ("PM", "#6941C6"), "ba": ("BA", "#B54708"), "backend": ("BE", "#175CD3"),
    "frontend": ("FE", "#087443"), "reviewer": ("RV", "#C11574"), "tester": ("QA", "#344054"),
}


def main() -> None:
    out = ROOT / "public" / "avatars"
    out.mkdir(parents=True, exist_ok=True)
    font = ImageFont.load_default(size=96)
    for name, (text, color) in ROLES.items():
        img = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.ellipse((0, 0, 255, 255), fill=color)
        d.text((128, 128), text, fill="white", font=font, anchor="mm")
        img.save(out / f"{name}.png")
        print(out / f"{name}.png")


if __name__ == "__main__":
    main()
