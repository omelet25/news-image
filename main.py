#!/usr/bin/env python3
"""The World in One Day -- Monday 23 November 2026 in one image.

A dense broadsheet front page drawn entirely in code with the Python
standard library only (no PIL, no fonts, no network).

Readability pass (v4): the page is composed in a 2048x2048 design
space but rasterised on a 4096x4096 canvas and reduced to 1024x1024
with a 4x4 area-average (box) filter, so stroke edges land smoothly
instead of crumbling.  Small type gets proportionally heavier strokes
and darker ink than in the previous edition, and the smallest sizes
were raised a step.  The output is deterministic: the same bytes on
every run.

Writes /output/entry.png (falls back to ./entry.png when /output is
not writable, e.g. a local dry run).
"""

import math
import os
import struct
import zlib
from array import array

DS = 2048         # design-space size: every layout number lives here
W = 4096          # internal render canvas
H = 4096
K = W / DS        # design -> render scale factor (2.0)
OUT = 1024        # final image size

# ---------------------------------------------------------------- palette
PAPER = (247, 243, 232)      # cream newsprint
CARD_BG = (253, 251, 245)    # card face, a touch lighter than the sheet
NAVY = (17, 31, 59)          # deep ink navy
INK = (26, 29, 38)           # body text (darkened for small sizes)
DARKTXT = (43, 46, 58)       # captions and other small print
GRAY = (78, 83, 96)          # secondary text (darkened vs v3)
FAINT = (203, 199, 186)      # hairlines on the sheet
RED = (178, 33, 44)          # accent red
TEAL = (0, 104, 94)          # REPORTED tag
GOLD = (198, 158, 52)
WHITE = (255, 255, 255)

buf = bytearray(bytes(PAPER) * (W * H))


# ------------------------------------------------------- canvas (render)
def _fill_r(x0, y0, x1, y1, c):
    """Fill an axis-aligned rectangle on the render canvas, clipped."""
    x0 = max(0, int(x0)); y0 = max(0, int(y0))
    x1 = min(W, int(x1)); y1 = min(H, int(y1))
    if x1 <= x0 or y1 <= y0:
        return
    row = bytes(c) * (x1 - x0)
    n = len(row)
    for y in range(y0, y1):
        i = (y * W + x0) * 3
        buf[i:i + n] = row


def _disc_r(cx, cy, r, c):
    """Filled circle on the render canvas (float centre/radius)."""
    R = int(math.ceil(r))
    for dy in range(-R, R + 1):
        dx = math.sqrt(max(0.0, r * r - dy * dy))
        _fill_r(cx - dx, cy + dy, cx + dx + 1, cy + dy + 1, c)


def _line_r(x0, y0, x1, y1, w, c):
    """Thick line with round caps, drawn as a chain of discs."""
    r = max(0.8, w / 2.0)
    d = math.hypot(x1 - x0, y1 - y0)
    steps = max(1, int(d / max(1.0, r * 0.9)))
    for i in range(steps + 1):
        t = i / steps
        _disc_r(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, r, c)


def _fill_poly_r(pts, c):
    """Scanline even-odd polygon fill on the render canvas."""
    ys = [p[1] for p in pts]
    ymin = max(0, int(min(ys)))
    ymax = min(H - 1, int(max(ys)))
    n = len(pts)
    for y in range(ymin, ymax + 1):
        yc = y + 0.5
        xs = []
        for i in range(n):
            x0, y0 = pts[i]
            x1, y1 = pts[(i + 1) % n]
            if (y0 <= yc < y1) or (y1 <= yc < y0):
                xs.append(x0 + (yc - y0) * (x1 - x0) / (y1 - y0))
        xs.sort()
        for i in range(0, len(xs) - 1, 2):
            _fill_r(xs[i], y, xs[i + 1] + 1, y + 1, c)


# ------------------------------------------- canvas (design-space facade)
# Every public primitive takes design-space coordinates (the 2048 grid
# the layout is written in) and scales them onto the render canvas.

def fill_rect(x0, y0, x1, y1, c):
    _fill_r(x0 * K, y0 * K, x1 * K, y1 * K, c)


def disc(cx, cy, r, c):
    _disc_r(cx * K, cy * K, r * K, c)


def line(x0, y0, x1, y1, w, c):
    _line_r(x0 * K, y0 * K, x1 * K, y1 * K, w * K, c)


def polyline(pts, w, c, close=False):
    seq = list(pts)
    if close and len(seq) > 2:
        seq = seq + [seq[0]]
    for i in range(len(seq) - 1):
        line(seq[i][0], seq[i][1], seq[i + 1][0], seq[i + 1][1], w, c)


def fill_poly(pts, c):
    _fill_poly_r([(x * K, y * K) for x, y in pts], c)


def ellipse_pts(cx, cy, rx, ry, n=44, a0=0.0, a1=360.0):
    return [(cx + rx * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
             cy + ry * math.sin(math.radians(a0 + (a1 - a0) * i / n)))
            for i in range(n + 1)]


def fill_ellipse(cx, cy, rx, ry, c):
    fill_poly(ellipse_pts(cx, cy, rx, ry), c)


def outline_ellipse(cx, cy, rx, ry, w, c, a0=0.0, a1=360.0):
    polyline(ellipse_pts(cx, cy, rx, ry, 44, a0, a1), w, c)


def rrect(x0, y0, x1, y1, r, c):
    """Filled rounded rectangle."""
    fill_rect(x0 + r, y0, x1 - r, y1, c)
    fill_rect(x0, y0 + r, x1, y1 - r, c)
    disc(x0 + r, y0 + r, r, c)
    disc(x1 - r, y0 + r, r, c)
    disc(x0 + r, y1 - r, r, c)
    disc(x1 - r, y1 - r, r, c)


def rrect_outline(x0, y0, x1, y1, r, w, c):
    line(x0 + r, y0, x1 - r, y0, w, c)
    line(x0 + r, y1, x1 - r, y1, w, c)
    line(x0, y0 + r, x0, y1 - r, w, c)
    line(x1, y0 + r, x1, y1 - r, w, c)
    polyline(ellipse_pts(x0 + r, y0 + r, r, r, 12, 180, 270), w, c)
    polyline(ellipse_pts(x1 - r, y0 + r, r, r, 12, 270, 360), w, c)
    polyline(ellipse_pts(x1 - r, y1 - r, r, r, 12, 0, 90), w, c)
    polyline(ellipse_pts(x0 + r, y1 - r, r, r, 12, 90, 180), w, c)


# ---------------------------------------------------------------- png out
def downsample():
    """4096x4096 -> 1024x1024 with a 4x4 area-average box filter.

    Two passes: first sum each group of 4 horizontal pixels (per
    channel) into a uint16 buffer, then sum groups of 4 rows and
    divide by 16 with rounding.
    """
    W3 = W * 3
    hsums = array('H')
    for y in range(H):
        row = buf[y * W3:(y + 1) * W3]
        chans = []
        for base in (0, 1, 2):
            s = [sum(t) for t in zip(row[base::12], row[base + 3::12],
                                     row[base + 6::12], row[base + 9::12])]
            chans.append(s)
        vals = [0] * (OUT * 3)
        vals[0::3] = chans[0]
        vals[1::3] = chans[1]
        vals[2::3] = chans[2]
        hsums.extend(vals)
    out = bytearray(OUT * OUT * 3)
    stride = OUT * 3
    for oy in range(OUT):
        a = (4 * oy) * stride
        rows = [hsums[a + j * stride:a + (j + 1) * stride] for j in range(4)]
        orow = bytes((v + 8) >> 4 for v in map(sum, zip(*rows)))
        out[oy * stride:(oy + 1) * stride] = orow
    return bytes(out)


