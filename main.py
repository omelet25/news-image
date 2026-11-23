#!/usr/bin/env python3
"""THE WORLD TODAY -- a one-page summary of the world's news of
Monday 23 November 2026, drawn as a newspaper front page.

The program uses only the Python standard library.  It renders the
page on a supersampled canvas with a hand-made stroke font, shrinks
it to 1024x1024 (which anti-aliases every edge), adds a whisper of
paper grain and writes the result as a PNG to /output/entry.png.
Every step is integer/fixed-seed arithmetic, so two runs produce
exactly the same bytes.
"""

import math
import os
import struct
import zlib
from binascii import crc32
from math import isqrt

# ---------------------------------------------------------------- canvas

SS = 2                      # supersampling factor
W = H = 1024                # final image size
CW, CH = W * SS, H * SS     # canvas size

INK    = (29, 26, 22)
PAPER_T = (250, 244, 228)   # paper, top
PAPER_B = (243, 233, 205)   # paper, bottom
RED    = (176, 44, 36)
DRED   = (146, 32, 28)
BLUE   = (33, 82, 160)
TEAL   = (26, 105, 99)
ORANGE = (190, 88, 26)
PURPLE = (88, 72, 152)
GREEN  = (28, 102, 54)
DGREEN = (20, 78, 40)
GOLD   = (176, 138, 44)
GREY   = (110, 100, 84)
WHITE  = (255, 253, 246)
BLACK  = (24, 21, 18)

buf = bytearray(CW * CH * 3)


def _grad_bg():
    """Vertical paper gradient, one flat colour per canvas row."""
    for j in range(CH):
        t = j / (CH - 1)
        r = int(PAPER_T[0] + (PAPER_B[0] - PAPER_T[0]) * t)
        g = int(PAPER_T[1] + (PAPER_B[1] - PAPER_T[1]) * t)
        b = int(PAPER_T[2] + (PAPER_B[2] - PAPER_T[2]) * t)
        row = bytes((r, g, b)) * CW
        buf[j * CW * 3:(j + 1) * CW * 3] = row


class _Lcg:
    """Tiny deterministic pseudo-random source (fixed seed)."""

    def __init__(self, seed):
        self.s = seed & 0x7FFFFFFF

    def next(self):
        self.s = (self.s * 1103515245 + 12345) & 0x7FFFFFFF
        return self.s


def _speckles(n=5200):
    """Paper flecks: tiny darker/lighter specks, drawn before content."""
    rnd = _Lcg(20261123)
    dark = (232, 222, 192)
    light = (255, 252, 240)
    for _ in range(n):
        x = rnd.next() % (CW - 4)
        y = rnd.next() % (CH - 4)
        wdt = 1 + rnd.next() % 3
        col = dark if rnd.next() % 3 else light
        seg = bytes(col) * wdt
        idx = (y * CW + x) * 3
        buf[idx:idx + 3 * wdt] = seg
        if rnd.next() % 4 == 0:  # some flecks are two rows tall
            idx2 = idx + CW * 3
            if idx2 + 3 * wdt <= len(buf):
                buf[idx2:idx2 + 3 * wdt] = seg


def fill_rect(x0, y0, x1, y1, color):
    """Solid rectangle in final-image coordinates."""
    X0, Y0 = max(0, int(x0 * SS)), max(0, int(y0 * SS))
    X1, Y1 = min(CW, int(x1 * SS)), min(CH, int(y1 * SS))
    if X1 <= X0 or Y1 <= Y0:
        return
    seg = bytes(color) * (X1 - X0)
    for j in range(Y0, Y1):
        idx = (j * CW + X0) * 3
        buf[idx:idx + len(seg)] = seg


def fill_disc(cx, cy, r, color):
    """Solid disc in final-image coordinates."""
    CX, CY, R = int(cx * SS), int(cy * SS), int(r * SS)
    seg_cache = {}
    for dy in range(-R, R + 1):
        half = isqrt(R * R - dy * dy)
        j = CY + dy
        if 0 <= j < CH:
            x0 = max(0, CX - half)
            x1 = min(CW, CX + half)
            seg = seg_cache.get(x1 - x0)
            if seg is None:
                seg = bytes(color) * (x1 - x0)
                seg_cache[x1 - x0] = seg
            idx = (j * CW + x0) * 3
            buf[idx:idx + len(seg)] = seg


