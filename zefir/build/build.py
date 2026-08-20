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
import datetime
import html
import json
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


def image_size(path: pathlib.Path) -> tuple[int, int] | None:
    """(width, height) read from the file header, or None if unreadable.

    Emitting width/height on every <img> is what stops the page reflowing as
    photos decode (CLS). Parsed by hand from the header bytes rather than with
    Pillow so the build keeps its only requirement as "python3".
    """
    try:
        data = path.read_bytes()
    except OSError:
        return None

    try:
        if data[:8] == b"\x89PNG\r\n\x1a\n":
            return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")

        if data[:3] == b"\xff\xd8\xff":  # JPEG: walk the segments to a SOF marker
            i = 2
            while i + 9 < len(data):
                if data[i] != 0xFF:
                    i += 1
                    continue
                marker = data[i + 1]
                # SOF0..SOF15, minus the non-frame markers in that range
                if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
                    return (int.from_bytes(data[i + 7:i + 9], "big"),
                            int.from_bytes(data[i + 5:i + 7], "big"))
                i += 2 + int.from_bytes(data[i + 2:i + 4], "big")
            return None

        if data[:6] in (b"GIF87a", b"GIF89a"):
            return (int.from_bytes(data[6:8], "little"),
                    int.from_bytes(data[8:10], "little"))

        if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            fmt = data[12:16]
            if fmt == b"VP8X":
                return (int.from_bytes(data[24:27], "little") + 1,
                        int.from_bytes(data[27:30], "little") + 1)
            if fmt == b"VP8 ":
                return (int.from_bytes(data[26:28], "little") & 0x3FFF,
                        int.from_bytes(data[28:30], "little") & 0x3FFF)
            if fmt == b"VP8L":
                bits = int.from_bytes(data[21:25], "little")
                return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
            return None
    except (IndexError, ValueError):
        return None
    return None  # AVIF and anything else: skip rather than guess


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

        size = image_size(path)
        dims = f' width="{size[0]}" height="{size[1]}"' if size else ""
        note = f"{size[0]}x{size[1]}" if size else "no dimensions"
        report.append(f"  {slug:14s} — {path.name} ({kb:.0f} KB, {note})")

        # The hero is the LCP element, so it loads eagerly and gets decode
        # priority; everything below the fold stays lazy.
        eager = slug == "hero"
        loading = 'loading="eager" fetchpriority="high"' if eager else 'loading="lazy"'
        return (
            f'<img class="{cls}" src="{data_uri(path)}" alt="{alt}"{dims} '
            f'{loading} decoding="async">'
        )

    def swap_if(m: re.Match) -> str:
        return m.group("yes") if find_photo(m.group("slug")) else m.group("no")

    text = IFIMG_BLOCK.sub(swap_if, text)
    return IMG_BLOCK.sub(swap_img, text)


# ── SEO files ────────────────────────────────────────────────────────

SEO_MARKER = "<!--@SEO-->"
OG_IMAGE = "og-image.png"


def parse_site_url(argv: list[str]) -> str | None:
    """--site-url https://example.com  (or --site-url=https://example.com)."""
    for i, arg in enumerate(argv):
        value = None
        if arg == "--site-url" and i + 1 < len(argv):
            value = argv[i + 1]
        elif arg.startswith("--site-url="):
            value = arg.split("=", 1)[1]
        if value:
            if not value.startswith(("http://", "https://")):
                sys.exit(f"--site-url must include the scheme, got: {value}")
            return value.rstrip("/")
    return None


def seo_head(site_url: str | None) -> str:
    """Head tags that only make sense once the real origin is known."""
    if not site_url:
        # A canonical aimed at a guessed host would actively point Google at
        # the wrong URL, so emit nothing and downgrade the card instead.
        return '<meta name="twitter:card" content="summary">'
    return "\n".join([
        f'<link rel="canonical" href="{site_url}/">',
        f'<meta property="og:url" content="{site_url}/">',
        f'<meta property="og:image" content="{site_url}/{OG_IMAGE}">',
        '<meta property="og:image:width" content="1200">',
        '<meta property="og:image:height" content="630">',
        '<meta property="og:image:alt" content="Zefir — студия маникюра и педикюра">',
        '<meta name="twitter:card" content="summary_large_image">',
        f'<meta name="twitter:image" content="{site_url}/{OG_IMAGE}">',
    ])


JSONLD_MARKER = "<!--@JSONLD-->"

TITLE = "Zefir — студия маникюра и педикюра"
SAME_AS = [
    "https://www.instagram.com/zefir.manicure/",
    "https://www.instagram.com/zefir.beautystudio/",
]


