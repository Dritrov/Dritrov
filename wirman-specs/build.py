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
premium (graphite/gold, 3D illustration), graphite (dark/electric blue). Output goes to output/<theme>/.
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
    "premium":    {"key": "premium",    "name": "Premium 3D",        "primary": "#0C0F14", "primary2": "#161B23", "primary3": "#242B37", "accent": "#C9A227", "accent2": "#EAD27A", "on_accent": "#0C0F14"},
    "datasheet":  {"key": "datasheet",  "name": "Data Sheet (Cummins-style order)", "template": "datasheet-cummins.html.j2", "primary": "#1B2A3A", "primary2": "#1B2A3A", "primary3": "#2B3F55", "accent": "#F2A900", "accent2": "#FFC53D", "on_accent": "#1B2A3A"},
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


def genset_svg(dim: dict, theme: dict) -> Markup:
    """Isometric, shaded 3D illustration of the canopied genset, proportional to W x L x H."""
    W, L, H = float(dim["w"]), float(dim["l"]), float(dim["h"])
    s = 150.0 / L
    Lp, Wp, Hp = L * s, W * s, H * s
    base = Hp * 0.11                      # base frame height (px)
    gold, gold2 = theme["accent"], theme["accent2"]
    # isometric unit vectors
    ux, uy = 0.866, 0.5                   # along L (right-down)
    vx, vy = 0.866, -0.5                  # along W (right-up)
    ox = 14.0
    oy = 12.0 + Wp * 0.5 + Hp + base          # origin = bottom-front-left corner (of base)
    vb_w = (Lp + Wp) * 0.866 + 30
    vb_h = oy + Lp * 0.5 + 30

    def P(u, v, h):  # point from local coords: u along L, v along W, h up
        return (ox + u * ux + v * vx, oy + u * uy + v * vy - h)

    def poly(pts, **kw):
        attrs = " ".join(f'{k.replace("_", "-")}="{val}"' for k, val in kw.items())
        return f'<polygon points="{" ".join(f"{x:.1f},{y:.1f}" for x, y in pts)}" {attrs}/>'

    # transforms for drawing in face-local coordinates (u right, v down)
    def face_tf(u0, v0, h0, kind):
        x, y = P(u0, v0, h0)
        if kind == "front":   # local u -> along L, local v -> down
            return f"matrix({ux:.4f},{uy:.4f},0,1,{x:.2f},{y:.2f})"
        if kind == "side":    # local u -> along W, local v -> down
            return f"matrix({vx:.4f},{vy:.4f},0,1,{x:.2f},{y:.2f})"
        return f"matrix({ux:.4f},{uy:.4f},{vx:.4f},{vy:.4f},{x:.2f},{y:.2f})"  # top: u->L, v->W

    zc = base                               # canopy bottom height
    zt = base + Hp                          # canopy top height
    # --- shadow
    sh_cx, sh_cy = P(Lp * 0.55, Wp * 0.5, 0)
    shadow = f'<ellipse cx="{sh_cx:.1f}" cy="{sh_cy + 6:.1f}" rx="{(Lp + Wp) * 0.55:.1f}" ry="{(Lp + Wp) * 0.16:.1f}" fill="#000" opacity="0.55" filter="url(#blur)"/>'
    # --- base frame (dark steel)
    bf = poly([P(0, 0, 0), P(Lp, 0, 0), P(Lp, 0, zc), P(0, 0, zc)], fill="url(#steelF)")
    bs = poly([P(Lp, 0, 0), P(Lp, Wp, 0), P(Lp, Wp, zc), P(Lp, 0, zc)], fill="url(#steelS)")
    pockets = "".join(
        f'<rect x="{Lp * k:.1f}" y="{2:.1f}" width="{Lp * 0.09:.1f}" height="{base - 4:.1f}" fill="#05070A" opacity="0.8" transform="{face_tf(0, 0, zc, "front")}"/>'
        for k in (0.18, 0.66)
    )
    # --- canopy faces
    front = poly([P(0, 0, zc), P(Lp, 0, zc), P(Lp, 0, zt), P(0, 0, zt)], fill="url(#canF)")
    side = poly([P(Lp, 0, zc), P(Lp, Wp, zc), P(Lp, Wp, zt), P(Lp, 0, zt)], fill="url(#canS)")
    top = poly([P(0, 0, zt), P(Lp, 0, zt), P(Lp, Wp, zt), P(0, Wp, zt)], fill="url(#canT)")
    edge = poly([P(0, 0, zc), P(Lp, 0, zc), P(Lp, 0, zt), P(0, 0, zt)], fill="none", stroke="rgba(255,255,255,0.35)", stroke_width="0.6")
    edge2 = poly([P(Lp, 0, zc), P(Lp, Wp, zc), P(Lp, Wp, zt), P(Lp, 0, zt)], fill="none", stroke="rgba(0,0,0,0.25)", stroke_width="0.6")
    # --- front-face details (local coords: width Lp, height Hp, v downwards from top)
    tf = face_tf(0, 0, zt, "front")
    louv = "".join(
        f'<rect x="{Lp * 0.06:.1f}" y="{Hp * (0.16 + i * 0.075):.1f}" width="{Lp * 0.20:.1f}" height="{Hp * 0.035:.1f}" rx="0.6" fill="#2A313B" opacity="0.85"/>'
        for i in range(9)
    )
    door = f'<rect x="{Lp * 0.31:.1f}" y="{Hp * 0.12:.1f}" width="{Lp * 0.34:.1f}" height="{Hp * 0.76:.1f}" rx="1.2" fill="none" stroke="#7B8590" stroke-width="0.7"/>'
    handle = f'<rect x="{Lp * 0.60:.1f}" y="{Hp * 0.47:.1f}" width="{Lp * 0.025:.1f}" height="{Hp * 0.10:.1f}" rx="0.6" fill="#1B2027"/>'
    brand = f'<text x="{Lp * 0.48:.1f}" y="{Hp * 0.36:.1f}" text-anchor="middle" font-family="Barlow Condensed, Arial Narrow, sans-serif" font-weight="800" font-size="{Hp * 0.16:.1f}" fill="#2B333D" letter-spacing="1">WIRMAN</text>'
    stripe = f'<rect x="0" y="{Hp * 0.86:.1f}" width="{Lp:.1f}" height="{Hp * 0.05:.1f}" fill="url(#goldH)"/>'
    win_x, win_y, win_w, win_h = Lp * 0.71, Hp * 0.18, Lp * 0.22, Hp * 0.26
    window = (
        f'<rect x="{win_x:.1f}" y="{win_y:.1f}" width="{win_w:.1f}" height="{win_h:.1f}" rx="1" fill="#0F1318"/>'
        f'<rect x="{win_x + 2:.1f}" y="{win_y + 2:.1f}" width="{win_w - 4:.1f}" height="{win_h - 4:.1f}" rx="0.8" fill="url(#screen)"/>'
        f'<rect x="{win_x + 5:.1f}" y="{win_y + 6:.1f}" width="{win_w * 0.5:.1f}" height="1.6" fill="#0B2740" opacity="0.6"/>'
        f'<rect x="{win_x + 5:.1f}" y="{win_y + 10:.1f}" width="{win_w * 0.35:.1f}" height="1.6" fill="#0B2740" opacity="0.45"/>'
        f'<circle cx="{win_x + win_w * 0.82:.1f}" cy="{win_y + win_h + 6:.1f}" r="2.4" fill="#C8102E"/>'
        f'<rect x="{win_x + win_w * 0.82 - 3.2:.1f}" y="{win_y + win_h + 3.4:.1f}" width="6.4" height="1" fill="#F5C400" opacity="0.9"/>'
    )
    gloss = f'<rect x="0" y="0" width="{Lp:.1f}" height="{Hp * 0.22:.1f}" fill="url(#glossV)"/>'
    front_details = f'<g transform="{tf}">{louv}{door}{handle}{brand}{stripe}{window}{gloss}</g>'
    # --- side face details (radiator grille)
    ts = face_tf(Lp, 0, zt, "side")
    grille = f'<rect x="{Wp * 0.12:.1f}" y="{Hp * 0.14:.1f}" width="{Wp * 0.76:.1f}" height="{Hp * 0.68:.1f}" rx="1" fill="#1D232B"/>' + "".join(
        f'<rect x="{Wp * (0.16 + i * 0.09):.1f}" y="{Hp * 0.17:.1f}" width="{Wp * 0.045:.1f}" height="{Hp * 0.62:.1f}" fill="#3A434E"/>'
        for i in range(8)
    ) + f'<rect x="0" y="{Hp * 0.86:.1f}" width="{Wp:.1f}" height="{Hp * 0.05:.1f}" fill="url(#goldH)" opacity="0.8"/>'
    side_details = f'<g transform="{ts}">{grille}</g>'
    # --- top details: exhaust cap + lifting eye + seams
    tt = face_tf(0, 0, zt, "top")
    top_details = (
        f'<g transform="{tt}">'
        f'<rect x="{Lp * 0.31:.1f}" y="{Wp * 0.08:.1f}" width="{Lp * 0.34:.1f}" height="{Wp * 0.84:.1f}" fill="none" stroke="rgba(0,0,0,0.12)" stroke-width="0.6"/>'
        f'<circle cx="{Lp * 0.12:.1f}" cy="{Wp * 0.62:.1f}" r="{Wp * 0.13:.1f}" fill="#8F98A3"/>'
        f'<circle cx="{Lp * 0.12:.1f}" cy="{Wp * 0.62:.1f}" r="{Wp * 0.08:.1f}" fill="#2B333D"/>'
        f'<rect x="{Lp * 0.47:.1f}" y="{Wp * 0.40:.1f}" width="{Lp * 0.06:.1f}" height="{Wp * 0.2:.1f}" rx="1" fill="#6E7883"/>'
        f'</g>'
    )
    defs = f"""<defs>
<filter id="blur" x="-30%" y="-80%" width="160%" height="260%"><feGaussianBlur stdDeviation="5"/></filter>
<linearGradient id="canF" x1="0" y1="0" x2="0.2" y2="1"><stop offset="0" stop-color="#E9EDF2"/><stop offset="0.55" stop-color="#C5CCD5"/><stop offset="1" stop-color="#9AA3AE"/></linearGradient>
<linearGradient id="canS" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#AEB6C0"/><stop offset="1" stop-color="#6F7883"/></linearGradient>
<linearGradient id="canT" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#FFFFFF"/><stop offset="1" stop-color="#D7DDE4"/></linearGradient>
<linearGradient id="steelF" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#3A414B"/><stop offset="1" stop-color="#1A1F26"/></linearGradient>
<linearGradient id="steelS" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#2A3038"/><stop offset="1" stop-color="#12161B"/></linearGradient>
<linearGradient id="goldH" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{gold}"/><stop offset="0.5" stop-color="{gold2}"/><stop offset="1" stop-color="{gold}"/></linearGradient>
<linearGradient id="glossV" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#FFFFFF" stop-opacity="0.55"/><stop offset="1" stop-color="#FFFFFF" stop-opacity="0"/></linearGradient>
<linearGradient id="screen" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#BFE3F5"/><stop offset="1" stop-color="#7FB8D6"/></linearGradient>
</defs>"""
    svg = f'<svg viewBox="0 0 {vb_w:.0f} {vb_h:.0f}" xmlns="http://www.w3.org/2000/svg">{defs}{shadow}{bf}{bs}{pockets}{front}{side}{top}{front_details}{side_details}{top_details}{edge}{edge2}</svg>'
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


def find_photo(m: dict) -> str:
    """Real product photo, if one was dropped into assets/photos/ (per model or shared)."""
    for stem in (m["file"], m["kva_short"], "wirman"):
        for ext in ("jpg", "jpeg", "png", "webp"):
            p = ASSETS / "photos" / f"{stem}.{ext}"
            if p.exists():
                return p.as_uri()
    return ""


def render_html(env: Environment, d: dict, m: dict, t: dict) -> Path:
    tpl = env.get_template(t.get("template", "datasheet.html.j2"))
    html = tpl.render(
        d=d, m=m, t=t, assets=ASSETS.as_uri(), photo=find_photo(m),
        dims_svg=lambda dim: dims_svg(dim, t), panel_svg=lambda: panel_svg(t),
        genset_svg=lambda dim: genset_svg(dim, t),
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