def line(x0, y0, x1, y1, w, color):
    """Anti-aliased line with round caps, final-image coordinates.

    Coverage is computed per canvas pixel from the distance to the
    segment; the 2x supersampling then smooths it further.
    """
    X0, Y0 = x0 * SS, y0 * SS
    X1, Y1 = x1 * SS, y1 * SS
    rad = w * SS / 2.0
    minx = max(0, int(min(X0, X1) - rad - 1))
    maxx = min(CW - 1, int(max(X0, X1) + rad + 1))
    miny = max(0, int(min(Y0, Y1) - rad - 1))
    maxy = min(CH - 1, int(max(Y0, Y1) + rad + 1))
    dx, dy = X1 - X0, Y1 - Y0
    len2 = dx * dx + dy * dy
    cr, cg, cb = color
    for j in range(miny, maxy + 1):
        py = j + 0.5
        rowbase = j * CW * 3
        for i in range(minx, maxx + 1):
            px = i + 0.5
            if len2 == 0.0:
                t = 0.0
            else:
                t = ((px - X0) * dx + (py - Y0) * dy) / len2
                t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
            qx = X0 + t * dx - px
            qy = Y0 + t * dy - py
            dist = math.sqrt(qx * qx + qy * qy)
            cov = rad + 0.5 - dist
            if cov <= 0.0:
                continue
            idx = rowbase + i * 3
            if cov >= 1.0:
                buf[idx] = cr
                buf[idx + 1] = cg
                buf[idx + 2] = cb
            else:
                a = cov
                ia = 1.0 - a
                buf[idx] = int(buf[idx] * ia + cr * a)
                buf[idx + 1] = int(buf[idx + 1] * ia + cg * a)
                buf[idx + 2] = int(buf[idx + 2] * ia + cb * a)


def polyline(points, w, color, close=False):
    pts = list(points)
    if close and pts:
        pts.append(pts[0])
    for a, b in zip(pts, pts[1:]):
        line(a[0], a[1], b[0], b[1], w, color)


def circle(cx, cy, r, w, color):
    pts = []
    steps = 72
    for k in range(steps + 1):
        a = 2 * math.pi * k / steps
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    polyline(pts, w, color)


def ellipse(cx, cy, rx, ry, w, color, squash_x=1.0):
    pts = []
    steps = 72
    for k in range(steps + 1):
        a = 2 * math.pi * k / steps
        pts.append((cx + rx * math.cos(a) * squash_x, cy + ry * math.sin(a)))
    polyline(pts, w, color)


# ------------------------------------------------------------------ font
# Hand-made stroke font.  Coordinates live in a 10-unit cap height:
# y=0 is the cap top, y=10 the baseline, descenders reach y=13.
# Each glyph is (advance, [stroke, ...]); a stroke is a list of points.