def write_png(path, pix, w, h):
    # Filter type 0 (None) on every row: for this flat, palette-like
    # page the raw rows repeat so much from line to line that zlib
    # finds far longer matches than with any predictive filter
    # (measured: ~218 KB vs ~302 KB for Sub).  Pure function of the
    # pixels, so the output stays deterministic.
    raw = bytearray()
    stride = w * 3
    for y in range(h):
        raw.append(0)  # filter: None
        raw += pix[y * stride:(y + 1) * stride]
    comp = zlib.compress(bytes(raw), 9)

    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", comp)
           + chunk(b"IEND", b""))
    with open(path, "wb") as f:
        f.write(png)
    return len(png)


# ---------------------------------------------------------------- font
# Hand-built stroke font.  Glyph space: x grows right, y grows down,
# cap height spans y=0..100, the baseline is y=100, descenders reach
# y=132, accents sit above y=0.  Each glyph is (advance, [stroke, ...])
# where a stroke is a polyline of (x, y) points.

def _arc(cx, cy, rx, ry, a0, a1, n=14):
    return ellipse_pts(cx, cy, rx, ry, n, a0, a1)


GLYPHS = {
    ' ': (30, []),
    'A': (74, [[(2, 100), (37, 0), (72, 100)], [(14, 66), (60, 66)]]),
    'B': (68, [[(4, 0), (4, 100)],
               [(4, 0), (40, 0), (54, 10), (54, 38), (42, 50), (4, 50)],
               [(4, 50), (44, 50), (58, 62), (58, 86), (44, 100), (4, 100)]]),
    'C': (70, [[(64, 20), (50, 6), (30, 2), (14, 10), (5, 28), (3, 50),
                (5, 72), (14, 90), (30, 98), (50, 94), (64, 80)]]),
    'D': (72, [[(4, 0), (4, 100)],
               [(4, 0), (38, 0), (58, 16), (66, 38), (66, 62),
                (58, 84), (38, 100), (4, 100)]]),
    'E': (62, [[(58, 0), (4, 0), (4, 100), (58, 100)], [(4, 50), (46, 50)]]),
    'F': (58, [[(58, 0), (4, 0), (4, 100)], [(4, 50), (44, 50)]]),
    'G': (74, [[(66, 20), (52, 6), (32, 2), (15, 10), (6, 28), (4, 50),
                (6, 72), (15, 90), (32, 98), (52, 96), (66, 84), (66, 54),
                (44, 54)]]),
    'H': (74, [[(4, 0), (4, 100)], [(70, 0), (70, 100)], [(4, 50), (70, 50)]]),
    'I': (30, [[(15, 0), (15, 100)], [(2, 0), (28, 0)], [(2, 100), (28, 100)]]),
    'J': (56, [[(28, 0), (54, 0)],
               [(52, 0), (52, 70), (44, 90), (26, 100), (8, 94), (2, 78)]]),
    'K': (70, [[(4, 0), (4, 100)], [(62, 0), (8, 54)], [(16, 44), (64, 100)]]),
    'L': (58, [[(4, 0), (4, 100), (56, 100)]]),
    'M': (88, [[(2, 100), (2, 0), (44, 58), (86, 0), (86, 100)]]),
    'N': (76, [[(4, 100), (4, 0), (72, 100), (72, 0)]]),
    'O': (78, [_arc(39, 50, 36, 49, 0, 360, 26)]),
    'P': (66, [[(4, 0), (4, 100)],
               [(4, 0), (42, 0), (56, 12), (56, 36), (42, 50), (4, 50)]]),
    'Q': (78, [_arc(39, 50, 36, 49, 0, 360, 26), [(46, 76), (74, 104)]]),
    'R': (68, [[(4, 0), (4, 100)],
               [(4, 0), (42, 0), (56, 12), (56, 36), (42, 50), (4, 50)],
               [(38, 50), (64, 100)]]),
    'S': (66, [[(60, 14), (44, 3), (24, 3), (8, 14), (6, 30), (14, 44),
                (52, 58), (60, 72), (54, 90), (36, 99), (16, 96), (4, 84)]]),
    'T': (66, [[(2, 0), (64, 0)], [(33, 0), (33, 100)]]),
    'U': (74, [[(4, 0), (4, 62), (12, 86), (26, 98), (48, 98), (62, 86),
                (70, 62), (70, 0)]]),
    'V': (72, [[(2, 0), (36, 100), (70, 0)]]),
    'W': (94, [[(2, 0), (15, 100), (35, 28), (47, 100), (59, 28),
                (72, 100), (84, 0)]]),
    'X': (68, [[(4, 0), (64, 100)], [(64, 0), (4, 100)]]),
    'Y': (68, [[(2, 0), (34, 46), (66, 0)], [(34, 46), (34, 100)]]),
    'Z': (66, [[(4, 0), (62, 0), (4, 100), (62, 100)]]),
    'a': (58, [[(50, 38), (50, 98)],
               [(48, 48), (38, 37), (20, 35), (9, 46), (7, 67), (10, 87),
                (22, 98), (38, 98), (49, 87)]]),
    'b': (58, [[(8, 0), (8, 100)],
               [(8, 56), (18, 40), (34, 35), (47, 45), (50, 66), (44, 88),
                (30, 98), (16, 95), (8, 84)]]),
    'c': (54, [[(48, 44), (36, 35), (20, 35), (10, 46), (7, 66), (10, 87),
                (22, 98), (38, 98), (48, 88)]]),
    'd': (58, [[(50, 0), (50, 100)],
               [(50, 46), (40, 37), (22, 35), (10, 46), (7, 66), (10, 87),
                (22, 98), (38, 98), (50, 88)]]),
    'e': (56, [[(8, 66), (50, 66)],
               [(50, 66), (48, 50), (38, 37), (22, 35), (11, 44), (7, 62),
                (9, 84), (20, 96), (36, 98), (48, 90)]]),
    'f': (34, [[(44, 6), (32, 0), (20, 8), (16, 22), (16, 100)],
               [(4, 36), (40, 36)]]),
    'g': (58, [[(48, 46), (38, 36), (20, 35), (9, 46), (7, 66), (10, 86),
                (22, 97), (38, 97), (50, 86)],
               [(50, 36), (50, 86), (46, 104), (32, 114), (16, 110),
                (8, 98)]]),
    'h': (58, [[(8, 0), (8, 100)],
               [(8, 58), (16, 42), (30, 35), (44, 40), (50, 54),
                (50, 100)]]),
    'i': (26, [[(13, 36), (13, 100)], [(13, 13), (13, 19)]]),
    'j': (30, [[(24, 36), (24, 92), (18, 106), (6, 108)],
               [(24, 13), (24, 19)]]),
    'k': (56, [[(8, 0), (8, 100)], [(46, 36), (10, 72)], [(18, 62),
               (48, 100)]]),
    'l': (26, [[(13, 0), (13, 100)]]),
    'm': (86, [[(6, 36), (6, 100)],
               [(6, 56), (12, 42), (24, 36), (36, 40), (42, 54), (42, 100)],
               [(42, 56), (48, 42), (60, 36), (74, 40), (80, 54),
                (80, 100)]]),
    'n': (58, [[(6, 36), (6, 100)],
               [(6, 56), (12, 42), (26, 35), (40, 40), (46, 54),
                (46, 100)]]),
    'o': (60, [_arc(30, 67, 24, 32, 0, 360, 20)]),
    'p': (58, [[(8, 36), (8, 132)],
               [(8, 56), (18, 40), (34, 35), (47, 45), (50, 66), (44, 88),
                (30, 98), (16, 95), (8, 84)]]),
    'q': (58, [[(50, 36), (50, 132)],
               [(50, 46), (40, 37), (22, 35), (10, 46), (7, 66), (10, 87),
                (22, 98), (38, 98), (50, 88)]]),
    'r': (40, [[(8, 36), (8, 100)],
               [(8, 58), (14, 44), (26, 37), (38, 36)]]),
    's': (54, [[(46, 42), (34, 35), (18, 35), (9, 44), (10, 56), (18, 64),
                (40, 72), (46, 82), (40, 95), (24, 99), (10, 94)]]),
    't': (36, [[(18, 14), (18, 84), (24, 96), (36, 98)],
               [(4, 36), (34, 36)]]),
    'u': (58, [[(6, 36), (6, 74), (11, 90), (24, 98), (38, 96), (50, 82),
                (50, 36)], [(50, 78), (50, 100)]]),
    'v': (54, [[(2, 36), (27, 100), (52, 36)]]),
    'w': (78, [[(2, 36), (11, 100), (25, 50), (39, 100), (48, 50),
                (57, 100), (66, 36)]]),
    'x': (52, [[(4, 36), (48, 100)], [(48, 36), (4, 100)]]),
    'y': (54, [[(2, 36), (27, 82)], [(52, 36), (27, 82), (14, 110),
                (4, 112)]]),
    'z': (52, [[(4, 36), (48, 36), (4, 100), (48, 100)]]),
    '0': (62, [_arc(31, 50, 27, 49, 0, 360, 24)]),
    '1': (62, [[(14, 16), (34, 4), (34, 100)], [(12, 100), (52, 100)]]),
    '2': (62, [[(8, 22), (20, 6), (38, 4), (52, 16), (52, 32), (6, 100),
                (56, 100)]]),
    '3': (62, [[(8, 14), (24, 4), (42, 6), (52, 20), (44, 38), (26, 46)],
               [(26, 46), (44, 52), (54, 68), (48, 90), (30, 99), (10, 94),
                (4, 80)]]),
    '4': (62, [[(40, 100), (40, 0), (6, 66), (58, 66)]]),
    '5': (62, [[(54, 4), (14, 4), (10, 40), (24, 34), (42, 38), (52, 54),
                (50, 78), (38, 94), (18, 97), (6, 86)]]),
    '6': (62, [[(50, 12), (34, 4), (18, 12), (8, 34), (6, 62), (12, 86),
                (26, 97), (42, 95), (52, 82), (50, 60), (38, 48), (20, 49),
                (9, 60)]]),
    '7': (62, [[(6, 4), (56, 4), (28, 100)]]),
    '8': (62, [[(22, 6), (40, 4), (50, 16), (44, 34), (30, 44), (16, 52),
                (8, 68), (14, 90), (28, 99), (44, 96), (52, 82), (46, 58),
                (32, 48), (18, 40), (10, 24), (14, 10), (22, 6)]]),
    '9': (62, [[(10, 88), (26, 97), (42, 91), (52, 70), (54, 36), (46, 14),
                (30, 5), (16, 12), (12, 32), (22, 46), (38, 47),
                (50, 37)]]),
    '.': (20, [[(8, 93), (8, 99)]]),
    ',': (20, [[(10, 92), (6, 106)]]),
    ':': (20, [[(8, 38), (8, 44)], [(8, 92), (8, 98)]]),
    ';': (20, [[(8, 38), (8, 44)], [(10, 92), (6, 106)]]),
    "'": (18, [[(10, 2), (6, 16)]]),
    '\u2019': (18, [[(10, 2), (6, 16)]]),
    '"': (28, [[(8, 2), (4, 16)], [(22, 2), (18, 16)]]),
    '-': (40, [[(4, 58), (36, 58)]]),
    '\u2013': (52, [[(2, 58), (48, 58)]]),
    '\u2014': (68, [[(2, 58), (64, 58)]]),
    '\u00b7': (16, [[(6, 52), (6, 58)]]),
    '\u2026': (34, [[(4, 93), (4, 99)], [(16, 93), (16, 99)],
                    [(28, 93), (28, 99)]]),
    '/': (52, [[(44, 102), (10, -2)]]),
    '(': (34, [[(36, 4), (22, 20), (16, 50), (22, 82), (36, 100)]]),
    ')': (34, [[(2, 4), (16, 20), (22, 50), (16, 82), (2, 100)]]),
    '$': (62, [[(31, -6), (31, 106)],
               [(48, 22), (36, 10), (20, 10), (10, 22), (12, 36), (24, 44),
                (44, 52), (50, 64), (42, 80), (24, 86), (10, 76)]]),
    '%': (86, [_arc(17, 25, 12, 14, 0, 360, 12), [(66, 100), (18, 0)],
               _arc(61, 75, 12, 14, 0, 360, 12)]),
    '+': (60, [[(30, 28), (30, 78)], [(7, 53), (53, 53)]]),
    '&': (72, [[(44, 86), (30, 98), (16, 94), (8, 80), (12, 62), (30, 44),
                (44, 32), (42, 16), (30, 8), (18, 16), (20, 30), (50, 66),
                (58, 86), (66, 98)]]),
    '!': (20, [[(10, 0), (10, 66)], [(10, 92), (10, 98)]]),
    '?': (58, [[(8, 20), (20, 6), (38, 6), (50, 18), (48, 34), (36, 46),
                (28, 54), (28, 66)], [(28, 92), (28, 98)]]),
    '\u00b0': (30, [_arc(15, 15, 10, 11, 0, 360, 10)]),
    '#': (64, [[(22, 0), (14, 100)], [(48, 0), (40, 100)],
               [(6, 36), (58, 36)], [(4, 68), (56, 68)]]),
    '*': (60, [[(30, 18), (30, 62)], [(11, 29), (49, 51)],
               [(49, 29), (11, 51)]]),
    '=': (60, [[(6, 38), (54, 38)], [(6, 66), (54, 66)]]),
    '_': (60, [[(2, 104), (58, 104)]]),
    '\u00e9': (56, [[(8, 66), (50, 66)],
                    [(50, 66), (48, 50), (38, 37), (22, 35), (11, 44),
                     (7, 62), (9, 84), (20, 96), (36, 98), (48, 90)],
                    [(36, 20), (47, 6)]]),
    '\u00c9': (62, [[(58, 0), (4, 0), (4, 100), (58, 100)],
                    [(4, 50), (46, 50)], [(38, -30), (50, -16)]]),
    '\u00fc': (58, [[(6, 36), (6, 74), (11, 90), (24, 98), (38, 96),
                     (50, 82), (50, 36)], [(50, 78), (50, 100)],
                    [(19, 16), (19, 22)], [(41, 16), (41, 22)]]),
    '\u00dc': (74, [[(4, 0), (4, 62), (12, 86), (26, 98), (48, 98), (62, 86),
                     (70, 62), (70, 0)],
                    [(21, -16), (21, -10)], [(49, -16), (49, -10)]]),
    '\u0107': (54, [[(48, 44), (36, 35), (20, 35), (10, 46), (7, 66),
                     (10, 87), (22, 98), (38, 98), (48, 88)],
                    [(34, 20), (45, 6)]]),
}

