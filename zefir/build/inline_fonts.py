#!/usr/bin/env python3
"""Inline the variable-weight woff2 faces into each source page.

The target platform blocks external hosts, so a linked webfont would fail
silently and fall back to system UI fonts. Each source file in src/ carries
a `/*@FONTS@*/` marker; this script replaces it with @font-face blocks whose
src is a base64 data URI, and writes the result to dist/.

Each family ships as two files (latin + cyrillic), both variable across the
full weight range used on the page, so the browser loads exactly the glyphs
a given run of text needs.

Run: python3 build/inline_fonts.py
"""

import base64
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"
SRC = ROOT / "src"
DIST = ROOT / "dist"

LATIN = (
    "U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,"
    "U+0304,U+0308,U+0329,U+2000-206F,U+20AC,U+2122,U+2191,U+2193,"
    "U+2212,U+2215,U+FEFF,U+FFFD"
)
CYRILLIC = "U+0301,U+0400-045F,U+0490-0491,U+04B0-04B1,U+2116"

# family, file stem, css weight range, css font-style
FACES = [
    ("Cormorant", "Cormorant", "300 700", "normal"),
    ("Cormorant", "CormorantItalic", "400 600", "italic"),
    ("Commissioner", "Commissioner", "300 700", "normal"),
]


def face(family: str, filename: str, weight: str, style: str, unicode_range: str) -> str:
    path = BUILD / filename
    if not path.exists():
        sys.exit(f"missing font file: {path}")
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    return (
        "@font-face{"
        f"font-family:'{family}';"
        f"font-style:{style};"
        f"font-weight:{weight};"
        "font-display:swap;"
        f"unicode-range:{unicode_range};"
        f"src:url(data:font/woff2;base64,{b64}) format('woff2');"
        "}"
    )


def font_css() -> str:
    out = []
    for family, stem, weight, style in FACES:
        out.append(face(family, f"{stem}-latin.woff2", weight, style, LATIN))
        out.append(face(family, f"{stem}-cyrillic.woff2", weight, style, CYRILLIC))
    return "\n".join(out)


def main() -> None:
    css = font_css()
    DIST.mkdir(exist_ok=True)
    pages = sorted(SRC.glob("*.html"))
    if not pages:
        sys.exit("no source pages found in src/")

    marker = "/*@FONTS@*/"
    for page in pages:
        text = page.read_text(encoding="utf-8")
        if marker not in text:
            sys.exit(f"{page.name} has no {marker} marker")
        built = text.replace(marker, css)
        target = DIST / page.name
        target.write_text(built, encoding="utf-8")
        kb = len(built.encode("utf-8")) / 1024
        print(f"{page.name} -> dist/{target.name}  {kb:.0f} KB")

    for page in pages:
        text = page.read_text(encoding="utf-8")
        if "prefers-color-scheme" in text and ":root" not in text:
            print(f"  warning: {page.name} themes without a :root token block")


if __name__ == "__main__":
    main()
