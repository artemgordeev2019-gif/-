#!/usr/bin/env python3
"""Build the self-contained page: inline fonts, then inline photos.

The target platform blocks external hosts, so every asset has to travel
inside the HTML itself. This script does two passes over each file in
src/ and writes the result to dist/:

1. Fonts — replaces the `/*@FONTS@*/` marker with @font-face blocks whose
   src is a base64 data URI. Each family ships as two variable files
   (latin + cyrillic) so the browser downloads only the glyphs a given
   run of text needs.

2. Photos — fills the image slots marked up in the HTML from whatever
   files are present in references/. Slots with no matching file keep
   their placeholder, so the page is always valid and shippable, whether
   zero photos or all of them are available.

Slot markers (see references/README.md for the file names):

    <!--@IMG:slug|alt text-->  <placeholder markup>  <!--@/IMG-->

        With references/<slug>.<ext> present, the whole block becomes
        <img class="<classes from the placeholder>" src="data:..."
        alt="<alt text>">. Without it, the placeholder is kept as-is.

    <!--@IFIMG:slug-->A<!--@ELSE-->B<!--@/IFIMG-->

        Emits A when the photo exists, B otherwise. Used for captions
        that only make sense while a slot is still a placeholder.

Run: python3 build/build.py
"""

import base64
import html
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"
SRC = ROOT / "src"
DIST = ROOT / "dist"
REFS = ROOT / "references"

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

# Browsers get the type from the data URI, not the file name, so the
# extension has to be mapped rather than pasted through.
MIME = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".avif": "image/avif",
    ".gif": "image/gif",
}


# ── fonts ────────────────────────────────────────────────────────────

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


# ── photos ───────────────────────────────────────────────────────────

def find_photo(slug: str) -> pathlib.Path | None:
    """First file in references/ named <slug>.<known image extension>."""
    if not REFS.is_dir():
        return None
    for path in sorted(REFS.iterdir()):
        if path.is_file() and path.stem == slug and path.suffix.lower() in MIME:
            return path
    return None


def data_uri(path: pathlib.Path) -> str:
    mime = MIME[path.suffix.lower()]
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"


IMG_BLOCK = re.compile(
    r"<!--@IMG:(?P<slug>[\w-]+)\|(?P<alt>[^>]*?)-->(?P<placeholder>.*?)<!--@/IMG-->",
    re.S,
)
IFIMG_BLOCK = re.compile(
    r"<!--@IFIMG:(?P<slug>[\w-]+)-->(?P<yes>.*?)<!--@ELSE-->(?P<no>.*?)<!--@/IFIMG-->",
    re.S,
)
CLASS_ATTR = re.compile(r'class="([^"]*)"')


def inline_photos(text: str, report: list[str]) -> str:
    def swap_img(m: re.Match) -> str:
        slug = m.group("slug")
        path = find_photo(slug)
        if path is None:
            report.append(f"  {slug:14s} — placeholder (no references/{slug}.*)")
            return m.group("placeholder")

        # Reuse the placeholder's classes so the image lands in the same
        # slot with the same layout, sizing and rounding.
        cls = CLASS_ATTR.search(m.group("placeholder"))
        cls = cls.group(1) if cls else ""
        alt = html.escape(m.group("alt"), quote=True)
        kb = path.stat().st_size / 1024
        report.append(f"  {slug:14s} — {path.name} ({kb:.0f} KB)")
        return (
            f'<img class="{cls}" src="{data_uri(path)}" alt="{alt}" loading="lazy" decoding="async">'
        )

    def swap_if(m: re.Match) -> str:
        return m.group("yes") if find_photo(m.group("slug")) else m.group("no")

    text = IFIMG_BLOCK.sub(swap_if, text)
    return IMG_BLOCK.sub(swap_img, text)


# ── main ─────────────────────────────────────────────────────────────

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

        report: list[str] = []
        built = inline_photos(text.replace(marker, css), report)

        target = DIST / page.name
        target.write_text(built, encoding="utf-8")
        kb = len(built.encode("utf-8")) / 1024
        print(f"{page.name} -> dist/{target.name}  {kb:.0f} KB")
        for line in report:
            print(line)

        if "prefers-color-scheme" in text and ":root" not in text:
            print(f"  warning: {page.name} themes without a :root token block")


if __name__ == "__main__":
    main()
