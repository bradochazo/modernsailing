#!/usr/bin/env python3
"""Draws the little animated GIFs used by the page's "Party" mode (needs Pillow).

Everything is drawn from scratch here (no third-party art). Run:
    python3 scripts/make_party_gifs.py            # writes site/party/*.gif
The generated files are committed, so the site build does not need Pillow.
"""
import math
import os
import sys

from PIL import Image, ImageDraw

KEY = (255, 0, 255)          # transparent background key; never used for artwork
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "site", "party")

BLACK, WHITE = (20, 20, 20), (255, 255, 255)
YELLOW, ORANGE, DORANGE = (255, 214, 0), (255, 140, 0), (190, 100, 0)
GREEN, DGREEN = (0, 190, 60), (0, 120, 40)
BROWN, DBROWN = (160, 100, 40), (110, 65, 20)
RED = (230, 30, 60)


def to_gif(frames, name, scale, delay_ms, transparent=True):
    """Quantize every frame to ONE shared exact palette so colours never shift."""
    colors = []
    for f in frames:
        for _, c in f.getcolors(maxcolors=100000):
            if c not in colors:
                colors.append(c)
    if len(colors) > 256:
        sys.exit(f"{name}: {len(colors)} colours (max 256)")
    pal = Image.new("P", (1, 1))
    flat = [v for c in colors for v in c] + [0] * (768 - 3 * len(colors))
    pal.putpalette(flat)
    out = []
    for f in frames:
        f = f.resize((f.width * scale, f.height * scale), Image.NEAREST)
        out.append(f.quantize(palette=pal, dither=Image.Dither.NONE))
    kw = dict(save_all=True, append_images=out[1:], duration=delay_ms, loop=0, disposal=2)
    if transparent:
        kw["transparency"] = colors.index(KEY)
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, name)
    out[0].save(path, **kw)
    print(f"{name}: {len(frames)} frames, {os.path.getsize(path)} bytes")


def pineapple(n=8):
    W, H = 40, 52
    frames = []
    for i in range(n):
        t = 2 * math.pi * i / n
        sway = 12 * math.sin(t)
        hop = round(3 * abs(math.sin(t)))
        im = Image.new("RGB", (W, H), KEY)
        d = ImageDraw.Draw(im)
        cx, cy = 20, 31
        # leaves
        for dx, top in ((-9, 8), (-4, 3), (0, 0), (4, 3), (9, 8)):
            d.polygon([(cx - 4, 19), (cx + dx, top), (cx + 4, 19)], fill=GREEN, outline=DGREEN)
        # body
        d.ellipse([cx - 11, cy - 13, cx + 11, cy + 13], fill=YELLOW, outline=DORANGE)
        hatch = Image.new("RGB", (W, H), KEY)       # diamond cross-hatch, clipped to the body
        hd = ImageDraw.Draw(hatch)
        for k in range(-24, 25, 6):
            hd.line([(cx - 11, cy + k), (cx + 11, cy + k + 22)], fill=ORANGE)
            hd.line([(cx - 11, cy + k), (cx + 11, cy + k - 22)], fill=ORANGE)
        mask = Image.new("1", (W, H), 0)
        ImageDraw.Draw(mask).ellipse([cx - 10, cy - 12, cx + 10, cy + 12], fill=1)
        im.paste(hatch, (0, 0), mask)
        d.ellipse([cx - 11, cy - 13, cx + 11, cy + 13], outline=DORANGE)
        # sunglasses + grin
        d.rectangle([cx - 9, cy - 8, cx - 1, cy - 2], fill=BLACK)
        d.rectangle([cx + 1, cy - 8, cx + 9, cy - 2], fill=BLACK)
        d.line([(cx - 1, cy - 6), (cx + 1, cy - 6)], fill=BLACK)
        d.point([(cx - 7, cy - 7), (cx + 3, cy - 7)], fill=WHITE)
        d.arc([cx - 6, cy - 1, cx + 6, cy + 8], 20, 160, fill=RED, width=2)
        # arms and feet, alternating
        up = i % 2 == 0
        d.line([(cx - 11, cy), (cx - 17, cy - 8 if up else cy + 4)], fill=DORANGE, width=2)
        d.line([(cx + 11, cy), (cx + 17, cy + 4 if up else cy - 8)], fill=DORANGE, width=2)
        d.line([(cx - 5, cy + 13), (cx - 7, cy + 18)], fill=DORANGE, width=2)
        d.line([(cx + 5, cy + 13), (cx + 7, cy + 18)], fill=DORANGE, width=2)
        im = im.rotate(sway, resample=Image.NEAREST, fillcolor=KEY, center=(cx, H - 2))
        shifted = Image.new("RGB", (W, H), KEY)
        shifted.paste(im, (0, -hop))
        frames.append(shifted)
    to_gif(frames, "pineapple.gif", 2, 90)