GLYPHS['\u0130'] = (30, [[(15, 0), (15, 100)], [(2, 0), (28, 0)],
                         [(2, 100), (28, 100)], [(15, -17), (15, -11)]])


def glyph(ch):
    return GLYPHS.get(ch, GLYPHS['?'])


def text_width(s, size, bold=False, tracking=0.0):
    sc = size / 100.0
    w = 0.0
    for ch in s:
        w += glyph(ch)[0] * sc + tracking
    return w - tracking if s else 0.0


def draw_text(x, y, s, size, color, bold=False, align='l', tracking=0.0,
              serif=False):
    """Draw string s with its baseline at y (design space).

    Returns the drawn width in design units.  Stroke weight is a
    larger fraction of the em than in v3, and small type (under 20
    design units) gets a further boost, because thin strokes are
    what crumble when the page is reduced to 1024 px.
    """
    sc = size / 100.0
    w = text_width(s, size, bold, tracking)
    if align == 'c':
        x -= w / 2.0
    elif align == 'r':
        x -= w
    if bold:
        lw = size * (0.205 if size < 20 else 0.19)
    else:
        lw = size * (0.155 if size < 20 else 0.13)
    cx = x
    for ch in s:
        adv, strokes = glyph(ch)
        for st in strokes:
            pts = [(cx + gx * sc, y + (gy - 100.0) * sc) for gx, gy in st]
            if len(pts) == 1:
                disc(pts[0][0], pts[0][1], lw / 2.0, color)
            else:
                polyline(pts, lw, color)
            if serif and len(pts) >= 2:
                for px_, py_ in (pts[0], pts[-1]):
                    line(px_ - size * 0.09, py_, px_ + size * 0.09, py_,
                         lw * 0.8, color)
        cx += adv * sc + tracking
    return w


