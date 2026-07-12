"""Draw ``engine/termcade/assets/termcade.ico`` — the cabinet, mid-blast, as a Windows icon.

    pip install -e ".[build]"
    python make_icon.py

The cabinet (``assets/cabinet.png``) is a transparent PNG. Behind it goes a white pixel halo,
generated here rather than stored: it is drawn on a coarse grid and scaled up with NEAREST, which
is what keeps its edge blocky instead of smoothly antialiased.

Two things the icon has to survive, both of which drove the design:

* **16x16.** The cabinet alone is tall and narrow, so it never fills the square and sinks into a
  dark taskbar. The halo fills the corners and puts a hard white edge behind it at every size.
* **Any backdrop.** The background is transparent, not black — a black-backed icon shows up as a
  black tile on a light taskbar.

Only re-run this to change the art; the ``.ico`` is committed, since PyInstaller needs a file.
"""

from __future__ import annotations

import math
import random
import struct
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).parent
CABINET = ROOT / "engine" / "termcade" / "assets" / "cabinet.png"
OUT = ROOT / "engine" / "termcade" / "assets" / "termcade.ico"

# Slightly see-through, so the cloud sits behind the cabinet as atmosphere rather than as a solid
# white cut-out. Only slightly: at 16x16 the halo is what separates the machine from the taskbar,
# and a truly translucent one stops doing that job.
SMOKE_ALPHA = 0xDC
WHITE = (0xFF, 0xFF, 0xFF, SMOKE_ALPHA)
LILAC = (0xC9, 0xBF, 0xFF, SMOKE_ALPHA)  # a shaded rim, so the halo keeps an edge on a light backdrop
CLEAR = (0, 0, 0, 0)

GRID = 64  # the halo's pixel grid, scaled up whole — the source of its blockiness
LOBES = 6
# Both of these are deliberately near the edge of the canvas. An icon that leaves a wide margin
# wastes the only pixels it gets: at 16x16 the subject was landing about six pixels tall and going
# to mush. Fill the square.
BURST_SCALE = 0.98
CABINET_HEIGHT = 0.84  # of the icon's height, after the legs are cut
LEGS_CROP = 0.24  # how much of the base to amputate — through the legs and into the lower box
FADE = 0.20  # of the cabinet's height: the bottom band that dithers away into the cloud
# How far the machine is lifted off the canvas floor. It has to be enough that the crumbling blocks
# land *inside* the cloud: any lower and the speckle trails out beneath the smoke, into thin air,
# which gives the game away — the cabinet has to end in the blast, not fall out the bottom of it.
SINK = 0.13

# How ragged the crumble is. JITTER knocks each ordered threshold about, so the dissolve stops
# looking like a woven texture; STRAY_CHANCE flakes the odd block off above the band, reaching
# STRAY_REACH blocks higher, so the decay has no clean upper edge.
JITTER = 5.0
STRAY_CHANCE = 0.05
STRAY_REACH = 1  # one block, no more: reach further up and the strays punch holes in the control
# panel, which stops reading as decay and starts reading as a corrupt image

SIZES = (16, 32, 48, 64, 128, 256)
MASTER = 512  # composed once at this size, then downsampled per icon size


def halo(size: int) -> Image.Image:
    """Rounded lobes on a coarse grid. The floor under the cosine keeps the body solid, so the
    lobes never break off into loose petals."""
    cells = Image.new("RGBA", (GRID, GRID), CLEAR)
    pixel = cells.load()
    centre = (GRID - 1) / 2

    for y in range(GRID):
        for x in range(GRID):
            dx, dy = x - centre, y - centre
            radius = math.hypot(dx, dy)
            angle = math.atan2(dy, dx)
            spike = (20 + 11 * (0.4 + 0.6 * abs(math.cos(LOBES * angle)))) * BURST_SCALE
            if radius <= spike:
                pixel[x, y] = WHITE if radius <= spike - 3 else LILAC

    return cells.resize((size, size), Image.NEAREST)


# An ordered (Bayer) matrix: thresholds spread evenly through 0..15, so raising the cut-off drops
# blocks out in a scattered pattern rather than in rows.
BAYER = (
    (0, 8, 2, 10),
    (12, 4, 14, 6),
    (3, 11, 1, 9),
    (15, 7, 13, 5),
)


