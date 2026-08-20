#!/usr/bin/env python3
"""Render build/og-image.png — the 1200x630 card shown when the site is shared.

og:image has to be a real fetchable file at an absolute URL: crawlers and chat
previews won't take a data URI, which is why this one asset lives outside the
otherwise fully-inlined page.

Rendered through a headless browser rather than drawn with an image library so
it reuses the site's own fonts and the same logo SVG, and therefore can't drift
from the brand.

Run: python3 build/make_og_image.py   (needs playwright + the chromium at
/opt/pw-browsers/chromium; only needs re-running if the logo or palette change)
"""

import asyncio
import pathlib
import sys

BUILD = pathlib.Path(__file__).resolve().parent
OUT = BUILD / "og-image.png"

# Kept in sync with :root in src/index.html by hand — this file renders once and
# is committed, so it can't read the tokens at build time.
CARD = """
<!doctype html><meta charset="utf-8">
<style>
  {fonts}
  *{{ margin:0; box-sizing:border-box; }}
  body{{ width:1200px; height:630px; overflow:hidden; }}
  .card{{
    position:relative; width:1200px; height:630px;
    display:flex; flex-direction:column; align-items:center; justify-content:center;
    background:
      radial-gradient(60% 70% at 18% 8%, rgba(139,79,214,.42), transparent 62%),
      radial-gradient(62% 72% at 88% 96%, rgba(122,22,56,.5), transparent 64%),
      radial-gradient(90% 80% at 50% 45%, #1C0F26, #12081A 74%);
    color:#F5EEE9;
  }}
  .mark{{ width:132px; height:132px; }}
  .name{{
    font-family:Cormorant, Georgia, serif; font-weight:500; font-size:110px;
    line-height:1; letter-spacing:.18em; text-indent:.18em; margin-top:14px;
  }}
  .tag{{
    font-family:Commissioner, system-ui, sans-serif; font-weight:500; font-size:20px;
    letter-spacing:.34em; text-indent:.34em; text-transform:uppercase;
    color:#C7B6D4; margin-top:26px;
  }}
  .rule{{ width:132px; height:1px; background:rgba(216,178,107,.5); margin-top:34px; }}
</style>
<div class="card">
  <svg class="mark" viewBox="0 0 100 100">
    <g fill="none" stroke="currentColor" stroke-width="1.1" stroke-linecap="round" opacity=".8">
      <path d="M58 13 C34 13, 21 28, 21 48 C21 66, 33 81, 52 86 C60 88, 66 85, 64 80 C63 77, 59 77, 58 80"/>
      <path d="M42 87 C66 87, 79 72, 79 52 C79 34, 67 19, 48 14 C40 12, 34 15, 36 20 C37 23, 41 23, 42 20"/>
    </g>
    <text x="50" y="69" text-anchor="middle" font-family="Cormorant, Georgia, serif"
          font-size="56" font-weight="500" fill="currentColor">Z</text>
    <path d="M82 26 l1.5 4 4 1.5 -4 1.5 -1.5 4 -1.5 -4 -4 -1.5 4 -1.5Z" fill="#D8B26B"/>
    <path d="M18 66 l2 5.3 5.3 2 -5.3 2 -2 5.3 -2 -5.3 -5.3 -2 5.3 -2Z" fill="#D8B26B"/>
  </svg>
  <div class="name">Zefir</div>
  <div class="tag">Студия маникюра и педикюра</div>
  <div class="rule"></div>
</div>
"""


async def render(html: str) -> None:
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path="/opt/pw-browsers/chromium")
        page = await browser.new_page(viewport={"width": 1200, "height": 630})
        await page.set_content(html)
        await page.wait_for_timeout(600)  # let the embedded faces settle
        await page.screenshot(path=str(OUT))
        await browser.close()


def main() -> None:
    sys.path.insert(0, str(BUILD))
    import build  # reuse the same @font-face data-URI blocks the page uses

    asyncio.run(render(CARD.format(fonts=build.font_css())))
    print(f"og-image.png -> {OUT.stat().st_size / 1024:.0f} KB (1200x630)")


if __name__ == "__main__":
    main()