GLYPHS = {
    'A': (8.4, [[(0.4, 10), (4.2, 0), (8, 10)],
                [(2.1, 6.2), (6.3, 6.2)]]),
    'B': (7.6, [[(0.8, 0), (0.8, 10)],
                [(0.8, 0), (4.2, 0), (5.9, 1.4), (5.9, 3.6), (4.2, 5),
                 (0.8, 5)],
                [(0.8, 5), (4.6, 5), (6.4, 6.4), (6.4, 8.6), (4.6, 10),
                 (0.8, 10)]]),
    'C': (7.8, [[(7.2, 2.6), (5.6, 0.7), (3.4, 0), (1.6, 1.2), (0.6, 3.2),
                 (0.6, 6.8), (1.6, 8.8), (3.4, 10), (5.6, 9.3), (7.2, 7.4)]]),
    'D': (8.2, [[(0.8, 0), (0.8, 10)],
                [(0.8, 0), (3.6, 0), (5.4, 1.2), (6.4, 3.4), (6.4, 6.6),
                 (5.4, 8.8), (3.6, 10), (0.8, 10)]]),
    'E': (6.6, [[(5.8, 0), (0.8, 0), (0.8, 10), (5.8, 10)],
                [(0.8, 5), (4.8, 5)]]),
    'F': (6.2, [[(5.8, 0), (0.8, 0), (0.8, 10)],
                [(0.8, 5), (4.6, 5)]]),
    'G': (8.4, [[(7.6, 2.6), (6, 0.7), (3.6, 0), (1.7, 1.2), (0.7, 3.2),
                 (0.7, 6.8), (1.7, 8.8), (3.6, 10), (6, 9.6), (7.6, 8.2),
                 (7.6, 6.2), (5.2, 6.2)]]),
    'H': (8.4, [[(0.8, 0), (0.8, 10)],
                [(7.6, 0), (7.6, 10)],
                [(0.8, 5), (7.6, 5)]]),
    'I': (3.4, [[(1.7, 0), (1.7, 10)],
                [(0.2, 0), (3.2, 0)],
                [(0.2, 10), (3.2, 10)]]),
    'J': (5.6, [[(5, 0), (5, 7.6), (4, 9.6), (2.2, 10.2), (0.8, 9.2),
                 (0.6, 7.6)]]),
    'K': (7.8, [[(0.8, 0), (0.8, 10)],
                [(6.8, 0), (1, 5.2)],
                [(2.4, 4), (7.2, 10)]]),
    'L': (6.4, [[(0.8, 0), (0.8, 10), (5.8, 10)]]),
    'M': (10.0, [[(0.6, 10), (0.6, 0), (5, 5.6), (9.4, 0), (9.4, 10)]]),
    'N': (8.6, [[(0.8, 10), (0.8, 0), (7.8, 10), (7.8, 0)]]),
    'O': (8.6, [[(4.3, 0), (6.6, 0.7), (8, 3), (8, 7), (6.6, 9.3),
                 (4.3, 10), (2, 9.3), (0.6, 7), (0.6, 3), (2, 0.7),
                 (4.3, 0)]]),
    'P': (7.4, [[(0.8, 10), (0.8, 0), (4.4, 0), (6.2, 1.4), (6.2, 4.2),
                 (4.4, 5.6), (0.8, 5.6)]]),
    'Q': (8.6, [[(4.3, 0), (6.6, 0.7), (8, 3), (8, 7), (6.6, 9.3),
                 (4.3, 10), (2, 9.3), (0.6, 7), (0.6, 3), (2, 0.7),
                 (4.3, 0)],
                [(5.4, 7.2), (8.6, 10.4)]]),
    'R': (7.8, [[(0.8, 10), (0.8, 0), (4.4, 0), (6.2, 1.4), (6.2, 4.2),
                 (4.4, 5.6), (0.8, 5.6)],
                [(4, 5.6), (7.2, 10)]]),
    'S': (7.2, [[(6.6, 2.4), (5.2, 0.6), (2.8, 0), (1.2, 1.4), (1, 3.2),
                 (2.2, 4.6), (5, 5.6), (6.4, 7), (6.2, 8.8), (4.6, 10.2),
                 (2.2, 10.2), (0.8, 8.8)]]),
    'T': (7.4, [[(0.4, 0), (7, 0)],
                [(3.7, 0), (3.7, 10)]]),
    'U': (8.4, [[(0.8, 0), (0.8, 7.2), (2, 9.4), (4.2, 10.2), (6.4, 9.4),
                 (7.6, 7.2), (7.6, 0)]]),
    'V': (8.4, [[(0.4, 0), (4.2, 10.4), (8, 0)]]),
    'W': (10.8, [[(0.4, 0), (2.6, 10), (5.2, 3), (7.8, 10), (10, 0)]]),
    'X': (7.6, [[(0.6, 0), (7, 10)],
                [(7, 0), (0.6, 10)]]),
    'Y': (7.6, [[(0.6, 0), (3.8, 4.6), (7, 0)],
                [(3.8, 4.6), (3.8, 10)]]),
    'Z': (7.2, [[(0.6, 0), (6.6, 0), (0.6, 10), (6.6, 10)]]),
    '0': (7.6, [[(3.8, 0), (5.8, 0.8), (6.8, 3), (6.8, 7), (5.8, 9.2),
                 (3.8, 10), (1.8, 9.2), (0.8, 7), (0.8, 3), (1.8, 0.8),
                 (3.8, 0)]]),
    '1': (5.2, [[(1.6, 2.2), (3.6, 0.4), (3.6, 10)],
                [(1.2, 10), (5.6, 10)]]),
    '2': (7.2, [[(1, 2.4), (2.2, 0.6), (4.4, 0), (6, 1.4), (6.2, 3.4),
                 (5, 5.4), (0.8, 9.8), (6.6, 10)]]),
    '3': (7.2, [[(1, 1.6), (2.6, 0.2), (4.8, 0.2), (6, 1.6), (5.8, 3.6),
                 (4.2, 4.8), (5.9, 5.9), (6.1, 8.4), (4.8, 10), (2.4, 10),
                 (0.9, 8.9)]]),
    '4': (7.6, [[(4.8, 10), (4.8, 0), (0.6, 7.2), (7.2, 7.2)]]),
    '5': (7.0, [[(6.2, 0), (1.4, 0), (1.2, 4.2), (3.4, 3.6), (5.6, 4.4),
                 (6.2, 6.8), (5.4, 9.2), (3, 10.2), (1, 9.4), (0.7, 7.6)]]),
    '6': (7.2, [[(5.9, 1.8), (4.2, 0.4), (2.2, 1.2), (1, 3.6), (0.7, 7),
                 (1.6, 9.4), (3.6, 10.2), (5.6, 9.6), (6.4, 7.8), (5.8, 5.6),
                 (4, 5), (1.6, 5.9)]]),
    '7': (7.0, [[(0.8, 0), (6.6, 0), (3.4, 10)]]),
    '8': (7.2, [[(3.6, 5), (2, 4.2), (1.8, 2), (3, 0.4), (5.2, 0.4),
                 (6.2, 2), (6, 4.2), (3.6, 5)],
                [(3.6, 5), (1.6, 6), (1.4, 8.4), (2.8, 10), (5.4, 10),
                 (6.6, 8.4), (6.4, 6), (3.6, 5)]]),
    '9': (7.2, [[(1.3, 8.2), (3, 9.6), (5, 8.8), (6.2, 6.4), (6.5, 3),
                 (5.6, 0.6), (3.6, 0), (1.6, 0.4), (0.8, 2.2), (1.4, 4.4),
                 (3.2, 5), (5.6, 4.1)]]),
}