def wrap_text(s, size, bold, max_width, tracking=0.0):
    """Greedy word wrap; returns a list of lines that fit max_width."""
    lines = []
    cur = ''
    for word in s.split(' '):
        trial = word if not cur else cur + ' ' + word
        if text_width(trial, size, bold, tracking) <= max_width or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


# ---------------------------------------------------------------- content
# All stories happened, or were first reported, on Monday 23 Nov 2026 (UTC).
# tag: ON RECORD = stated by the source itself; REPORTED = via the named
# outlet; CLAIM = one side's assertion, not independently verified.

CARDS = [
    dict(n=1, loc="SANTA CLARA, US", cat="TECH", tag="ON RECORD",
         banner="HUANG RETURNS", tint=(213, 221, 236), illus="chip",
         head="Nvidia puts Huang back in charge as Trump joins board call",
         body="Nvidia said Monday that Jensen Huang returns as president, "
              "CEO and director. President Trump joined the board call, the "
              "White House confirmed, as Commerce blacklisted Megaspeed and "
              "Alibaba unit Apex Enterprise Solutions.",
         src="REUTERS"),
    dict(n=2, loc="CIKANDE, INDONESIA", cat="DISASTER", tag="REPORTED",
         banner="TOLL RISES TO 24", tint=(243, 219, 203), illus="fire",
         head="Candy factory fire toll climbs to 24, dozens still missing",
         body="The death toll from the candy plant fire rose to 24 on "
              "Monday. Dozens are still unaccounted for, and search "
              "teams kept combing the site.",
         src="REUTERS"),
    dict(n=3, loc="NORTH CAROLINA, US", cat="POLITICS", tag="REPORTED",
         banner="258 SEATS", tint=(215, 226, 215), illus="capitol",
         head="Democrats reach 258 House seats, biggest majority since "
              "the early 1990s",
         body="A win in North Carolina locked in at least 258 House seats "
              "for the Democrats, their largest majority since the early "
              "1990s.",
         src="REUTERS"),
    dict(n=4, loc="BENGHAZI, LIBYA", cat="SEA WAR", tag="CLAIM",
         banner="SUNK AT BENGHAZI", tint=(196, 219, 228), illus="ship",
         head="Ukraine says sea drones sank a Russian corvette off Benghazi",
         body="Kyiv said seven sea drones hit two Russian ships and sank "
              "the corvette Merkury at Benghazi, pushing the naval war "
              "into the Mediterranean.",
         src="MIDDLE EAST EYE"),
    dict(n=5, loc="KYIV REGION, UKRAINE", cat="WAR", tag="REPORTED",
         banner="DEADLY STRIKE", tint=(228, 214, 222), illus="skyline",
         head="Russian attack kills at least 15 in Kyiv region",
         body="At least 15 people were killed in a Russian attack on Kyiv "
              "region, Ukrainian authorities said on Monday.",
         src="UKRAINIAN AUTHORITIES"),
    dict(n=6, loc="ANTALYA, T\u00dcRK\u0130YE", cat="CLIMATE",
         tag="REPORTED", banner="TALKS END EMPTY", tint=(209, 228, 219),
         illus="globe",
         head="COP31 ends without a deal, and Monday brings the fallout",
         body="The final text never mentioned fossil fuels. The EU and "
              "90-plus countries rejected the draft; island states "
              "voiced dismay; the UN chief warned.",
         src="NEWS AGENCIES"),
    dict(n=7, loc="FREIBURG, GERMANY", cat="SECURITY", tag="REPORTED",
         banner="450 SCHOOLS", tint=(238, 230, 204), illus="school",
         head="Bomb threats hit some 450 schools across Germany",
         body="Around 450 schools across Germany received bomb-threat "
              "emails on Monday morning. Police opened investigations "
              "nationwide.",
         src="BILD / REUTERS"),
    dict(n=8, loc="MADRID, SPAIN", cat="POLITICS", tag="ON RECORD",
         banner="THE WAY HOME OPENS", tint=(244, 224, 189), illus="flag",
         head="Court shelves Puigdemont case, clearing his road home",
         body="The Supreme Court shelved the case against Catalan "
              "leader Carles Puigdemont, removing the last bar to his "
              "return after 10 years in exile.",
         src="REUTERS"),
    dict(n=9, loc="WASHINGTON, US", cat="CRYPTO", tag="ON RECORD",
         banner="$1B CLAWBACK", tint=(221, 217, 238), illus="coin",
         head="US sues to claw back $1B in crypto stolen from Binance",
         body="The Justice Department sued to recover more than $1 billion "
              "in crypto stolen in the Binance hack, blaming a North "
              "Korean hacking group.",
         src="REUTERS"),
    dict(n=10, loc="PYONGYANG, NORTH KOREA", cat="DIPLOMACY",
         tag="REPORTED", banner="OFFICE AT RISK", tint=(229, 214, 207),
         illus="office",
         head="Pyongyang may shut Swiss office over children's camp "
              "sanctions",
         body="North Korea lashed out at Swiss sanctions linked to a "
              "children's camp and said it may close Switzerland's "
              "diplomatic office in Pyongyang.",
         src="KCNA / REUTERS"),
    dict(n=11, loc="IOWA, US", cat="MILITARY", tag="REPORTED",
         banner="BLAST ON HOLD", tint=(219, 224, 209), illus="barrels",
         head="Trump halts planned blast of 10,000 lb of lead azide",
         body="The president halted, pending a court ruling, the planned "
              "detonation of about 10,000 lb (68 barrels) of degraded "
              "lead azide at an Iowa Army site.",
         src="REUTERS"),
    dict(n=12, loc="WASHINGTON, US", cat="FOOTBALL", tag="REPORTED",
         banner="39 SECONDS LEFT", tint=(203, 228, 203), illus="football",
         head="Commanders stun Bengals 22\u201320 on a 39-second drive",
         body="With 39 seconds left, Daniels marched 64 yards in 34 "
              "seconds, and Stevens hit a 26-yard field goal to beat "
              "Cincinnati 22\u201320 on Monday night.",
         src="AP"),
    dict(n=13, loc="NEW YORK, US", cat="BASEBALL", tag="REPORTED",
         banner="RECORD $450M", tint=(240, 226, 213), illus="baseball",
         head="Skubal lands record $450M, nine-year deal with the Mets",
         body="Tarik Skubal agreed a nine-year, $450 million contract "
              "with the New York Mets, the richest deal ever handed to "
              "a pitcher.",
         src="AP"),
]