def json_ld(site_url: str | None) -> str:
    """BeautySalon (a specific LocalBusiness subtype, per docs/08) plus the
    WebPage baseline docs/08 asks for on any page.

    address/telephone/openingHours are 'strongly expected' by docs/08 and are
    the core of local SEO — they are deliberately absent because the studio
    hasn't supplied them. NAP has to match the Google Business Profile
    character-for-character, so inventing plausible values would be worse than
    omitting them. BreadcrumbList is likewise omitted: one page, no hierarchy
    to describe.
    """
    business: dict = {
        "@type": "BeautySalon",
        "@id": f"{site_url}/#business" if site_url else "#business",
        "name": "Zefir",
        "description": "Студия маникюра и педикюра",
        "priceRange": "₽₽",
        "sameAs": SAME_AS,
    }
    graph: list[dict] = [business]

    if site_url:
        business["url"] = f"{site_url}/"
        business["image"] = f"{site_url}/{OG_IMAGE}"
        graph.append({
            "@type": "WebPage",
            "@id": f"{site_url}/",
            "url": f"{site_url}/",
            "name": TITLE,
            "inLanguage": "ru-RU",
            # A bare {"@id": …} reference is valid JSON-LD, but repeating the
            # type keeps the node self-describing for consumers that don't
            # resolve the graph.
            "about": {"@type": "BeautySalon", "@id": business["@id"]},
        })

    payload = {"@context": "https://schema.org", "@graph": graph}
    body = json.dumps(payload, ensure_ascii=False, indent=2)
    return f'<script type="application/ld+json">\n{body}\n</script>'


def robots_txt(site_url: str) -> str:
    """Deliberate AI-crawler policy, per docs/10: this is a business that wants
    to be found, so the retrieval agents that make a site eligible for citation
    in AI answers are allowed explicitly rather than left to a default. Training
    agents are allowed too — a small salon has no proprietary content to
    protect — and the block below is where to flip that if that changes.
    The agent list needs re-checking periodically; it moves."""
    retrieval = ["OAI-SearchBot", "ChatGPT-User", "PerplexityBot",
                 "Claude-SearchBot", "Claude-User"]
    training = ["GPTBot", "Google-Extended", "ClaudeBot", "CCBot",
                "anthropic-ai", "Meta-ExternalAgent"]
    lines = ["# Полный доступ: одностраничный сайт, скрывать нечего.",
             "User-agent: *", "Allow: /", ""]
    lines += ["# Retrieval-агенты ИИ-поисковиков — разрешены осознанно:",
              "# от них зависит, попадёт ли студия в ответы ИИ.", ""]
    for agent in retrieval:
        lines += [f"User-agent: {agent}", "Allow: /", ""]
    lines += ["# Training-агенты. Чтобы запретить обучение на контенте,",
              "# поменяйте Allow на Disallow в блоках ниже.", ""]
    for agent in training:
        lines += [f"User-agent: {agent}", "Allow: /", ""]
    lines += [f"Sitemap: {site_url}/sitemap.xml", ""]
    return "\n".join(lines)


def sitemap_xml(site_url: str) -> str:
    # lastmod is the page's real build date: Google only honours it when it
    # tracks actual content changes, so it must not be faked forward.
    today = datetime.date.today().isoformat()
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        "  <url>\n"
        f"    <loc>{site_url}/</loc>\n"
        f"    <lastmod>{today}</lastmod>\n"
        "  </url>\n"
        "</urlset>\n"
    )


def write_seo_files(site_url: str | None) -> None:
    og_src = BUILD / OG_IMAGE
    if og_src.exists():
        (DIST / OG_IMAGE).write_bytes(og_src.read_bytes())
        print(f"  {OG_IMAGE:14s} — {og_src.stat().st_size / 1024:.0f} KB")
    else:
        print(f"  {OG_IMAGE:14s} — missing (run build/make_og_image.py)")

    if not site_url:
        # Clear anything a previous --site-url build left behind: a stale
        # robots.txt/sitemap.xml still points at the old host, and shipping
        # that is worse than shipping neither.
        stale = [name for name in ("robots.txt", "sitemap.xml") if (DIST / name).exists()]
        for name in stale:
            (DIST / name).unlink()
        note = f", removed stale {', '.join(stale)}" if stale else ""
        print(f"  robots/sitemap — skipped: pass --site-url https://<domain> to emit them{note}")
        return

    (DIST / "robots.txt").write_text(robots_txt(site_url), encoding="utf-8")
    (DIST / "sitemap.xml").write_text(sitemap_xml(site_url), encoding="utf-8")
    print(f"  robots.txt     — ok ({site_url}/robots.txt)")
    print(f"  sitemap.xml    — ok (1 URL)")


# ── main ─────────────────────────────────────────────────────────────

def main() -> None:
    css = font_css()
    DIST.mkdir(exist_ok=True)
    pages = sorted(SRC.glob("*.html"))
    if not pages:
        sys.exit("no source pages found in src/")

    site_url = parse_site_url(sys.argv[1:])

    marker = "/*@FONTS@*/"
    for page in pages:
        text = page.read_text(encoding="utf-8")
        if marker not in text:
            sys.exit(f"{page.name} has no {marker} marker")

        report: list[str] = []
        built = inline_photos(text.replace(marker, css), report)
        built = built.replace(SEO_MARKER, seo_head(site_url))
        built = built.replace(JSONLD_MARKER, json_ld(site_url))

        target = DIST / page.name
        target.write_text(built, encoding="utf-8")
        kb = len(built.encode("utf-8")) / 1024
        print(f"{page.name} -> dist/{target.name}  {kb:.0f} KB")
        for line in report:
            print(line)

        if "prefers-color-scheme" in text and ":root" not in text:
            print(f"  warning: {page.name} themes without a :root token block")

    write_seo_files(site_url)


if __name__ == "__main__":
    main()