GLYPHS.update({
    'a': (6.8, [[(6, 4.6), (4.4, 3.2), (2.2, 3.2), (1, 4.8), (1, 8.4),
                 (2.2, 10), (4.4, 10.2), (6, 9.4)],
                [(6, 3), (6, 10)]]),
    'b': (6.8, [[(0.8, 0), (0.8, 10)],
                [(0.8, 6), (2.4, 3.4), (4.6, 3), (6, 4.4), (6, 8.6),
                 (4.6, 10.2), (2.4, 10.2), (0.8, 8.8)]]),
    'c': (6.0, [[(5.6, 4.6), (4.2, 3.2), (2.2, 3.2), (1, 4.8), (1, 8.2),
                 (2.2, 9.8), (4.2, 9.8), (5.6, 8.4)]]),
    'd': (6.8, [[(6, 4.6), (4.4, 3.2), (2.2, 3.2), (1, 4.8), (1, 8.4),
                 (2.2, 10), (4.4, 10.2), (6, 9.4)],
                [(6, 0), (6, 10)]]),
    'e': (6.2, [[(1, 6.4), (6, 6.4), (5.8, 4.6), (4.4, 3.2), (2.4, 3.2),
                 (1, 4.8), (1, 8.4), (2.4, 10), (4.6, 10), (5.8, 8.8)]]),
    'f': (4.4, [[(4.2, 1.2), (3, 0.2), (1.8, 1), (1.6, 3), (1.6, 10)],
                [(0.2, 3.4), (3.6, 3.4)]]),
    'g': (6.8, [[(6, 4.6), (4.4, 3.2), (2.2, 3.2), (1, 4.8), (1, 8.4),
                 (2.2, 10), (4.4, 10.2), (6, 9.4)],
                [(6, 3), (6, 9.8), (5, 12), (3, 12.8), (1.4, 11.8)]]),
    'h': (7.0, [[(0.8, 0), (0.8, 10)],
                [(0.8, 5.6), (2.4, 3.4), (4.6, 3.2), (6.2, 4.6),
                 (6.2, 10)]]),
    'i': (3.0, [[(1.5, 3), (1.5, 10)],
                [(1.5, 0.1), (1.5, 0.9)]]),
    'j': (3.6, [[(2.8, 3), (2.8, 10.4), (1.8, 12.2), (0.4, 12.4)],
                [(2.8, 0.1), (2.8, 0.9)]]),
    'k': (6.4, [[(0.8, 0), (0.8, 10)],
                [(5.6, 3.2), (0.9, 6.8)],
                [(2.2, 5.6), (5.8, 10)]]),
    'l': (3.0, [[(1.5, 0), (1.5, 10)]]),
    'm': (10.4, [[(0.8, 3), (0.8, 10)],
                 [(0.8, 5.4), (2.2, 3.4), (4, 3.2), (5.2, 4.4), (5.2, 10)],
                 [(5.2, 5.4), (6.6, 3.4), (8.4, 3.2), (9.6, 4.4),
                  (9.6, 10)]]),
    'n': (7.0, [[(0.8, 3), (0.8, 10)],
                [(0.8, 5.4), (2.4, 3.4), (4.6, 3.2), (6.2, 4.6),
                 (6.2, 10)]]),
    'o': (6.8, [[(3.4, 3), (5.2, 3.4), (6.2, 5.4), (6.2, 7.8), (5.2, 9.6),
                 (3.4, 10), (1.6, 9.6), (0.6, 7.8), (0.6, 5.4), (1.6, 3.4),
                 (3.4, 3)]]),
    'p': (6.8, [[(0.8, 3), (0.8, 13)],
                [(0.8, 4.6), (2.4, 3.2), (4.6, 3), (6, 4.4), (6, 7.6),
                 (4.6, 9.6), (2.4, 9.8), (0.8, 8.4)]]),
    'q': (6.8, [[(6, 4.6), (4.4, 3.2), (2.2, 3.2), (1, 4.6), (1, 7.6),
                 (2.2, 9.6), (4.4, 9.8), (6, 8.4)],
                [(6, 3), (6, 13)]]),
    'r': (4.8, [[(0.8, 3), (0.8, 10)],
                [(0.8, 5.2), (2.2, 3.4), (4.2, 3.2)]]),
    's': (5.8, [[(5.4, 4.4), (4, 3.2), (2, 3.2), (1, 4.4), (1.4, 5.8),
                 (3.2, 6.6), (5, 7.4), (5.4, 9), (4.2, 10.2), (2, 10.2),
                 (0.8, 9.2)]]),
    't': (4.6, [[(2.2, 0.8), (2.2, 8.6), (3, 10), (4.4, 9.8)],
                [(0.4, 3.4), (4.2, 3.4)]]),
    'u': (7.0, [[(0.8, 3), (0.8, 8.2), (2.2, 10), (4.4, 10), (6, 8.8)],
                [(6, 3), (6, 10)]]),
    'v': (6.4, [[(0.4, 3), (3.2, 10.2), (6, 3)]]),
    'w': (9.2, [[(0.4, 3), (2, 10), (4.4, 4.6), (6.6, 10), (8.8, 3)]]),
    'x': (6.0, [[(0.6, 3), (5.6, 10)],
                [(5.6, 3), (0.6, 10)]]),
    'y': (6.4, [[(0.4, 3), (3.2, 8.4)],
                [(6, 3), (3.2, 8.4), (2.4, 11.4), (1, 12.4), (0.2, 11.6)]]),
    'z': (6.0, [[(0.6, 3), (5.6, 3), (0.6, 10), (5.6, 10)]]),
    ' ': (4.0, []),
    '.': (3.0, [[(1.5, 9.6), (1.5, 10.1)]]),
    ',': (3.0, [[(2.2, 9.4), (1.4, 12)]]),
    ':': (3.0, [[(1.5, 3.7), (1.5, 4.2)],
                [(1.5, 9.6), (1.5, 10.1)]]),
    ';': (3.0, [[(1.5, 3.7), (1.5, 4.2)],
                [(2.2, 9.4), (1.4, 12)]]),
    "'": (3.0, [[(2.2, 0), (1.6, 2.6)]]),
    '"': (5.0, [[(1.4, 0), (1, 2.6)],
                [(3.8, 0), (3.4, 2.6)]]),
    '-': (5.4, [[(0.6, 6), (4.8, 6)]]),
    '–': (7.0, [[(0.6, 6), (6.4, 6)]]),
    '—': (10.0, [[(0.4, 6), (9.6, 6)]]),
    '!': (3.0, [[(1.5, 0), (1.5, 6.8)],
                [(1.5, 9.6), (1.5, 10.1)]]),
    '?': (6.4, [[(1, 2.2), (2.2, 0.4), (4.4, 0.2), (5.8, 1.6), (5.4, 3.6),
                 (3.4, 5), (3.2, 6.8)],
                [(3.2, 9.6), (3.2, 10.1)]]),
    '(': (4.0, [[(3.6, 0.2), (2, 2.2), (1.2, 5.4), (2, 8.6), (3.6, 10.6)]]),
    ')': (4.0, [[(0.4, 0.2), (2, 2.2), (2.8, 5.4), (2, 8.6), (0.4, 10.6)]]),
    '/': (5.0, [[(0.8, 10.4), (4.4, 0)]]),
    '&': (8.4, [[(6.8, 9.4), (3, 4.2), (2.2, 1.8), (3.4, 0.2), (5.4, 0.6),
                 (5.8, 2.4), (4.4, 4.4), (1.2, 7.4), (1.6, 9.6), (4, 10.4),
                 (7.2, 10.2)]]),
    '%': (9.4, [[(2.4, 0.6), (3.6, 1.2), (3.4, 3), (2.2, 3.6), (1, 3),
                 (0.8, 1.2), (2.4, 0.6)],
                [(7.6, 0), (1.8, 10.4)],
                [(7, 6.8), (8.2, 7.4), (8, 9.2), (6.8, 9.8), (5.6, 9.2),
                 (5.4, 7.4), (7, 6.8)]]),
    '+': (7.0, [[(3.5, 2.6), (3.5, 7.6)],
                [(1, 5.1), (6, 5.1)]]),
    '·': (3.4, [[(1.7, 5.2), (1.7, 5.8)]]),
    '•': (3.4, [[(1.7, 5.2), (1.7, 5.8)]]),
    '*': (5.0, [[(2.5, 2), (2.5, 8)],
                [(0.8, 3.4), (4.2, 6.6)],
                [(4.2, 3.4), (0.8, 6.6)]]),
    '=': (7.0, [[(0.6, 4), (6.4, 4)],
                [(0.6, 7), (6.4, 7)]]),
    '<': (6.0, [[(5.4, 1.4), (0.8, 5.4), (5.4, 9.4)]]),
    '>': (6.0, [[(0.6, 1.4), (5.2, 5.4), (0.6, 9.4)]]),
    '[': (4.0, [[(3.4, 0.4), (1.2, 0.4), (1.2, 9.6), (3.4, 9.6)]]),
    ']': (4.0, [[(0.6, 0.4), (2.8, 0.4), (2.8, 9.6), (0.6, 9.6)]]),
    '$': (7.0, [[(6.4, 2.4), (5, 0.6), (2.6, 0), (1.1, 1.4), (1, 3.2),
                 (2.1, 4.6), (4.8, 5.6), (6.2, 7), (6, 8.8), (4.4, 10.2),
                 (2, 10.2), (0.7, 8.8)],
                [(3.5, 0), (3.5, 10.4)]]),
    '°': (4.4, [[(2.2, 0.4), (3.4, 1), (3.2, 2.4), (2, 3), (0.8, 2.4),
                 (0.6, 1), (2.2, 0.4)]]),
})

