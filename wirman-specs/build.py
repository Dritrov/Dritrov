#!/usr/bin/env python3
"""Build the WIRMAN diesel generator datasheets (25-220 kVA).

Reads data/models.json, renders template/datasheet.html.j2 for every model,
prints each HTML page to an A4 PDF with headless Chromium and (optionally)
renders PNG previews of every page with PyMuPDF.

Usage:
    python3 build.py                     # build all models in all themes
    python3 build.py 25 220              # only the listed kVA sizes
    python3 build.py classic minimal     # only the listed themes
    python3 build.py --no-preview        # skip PNG previews

Themes: classic (navy/amber), industrial (charcoal/red), minimal (white/teal),
graphite (dark/electric blue). Output goes to output/<theme>/.
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data" / "models.json"
TEMPLATE_DIR = ROOT / "template"
ASSETS = ROOT / "assets"
OUT = ROOT / "output"
HTML_OUT = OUT / "html"
PREVIEW = ROOT / "preview"

THEMES = {
    "classic":    {"key": "classic",    "name": "Classic Navy",      "primary": "#0B2740", "primary2": "#153B5E", "primary3": "#1E4D78", "accent": "#F2A900", "accent2": "#FFC53D", "on_accent": "#0B2740"},
    "industrial": {"key": "industrial", "name": "Industrial Red",    "primary": "#1F2326", "primary2": "#2B3034", "primary3": "#3A4046", "accent": "#D7261E", "accent2": "#FF6A5F", "on_accent": "#FFFFFF"},
    "minimal":    {"key": "minimal",    "name": "Minimal Teal",      "primary": "#16202B", "primary2": "#16202B", "primary3": "#16202B", "accent": "#0E7C86", "accent2": "#14A3AF", "on_accent": "#FFFFFF"},
    "graphite":   {"key": "graphite",   "name": "Graphite Electric", "primary": "#14181D", "primary2": "#1C2128", "primary3": "#2A323C", "accent": "#2F80ED", "accent2": "#7FB3FF", "on_accent": "#FFFFFF"},
}

CHROME_CANDIDATES = [
    os.environ.get("CHROME_BIN", ""),
    "/opt/pw-browsers/chromium-1194/chrome-linux/chrome",
    shutil.which("chromium") or "",
    shutil.which("chromium-browser") or "",
    shutil.which("google-chrome") or "",
]


def find_chrome() -> str:
    for c in CHROME_CANDIDATES:
        if c and Path(c).exists():
            return c
    # last resort: any playwright chromium
    for p in Path("/opt/pw-browsers").glob("chromium-*/chrome-linux/chrome"):
        return str(p)
    raise SystemExit("Chromium not found; set CHROME_BIN")


# --------------------------------------------------------------------------
# SVG generators (design elements only, values come straight from the data)
# --------------------------------------------------------------------------
def dims_svg(dim: dict, theme: dict) -> Markup:
    """Oblique-projection canopy outline annotated with W x L x H."""
    W, L, H = float(dim["w"]), float(dim["l"]), float(dim["h"])
    s = 150.0 / L
    fw, fh = L * s, H * s
    dx, dy = W * s * 0.55, W * s * 0.30
    x0, yb = 42.0, 118.0
    yt = yb - fh
    navy, amber, muted = theme["primary"], theme["accent"], "#5B6877"

    def f(v):
        return f"{v:.1f}"

    top = f"{f(x0)},{f(yt)} {f(x0+fw)},{f(yt)} {f(x0+fw+dx)},{f(yt-dy)} {f(x0+dx)},{f(yt-dy)}"
    side = f"{f(x0+fw)},{f(yt)} {f(x0+fw+dx)},{f(yt-dy)} {f(x0+fw+dx)},{f(yb-dy)} {f(x0+fw)},{f(yb)}"
    louvers = "".join(
        f'<line x1="{f(x0+fw*0.08)}" y1="{f(yt+fh*k)}" x2="{f(x0+fw*0.30)}" y2="{f(yt+fh*k)}" stroke="{navy}" stroke-width="0.8" opacity="0.45"/>'
        for k in (0.30, 0.40, 0.50, 0.60, 0.70)
    )
    door = f'<rect x="{f(x0+fw*0.40)}" y="{f(yt+fh*0.18)}" width="{f(fw*0.48)}" height="{f(fh*0.66)}" fill="none" stroke="{navy}" stroke-width="0.8" opacity="0.55" rx="1"/>'
    window = f'<rect x="{f(x0+fw*0.60)}" y="{f(yt+fh*0.28)}" width="{f(fw*0.20)}" height="{f(fh*0.22)}" fill="{navy}" opacity="0.12" rx="1"/>'
    arrow = f'<defs><marker id="a" viewBox="0 0 6 6" refX="3" refY="3" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M0,0 L6,3 L0,6 z" fill="{muted}"/></marker></defs>'
    txt = f'font-family="Barlow Condensed, Arial Narrow, sans-serif" font-weight="700" fill="{navy}"'
    lbl = f'font-family="Barlow Condensed, Arial Narrow, sans-serif" font-weight="600" fill="{muted}" font-size="10"'
    # dimension lines
    yl = yb + 12
    L_line = f'<line x1="{f(x0)}" y1="{f(yl)}" x2="{f(x0+fw)}" y2="{f(yl)}" stroke="{muted}" stroke-width="0.8" marker-start="url(#a)" marker-end="url(#a)"/>'
    L_txt = f'<text x="{f(x0+fw/2)}" y="{f(yl+11)}" text-anchor="middle" font-size="14" {txt}>L {int(L)}</text>'
    xh = x0 - 12
    H_line = f'<line x1="{f(xh)}" y1="{f(yt)}" x2="{f(xh)}" y2="{f(yb)}" stroke="{muted}" stroke-width="0.8" marker-start="url(#a)" marker-end="url(#a)"/>'
    H_txt = f'<text transform="translate({f(xh-4)},{f((yt+yb)/2)}) rotate(-90)" text-anchor="middle" font-size="14" {txt}>H {int(H)}</text>'
    W_line = f'<line x1="{f(x0+fw+8)}" y1="{f(yb+4)}" x2="{f(x0+fw+dx+8)}" y2="{f(yb-dy+4)}" stroke="{muted}" stroke-width="0.8" marker-start="url(#a)" marker-end="url(#a)"/>'
    W_txt = f'<text x="{f(x0+fw+dx/2+16)}" y="{f(yb-dy/2+10)}" font-size="14" {txt}>W {int(W)}</text>'
    unit = f'<text x="{f(x0+fw+dx+6)}" y="{f(yt-dy-6)}" text-anchor="end" {lbl}>mm</text>'
    svg = f"""<svg viewBox="0 0 272 150" xmlns="http://www.w3.org/2000/svg">
{arrow}
<polygon points="{top}" fill="#E9EDF1" stroke="{navy}" stroke-width="1"/>
<polygon points="{side}" fill="#C9D3DD" stroke="{navy}" stroke-width="1"/>
<rect x="{f(x0)}" y="{f(yt)}" width="{f(fw)}" height="{f(fh)}" fill="#F3F5F8" stroke="{navy}" stroke-width="1.1"/>
{louvers}{door}{window}
<rect x="{f(x0)}" y="{f(yb-3)}" width="{f(fw)}" height="3" fill="{amber}"/>
{L_line}{L_txt}{H_line}{H_txt}{W_line}{W_txt}{unit}
</svg>"""
    return Markup(svg)


def panel_svg(theme: dict) -> Markup:
    """Stylised front view of the DSE6120 MKIII control module with numbered callouts."""
    navy, amber = theme["on_accent"], theme["accent"]
    body, bezel = "#2E333A", "#1C2025"
    font = 'font-family="Barlow Condensed, Arial Narrow, sans-serif"'

    def btn(cx, cy, fill, glyph, n, r=15, glyph_fill="#fff"):
        return (
            f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{fill}" stroke="#0F1114" stroke-width="1.2"/>'
            f'<circle cx="{cx}" cy="{cy}" r="{r-3}" fill="none" stroke="rgba(255,255,255,0.18)" stroke-width="1"/>'
            f"{glyph}"
            f'<circle cx="{cx+r-2}" cy="{cy-r+2}" r="8" fill="{amber}" stroke="#fff" stroke-width="1.2"/>'
            f'<text x="{cx+r-2}" y="{cy-r+5.2}" text-anchor="middle" font-size="9.5" font-weight="800" fill="{navy}" {font}>{n}</text>'
        )

    def label(cx, cy, text):
        return f'<text x="{cx}" y="{cy}" text-anchor="middle" font-size="8.5" font-weight="600" fill="#C9D0D8" letter-spacing="0.5" {font}>{text}</text>'

    # LCD text lines (decorative bars, no textual content)
    lines = "".join(
        f'<rect x="{34}" y="{46 + i*17}" width="{w}" height="6" rx="1.5" fill="#0B2740" opacity="{o}"/>'
        for i, (w, o) in enumerate([(120, 0.75), (150, 0.45), (95, 0.45), (135, 0.45)])
    )
    nav = ""
    for i, (x, g) in enumerate([(56, "M-4,0 L4,0 M0,-4 L-4,0 L0,4"), (86, "M-4,0 L4,0 M0,-4 L4,0 L0,4"), (116, "M0,-4 L0,4 M-4,0 L0,-4 L4,0"), (146, "M0,-4 L0,4 M-4,0 L0,4 L4,0"), (176, "M-4,0 L-1,3 L4,-3")]):
        nav += f'<circle cx="{x}" cy="170" r="10" fill="#3A4048" stroke="#0F1114" stroke-width="1"/><path d="{g}" transform="translate({x},170)" stroke="#fff" stroke-width="1.6" fill="none" stroke-linecap="round" stroke-linejoin="round"/>'
    nav += f'<circle cx="196" cy="160" r="8" fill="{amber}" stroke="#fff" stroke-width="1.2"/><text x="196" y="163.2" text-anchor="middle" font-size="9.5" font-weight="800" fill="{navy}" {font}>7</text>'

    stop = btn(270, 70, "#C8102E", f'<rect x="264" y="64" width="12" height="12" fill="#fff" rx="1"/>', 1)
    manual = btn(330, 70, "#4A5058", f'<path d="M324,76 v-8 a2,2 0 0 1 4,0 v-3 a2,2 0 0 1 4,0 v3 a2,2 0 0 1 4,0 v8 z" fill="#fff"/>', 2)
    test = btn(390, 70, "#4A5058", f'<text x="390" y="74.5" text-anchor="middle" font-size="11" font-weight="800" fill="#fff" {font}>TEST</text>', 3)
    auto = btn(270, 130, "#4A5058", f'<text x="270" y="134.5" text-anchor="middle" font-size="11" font-weight="800" fill="#fff" {font}>AUTO</text>', 4)
    mute = btn(330, 130, "#4A5058", f'<path d="M330,121 c-4,0 -6,3 -6,7 v4 l-2,3 h16 l-2,-3 v-4 c0,-4 -2,-7 -6,-7 z M327,136 a3,3 0 0 0 6,0" fill="#fff"/>', 5)
    start = btn(390, 130, "#1E8E3E", f'<rect x="388" y="123" width="4" height="14" fill="#fff" rx="1"/>', 6)

    svg = f"""<svg viewBox="0 0 440 210" xmlns="http://www.w3.org/2000/svg">
