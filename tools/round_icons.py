"""Cut transparent rounded corners into the icon PNGs.

The PNGs are rasterised from app/static/img/favicon.svg with qlmanage, which
flattens onto a white page. The rounded corners therefore come out as opaque
white rather than clear, and on a dark tab bar that reads as a pale frame
around the mark. This puts the corners back the way the SVG means them.

Only the icons a browser draws as they are get rounded. The ones an operating
system masks itself stay square and full bleed, because a home screen icon
that is already round gets rounded a second time and loses its edge.

    python3 tools/round_icons.py
"""

import math
import os
import struct
import sys
import zlib

HIER = os.path.dirname(os.path.abspath(__file__))
BILDER = os.path.join(os.path.dirname(HIER), "app", "static", "img")

# The radius the SVG uses, as a share of the side, so every size matches.
ANTEIL = 112 / 512

# Drawn as they are, so they carry their own rounding.
RUNDEN = ["icon-192.png"]
# Masked by the system, so they stay square.
ECKIG = ["icon-180.png", "icon-512.png", "icon-512-maskable.png"]


def lies(pfad):
    roh = open(pfad, "rb").read()
    if roh[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"{pfad} is not a PNG")
    i, daten, kopf = 8, b"", None
    while i < len(roh):
        n = struct.unpack(">I", roh[i:i + 4])[0]
        art = roh[i + 4:i + 8]
        if art == b"IHDR":
            kopf = struct.unpack(">IIBBBBB", roh[i + 8:i + 8 + n])
        elif art == b"IDAT":
            daten += roh[i + 8:i + 8 + n]
        i += 12 + n
    breite, hoehe, tiefe, farbe = kopf[0], kopf[1], kopf[2], kopf[3]
    if tiefe != 8 or farbe != 6:
        raise ValueError(f"{pfad} is not 8 bit RGBA")
    roh, schritt = zlib.decompress(daten), breite * 4
    zeilen, vorher, pos = [], bytearray(schritt), 0
    for _ in range(hoehe):
        f = roh[pos]
        pos += 1
        z = bytearray(roh[pos:pos + schritt])
        pos += schritt
        for x in range(schritt):
            a = z[x - 4] if x >= 4 else 0
            b = vorher[x]
            c = vorher[x - 4] if x >= 4 else 0
            if f == 1:
                z[x] = (z[x] + a) & 255
            elif f == 2:
                z[x] = (z[x] + b) & 255
            elif f == 3:
                z[x] = (z[x] + (a + b) // 2) & 255
            elif f == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                z[x] = (z[x] + (a if pa <= pb and pa <= pc
                                else (b if pb <= pc else c))) & 255
        zeilen.append(z)
        vorher = z
    return breite, hoehe, zeilen


def schreib(pfad, breite, hoehe, zeilen):
    roh = b"".join(b"\x00" + bytes(z) for z in zeilen)

    def stueck(art, inhalt):
        return (struct.pack(">I", len(inhalt)) + art + inhalt
                + struct.pack(">I", zlib.crc32(art + inhalt) & 0xFFFFFFFF))

    open(pfad, "wb").write(
        b"\x89PNG\r\n\x1a\n"
        + stueck(b"IHDR", struct.pack(">IIBBBBB", breite, hoehe, 8, 6, 0, 0, 0))
        + stueck(b"IDAT", zlib.compress(roh, 9))
        + stueck(b"IEND", b""))


def deckung(x, y, breite, hoehe, radius):
    """How much of this pixel is inside the rounded rectangle, 0 to 1.

    Sampled over a four by four grid inside the pixel rather than by its
    middle alone, so the curve comes out smooth instead of stepped.
    """
    treffer, schritte = 0, 4
    for sy in range(schritte):
        for sx in range(schritte):
            px = x + (sx + 0.5) / schritte
            py = y + (sy + 0.5) / schritte
            # The nearest corner circle's middle, if we are in a corner at all.
            mx = radius if px < radius else (breite - radius if px > breite - radius else px)
            my = radius if py < radius else (hoehe - radius if py > hoehe - radius else py)
            if math.hypot(px - mx, py - my) <= radius:
                treffer += 1
    return treffer / (schritte * schritte)


def runde(pfad):
    breite, hoehe, zeilen = lies(pfad)
    radius = ANTEIL * breite
    rand = int(math.ceil(radius)) + 1
    geaendert = 0
    for y in list(range(rand)) + list(range(hoehe - rand, hoehe)):
        for x in list(range(rand)) + list(range(breite - rand, breite)):
            d = deckung(x, y, breite, hoehe, radius)
            if d < 1:
                alt = zeilen[y][x * 4 + 3]
                zeilen[y][x * 4 + 3] = int(round(alt * d))
                geaendert += 1
    schreib(pfad, breite, hoehe, zeilen)
    return geaendert


def main():
    for name in RUNDEN:
        pfad = os.path.join(BILDER, name)
        if not os.path.exists(pfad):
            print(f"  {name}: not here", file=sys.stderr)
            continue
        print(f"  {name}: {runde(pfad)} corner pixels made clear")
    for name in ECKIG:
        print(f"  {name}: left square, the system masks it")


if __name__ == "__main__":
    main()