_FALLBACK = (8.0, [[(1, 1), (7, 1), (7, 9), (1, 9), (1, 1)]])


def _glyph(ch):
    return GLYPHS.get(ch, _FALLBACK)


def text_width(s, cap, bold=False, tracking=0.0):
    unit = cap / 10.0
    w = 0.0
    for ch in s:
        w += _glyph(ch)[0] * unit
    if len(s) > 1:
        w += tracking * (len(s) - 1)
    return w


def draw_text(x, baseline, s, cap, color, bold=False, tracking=0.0,
              align='left'):
    """Draw a line of text; returns its width in final-image units."""
    unit = cap / 10.0
    w = text_width(s, cap, bold, tracking)
    if align == 'center':
        x -= w / 2.0
    elif align == 'right':
        x -= w
    lw = cap * (0.155 if bold else 0.105)
    pen = x
    for ch in s:
        adv, strokes = _glyph(ch)
        for stroke in strokes:
            pts = [(pen + gx * unit, baseline - (10.0 - gy) * unit)
                   for gx, gy in stroke]
            polyline(pts, lw, color)
        pen += adv * unit + tracking
    return w


def draw_text_rot(cx, cy, s, cap, color, bold, angle_deg):
    """Text rotated about a centre point (for the NO DEAL stamp)."""
    unit = cap / 10.0
    w = text_width(s, cap, bold)
    lw = cap * (0.155 if bold else 0.105)
    a = math.radians(angle_deg)
    ca, sa = math.cos(a), math.sin(a)

    def tf(lx, ly):
        return (cx + lx * ca - ly * sa, cy + lx * sa + ly * ca)

    pen = -w / 2.0
    for ch in s:
        adv, strokes = _glyph(ch)
        for stroke in strokes:
            pts = [tf(pen + gx * unit, -(10.0 - gy) * unit)
                   for gx, gy in stroke]
            polyline(pts, lw, color)
        pen += adv * unit


