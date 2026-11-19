from __future__ import annotations

import math
from pathlib import Path
import struct
import zlib


def create_png(width: int, height: int, get_pixel_func) -> bytes:
    """Generate valid PNG 32-bit RGBA binary data using Python standard library."""
    raw_lines = bytearray()
    for y in range(height):
        raw_lines.append(0)  # filter type 0: None
        for x in range(width):
            r, g, b, a = get_pixel_func(x, y, width, height)
            raw_lines.extend((r, g, b, a))

    compressed = zlib.compress(bytes(raw_lines), 9)

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    png = bytearray(b"\x89PNG\r\n\x1a\n")
    png.extend(chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)))
    png.extend(chunk(b"IDAT", compressed))
    png.extend(chunk(b"IEND", b""))
    return bytes(png)


def point_in_polygon(px: float, py: float, poly: list[tuple[float, float]]) -> bool:
    """Ray-casting algorithm to test if point is inside polygon."""
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if ((y1 > py) != (y2 > py)) and (px < (x2 - x1) * (py - y1) / (y2 - y1 + 1e-12) + x1):
            inside = not inside
    return inside


def dist_to_segment(px: float, py: float, x1: float, y1: float, x2: float, y2: float) -> float:
    """Distance from point to a line segment."""
    dx = x2 - x1
    dy = y2 - y1
    l2 = dx * dx + dy * dy
    if l2 == 0:
        return math.hypot(px - x1, py - y1)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / l2))
    proj_x = x1 + t * dx
    proj_y = y1 + t * dy
    return math.hypot(px - proj_x, py - proj_y)


def make_anvexa_icon(is_maskable: bool = False):
    # Normalized coordinate system 0..64
    poly_a_outer = [
        (32.0, 11.0),
        (15.0, 50.0),
        (24.0, 50.0),
        (28.0, 40.0),
        (36.0, 40.0),
        (40.0, 50.0),
        (49.0, 50.0),
    ]
    poly_a_inner = [
        (32.0, 23.0),
        (34.6, 33.0),
        (29.4, 33.0),
    ]

    def get_pixel(x: int, y: int, width: int, height: int) -> tuple[int, int, int, int]:
        fx = (x + 0.5) / width
        fy = (y + 0.5) / height

        # Map to 0..64 coords
        if is_maskable:
            scale = 0.72
            offset = (1.0 - scale) / 2.0
            sx = (fx - offset) / scale * 64.0
            sy = (fy - offset) / scale * 64.0
        else:
            scale = 0.94
            offset = (1.0 - scale) / 2.0
            sx = (fx - offset) / scale * 64.0
            sy = (fy - offset) / scale * 64.0

        # Background rounded rect check
        if not is_maskable:
            # Rounded rect from 2 to 62 (center 32, radius 14)
            rx = 14.0
            left, right, top, bottom = 2.0, 62.0, 2.0, 62.0
            if sx < left or sx > right or sy < top or sy > bottom:
                return (0, 0, 0, 0)
            # Corner checks
            if sx < left + rx and sy < top + rx and math.hypot(sx - (left + rx), sy - (top + rx)) > rx:
                return (0, 0, 0, 0)
            if sx > right - rx and sy < top + rx and math.hypot(sx - (right - rx), sy - (top + rx)) > rx:
                return (0, 0, 0, 0)
            if sx > right - rx and sy > bottom - rx and math.hypot(sx - (right - rx), sy - (bottom - rx)) > rx:
                return (0, 0, 0, 0)
            if sx < left + rx and sy > bottom - rx and math.hypot(sx - (left + rx), sy - (bottom - rx)) > rx:
                return (0, 0, 0, 0)

        # Base gradient: #6366f1 (99, 102, 241) to #9333ea (147, 51, 234)
        t = (fx + fy) / 2.0
        bg_r = int(99 + (147 - 99) * t)
        bg_g = int(102 + (51 - 102) * t)
        bg_b = int(241 + (234 - 241) * t)
        bg_a = 255

        # Checkmark & badge coordinates: center at (48, 48)
        d_badge = math.hypot(sx - 48.0, sy - 48.0)
        if d_badge <= 11.5:
            if d_badge > 9.8:
                return (15, 23, 42, 255)  # Dark border ring #0f172a
            # Inside green badge
            # Checkmark strokes: (43.5, 48.0) -> (46.5, 51.0) -> (52.5, 44.5)
            d1 = dist_to_segment(sx, sy, 43.5, 48.0, 46.5, 51.0)
            d2 = dist_to_segment(sx, sy, 46.5, 51.0, 52.5, 44.5)
            if min(d1, d2) <= 1.2:
                return (255, 255, 255, 255)  # White checkmark
            # Green gradient #34d399 (52, 211, 153) to #059669 (5, 150, 105)
            tb = (sx - 38.0 + sy - 38.0) / 20.0
            tb = max(0.0, min(1.0, tb))
            gr_r = int(52 + (5 - 52) * tb)
            gr_g = int(211 + (150 - 211) * tb)
            gr_b = int(153 + (105 - 153) * tb)
            return (gr_r, gr_g, gr_b, 255)

        # Geometric letter "A"
        # Shadow
        in_outer_shadow = point_in_polygon(sx, sy - 1.2, poly_a_outer)
        in_inner_shadow = point_in_polygon(sx, sy - 1.2, poly_a_inner)
        is_shadow = in_outer_shadow and not in_inner_shadow

        in_outer = point_in_polygon(sx, sy, poly_a_outer)
        in_inner = point_in_polygon(sx, sy, poly_a_inner)
        is_a = in_outer and not in_inner

        if is_a:
            return (255, 255, 255, 255)
        elif is_shadow:
            return (int(bg_r * 0.7), int(bg_g * 0.7), int(bg_b * 0.7), 255)

        return (bg_r, bg_g, bg_b, bg_a)

    return get_pixel


def main():
    icons_dir = Path(__file__).resolve().parents[1] / "backend" / "app" / "static" / "icons"
    icons_dir.mkdir(parents=True, exist_ok=True)

    targets = [
        ("icon-192.png", 192, 192, False),
        ("icon-192-maskable.png", 192, 192, True),
        ("icon-512.png", 512, 512, False),
        ("icon-512-maskable.png", 512, 512, True),
        ("apple-touch-icon.png", 180, 180, False),
    ]

    for fname, w, h, maskable in targets:
        out_path = icons_dir / fname
        print(f"Generating {fname} ({w}x{h})...")
        func = make_anvexa_icon(is_maskable=maskable)
        png_bytes = create_png(w, h, func)
        out_path.write_bytes(png_bytes)
        print(f"  [+] Saved {out_path} ({len(png_bytes)} bytes)")

    # Also copy svg as scalable icon
    svg_source = icons_dir.parent / "favicon.svg"
    if svg_source.is_file():
        (icons_dir / "icon.svg").write_text(svg_source.read_text(encoding="utf-8"), encoding="utf-8")
        print("  [+] Copied icon.svg")


if __name__ == "__main__":
    main()