SHORTS = [
    ("PARIS", "M\u00e9lenchon climbs 5 points in runoff polling: "
              "Le Pen 65%, M\u00e9lenchon 35% (Toluna Harris)."),
    ("SAN FRANCISCO", "CrowdStrike to buy Zscaler for $44 billion."),
    ("SACRAMENTO", "Spurs beat Kings 123\u2013107 without Wembanyama; "
                   "Castle scores 28 with 11 assists."),
    ("DENVER", "Joki\u0107 posts his 202nd career triple-double as the "
               "Nuggets edge the Bulls 151\u2013145 in overtime."),
    ("WASHINGTON", "FBI investigates a hack of the national crime and "
                   "justice database."),
    ("SEATTLE", "ICE arrests two passengers at the airport, moments "
                "before they were to board."),
    ("CALIFORNIA", "Miley Cyrus marries drummer Maxx Morando."),
    ("LONDON", "Princess Catherine opens up about living with cancer "
               "in a new documentary."),
    ("ASIA", "Authorities across Asia move to steady markets after "
             "the AI-stock selloff."),
    ("OTTAWA / DOHA", "Canada and Qatar to sign an investment pact "
                      "on Tuesday."),
    ("DAMASCUS", "US holds talks on mine-clearing training for "
                 "Syrian forces."),
    ("KHARTOUM", "A drone hits homes and a UN building in Sudan's "
                 "capital."),
    ("KYIV", "Caf\u00e9 owners in the capital brace for a hard winter."),
    ("MEXICO CITY", "49ers rout the Vikings 35\u201310; Purdy throws "
                    "3 TDs and the Niners go 9\u20131."),
    ("KANSAS CITY", "Chiefs rout the Cardinals 34\u20137; Mahomes "
                    "throws for 324 yards and 3 TDs."),
]

STATS = [
    ("24", "dead in the Cikande fire"),
    ("258", "House seats for Democrats"),
    ("$44B", "CrowdStrike's Zscaler deal"),
    ("$1B+", "US suit to recover crypto"),
    ("450", "schools hit by bomb threats in Germany"),
    ("$450M", "Skubal's record contract with the Mets"),
    ("202", "career triple-doubles for Joki\u0107"),
    ("28", "stories on this page, all from one day"),
]

TIMELINE = [
    ("03:00", 180, "49ers win in Mexico City"),
    ("10:43", 643, "450 German schools threatened"),
    ("18:32", 1112, "US files $1B crypto claim"),
    ("21:24", 1284, "KCNA Swiss-office warning"),
]

CHIPS = ["NORTH AMERICA 14", "EUROPE 7", "ASIA 3", "AFRICA 2",
         "LATIN AMERICA 1", "MIDDLE EAST 1"]

# map pins: card number -> (longitude, latitude, dx, dy) in degrees/px
PINS = {
    1: (-122, 37, 0, 0), 2: (106, -6, 0, 0), 3: (-79, 35, -14, 10),
    4: (20, 32, 0, 6), 5: (30.5, 50.4, 0, -6), 6: (30.7, 36.9, 14, 8),
    7: (7.9, 48, -12, -8), 8: (-3.7, 40.4, -6, 10), 9: (-77, 38.9, 0, -14),
    10: (125.8, 39.1, 0, 0), 11: (-93.6, 42, -6, -4),
    12: (-77, 38.9, 16, 14), 13: (-74, 40.7, 14, -10),
}

# stylised land masses for the dotted map: (lon centre, lat centre,
# lon radius, lat radius) ellipses
LAND = [
    (-100, 48, 38, 14), (-85, 38, 22, 9), (-152, 64, 12, 5),
    (-102, 23, 10, 6), (-84, 14, 7, 3), (-42, 72, 10, 5),
    (-62, -12, 11, 13), (-70, -25, 6, 12),
    (15, 50, 16, 7), (16, 63, 10, 5), (-3, 43, 6, 4), (-2, 54, 3, 4),
    (20, 6, 17, 16), (24, -16, 11, 10), (47, -19, 3, 5),
    (45, 27, 10, 7), (95, 58, 48, 10), (70, 45, 16, 7),
    (78, 21, 8, 9), (105, 33, 15, 10), (102, 15, 7, 7),
    (128, 37, 3, 3), (138, 37, 4, 4),
    (107, -6, 6, 2), (120, -2, 7, 3), (136, -3, 6, 3),
    (134, -25, 13, 7), (172, -42, 3, 4),
]


# ---------------------------------------------------------------- panels
# Flat illustrations, drawn inside the scene area of each card panel.

DARK = (56, 66, 84)


def illus_chip(x, y, w, h):
    cx, cy = x + w * 0.42, y + h * 0.5
    s = h * 0.30
    for k in (-0.55, 0.0, 0.55):
        line(cx - s - 12, cy + k * s * 1.4, cx - s, cy + k * s * 1.4, 4, NAVY)
        line(cx + s, cy + k * s * 1.4, cx + s + 12, cy + k * s * 1.4, 4, NAVY)
        line(cx + k * s * 1.4, cy - s - 10, cx + k * s * 1.4, cy - s, 4, NAVY)
        line(cx + k * s * 1.4, cy + s, cx + k * s * 1.4, cy + s + 10, 4, NAVY)
    rrect(cx - s, cy - s, cx + s, cy + s, 5, (238, 242, 249))
    rrect_outline(cx - s, cy - s, cx + s, cy + s, 5, 4, NAVY)
    rrect_outline(cx - s * 0.5, cy - s * 0.5, cx + s * 0.5, cy + s * 0.5,
                  3, 3, NAVY)
    ax, ay = x + w * 0.74, y + h * 0.62
    line(ax, ay, ax + 26, ay - 26, 6, RED)
    polyline([(ax + 10, ay - 27), (ax + 27, ay - 27), (ax + 27, ay - 10)],
             6, RED)


def illus_fire(x, y, w, h):
    gy = y + h * 0.94
    fill_rect(x + w * 0.14, gy - h * 0.52, x + w * 0.52, gy, DARK)
    fill_rect(x + w * 0.52, gy - h * 0.34, x + w * 0.66, gy, DARK)
    polyline([(x + w * 0.14, gy - h * 0.52), (x + w * 0.24, gy - h * 0.66),
              (x + w * 0.34, gy - h * 0.52), (x + w * 0.44, gy - h * 0.66),
              (x + w * 0.52, gy - h * 0.52)], 4, DARK)
    for fx, fs in ((0.24, 0.8), (0.36, 1.05), (0.47, 0.7)):
        bx = x + w * fx
        by = gy - h * 0.55
        fill_poly([(bx - 8 * fs, by), (bx - 3 * fs, by - 14 * fs),
                   (bx + 2 * fs, by - 6 * fs), (bx + 5 * fs, by - 18 * fs),
                   (bx + 9 * fs, by)], (233, 122, 40))
        fill_poly([(bx - 3.5 * fs, by), (bx, by - 8 * fs),
                   (bx + 4 * fs, by)], RED)
    disc(x + w * 0.78, y + h * 0.24, 9, (176, 176, 180))
    disc(x + w * 0.84, y + h * 0.16, 12, (186, 186, 190))
    disc(x + w * 0.30, y + h * 0.16, 8, (186, 186, 190))
    line(x, gy, x + w, gy, 4, NAVY)