def wrap_text(s, cap, max_width, bold=False):
    """Greedy word wrap using the stroke font's own metrics."""
    words = s.split()
    lines = []
    cur = ''
    for word in words:
        trial = word if not cur else cur + ' ' + word
        if text_width(trial, cap, bold) <= max_width or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


# ------------------------------------------------------------- page bits

def chip(x, y, text, bg, cap=12.5):
    """Coloured section label with white bold text; returns its width."""
    w = text_width(text, cap, True) + 18
    fill_rect(x, y, x + w, y + 22, bg)
    draw_text(x + 9, y + 16.5, text, cap, WHITE, bold=True)
    return w


def icon_drone(x, y, c):
    w = 3.0
    polyline([(x + 14, y + 14), (x + 6, y + 6)], w, c)
    polyline([(x + 34, y + 14), (x + 42, y + 6)], w, c)
    polyline([(x + 14, y + 34), (x + 6, y + 42)], w, c)
    polyline([(x + 34, y + 34), (x + 42, y + 42)], w, c)
    for cx, cy in ((6, 6), (42, 6), (6, 42), (42, 42)):
        circle(x + cx, y + cy, 5.5, w, c)
    polyline([(x + 17, y + 17), (x + 31, y + 17), (x + 31, y + 31),
              (x + 17, y + 31), (x + 17, y + 17)], w, c)
    fill_disc(x + 24, y + 27, 3.2, c)


def icon_capitol(x, y, c):
    w = 3.0
    pts = []
    for k in range(21):
        a = math.pi * k / 20
        pts.append((x + 24 - 15 * math.cos(a), y + 30 - 17 * math.sin(a)))
    polyline(pts, w, c)
    line(x + 24, y + 13, x + 24, y + 5, w, c)
    fill_disc(x + 24, y + 4, 2.4, c)
    line(x + 5, y + 33, x + 43, y + 33, w, c)
    for cx in (13, 20, 27, 34):
        line(x + cx, y + 33, x + cx, y + 42, w, c)
    line(x + 4, y + 45, x + 44, y + 45, w, c)


def icon_building(x, y, c):
    w = 3.0
    polyline([(x + 13, y + 5), (x + 35, y + 5), (x + 35, y + 45),
              (x + 13, y + 45), (x + 13, y + 5)], w, c)
    for r in range(4):
        for col in range(3):
            fill_rect(x + 17 + col * 6.5, y + 10 + r * 7.5,
                      x + 20.5 + col * 6.5, y + 13.5 + r * 7.5, c)
    fill_rect(x + 21.5, y + 38, x + 26.5, y + 45, c)


def icon_tanker(x, y, c):
    w = 3.0
    polyline([(x + 4, y + 27), (x + 44, y + 27), (x + 38, y + 37),
              (x + 10, y + 37), (x + 4, y + 27)], w, c)
    line(x + 11, y + 27, x + 11, y + 19, w, c)
    line(x + 11, y + 19, x + 29, y + 19, w, c)
    line(x + 29, y + 19, x + 29, y + 27, w, c)
    line(x + 34, y + 27, x + 34, y + 14, w, c)
    for off in (0, 7):
        pts = []
        for k in range(13):
            px = x + 2 + k * 3.7
            pts.append((px, y + 42 + off * 0.55 +
                        2.2 * math.sin(k * 1.05 + off)))
        polyline(pts, 2.4, c)


def icon_flame(x, y, c):
    w = 3.0
    outer = [(x + 24, y + 2), (x + 29, y + 13), (x + 35, y + 22),
             (x + 34, y + 34), (x + 28, y + 42), (x + 20, y + 42),
             (x + 14, y + 34), (x + 13, y + 23), (x + 18, y + 13),
             (x + 24, y + 2)]
    polyline(outer, w, c)
    inner = [(x + 24, y + 20), (x + 28, y + 27), (x + 27, y + 35),
             (x + 24, y + 39), (x + 21, y + 35), (x + 20, y + 27),
             (x + 24, y + 20)]
    polyline(inner, w, c)


