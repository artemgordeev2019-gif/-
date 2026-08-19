#!/usr/bin/env python3
"""Inline the subset woff2 faces and the local artwork into each source page.

Artifact pages are served under a strict CSP that blocks every external host,
so a linked webfont would fail silently and fall back. Each source file in
src/ carries a `/*@FONTS@*/` marker; this script replaces it with a @font-face
block whose src is a base64 data URI, and writes the result to dist/.

The same reasoning covers the images: a page in dist/ must not reach for a
sibling file either, since it is served alone. Every `assets/...` reference in
the source — in markup or in CSS — is rewritten to a data URI on the way out,
which is why src/ can keep readable relative paths.

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

# an assets/ reference, whether it sits in a src="" or inside url()
ASSET_RE = re.compile(r"(?<=[\"'(])(assets/[\w./-]+)")

MIME = {
    ".webp": "image/webp",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".svg": "image/svg+xml",
}


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


def inline_assets(text: str, page_name: str) -> str:
    """Swap every assets/ reference for a data URI of the file itself."""
    cache: dict[str, str] = {}

    def sub(match: re.Match) -> str:
        rel = match.group(1)
        if rel not in cache:
            path = ROOT / rel
            if not path.exists():
                sys.exit(f"{page_name} references a missing asset: {rel}")
            mime = MIME.get(path.suffix.lower())
            if mime is None:
                sys.exit(f"{page_name}: no mime type known for {rel}")
            b64 = base64.b64encode(path.read_bytes()).decode("ascii")
            cache[rel] = f"data:{mime};base64,{b64}"
        return cache[rel]

    return ASSET_RE.sub(sub, text)


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
        built = inline_assets(text.replace(MARKER, css), page.name)
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