def dissolve(cabinet: Image.Image, block: int) -> None:
    """Dither the cabinet's bottom band away into chunky blocks, in place.

    A smooth alpha ramp is the one thing this art cannot have: a soft gradient is an anti-pixel
    gesture, and against a hard-edged cloud it reads as a mistake. So a block is either fully there
    or fully gone — the machine crumbles into pixels the same size as the cloud's, and the eye reads
    the two as made of the same stuff.

    The ordered matrix alone is too tidy, though; a bare Bayer ramp reads as a *texture*, a neat
    diagonal weave that nothing in the world dissolves into. So each threshold is knocked about by a
    fixed amount of noise, and a few blocks flake off above the band entirely — the machine is being
    eaten unevenly, the way it would be.
    """
    noise = random.Random(0xCAB1DE)  # fixed: the art must not change from one build to the next
    alpha = cabinet.getchannel("A")
    pixel = alpha.load()
    band = max(1, int(cabinet.height * FADE))
    top = cabinet.height - band

    def erase(bx: int, by: int) -> None:
        for y in range(by * block, min((by + 1) * block, cabinet.height)):
            for x in range(bx * block, min((bx + 1) * block, cabinet.width)):
                pixel[x, y] = 0

    for by in range(max(0, top // block - STRAY_REACH), (cabinet.height + block - 1) // block):
        for bx in range((cabinet.width + block - 1) // block):
            depth = (by * block + block / 2 - top) / band  # 0 at the band's top, 1 at the bottom
            if depth <= 0:
                # Above the crumbling band: mostly solid, but let the odd pixel flake off early so
                # the edge of the decay isn't a clean horizontal line.
                if noise.random() < STRAY_CHANCE:
                    erase(bx, by)
                continue
            threshold = BAYER[by % 4][bx % 4] + noise.uniform(-JITTER, JITTER)
            if depth * 16 > threshold:
                erase(bx, by)

    cabinet.putalpha(alpha)


def compose(size: int = MASTER) -> Image.Image:
    cabinet = Image.open(CABINET).convert("RGBA")
    cabinet = cabinet.crop(cabinet.getbbox())

    # Cut the legs off, up into the lower box. A cabinet with feet is standing on something, and
    # there is nothing there to stand on — it reads as pasted onto the cloud rather than rising
    # out of it.
    cabinet = cabinet.crop((0, 0, cabinet.width, int(cabinet.height * (1 - LEGS_CROP))))

    height = int(size * CABINET_HEIGHT)
    width = max(1, round(cabinet.width * height / cabinet.height))
    cabinet = cabinet.resize((width, height), Image.LANCZOS)
    # The cloud's pixels are `size // GRID` across; the dissolve uses the same block, so the machine
    # crumbles into the very pixels the smoke is made of.
    dissolve(cabinet, max(1, size // GRID))

    art = Image.new("RGBA", (size, size), CLEAR)
    art.alpha_composite(halo(size))
    # Sunk past the floor, so the faded edge sits deep in the cloud rather than below it.
    art.alpha_composite(cabinet, ((size - width) // 2, size - height - int(size * SINK)))
    return art


def bmp(image: Image.Image) -> bytes:
    """One icon image as a BMP: a DIB header, BGRA rows bottom-up, then the AND mask.

    The header's height is doubled — the format expects the colour rows and a 1-bit mask stacked.
    The mask is left all-zero (fully opaque) because a 32-bit image carries its own alpha, which
    Windows reads instead; it still refuses an image with no mask at all.
    """
    size = image.width
    header = struct.pack("<IiiHHIIiiII", 40, size, size * 2, 1, 32, 0, 0, 0, 0, 0, 0)

    colour = bytearray()
    for y in reversed(range(size)):  # bottom-up
        for x in range(size):
            r, g, b, a = image.getpixel((x, y))
            colour += bytes((b, g, r, a))  # BGRA

    mask_stride = ((size + 31) // 32) * 4  # each mask row pads to 4 bytes
    return header + bytes(colour) + bytes(mask_stride * size)


def ico(images: list[Image.Image]) -> bytes:
    """Pack the images into an ICO: a directory of fixed-width entries, then the images."""
    blobs = [bmp(image) for image in images]
    offset = 6 + 16 * len(blobs)  # past the header and the whole directory

    directory = bytearray(struct.pack("<HHH", 0, 1, len(blobs)))
    for image, blob in zip(images, blobs):
        side = image.width if image.width < 256 else 0  # 256 is written as 0 — a byte can't hold it
        directory += struct.pack("<BBBBHHII", side, side, 0, 0, 1, 32, len(blob), offset)
        offset += len(blob)

    return bytes(directory) + b"".join(blobs)


def main() -> None:
    master = compose()
    images = [master.resize((size, size), Image.LANCZOS) for size in SIZES]
    OUT.write_bytes(ico(images))
    print(f"[OK] {OUT} — {', '.join(f'{s}x{s}' for s in SIZES)} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