def illus_capitol(x, y, w, h):
    cx = x + w * 0.5
    base = y + h * 0.92
    dome = ellipse_pts(cx, base - h * 0.30, w * 0.105, h * 0.46, 26, 180, 360)
    fill_poly(dome + [(cx + w * 0.105, base - h * 0.30),
                      (cx - w * 0.105, base - h * 0.30)], NAVY)
    line(cx, base - h * 0.76, cx, base - h * 0.90, 4, NAVY)
    fill_poly([(cx, base - h * 0.90), (cx + 13, base - h * 0.82),
               (cx, base - h * 0.82)], RED)
    fill_rect(cx - w * 0.20, base - h * 0.30, cx + w * 0.20, base - h * 0.20,
              NAVY)
    for k in (-0.15, -0.05, 0.05, 0.15):
        line(cx + w * k, base - h * 0.28, cx + w * k, base - h * 0.22, 3,
             (247, 243, 232))
    fill_rect(cx - w * 0.24, base - h * 0.20, cx + w * 0.24, base - h * 0.10,
              NAVY)
    fill_rect(cx - w * 0.33, base - h * 0.10, cx + w * 0.33, base, NAVY)


def illus_ship(x, y, w, h):
    wy = y + h * 0.60
    for k in range(3):
        yy = wy + 8 + k * 9
        pts = [(x + 8 + i * 16, yy + (4 if i % 2 else -2))
               for i in range(int(w / 16))]
        polyline(pts, 3, TEAL if k % 2 else NAVY)
    hx0, hx1 = x + w * 0.16, x + w * 0.66
    fill_poly([(hx0, wy - 6), (hx1, wy - 6), (hx1 - 18, wy + 12),
               (hx0 + 14, wy + 12)], DARK)
    fill_rect(hx0 + 26, wy - 22, hx0 + 74, wy - 6, DARK)
    line(hx0 + 96, wy - 28, hx0 + 96, wy - 6, 4, DARK)
    dx_, dy_ = x + w * 0.84, y + h * 0.28
    disc(dx_, dy_, 6, DARK)
    for a in (45, 135, 225, 315):
        line(dx_, dy_, dx_ + 11 * math.cos(math.radians(a)),
             dy_ + 11 * math.sin(math.radians(a)), 3, DARK)
    for t in (0.25, 0.5, 0.75):
        sx = dx_ + (hx1 - 30 - dx_) * t
        sy = dy_ + (wy - 16 - dy_) * t
        line(sx - 5, sy, sx + 5, sy, 4, RED)


def illus_skyline(x, y, w, h):
    base = y + h
    heights = (0.52, 0.78, 0.40, 0.64, 0.34)
    bx = x + w * 0.06
    for i, fh in enumerate(heights):
        bw = w * 0.11
        fill_rect(bx, base - h * fh, bx + bw, base, DARK)
        bx += bw + w * 0.025
    cx, cy = x + w * 0.76, y + h * 0.34
    for a in range(0, 360, 45):
        line(cx, cy, cx + 15 * math.cos(math.radians(a)),
             cy + 15 * math.sin(math.radians(a)), 4, RED)
    disc(cx, cy, 7, (240, 150, 60))


def illus_globe(x, y, w, h):
    cx, cy = x + w * 0.5, y + h * 0.52
    r = h * 0.40
    outline_ellipse(cx, cy, r, r, 4, NAVY)
    outline_ellipse(cx, cy, r * 0.45, r, 3, TEAL)
    for f in (-0.48, 0.48):
        d = r * f
        half = math.sqrt(max(0.0, r * r - d * d))
        line(cx - half, cy + d, cx + half, cy + d, 3, TEAL)
    crack = [(cx - 4, cy - r), (cx + 7, cy - r * 0.55), (cx - 6, cy - r * 0.2),
             (cx + 8, cy + r * 0.25), (cx - 3, cy + r * 0.6), (cx + 5, cy + r)]
    polyline(crack, 5, RED)


def illus_school(x, y, w, h):
    bx, by = x + w * 0.12, y + h * 0.30
    bw, bh = w * 0.46, h * 0.64
    fill_rect(bx, by, bx + bw, by + bh, (252, 250, 244))
    polyline([(bx, by), (bx + bw, by), (bx + bw, by + bh), (bx, by + bh),
              (bx, by)], 4, NAVY)
    fill_poly([(bx - 8, by), (bx + bw + 8, by), (bx + bw * 0.5, by - h * 0.22)],
              NAVY)
    fill_rect(bx + bw * 0.42, by + bh * 0.45, bx + bw * 0.58, by + bh, NAVY)
    for r_ in range(2):
        for c_ in range(3):
            fill_rect(bx + 10 + c_ * bw * 0.3, by + 9 + r_ * bh * 0.3,
                      bx + 22 + c_ * bw * 0.3, by + 19 + r_ * bh * 0.3, NAVY)
    ex, ey, ew, eh = x + w * 0.68, y + h * 0.30, w * 0.25, h * 0.42
    fill_rect(ex, ey, ex + ew, ey + eh, WHITE)
    polyline([(ex, ey), (ex + ew, ey), (ex + ew, ey + eh), (ex, ey + eh),
              (ex, ey)], 3, NAVY)
    polyline([(ex, ey), (ex + ew * 0.5, ey + eh * 0.55), (ex + ew, ey)], 3,
             NAVY)
    disc(ex + ew * 0.82, ey + eh * 0.78, 6, RED)


def illus_flag(x, y, w, h):
    px = x + w * 0.30
    line(px, y + h * 0.08, px, y + h * 0.96, 5, DARK)
    fx, fy, fw, fh = px + 4, y + h * 0.12, w * 0.46, h * 0.44
    fill_rect(fx, fy, fx + fw, fy + fh, (240, 199, 60))
    for i in (1, 3, 5, 7):
        fill_rect(fx, fy + fh * i / 9, fx + fw, fy + fh * (i + 1) / 9, RED)
    polyline([(fx, fy), (fx + fw, fy), (fx + fw, fy + fh), (fx, fy + fh),
              (fx, fy)], 3, NAVY)


def illus_coin(x, y, w, h):
    cx, cy = x + w * 0.36, y + h * 0.52
    r = h * 0.38
    disc(cx, cy, r, GOLD)
    outline_ellipse(cx, cy, r, r, 4, NAVY)
    draw_text(cx, cy + r * 0.36, "B", r * 1.05, NAVY, bold=True, align='c')
    outline_ellipse(x + w * 0.72, y + h * 0.36, h * 0.17, h * 0.17, 4, NAVY)
    outline_ellipse(x + w * 0.81, y + h * 0.62, h * 0.17, h * 0.17, 4, NAVY)


