#!/usr/bin/env python3
"""Inline the subset woff2 faces into each source page.

Artifact pages are served under a strict CSP that blocks every external host,
so a linked webfont would fail silently and fall back. Each source file in
src/ carries a `/*@FONTS@*/` marker; this script replaces it with a @font-face
block whose src is a base64 data URI, and writes the result to dist/.

Run: python3 build/inline_fonts.py
"""

import base64
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"
SRC = ROOT / "src"
DIST = ROOT / "dist"

# family name, file, css weight range, css font-style
FACES = [
    ("Prata", "Prata.woff2", "400", "normal"),
    ("Golos", "Golos.woff2", "400 900", "normal"),
    ("JetMono", "Jet.woff2", "100 800", "normal"),
]

MARKER = "/*@FONTS@*/"


def font_css() -> str:
    out = []
    for family, filename, weight, style in FACES:
        path = BUILD / filename
        if not path.exists():
            sys.exit(f"missing font file: {path}")
        b64 = base64.b64encode(path.read_bytes()).decode("ascii")
        out.append(
            "@font-face{"
            f"font-family:'{family}';"
            f"font-style:{style};"
            f"font-weight:{weight};"
            "font-display:block;"
            f"src:url(data:font/woff2;base64,{b64}) format('woff2');"
            "}"
        )
    return "\n".join(out)


def main() -> None:
    css = font_css()
    DIST.mkdir(exist_ok=True)
    pages = sorted(SRC.glob("*.html"))
    if not pages:
        sys.exit("no source pages found in src/")

    for page in pages:
        text = page.read_text(encoding="utf-8")
        if MARKER not in text:
            sys.exit(f"{page.name} has no {MARKER} marker")
        built = text.replace(MARKER, css)
        target = DIST / page.name
        target.write_text(built, encoding="utf-8")
        kb = len(built.encode("utf-8")) / 1024
        print(f"{page.name} -> dist/{target.name}  {kb:.0f} KB")

    # Guard against the classic theming bug: a color defined only inside a
    # media query or [data-theme] block never applies in the unstamped state.
    for page in pages:
        text = page.read_text(encoding="utf-8")
        if "prefers-color-scheme" in text and ":root" not in text:
            print(f"  warning: {page.name} themes without a :root token block")


if __name__ == "__main__":
    main()