def icon_tennis(x, y, c):
    w = 3.0
    circle(x + 24, y + 24, 19, w, c)
    polyline([(x + 11, y + 9), (x + 18, y + 24), (x + 11, y + 39)], w, c)
    polyline([(x + 37, y + 9), (x + 30, y + 24), (x + 37, y + 39)], w, c)


def icon_planet(x, y, c):
    w = 2.8
    circle(x + 22, y + 24, 13, w, c)
    pts = []
    for k in range(49):
        a = 2 * math.pi * k / 48
        lx, ly = 21 * math.cos(a), 7.5 * math.sin(a)
        ca, sa = math.cos(-0.35), math.sin(-0.35)
        pts.append((x + 22 + lx * ca - ly * sa, y + 24 + lx * sa + ly * ca))
    polyline(pts, w, c)
    fill_disc(x + 40, y + 10, 2.6, c)


def globe(cx, cy, r):
    w = 2.6
    circle(cx, cy, r, 3.2, BLUE)
    ellipse(cx, cy, r, r, w, BLUE, squash_x=0.38)
    ellipse(cx, cy, r, r, w, BLUE, squash_x=0.72)
    line(cx, cy - r, cx, cy + r, w, BLUE)
    line(cx - r, cy, cx + r, cy, w, BLUE)
    ellipse(cx, cy - r * 0.42, r * 0.9, r * 0.2, w, BLUE)
    ellipse(cx, cy + r * 0.42, r * 0.9, r * 0.2, w, BLUE)
    crack = [(cx - 26, cy - r + 4), (cx - 12, cy - 62), (cx - 30, cy - 30),
             (cx - 10, cy + 2), (cx - 28, cy + 38), (cx - 14, cy + 78),
             (cx - 20, cy + r - 6)]
    polyline(crack, 3.4, RED)
    polyline([(cx - 30, cy - 30), (cx - 54, cy - 12)], 3.0, RED)
    polyline([(cx - 10, cy + 2), (cx + 12, cy + 22)], 3.0, RED)


def story(x, y0, tag, tagcolor, headline, body, icon, head_cap=19.0,
          body_cap=13.0):
    chip(x, y0, tag, tagcolor)
    icon(x + 468 - 50, y0 - 2, tagcolor)
    hy = y0 + 50
    for ln in wrap_text(headline, head_cap, 408, bold=True):
        draw_text(x, hy, ln, head_cap, INK, bold=True)
        hy += 24
    by = hy - 2
    for ln in wrap_text(body, body_cap, 468):
        draw_text(x, by, ln, body_cap, INK)
        by += 18


