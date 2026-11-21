"""Food list: turn an untrusted image upload into a clean PNG, without ever parsing an image file.

The browser decodes the photo itself, scales it down and sends only raw pixels:
    4-byte header: width, height (unsigned 16-bit, big-endian), each 1..MAX_SIDE
    then exactly width * height * 3 bytes of RGB, row by row, top to bottom
parse_rgb() checks that the numbers add up exactly (anything else is rejected) and returns the
pixels; encode_png() writes a brand-new PNG from them with zlib. No image decoder ever sees the
uploaded bytes, and nothing in them (metadata, location tags, extra chunks, scripts, polyglot
files) can survive: the saved file is only our own PNG header plus the pixel values.
"""

import struct
import zlib

MAX_SIDE = 800
HEADER = struct.Struct(">HH")
MAX_BYTES = HEADER.size + MAX_SIDE * MAX_SIDE * 3
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class BadImage(ValueError):
    """The upload isn't a well-formed raw RGB image (the message is shown to the user)."""


def parse_rgb(body):
    """Return (width, height, rgb bytes) from an upload, or raise BadImage."""
    if not isinstance(body, (bytes, bytearray)) or len(body) < HEADER.size:
        raise BadImage("The image data is too short.")
    if len(body) > MAX_BYTES:
        raise BadImage("The image is too big.")
    width, height = HEADER.unpack_from(body)
    if not (1 <= width <= MAX_SIDE and 1 <= height <= MAX_SIDE):
        raise BadImage(f"Images can be at most {MAX_SIDE}x{MAX_SIDE} pixels.")
    if len(body) != HEADER.size + width * height * 3:
        raise BadImage("The image data has the wrong size.")
    return width, height, bytes(body[HEADER.size:])


def _chunk(kind, data):
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


def encode_png(width, height, rgb):
    """A minimal 8-bit RGB PNG (IHDR, IDAT, IEND) holding exactly these pixels."""
    stride = width * 3
    if len(rgb) != stride * height:
        raise BadImage("The image data has the wrong size.")
    rows = b"".join(b"\x00" + rgb[y:y + stride] for y in range(0, len(rgb), stride))
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (PNG_SIGNATURE + _chunk(b"IHDR", header)
            + _chunk(b"IDAT", zlib.compress(rows, 6)) + _chunk(b"IEND", b""))
