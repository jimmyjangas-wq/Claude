#!/usr/bin/env python3
"""Generate the app icons (solid teal squares) using only the standard library.

Run once: python make_icons.py
Produces static/icon-180.png and static/icon-512.png.
"""

import struct
import zlib
from pathlib import Path

TEAL = (11, 114, 133)  # matches the app theme colour


def make_png(path: Path, size: int, rgb: tuple[int, int, int]) -> None:
    r, g, b = rgb
    row = bytes([0]) + bytes([r, g, b]) * size  # filter byte + RGB pixels
    raw = row * size
    compressed = zlib.compress(raw, 9)

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)  # 8-bit RGB
    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", compressed)
        + chunk(b"IEND", b"")
    )
    path.write_bytes(png)
    print(f"wrote {path} ({size}x{size})")


if __name__ == "__main__":
    static = Path(__file__).parent / "static"
    make_png(static / "icon-180.png", 180, TEAL)
    make_png(static / "icon-512.png", 512, TEAL)