<rect x="4" y="4" width="432" height="202" rx="10" fill="{bezel}"/>
<rect x="10" y="10" width="420" height="190" rx="7" fill="{body}"/>
<text x="24" y="30" font-size="12" font-weight="700" fill="#E6EAEE" letter-spacing="1" {font}>DSE6120 MKIII</text>
<rect x="24" y="38" width="196" height="102" rx="3" fill="#0F1114"/>
<rect x="28" y="42" width="188" height="94" rx="2" fill="#9CCBE3"/>
{lines}
{nav}
{label(116, 196, "MENU NAVIGATION")}
{stop}{manual}{test}{auto}{mute}{start}
{label(270, 95, "STOP / RESET")}{label(330, 95, "MANUAL")}{label(390, 95, "TEST")}
{label(270, 155, "AUTO")}{label(330, 155, "ALARM MUTE")}{label(390, 155, "START")}
<circle cx="236" cy="48" r="3" fill="#3BD16F"/><circle cx="236" cy="62" r="3" fill="#F2A900" opacity="0.5"/><circle cx="236" cy="76" r="3" fill="#C8102E" opacity="0.5"/>
</svg>"""
    return Markup(svg)


# --------------------------------------------------------------------------
def load_models(only: set[str]) -> tuple[dict, list[dict]]:
    d = json.loads(DATA.read_text(encoding="utf-8"))
    models = []
    for m in d["models"]:
        if only and m["kva_short"] not in only:
            continue
        m = dict(m)
        m["engine"] = {**d["engine_common"], **m["engine"]}
        m["alternator"] = {**d["alternator_common"], **m["alternator"]}
        models.append(m)
    return d, models


def render_html(env: Environment, d: dict, m: dict, t: dict) -> Path:
    tpl = env.get_template("datasheet.html.j2")
    html = tpl.render(
        d=d, m=m, t=t, assets=ASSETS.as_uri(),
        dims_svg=lambda dim: dims_svg(dim, t), panel_svg=lambda: panel_svg(t),
    )
    (HTML_OUT / t["key"]).mkdir(parents=True, exist_ok=True)
    p = HTML_OUT / t["key"] / f"{m['file']}.html"
    p.write_text(html, encoding="utf-8")
    return p


def print_pdf(chrome: str, html: Path, pdf: Path) -> None:
    cmd = [
        chrome, "--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars",
        "--run-all-compositor-stages-before-draw", "--virtual-time-budget=4000",
        "--no-pdf-header-footer", f"--print-to-pdf={pdf}", html.as_uri(),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if r.returncode != 0 or not pdf.exists():
        raise RuntimeError(f"Chromium failed for {html.name}:\n{r.stderr[-2000:]}")


def preview_pngs(pdf: Path, stem: str, theme: str) -> list[Path]:
    try:
        import pymupdf  # type: ignore
    except ImportError:
        try:
            import fitz as pymupdf  # type: ignore
        except ImportError:
            return []
    (PREVIEW / theme).mkdir(parents=True, exist_ok=True)
    out = []
    with pymupdf.open(pdf) as doc:
        for i, page in enumerate(doc, 1):
            pix = page.get_pixmap(dpi=110)
            p = PREVIEW / theme / f"{stem} - page {i}.png"
            pix.save(p)
            out.append(p)
    return out


def main(argv: list[str]) -> None:
    no_preview = "--no-preview" in argv
    only = {a for a in argv if a.isdigit()}
    themes = [a for a in argv if a in THEMES] or list(THEMES)
    chrome = find_chrome()
    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR), autoescape=select_autoescape(["html", "j2"]))
    d, models = load_models(only)
    for tk in themes:
        t = THEMES[tk]
        out_dir = OUT / tk
        out_dir.mkdir(parents=True, exist_ok=True)
        for m in models:
            html = render_html(env, d, m, t)
            pdf = out_dir / f"{m['file']}.pdf"
            print_pdf(chrome, html, pdf)
            pages = 0
            if not no_preview:
                pages = len(preview_pngs(pdf, m["file"], tk))
            print(f"OK  {tk:11s} {pdf.name:20s} {pdf.stat().st_size/1024:6.0f} KB  pages={pages or '?'}")


if __name__ == "__main__":
    main(sys.argv[1:])