def illus_office(x, y, w, h):
    bx, by = x + w * 0.30, y + h * 0.16
    bw, bh = w * 0.26, h * 0.80
    fill_rect(bx, by, bx + bw, by + bh, (250, 248, 244))
    polyline([(bx, by), (bx + bw, by), (bx + bw, by + bh), (bx, by + bh),
              (bx, by)], 4, NAVY)
    for r_ in range(4):
        for c_ in range(3):
            fill_rect(bx + 9 + c_ * bw * 0.3, by + 9 + r_ * bh * 0.2,
                      bx + 19 + c_ * bw * 0.3, by + 17 + r_ * bh * 0.2, NAVY)
    line(bx + bw * 0.5, by - h * 0.10, bx + bw * 0.5, by, 4, DARK)
    fx, fy = bx + bw * 0.5, by - h * 0.115
    fill_rect(fx, fy, fx + w * 0.13, fy + h * 0.17, RED)
    fill_rect(fx + w * 0.052, fy + h * 0.02, fx + w * 0.078, fy + h * 0.15,
              WHITE)
    fill_rect(fx + w * 0.02, fy + h * 0.062, fx + w * 0.11, fy + h * 0.108,
              WHITE)


def illus_barrels(x, y, w, h):
    for i, fx in enumerate((0.14, 0.34, 0.54)):
        bx, by = x + w * fx, y + h * 0.22
        bw, bh = w * 0.16, h * 0.72
        rrect(bx, by, bx + bw, by + bh, 7, (116, 128, 140) if i != 1
              else (128, 138, 120))
        line(bx, by + bh * 0.3, bx + bw, by + bh * 0.3, 3, DARK)
        line(bx, by + bh * 0.68, bx + bw, by + bh * 0.68, 3, DARK)
        if i == 1:
            fill_poly([(bx + 2, by + bh * 0.52), (bx + bw - 2, by + bh * 0.40),
                       (bx + bw - 2, by + bh * 0.56), (bx + 2, by + bh * 0.68)],
                      (240, 199, 60))
    ox, oy = x + w * 0.85, y + h * 0.48
    pts = [(ox + 17 * math.cos(math.radians(22.5 + 45 * i)),
            oy + 17 * math.sin(math.radians(22.5 + 45 * i))) for i in range(8)]
    fill_poly(pts, RED)
    fill_rect(ox - 9, oy - 3, ox + 9, oy + 3, WHITE)


def illus_football(x, y, w, h):
    for k in range(4):
        xx = x + w * (0.18 + 0.2 * k)
        line(xx, y + 3, xx, y + h - 3, 3, WHITE)
    cx, cy = x + w * 0.5, y + h * 0.52
    fill_ellipse(cx, cy, w * 0.13, h * 0.26, (150, 95, 55))
    line(cx - w * 0.055, cy - h * 0.20, cx - w * 0.055, cy + h * 0.20, 3, WHITE)
    line(cx + w * 0.055, cy - h * 0.20, cx + w * 0.055, cy + h * 0.20, 3, WHITE)
    line(cx - 9, cy, cx + 9, cy, 3, WHITE)


def illus_baseball(x, y, w, h):
    cx, cy = x + w * 0.38, y + h * 0.52
    r = h * 0.36
    disc(cx, cy, r, (253, 253, 250))
    outline_ellipse(cx, cy, r, r, 3, GRAY)
    polyline(ellipse_pts(cx - r * 0.42, cy, r * 0.34, r * 0.94, 14, -58, 58),
             3, RED)
    polyline(ellipse_pts(cx + r * 0.42, cy, r * 0.34, r * 0.94, 14, 122, 238),
             3, RED)
    fill_poly([(x + w * 0.66, y + h * 0.10), (x + w * 0.75, y + h * 0.16),
               (x + w * 0.55, y + h * 0.66), (x + w * 0.48, y + h * 0.60)],
              (205, 170, 110))


ILLUS = {
    "chip": illus_chip, "fire": illus_fire, "capitol": illus_capitol,
    "ship": illus_ship, "skyline": illus_skyline, "globe": illus_globe,
    "school": illus_school, "flag": illus_flag, "coin": illus_coin,
    "office": illus_office, "barrels": illus_barrels,
    "football": illus_football, "baseball": illus_baseball,
}

TAG_COLORS = {"ON RECORD": NAVY, "REPORTED": TEAL, "CLAIM": RED}


# ---------------------------------------------------------------- layout
MX = 44
RIGHT = 2004


def draw_fit(x, y, s, size, color, bold, max_width):
    """Draw text, shrinking the size until it fits max_width."""
    while size > 12 and text_width(s, size, bold) > max_width:
        size -= 0.5
    return draw_text(x, y, s, size, color, bold=bold)


def draw_card(card, x, y, w, h, wide=False):
    rrect(x, y, x + w, y + h, 8, CARD_BG)
    rrect_outline(x, y, x + w, y + h, 8, 3, NAVY)
    # illustration panel with banner strip (source rides in the strip)
    px, py, pw, ph = x + 10, y + 10, w - 20, 76
    fill_rect(px, py, px + pw, py + ph, card["tint"])
    ILLUS[card["illus"]](px, py, pw, ph - 22)
    fill_rect(px, py + ph - 22, px + pw, py + ph, NAVY)
    draw_text(px + 12, py + ph - 4.5, card["banner"], 15.5, WHITE, bold=True)
    draw_text(px + pw - 12, py + ph - 4.5, card["src"], 13,
              (216, 221, 231), bold=True, align='r')
    # number badge
    disc(x + 28, y + 28, 18, RED)
    draw_text(x + 28, y + 35.5, str(card["n"]), 21, WHITE, bold=True,
              align='c')
    # status tag chip
    tag = card["tag"]
    tw = text_width(tag, 14, True) + 18
    rrect(x + w - 12 - tw, y + 94, x + w - 12, y + 116, 5,
          TAG_COLORS[tag])
    draw_text(x + w - 12 - tw / 2, y + 110, tag, 14, WHITE, bold=True,
              align='c')
    # location line
    draw_fit(x + 12, y + 111, card["loc"] + " \u2014 " + card["cat"],
             18.5, NAVY, True, w - 24 - tw - 8)
    # headline
    hs = 25.5 if wide else 23.5
    hy = y + 142
    for ln in wrap_text(card["head"], hs, True, w - 24)[:3]:
        draw_text(x + 12, hy, ln, hs, INK, bold=True)
        hy += 31
    # summary
    sy = hy - 31 + 32
    for ln in wrap_text(card["body"], 17.5, False, w - 24):
        if sy > y + h - 7:
            break
        draw_text(x + 12, sy, ln, 17.5, INK)
        sy += 22.5


def draw_numbers(x, y, w, h):
    rrect(x, y, x + w, y + h, 8, CARD_BG)
    rrect_outline(x, y, x + w, y + h, 8, 3, NAVY)
    draw_text(x + 18, y + 40, "THE DAY IN NUMBERS", 25, NAVY, bold=True)
    fill_rect(x + 18, y + 50, x + 230, y + 54, RED)
    cw = (w - 36) / 4
    for i, (num, cap) in enumerate(STATS):
        cx = x + 18 + (i % 4) * cw
        ry = y + (0 if i < 4 else 88)
        draw_text(cx, ry + 108, num, 46, NAVY, bold=True)
        ly = ry + 132
        for ln in wrap_text(cap, 16, False, cw - 14)[:2]:
            draw_text(cx, ly, ln, 16, DARKTXT)
            ly += 20