def palm(n=8):
    W, H = 44, 56
    frames = []
    for i in range(n):
        t = 2 * math.pi * i / n
        im = Image.new("RGB", (W, H), KEY)
        d = ImageDraw.Draw(im)
        sway = 3 * math.sin(t)
        # curved trunk
        pts = [(18 + 8 * (s / 10) ** 2 + sway * (s / 10) ** 1.5 * -1 * -1, 54 - s * 4.4) for s in range(11)]
        for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
            d.line([(x1, y1), (x2, y2)], fill=BROWN, width=5)
        for (x, y) in pts[1::2]:
            d.line([(x - 3, y), (x + 3, y - 1)], fill=DBROWN)
        cx, cy = pts[-1]
        # fronds
        for k in range(7):
            a = math.radians(-160 + k * 50 + 8 * math.sin(t + k))
            ex, ey = cx + 18 * math.cos(a), cy + 10 * math.sin(a) + 4
            mx, my = cx + 11 * math.cos(a), cy + 11 * math.sin(a) - 5
            d.line([(cx, cy), (mx, my), (ex, ey)], fill=GREEN, width=4)
            d.line([(mx, my), (ex, ey + 2)], fill=DGREEN, width=1)
        d.ellipse([cx - 4, cy - 1, cx + 1, cy + 4], fill=DBROWN)
        d.ellipse([cx + 1, cy, cx + 6, cy + 5], fill=BROWN)
        frames.append(im)
    to_gif(frames, "palm.gif", 2, 110)


def sun(n=8):
    W = H = 44
    frames = []
    for i in range(n):
        im = Image.new("RGB", (W, H), KEY)
        d = ImageDraw.Draw(im)
        c = 22
        for k in range(12):
            a = math.radians(k * 30 + i * (30 / n))
            r1, r2 = 13, 21 if k % 2 == 0 else 18
            d.line([(c + r1 * math.cos(a), c + r1 * math.sin(a)),
                    (c + r2 * math.cos(a), c + r2 * math.sin(a))], fill=ORANGE, width=3)
        d.ellipse([c - 12, c - 12, c + 12, c + 12], fill=YELLOW, outline=ORANGE)
        d.rectangle([c - 9, c - 5, c - 2, c + 1], fill=BLACK)
        d.rectangle([c + 2, c - 5, c + 9, c + 1], fill=BLACK)
        d.line([(c - 2, c - 3), (c + 2, c - 3)], fill=BLACK)
        d.arc([c - 6, c, c + 6, c + 9], 20, 160, fill=RED, width=2)
        frames.append(im)
    to_gif(frames, "sun.gif", 2, 80)


def wave(n=8, period=40, width=120, height=12):
    frames = []
    deep, mid, light = (0, 110, 200), (0, 190, 210), (120, 240, 235)
    for i in range(n):
        ph = i * period / n
        im = Image.new("RGB", (width, height), KEY)
        d = ImageDraw.Draw(im)
        for x in range(width):
            y = 4 + 2.5 * math.sin(2 * math.pi * (x + ph) / period)
            top = int(round(y))
            d.line([(x, top), (x, height)], fill=mid)
            d.line([(x, top + 4), (x, height)], fill=deep)
            d.point((x, top), fill=WHITE)
            d.point((x, top + 1), fill=light)
        frames.append(im)
    to_gif(frames, "wave.gif", 2, 100)


def flamingo(n=6):
    W, H = 36, 56
    PINK, DPINK = (255, 105, 180), (220, 60, 140)
    frames = []
    for i in range(n):
        t = 2 * math.pi * i / n
        nod = 2 * math.sin(t)
        im = Image.new("RGB", (W, H), KEY)
        d = ImageDraw.Draw(im)
        d.line([(16, 36), (16, 54)], fill=DPINK, width=2)          # leg
        d.line([(16, 54), (21, 54)], fill=DPINK, width=2)
        d.ellipse([6, 26, 28, 42], fill=PINK, outline=DPINK)        # body
        d.arc([8, 29, 22, 40], 180, 300, fill=DPINK)                # wing
        neck = [(24, 30), (28, 22 + nod), (24, 14 + nod), (21, 9 + nod)]
        d.line(neck, fill=PINK, width=4)
        d.ellipse([17, 5 + nod, 25, 12 + nod], fill=PINK, outline=DPINK)
        d.polygon([(17, 8 + nod), (11, 12 + nod), (17, 11 + nod)], fill=BLACK)     # beak
        d.rectangle([19, 6 + nod, 23, 8 + nod], fill=BLACK)                        # shades
        frames.append(im)
    to_gif(frames, "flamingo.gif", 2, 160)


if __name__ == "__main__":
    for fn in (pineapple, palm, sun, wave, flamingo):
        fn()
