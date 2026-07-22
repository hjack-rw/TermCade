"""Regenerate the README screenshots from the real app, headless.

    python shoot_screens.py

Textual renders a screen to SVG, so a screenshot is reproducible rather than a photograph of
somebody's terminal — rerun it after a UI change and the README stops lying. A fixed seed keeps the
dealt board identical between runs, so a picture that changes means the UI changed.

**Rasterised through chromium, not cairo.** Cairo's toy text API takes one literal family, does no
fallback and no shaping: a CSS list resolves to nothing, variation selectors draw as tofu, and the
astral-plane icons come out blank. A browser does all three — and it is the engine `serve.py` already
ships the game in, so the picture is what a browser player actually sees. The fonts must be INSTALLED
(the browser reads system fonts, not the bundled ones under `engine/termcade/assets/`).

Two phases, and they cannot be interleaved: Textual drives an asyncio loop, and Playwright's sync API
refuses to run inside one. So every SVG is captured first, then rasterised after the loop closes.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

from termcade.ui.app import EngineApp
from xiaolin_showdown.game import build_game
from xiaolin_showdown.screens.start import StartScreen

OUT = Path(__file__).parent / "screenshots"
# Per screen: the board is laid out for 140 wide (what `serve.py` auto-fits the browser to) and
# truncates if shot narrower, while shooting the short screens that tall leaves empty frame.
# Tall enough that NOTHING scrolls: a screen shot shorter than its content grows a scrollbar and the
# picture shows a cut-off menu. Width is the tight part (the board needs 140 or its panels truncate);
# height is cheap, because the crop throws the empty rows away afterwards.
SIZES = {"menu": (96, 50), "board": (140, 34), "lore": (112, 46)}
# Per screen. The board's seed is chosen so neither hand holds a BOOTS Wu: its icon is U+26F8, and a
# browser draws that emoji-class glyph bigger than its cell where a terminal clamps it to the grid —
# so it is the one thing that renders unlike the real game. Dealing around it is honest (any seed is a
# real deal) and needs no glyph hacking.
SEEDS = {"menu": 1234, "board": 2, "lore": 1234}
SCALE = 2  # readable at the width GitHub renders a README image
# A CSS list, which chromium honours glyph by glyph: 0xProto for the body, the symbol font for the
# icons it lacks. The same fallback a real terminal performs.
#
# QUOTED, and that is not cosmetic: a CSS family name may not begin with a digit unless it is quoted,
# so bare `0xProto Nerd Font` is an invalid identifier that the browser silently discards — falling
# through to the next family, which is PROPORTIONAL, and the whole grid comes out unevenly spaced.
FONT = "'0xProto Nerd Font', 'Segoe UI Symbol', monospace"


async def _boot(app, pilot) -> None:
    for _ in range(80):
        if app.screen_stack and isinstance(app.screen, StartScreen):
            return
        await pilot.pause()
    raise AssertionError("start screen never appeared")


async def _capture(name: str, steps) -> Path:
    app = EngineApp(build_game(), data_dir=Path("C:/tmp/termcade-shots"), seed=SEEDS[name])
    async with app.run_test(size=SIZES[name]) as pilot:
        await _boot(app, pilot)
        await steps(pilot)
        await pilot.pause()
        svg = OUT / f"{name}.svg"
        app.save_screenshot(str(svg))
        return svg


def _flatten(png: Path) -> None:
    """Crop to the drawing and put it on black.

    The shot is taken with a TRANSPARENT background, so the alpha channel marks exactly where the
    terminal window is: everything else is the browser letterboxing the SVG inside the viewport.
    Cropping to that is exact — no colour guessing, no margin left over — and compositing onto black
    kills the white that used to show through the frame's rounded corners.

    Cropping to the PANEL borders was tried and is wrong: on a screen that is mostly ASCII wordmark
    the densest bordered thing is the little menu box, so it cuts the logo off.
    """
    image = Image.open(png).convert("RGBA")
    box = image.getbbox()  # the non-transparent region: the window and nothing else
    if box is not None:
        image = image.crop(box)
    backing = Image.new("RGBA", image.size, (0, 0, 0, 255))
    Image.alpha_composite(backing, image).convert("RGB").save(png)


def _rasterise(svgs: list[Path]) -> None:
    with sync_playwright() as play:
        browser = play.chromium.launch()
        page = browser.new_page(device_scale_factor=SCALE)
        for svg in svgs:
            patched = re.sub(
                r"(font-family[:=]\s*\"?)[^;\"}]*", rf"\g<1>{FONT}", svg.read_text(encoding="utf-8")
            )
            svg.write_text(patched, encoding="utf-8")
            # Size the viewport to the SVG's own viewBox so it renders 1:1 instead of being scaled to
            # fit whatever the default window happens to be.
            viewbox = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', patched)
            if viewbox:
                page.set_viewport_size(
                    {"width": int(float(viewbox.group(1))), "height": int(float(viewbox.group(2)))}
                )
            page.goto(svg.as_uri())
            page.wait_for_timeout(200)
            png = svg.with_suffix(".png")
            page.screenshot(path=str(png), omit_background=True)
            svg.unlink()  # the SVG is the intermediate; the README embeds the PNG
            _flatten(png)
            print(f"  {png.name}")
        browser.close()


async def _shots() -> list[Path]:
    async def menu(_pilot):
        return None

    async def board(pilot):
        await pilot.click("#play")
        await pilot.pause()
        await pilot.click("#char-1")
        await pilot.pause()

    async def lore(pilot):
        await pilot.click("#lore")
        await pilot.pause()
        await pilot.press("right")  # off the contents, onto prose

    return [
        await _capture("menu", menu),
        await _capture("board", board),
        await _capture("lore", lore),
    ]


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    print("writing screenshots:")
    _rasterise(asyncio.run(_shots()))