def draw_header():
    draw_text(MX, 76, "THE WORLD IN ONE DAY", 33, NAVY, bold=True)
    draw_text(RIGHT, 76, "28 STORIES \u00b7 6 REGIONS \u00b7 ALL FROM "
                         "THIS ONE DAY", 24, NAVY, bold=True, align='r')
    fill_rect(MX, 90, RIGHT, 97, NAVY)
    fill_rect(MX, 101, RIGHT, 105, RED)
    draw_text(1024, 232, "Monday 23 November 2026", 118, NAVY, bold=True,
              align='c', serif=True)
    kicker = ("NVIDIA RESTORES HUANG AS TRUMP JOINS THE BOARD CALL \u00b7 "
              "INDONESIA FIRE TOLL RISES TO 24 \u00b7 UKRAINE SAYS SEA "
              "DRONES SANK A RUSSIAN CORVETTE AT BENGHAZI \u00b7 DEMOCRATS "
              "TAKE 258 HOUSE SEATS")
    ly = 290
    for ln in wrap_text(kicker, 27, True, 1900):
        draw_text(1024, ly, ln, 27, RED, bold=True, align='c')
        ly += 38
    # region chips
    widths = [text_width(c, 23, True) + 42 for c in CHIPS]
    gap = (1960 - sum(widths)) / (len(CHIPS) - 1)
    cx = MX
    for chip, cwd in zip(CHIPS, widths):
        rrect_outline(cx, 344, cx + cwd, 392, 10, 3, NAVY)
        draw_text(cx + cwd / 2, 377, chip, 23, NAVY, bold=True, align='c')
        cx += cwd + gap


def draw_timeline():
    draw_text(MX, 438, "THE DAY IN UTC", 22, NAVY, bold=True)
    x0, x1, ay = 300, RIGHT, 464
    span = x1 - x0
    line(x0, ay, x1, ay, 3, NAVY)
    for hr in range(0, 25, 2):
        tx = x0 + hr * 60 / 1440 * span
        line(tx, ay - 6, tx, ay + 6, 2.5, NAVY)
    draw_text(x0, 446, "00:00", 15, (52, 57, 70), bold=True)
    draw_text(x1, 446, "24:00", 15, (52, 57, 70), bold=True, align='r')
    for t, mins, label in TIMELINE:
        ex = x0 + mins / 1440 * span
        disc(ex, ay, 8, RED)
        draw_text(ex, 444, t, 24, NAVY, bold=True, align='c')
        lx = min(max(ex, MX + 110), RIGHT - 110)
        ly = 492
        for ln in wrap_text(label, 19.5, False, 210):
            draw_text(lx, ly, ln, 19.5, INK, align='c')
            ly += 23


def draw_shorts():
    draw_text(MX, 1628, "ALSO ON MONDAY", 25, NAVY, bold=True)
    fill_rect(MX, 1638, 250, 1642, RED)
    cols = [MX, 452, 860]
    cursors = [1672, 1672, 1672]
    for i, (place, text) in enumerate(SHORTS):
        # fill columns in reading order: 5 per column
        c = i // 5
        cx = cols[c]
        by = cursors[c]
        num = str(i + 1)
        num_w = text_width(num, 16.5, True) + 10
        lines = wrap_text(place + " \u2014 " + text, 16.5, False,
                          388 - num_w)
        draw_text(cx, by, num, 16.5, RED, bold=True)
        for k, ln in enumerate(lines):
            draw_text(cx + (num_w if k == 0 else 0), by + k * 19.5, ln,
                      16.5, INK)
        draw_text(cx + num_w, by, place, 16.5, NAVY, bold=True)
        cursors[c] = by + len(lines) * 19.5 + 6.5


def draw_map():
    x0, y0, w, h = 1304, 1666, 700, 250
    draw_text(1304, 1628, "WHERE IT HAPPENED", 21, NAVY, bold=True)
    draw_text(1304, 1650, "PINS MATCH THE CARD NUMBERS 1\u201313", 15.5,
              (52, 57, 70), bold=True)

    def proj(lon, lat):
        return (x0 + (lon + 170) / 360 * w, y0 + (80 - lat) / 138 * h)

    lat = 78.0
    while lat > -56:
        lon = -168.0
        while lon < 188:
            for cx_, cy_, rx_, ry_ in LAND:
                if ((lon - cx_) / rx_) ** 2 + ((lat - cy_) / ry_) ** 2 <= 1.0:
                    px_, py_ = proj(lon, lat)
                    disc(px_, py_, 2.6, (148, 156, 172))
                    break
            lon += 3.6
        lat -= 4.2
    for n, (lon, lat_, dx, dy) in PINS.items():
        px_, py_ = proj(lon, lat_)
        disc(px_ + dx, py_ + dy, 12.5, RED)
        draw_text(px_ + dx, py_ + dy + 5.5, str(n), 15, WHITE, bold=True,
                  align='c')


def draw_footer():
    fill_rect(MX, 1956, RIGHT, 1959, NAVY)
    draw_text(MX, 1986, "DATE CHECK", 18, RED, bold=True)
    note = ("Every story on this page happened, or was first reported, on "
            "Monday 23 November 2026 (UTC). Items from earlier days were "
            "excluded \u2014 where the weekend set the stage, only Monday's "
            "development is told.")
    ly = 1986
    for ln in wrap_text(note, 16.5, False, 1010):
        draw_text(178, ly, ln, 16.5, INK)
        ly += 22
    groups = [(NAVY, "ON RECORD", "stated by the source"),
              (TEAL, "REPORTED", "via the named outlet"),
              (RED, "CLAIM", "one side's assertion")]
    gx = 1210
    for color, tag, desc in groups:
        fill_rect(gx, 1975, gx + 11, 1986, color)
        gx += 17
        gx += draw_text(gx, 1986, tag, 15, NAVY, bold=True) + 5
        gx += draw_text(gx, 1986, desc, 15, DARKTXT) + 14
    draw_text(RIGHT, 2014, "All pictures and the map are drawn in code "
                           "\u2014 no photographs.", 15, (70, 74, 86),
              align='r')


def build():
    draw_header()
    draw_timeline()
    cols_x = [44, 537, 1030, 1523]
    rows_y = [530, 798, 1066, 1334]
    cw, ch = 479, 258
    by_id = {c["n"]: c for c in CARDS}
    draw_card(by_id[1], cols_x[0], rows_y[0], 972, ch, wide=True)
    draw_card(by_id[2], cols_x[2], rows_y[0], cw, ch)
    draw_card(by_id[3], cols_x[3], rows_y[0], cw, ch)
    for j, n in enumerate((4, 5, 6, 7)):
        draw_card(by_id[n], cols_x[j], rows_y[1], cw, ch)
    for j, n in enumerate((8, 9, 10, 11)):
        draw_card(by_id[n], cols_x[j], rows_y[2], cw, ch)
    draw_card(by_id[12], cols_x[0], rows_y[3], cw, ch)
    draw_card(by_id[13], cols_x[1], rows_y[3], cw, ch)
    draw_numbers(cols_x[2], rows_y[3], 972, ch)
    draw_shorts()
    draw_map()
    draw_footer()


def main():
    build()
    pix = downsample()
    try:
        os.makedirs("/output", exist_ok=True)
        path = "/output/entry.png"
        n = write_png(path, pix, OUT, OUT)
    except OSError:
        path = os.path.join(os.getcwd(), "entry.png")
        n = write_png(path, pix, OUT, OUT)
    print("wrote", path, n, "bytes")


if __name__ == "__main__":
    main()
