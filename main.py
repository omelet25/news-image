#!/usr/bin/env python3
"""Sum up 23 November 2026's world news in one image.

A pure-standard-library program: it rasterises a one-page newspaper
poster (masthead, a lead story and seven further stories, all first
reported on Monday 23 November 2026) into a PNG and writes it to
/output/entry.png (or $MAKEFUN_OUTPUT_DIR/entry.png).

No network, no third-party packages, no fonts on disk: the typeface is
a small bitmap font defined below, and the PNG encoder is built on
zlib/struct from the standard library. The output is deterministic:
running the program twice writes exactly the same bytes.
"""

import math
import os
import struct
import zlib

# ---------------------------------------------------------------- canvas

W, H = 1024, 1024

PAPER = (246, 241, 227)
INK = (20, 22, 26)
GRAY = (74, 74, 78)
FAINT = (203, 196, 178)
RED = (179, 58, 43)
BLUE = (36, 86, 166)
GREEN = (38, 116, 74)
WHITE = (252, 250, 244)


class Canvas:
    def __init__(self, w, h, bg):
        self.w = w
        self.h = h
        self.px = bytearray(bg) * (w * h)

    def block(self, x, y, bw, bh, color):
        """Fill a rectangle, clipped to the canvas."""
        x0 = max(0, x)
        y0 = max(0, y)
        x1 = min(self.w, x + bw)
        y1 = min(self.h, y + bh)
        if x0 >= x1 or y0 >= y1:
            return
        row = bytes(color) * (x1 - x0)
        n = len(row)
        for yy in range(y0, y1):
            off = (yy * self.w + x0) * 3
            self.px[off:off + n] = row

    def rect(self, x, y, w, h, color):
        self.block(x, y, w, h, color)

    def frame(self, x, y, w, h, color, t=2):
        self.block(x, y, w, t, color)
        self.block(x, y + h - t, w, t, color)
        self.block(x, y, t, h, color)
        self.block(x + w - t, y, t, h, color)

    def disc(self, cx, cy, r, color):
        r2 = r * r
        for yy in range(cy - r, cy + r + 1):
            dy = yy - cy
            span = int(math.sqrt(r2 - dy * dy))
            self.block(cx - span, yy, 2 * span + 1, 1, color)

    def ring(self, cx, cy, r, color, t=3):
        steps = max(72, r * 4)
        for i in range(steps):
            a = 2.0 * math.pi * i / steps
            x = int(round(cx + r * math.cos(a)))
            y = int(round(cy + r * math.sin(a)))
            self.block(x - t // 2, y - t // 2, t, t, color)

    def ellipse_ring(self, cx, cy, rx, ry, color, t=3):
        steps = max(72, rx * 3)
        for i in range(steps):
            a = 2.0 * math.pi * i / steps
            x = int(round(cx + rx * math.cos(a)))
            y = int(round(cy + ry * math.sin(a)))
            self.block(x - t // 2, y - t // 2, t, t, color)


def png_bytes(cv):
    raw = bytearray()
    stride = cv.w * 3
    for y in range(cv.h):
        raw.append(0)
        raw += cv.px[y * stride:(y + 1) * stride]

    def chunk(kind, data):
        out = struct.pack(">I", len(data)) + kind + data
        out += struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        return out

    ihdr = struct.pack(">IIBBBBB", cv.w, cv.h, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
            + chunk(b"IEND", b""))


# ------------------------------------------------------------------ font
# A 6x8 bitmap typeface, drawn for this poster. '#' is ink, '.' is paper.
# Every glyph is 8 rows of 6 characters.

FONT = {
    "A": (".####.", "#....#", "#....#", "######", "#....#", "#....#", "#....#", "#....#"),
    "B": ("#####.", "#....#", "#....#", "#####.", "#....#", "#....#", "#....#", "#####."),
    "C": (".####.", "#....#", "#.....", "#.....", "#.....", "#.....", "#....#", ".####."),
    "D": ("####..", "#...#.", "#....#", "#....#", "#....#", "#....#", "#...#.", "####.."),
    "E": ("######", "#.....", "#.....", "#####.", "#.....", "#.....", "#.....", "######"),
    "F": ("######", "#.....", "#.....", "#####.", "#.....", "#.....", "#.....", "#....."),
    "G": (".####.", "#....#", "#.....", "#.####", "#....#", "#....#", "#....#", ".###.#"),
    "H": ("#....#", "#....#", "#....#", "######", "#....#", "#....#", "#....#", "#....#"),
    "I": ("######", "..##..", "..##..", "..##..", "..##..", "..##..", "..##..", "######"),
    "J": (".#####", "....#.", "....#.", "....#.", "....#.", "....#.", "#...#.", ".###.."),
    "K": ("#....#", "#...#.", "#..#..", "###...", "#..#..", "#...#.", "#....#", "#....#"),
    "L": ("#.....", "#.....", "#.....", "#.....", "#.....", "#.....", "#.....", "######"),
    "M": ("#....#", "##..##", "#.##.#", "#....#", "#....#", "#....#", "#....#", "#....#"),
    "N": ("#....#", "##...#", "#.#..#", "#.#..#", "#..#.#", "#...##", "#....#", "#....#"),
    "O": (".####.", "#....#", "#....#", "#....#", "#....#", "#....#", "#....#", ".####."),
    "P": ("#####.", "#....#", "#....#", "#####.", "#.....", "#.....", "#.....", "#....."),
    "Q": (".####.", "#....#", "#....#", "#....#", "#..#.#", "#...#.", ".###.#", "....##"),
    "R": ("#####.", "#....#", "#....#", "#####.", "#..#..", "#...#.", "#....#", "#....#"),
    "S": (".#####", "#.....", "#.....", ".####.", ".....#", ".....#", ".....#", "#####."),
    "T": ("######", "..##..", "..##..", "..##..", "..##..", "..##..", "..##..", "..##.."),
    "U": ("#....#", "#....#", "#....#", "#....#", "#....#", "#....#", "#....#", ".####."),
    "V": ("#....#", "#....#", "#....#", "#....#", "#....#", "#....#", ".#..#.", "..##.."),
    "W": ("#....#", "#....#", "#....#", "#....#", "#.#.#.", "#.#.#.", "#.#.#.", ".##.##."),
    "X": ("#....#", ".#..#.", "..##..", "..##..", "..##..", ".#..#.", "#....#", "#....#"),
    "Y": ("#....#", ".#..#.", ".#..#.", "..##..", "..##..", "..##..", "..##..", "..##.."),
    "Z": ("######", ".....#", "....#.", "...#..", "..#...", ".#....", "#.....", "######"),
    "0": (".####.", "#...##", "#..#.#", "#.#..#", "##...#", "#....#", "#....#", ".####."),
    "1": ("..#...", ".##...", "..#...", "..#...", "..#...", "..#...", "..#...", ".###.."),
    "2": (".####.", "#....#", ".....#", "....#.", "...#..", "..#...", ".#....", "######"),
    "3": (".####.", "#....#", ".....#", "..###.", ".....#", ".....#", "#....#", ".####."),
    "4": ("...#..", "..##..", ".#.#..", "#..#..", "######", "...#..", "...#..", "...#.."),
    "5": ("######", "#.....", "#.....", "#####.", ".....#", ".....#", "#....#", ".####."),
    "6": (".####.", "#....#", "#.....", "#####.", "#....#", "#....#", "#....#", ".####."),
    "7": ("######", ".....#", "....#.", "....#.", "...#..", "...#..", "...#..", "...#.."),
    "8": (".####.", "#....#", "#....#", ".####.", "#....#", "#....#", "#....#", ".####."),
    "9": (".####.", "#....#", "#....#", ".#####", ".....#", ".....#", "#....#", ".####."),
    " ": ("......", "......", "......", "......", "......", "......", "......", "......"),
    ".": ("......", "......", "......", "......", "......", "......", ".##...", ".##..."),
    ",": ("......", "......", "......", "......", "......", ".##...", ".##...", ".#...."),
    "'": (".##...", ".##...", ".#....", "......", "......", "......", "......", "......"),
    ":": ("......", ".##...", ".##...", "......", "......", ".##...", ".##...", "......"),
    ";": ("......", ".##...", ".##...", "......", "......", ".##...", ".##...", ".#...."),
    "!": ("..##..", "..##..", "..##..", "..##..", "..##..", "..##..", "......", "..##.."),
    "?": (".####.", "#....#", ".....#", "....#.", "...#..", "...#..", "......", "...#.."),
    "-": ("......", "......", "......", ".####.", "......", "......", "......", "......"),
    "/": (".....#", ".....#", "....#.", "...#..", "...#..", "..#...", ".#....", "#....."),
    "(": ("....#.", "...#..", "..#...", "..#...", "..#...", "..#...", "...#..", "....#."),
    ")": (".#....", "..#...", "...#..", "...#..", "...#..", "...#..", "..#...", ".#...."),
    "$": (".####.", "#.#.#.", "#.#...", ".####.", "..#.#.", "..#.#.", "#####.", ".####."),
    "%": ("##...#", "##..#.", "....#.", "...#..", "..#...", ".#....", "#..##.", "#..##."),
    "+": ("......", "..##..", "..##..", ".####.", ".####.", "..##..", "..##..", "......"),
    "*": ("......", "#.#.#.", ".###..", "#####.", ".###..", "#.#.#.", "......", "......"),
}

GLYPH_W = 6
GLYPH_H = 8


def text_width(s, scale, tracking=1):
    if not s:
        return 0
    return len(s) * (GLYPH_W + tracking) * scale - tracking * scale


def draw_text(cv, x, y, s, scale, color, tracking=1, bold=False):
    """Draw s with its top-left at (x, y); returns the x just past it."""
    cx = x
    for ch in s.upper():
        glyph = FONT.get(ch, FONT[" "])
        for row_i, row in enumerate(glyph):
            for col_i, cell in enumerate(row):
                if cell == "#":
                    bx = cx + col_i * scale
                    by = y + row_i * scale
                    cv.block(bx, by, scale, scale, color)
                    if bold:
                        cv.block(bx + max(1, scale // 3), by, scale, scale, color)
        cx += (GLYPH_W + tracking) * scale
    return cx


def draw_centered(cv, cx, y, s, scale, color, tracking=1, bold=False):
    w = text_width(s, scale, tracking)
    return draw_text(cv, cx - w // 2, y, s, scale, color, tracking, bold)


def wrap(s, scale, max_w, tracking=1):
    words = s.split()
    lines = []
    cur = ""
    for word in words:
        trial = word if not cur else cur + " " + word
        if text_width(trial, scale, tracking) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def draw_wrapped(cv, x, y, s, scale, color, max_w, line_gap=6, tracking=1,
                 bold=False, max_lines=None):
    lines = wrap(s, scale, max_w, tracking)
    if max_lines is not None:
        lines = lines[:max_lines]
    for line in lines:
        draw_text(cv, x, y, line, scale, color, tracking, bold)
        y += GLYPH_H * scale + line_gap
    return y


# -------------------------------------------------------------- graphics

def draw_globe(cv, cx, cy, r, color):
    cv.ring(cx, cy, r, color, t=4)
    cv.ellipse_ring(cx, cy, r // 2, r, color, t=3)
    cv.ellipse_ring(cx, cy, r, r // 3, color, t=3)
    cv.block(cx - r, cy - 2, 2 * r, 4, color)
    cv.block(cx - 2, cy - r, 4, 2 * r, color)


def draw_planet(cv, cx, cy, r, color, accent):
    cv.disc(cx, cy, r, color)
    cv.disc(cx - r // 3, cy - r // 3, r // 4, accent)
    cv.disc(cx + r // 3, cy + r // 4, r // 5, accent)
    # orbit path with a small probe dot
    cv.ellipse_ring(cx, cy, r + 34, (r + 34) // 3, color, t=3)
    a = -0.7
    px = int(cx + (r + 34) * math.cos(a))
    py = int(cy + ((r + 34) // 3) * math.sin(a))
    cv.disc(px, py, 7, accent)
    cv.block(px - 16, py - 2, 12, 4, accent)


def draw_ball(cv, cx, cy, r, color):
    cv.ring(cx, cy, r, color, t=4)
    steps = 60
    for i in range(steps + 1):
        t = i / steps
        x = cx - r + int(2 * r * t)
        y = cy + int((r // 2) * math.sin(t * math.pi * 1.2 - 0.6))
        cv.block(x - 2, y - 2, 4, 4, color)
        y2 = cy - int((r // 2) * math.sin(t * math.pi * 1.2 - 0.6))
        cv.block(x - 2, y2 - 2, 4, 4, color)


# ---------------------------------------------------------------- layout

def story_box(cv, x, y, w, tag, tag_color, headline, body):
    # tag chip
    tw = text_width(tag, 2) + 16
    cv.rect(x, y, tw, 24, tag_color)
    draw_text(cv, x + 8, y + 4, tag, 2, WHITE)
    y += 32
    y = draw_wrapped(cv, x, y, headline, 3, INK, w, line_gap=3, bold=True)
    y += 1
    y = draw_wrapped(cv, x, y, body, 2, GRAY, w, line_gap=2)
    return y


def build():
    cv = Canvas(W, H, PAPER)
    M = 40                      # page margin
    CW = W - 2 * M              # content width

    # page frame
    cv.frame(14, 14, W - 28, H - 28, INK, t=3)
    cv.frame(22, 22, W - 44, H - 44, FAINT, t=1)

    # ---- masthead
    draw_centered(cv, W // 2, 34, "THE WORLD TODAY", 8, INK, bold=True)
    draw_centered(cv, W // 2, 108,
                  "ONE PAGE - EIGHT STORIES - THE WHOLE DAY'S NEWS", 2, GRAY)
    cv.block(M, 134, CW, 3, INK)

    # date band
    cv.rect(M, 142, CW, 38, INK)
    draw_centered(cv, W // 2, 149, "MONDAY 23 NOVEMBER 2026", 3, WHITE,
                  bold=True)
    cv.block(M, 188, CW, 3, INK)

    # ---- lead story: COP31
    y = 204
    tw = text_width("TOP STORY", 2) + 16
    cv.rect(M, y, tw, 24, RED)
    draw_text(cv, M + 8, y + 4, "TOP STORY", 2, WHITE)
    draw_text(cv, M + tw + 14, y + 4, "CLIMATE SUMMIT", 2, RED)
    y += 34
    y = draw_wrapped(cv, M, y, "COP31 CLIMATE TALKS END WITHOUT A DEAL",
                     5, INK, 690, line_gap=8, bold=True)
    lead_body = (
        "The COP31 climate conference closed with no agreement after the "
        "EU and others rejected a final text with no move away from "
        "fossil fuels. Pacific island nations voiced dismay. The UN "
        "chief warned that the science is not ambiguous."
    )
    draw_wrapped(cv, M, y + 6, lead_body, 2, GRAY, 690, line_gap=5)
    draw_globe(cv, 856, 322, 86, BLUE)
    draw_centered(cv, 856, 420, "NO DEAL AT COP31", 2, BLUE)

    cv.block(M, 456, CW, 2, FAINT)

    # ---- story grid, two columns by three rows
    col_w = (CW - 28) // 2
    lx = M
    rx = M + col_w + 28

    story_box(
        cv, lx, 470, col_w, "UKRAINE WAR", RED,
        "AT LEAST 15 KILLED IN KYIV REGION",
        "Kyiv says Russian attacks killed at least 15. Its sea drones "
        "hit two Russian ships off Libya.")
    story_box(
        cv, rx, 470, col_w, "UNITED STATES", BLUE,
        "HISTORIC HOUSE WIN FOR DEMOCRATS",
        "At least 258 House seats secured - the party's biggest "
        "majority since 1992.")

    cv.block(M, 618, CW, 2, FAINT)
    story_box(
        cv, lx, 632, col_w, "SUDAN", RED,
        "DRONES HIT HOMES AND UN BUILDING",
        "A drone attack in Sudan's capital Khartoum struck homes and "
        "a United Nations building.")
    story_box(
        cv, rx, 632, col_w, "GULF TENSIONS", RED,
        "BAHRAIN: IRAN HIT INDUSTRIAL SITE",
        "Tanker damaged in the Strait of Hormuz. Trump leans to "
        "renewed conflict if no deal by New Year.")

    cv.block(M, 780, CW, 2, FAINT)
    story_box(
        cv, lx, 794, col_w, "INDONESIA", RED,
        "FIRE AT CANDY FACTORY KILLS AT LEAST 3",
        "Dozens are missing after the blaze tore through the factory "
        "in Indonesia.")
    story_box(
        cv, rx, 794, col_w, "SPORT - TENNIS", BLUE,
        "ALCARAZ WINS FIRST ATP FINALS TITLE",
        "Alcaraz beat Zverev to lift the ATP Finals trophy for the "
        "first time.")

    # ---- bright-news band: the Mercury probe
    by = 938
    cv.rect(M, by, CW, 48, GREEN)
    cv.disc(M + 34, by + 24, 13, WHITE)
    cv.disc(M + 30, by + 20, 4, GREEN)
    cv.ellipse_ring(M + 34, by + 24, 21, 7, WHITE, t=2)
    draw_text(cv, M + 58, by + 8, "BRIGHT NEWS", 2, WHITE, bold=True)
    draw_text(cv, M + 58, by + 27,
              "JAPAN-EUROPE PROBE ENTERS ORBIT AROUND MERCURY", 2, WHITE)
    return cv


def main():
    out_dir = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")
    os.makedirs(out_dir, exist_ok=True)
    data = png_bytes(build())
    with open(os.path.join(out_dir, "entry.png"), "wb") as fh:
        fh.write(data)


if __name__ == "__main__":
    main()