def draw_page():
    # frame
    polyline([(20, 20), (1004, 20), (1004, 1004), (20, 1004), (20, 20)],
             3.0, INK)
    polyline([(29, 29), (995, 29), (995, 995), (29, 995), (29, 29)],
             1.1, INK)

    # masthead
    draw_text(512, 58, "ONE PAGE · EIGHT STORIES · THE WHOLE DAY'S NEWS",
              13.5, DRED, bold=True, tracking=2.2, align='center')
    draw_text(512, 136, "THE WORLD TODAY", 70, INK, bold=True,
              tracking=1.5, align='center')
    fill_rect(34, 148, 990, 151.5, INK)
    fill_rect(34, 156, 990, 157.5, INK)
    fill_rect(34, 166, 990, 210, BLACK)
    draw_text(52, 195, "GLOBAL EDITION", 11.5, WHITE, bold=True,
              tracking=1.0)
    draw_text(512, 197, "MONDAY 23 NOVEMBER 2026", 25, WHITE, bold=True,
              tracking=1.2, align='center')
    draw_text(972, 195, "ONE PAGE", 11.5, WHITE, bold=True, tracking=1.0,
              align='right')

    # lead story
    cw_ = chip(34, 226, "TOP STORY", RED)
    draw_text(34 + cw_ + 12, 243, "CLIMATE SUMMIT — COP31", 15.5, DRED,
              bold=True, tracking=0.5)
    hy = 300
    for ln in wrap_text("COP31 CLIMATE TALKS END WITHOUT A DEAL", 38, 618,
                        bold=True):
        draw_text(34, hy, ln, 38, INK, bold=True)
        hy += 49
    by = hy - 20
    for ln in wrap_text(
            "COP31 closed with no agreement after the EU and others "
            "rejected a final text with no move away from fossil fuels. "
            "Pacific island nations voiced despair; the UN chief warned "
            "the science is not ambiguous.", 14.5, 618):
        draw_text(34, by, ln, 14.5, INK)
        by += 23.5
    globe(824, 322, 100)
    # NO DEAL stamp over the globe's lower-left edge
    circle(706, 412, 37, 3.2, RED)
    circle(706, 412, 31, 1.4, RED)
    draw_text_rot(706, 417, "NO DEAL", 13.5, RED, True, -13)
    fill_rect(34, 458, 990, 460, INK)

    # story grid: two columns, three rows
    colx = (34, 522)
    div = (178, 168, 144)
    line(512, 472, 512, 888, 1.2, div)
    story(colx[0], 472, "UKRAINE WAR", DRED,
          "AT LEAST 15 KILLED IN KYIV REGION STRIKES",
          "Ukraine says Russian attacks killed at least 15 in the Kyiv "
          "region; its sea drones hit two Russian ships off Libya, and "
          "the UN urges a probe.", icon_drone)
    story(colx[1], 472, "UNITED STATES", BLUE,
          "HISTORIC HOUSE WIN FOR DEMOCRATS",
          "Democrats have secured at least 258 House seats — the "
          "party's biggest majority since 1992.", icon_capitol)
    fill_rect(34, 616, 990, 617.6, div)
    story(colx[0], 626, "SUDAN", ORANGE,
          "DRONES HIT HOMES AND UN BUILDING",
          "A drone attack in Sudan's capital Khartoum struck homes "
          "and a United Nations building.", icon_building)
    story(colx[1], 626, "GULF TENSIONS", TEAL,
          "BAHRAIN: IRAN HIT INDUSTRIAL SITE",
          "A tanker was damaged in the Strait of Hormuz. Trump leans "
          "toward renewed conflict if no deal by the New Year.",
          icon_tanker)
    fill_rect(34, 762, 990, 763.6, div)
    story(colx[0], 772, "INDONESIA", RED,
          "FIRE AT CANDY FACTORY KILLS AT LEAST 3",
          "Dozens are missing after the blaze tore through the candy "
          "factory in Indonesia.", icon_flame, head_cap=18.5,
          body_cap=12.8)
    story(colx[1], 772, "SPORT · TENNIS", PURPLE,
          "ALCARAZ WINS FIRST ATP FINALS TITLE",
          "Carlos Alcaraz beat Alexander Zverev to lift the ATP "
          "Finals trophy for the first time.", icon_tennis,
          head_cap=18.5, body_cap=12.8)

    # brighter-news band
    fill_rect(34, 896, 990, 950, GREEN)
    draw_text(52, 922, "BRIGHTER", 13, WHITE, bold=True, tracking=1.0)
    draw_text(52, 942, "NEWS", 13, WHITE, bold=True, tracking=1.0)
    draw_text(168, 924, "JAPAN–EUROPE PROBE ENTERS ORBIT AROUND MERCURY",
              16.5, WHITE, bold=True)
    draw_text(168, 946,
              "A Japanese-European space probe has entered orbit "
              "around Mercury.", 12, (216, 238, 218))
    icon_planet(918, 902, WHITE)

    # footer
    draw_text(512, 978,
              "THE WORLD TODAY · SUMMING UP MONDAY 23 NOVEMBER 2026 · "
              "ONE PAGE · EIGHT STORIES",
              10.5, GREY, tracking=1.5, align='center')


# ------------------------------------------------------------ output

def downsample():
    """2x2 box filter from the 2048 canvas to the 1024 output."""
    out = bytearray(W * H * 3)
    stride = CW * 3
    for j in range(H):
        r0 = list(buf[(2 * j) * stride:(2 * j) * stride + stride])
        r1 = list(buf[(2 * j + 1) * stride:(2 * j + 1) * stride + stride])
        row = []
        ap = row.append
        for p in range(0, stride, 6):
            ap((r0[p] + r0[p + 3] + r1[p] + r1[p + 3] + 2) >> 2)
            ap((r0[p + 1] + r0[p + 4] + r1[p + 1] + r1[p + 4] + 2) >> 2)
            ap((r0[p + 2] + r0[p + 5] + r1[p + 2] + r1[p + 5] + 2) >> 2)
        out[j * W * 3:(j + 1) * W * 3] = bytes(row)
    return out


def grain(img, amp=3):
    """Deterministic luminance grain, like the tooth of newsprint."""
    span = 2 * amp + 1
    for y in range(H):
        seed = y * 668265263
        base = y * W * 3
        for x in range(W):
            h = (seed + x * 374761393) & 0xFFFFFFFF
            h ^= h >> 13
            h = (h * 1274126177) & 0xFFFFFFFF
            d = ((h >> 16) % span) - amp
            if d:
                idx = base + x * 3
                for c in range(3):
                    v = img[idx + c] + d
                    img[idx + c] = 0 if v < 0 else (255 if v > 255 else v)
    return img


def png_bytes(img):
    raw = bytearray()
    stride = W * 3
    for j in range(H):
        raw.append(0)
        raw += img[j * stride:(j + 1) * stride]
    comp = zlib.compress(bytes(raw), 9)

    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data +
                struct.pack(">I", crc32(tag + data) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) +
            chunk(b"IDAT", comp) + chunk(b"IEND", b""))


def main():
    _grad_bg()
    _speckles()
    draw_page()
    img = grain(downsample())
    data = png_bytes(img)
    out = os.environ.get("ENTRY_OUT", "/output/entry.png")
    parent = os.path.dirname(out)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(out, "wb") as fh:
        fh.write(data)


if __name__ == "__main__":
    main()
