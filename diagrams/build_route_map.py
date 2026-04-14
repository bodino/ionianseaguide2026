"""
Build an accurate Ionian route map using real OSM tiles + real coordinates.
All port coords verified via Nominatim. Route is drawn through realistic
sailing waypoints (around headlands, through channels) — not straight lines.
"""
import math
from staticmap import StaticMap, CircleMarker
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path

OUT = Path(__file__).parent / "ionian-route.png"

# --- Verified port coordinates (OSM Nominatim) ---
# Each: (lat, lon, kind, label_dx, label_dy)
# kind: base | port | anchor | ref
PORTS = {
    "Lefkas Marina":        (38.82891, 20.71110, "base",   30, -14),
    "Nidri":                (38.70695, 20.70989, "port",  -80, -22),
    "Sivota (Lefkada)":     (38.62196, 20.68372, "port", -195,  -4),
    "Spartohori":           (38.66120, 20.75933, "port",   30, -22),
    # Vathi (Meganisi) removed — too close to Spartohori, causes label clash
    "Kalamos":              (38.61500, 20.90600, "port",  40, -22),
    "Kastos":               (38.57270, 20.91215, "port",   30,  -4),
    "Frikes":               (38.45904, 20.66498, "port", -115, -22),
    "Kioni":                (38.44918, 20.68939, "port",   30,   8),
    "Vathi (Ithaca)":       (38.36453, 20.71816, "port",   30,  -4),
    "Fiskardo":             (38.46093, 20.57524, "port", -180,  -4),
    "Assos":                (38.37734, 20.54004, "anchor",-140, -4),
    "Sami":                 (38.22111, 20.64117, "port",   30,  -4),
    "Preveza":              (38.95717, 20.75162, "ref",    30,  -4),
}

# --- Overnight stops ---
# port key, day label, label_dx, label_dy
ROUTE_STOPS = [
    ("Lefkas Marina",  "Sat 18 + Fri 24",  50, -22),
    ("Spartohori",     "Sun 19 · Day 1",   50, -22),
    ("Kalamos",        "Mon 20 · Day 2",   50, -22),
    ("Vathi (Ithaca)", "Tue 21 · Day 3",   50, -22),
    ("Fiskardo",       "Wed 22 · Day 4", -305,  -4),
    ("Kioni",          "Thu 23 · Day 5",   50,  10),
]

# --- Realistic sailing route (waypoints follow channels, not land) ---
# Each leg is a list of (lat, lon) waypoints from origin to destination.
# Waypoints were chosen to keep track in water, around headlands, through strait.
ROUTE_LEGS = [
    # Leg 1: Lefkas Marina -> Spartohori
    [(38.82891, 20.71110),  # marina
     (38.800,  20.718),     # south in lagoon
     (38.750,  20.722),     # past Lygia
     (38.705,  20.724),     # past Nidri, east side of Lefkada
     (38.680,  20.740),     # crossing toward Meganisi
     (38.66120, 20.75933)], # Spartohori / Porto Spilia

    # Leg 2: Spartohori -> Kalamos village (on Kalamos island east side)
    [(38.66120, 20.75933),
     (38.640,  20.790),     # through Meganisi-mainland strait
     (38.610,  20.820),     # south of Meganisi
     (38.605,  20.870),     # open water E approaching Kalamos island
     (38.61500, 20.90600)], # Kalamos village

    # Leg 3: Kalamos -> Vathi Ithaca (S past Kastos, SW across, into Vathi bay)
    [(38.61500, 20.90600),
     (38.550,  20.905),     # S past Kastos E side
     (38.480,  20.860),     # SW open water
     (38.420,  20.810),     # towards Ithaca east coast
     (38.385,  20.740),     # rounding into Vathi approach
     (38.36453, 20.71816)], # Vathi Ithaca

    # Leg 4: Vathi -> Fiskardo (N up Ithaca east coast, round N cape, W to Fiskardo)
    [(38.36453, 20.71816),
     (38.405,  20.725),     # N out of bay
     (38.445,  20.715),     # N along Ithaca east coast
     (38.485,  20.685),     # round N cape Ithaca
     (38.480,  20.620),     # into the Ithaca-Kefalonia channel
     (38.46093, 20.57524)], # Fiskardo

    # Leg 5: Fiskardo -> Kioni (E across channel)
    [(38.46093, 20.57524),
     (38.465,  20.620),     # mid-channel
     (38.458,  20.670),     # approach Kioni
     (38.44918, 20.68939)], # Kioni

    # Leg 6: Kioni -> Lefkas Marina (N round Ithaca, NE to Meganisi, N up lagoon)
    [(38.44918, 20.68939),
     (38.485,  20.680),     # round N Ithaca
     (38.530,  20.705),     # NE cross
     (38.600,  20.740),     # Meganisi west approach
     (38.680,  20.730),     # lagoon south entrance
     (38.760,  20.720),     # through lagoon
     (38.810,  20.716),     # canal approach
     (38.82891, 20.71110)], # marina
]

# --- Map bounds (extend slightly for margins and to cover full route) ---
BBOX_N = 38.99
BBOX_S = 38.18
BBOX_W = 20.42
BBOX_E = 21.03

WIDTH = 1400
HEIGHT = 1850

_MAP = {"sm": None}

def lon_to_tilex(lon, zoom):
    return (lon + 180.0) / 360.0 * (1 << zoom)

def lat_to_tiley(lat, zoom):
    lat_rad = math.radians(lat)
    return (1.0 - math.log(math.tan(lat_rad) + 1 / math.cos(lat_rad)) / math.pi) / 2.0 * (1 << zoom)

def latlon_to_xy(lat, lon):
    sm = _MAP["sm"]
    tx = lon_to_tilex(lon, sm.zoom)
    ty = lat_to_tiley(lat, sm.zoom)
    return sm._x_to_px(tx), sm._y_to_px(ty)

def fetch_basemap():
    url_template = "https://a.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png"
    m = StaticMap(WIDTH, HEIGHT, url_template=url_template)
    m.add_marker(CircleMarker((BBOX_W, BBOX_S), "#ffffff00", 1))
    m.add_marker(CircleMarker((BBOX_E, BBOX_N), "#ffffff00", 1))
    img = m.render()
    _MAP["sm"] = m
    return img

def load_font(size, bold=False):
    candidates = [
        ("/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf"),
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial.ttf",
    ]
    for p in candidates:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()

def draw_text_with_halo(draw, xy, text, font, fill, halo="white", halo_width=2):
    x, y = xy
    for dx in range(-halo_width, halo_width+1):
        for dy in range(-halo_width, halo_width+1):
            if dx == 0 and dy == 0:
                continue
            draw.text((x+dx, y+dy), text, font=font, fill=halo)
    draw.text((x, y), text, font=font, fill=fill)

def draw_dashed_line(draw, start, end, fill, width, dash=14, gap=8):
    import math
    x1, y1 = start
    x2, y2 = end
    length = math.hypot(x2-x1, y2-y1)
    if length == 0:
        return
    dx = (x2-x1)/length
    dy = (y2-y1)/length
    pos = 0
    while pos < length:
        a = (x1 + dx*pos, y1 + dy*pos)
        b = (x1 + dx*min(pos+dash, length), y1 + dy*min(pos+dash, length))
        draw.line([a, b], fill=fill, width=width)
        pos += dash + gap

def main():
    print("Fetching OSM basemap tiles…")
    base = fetch_basemap().convert("RGBA")
    if base.size != (WIDTH, HEIGHT):
        base = base.resize((WIDTH, HEIGHT), Image.LANCZOS)

    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    font_port = load_font(20, bold=True)
    font_label = load_font(22, bold=True)
    font_small = load_font(16)
    font_day = load_font(26, bold=True)
    font_title = load_font(30, bold=True)

    # --- Draw sailing route (dashed red line through real waypoints) ---
    for leg in ROUTE_LEGS:
        pts = [latlon_to_xy(lat, lon) for lat, lon in leg]
        # solid halo under line for readability
        for i in range(len(pts) - 1):
            draw.line([pts[i], pts[i+1]], fill=(255, 255, 255, 200), width=9)
        for i in range(len(pts) - 1):
            draw_dashed_line(draw, pts[i], pts[i+1], fill=(192, 57, 43, 255), width=5)

    # --- Draw non-route ports as secondary markers ---
    route_port_names = {r[0] for r in ROUTE_STOPS}
    for name, (lat, lon, kind, dx, dy) in PORTS.items():
        if name in route_port_names:
            continue
        x, y = latlon_to_xy(lat, lon)
        if kind == "anchor":
            draw.rectangle([x-6, y-6, x+6, y+6], fill=(39, 100, 140, 255), outline="white", width=2)
        elif kind == "ref":
            draw.ellipse([x-5, y-5, x+5, y+5], fill=(110, 110, 110, 255))
        else:
            draw.ellipse([x-8, y-8, x+8, y+8], fill=(39, 100, 140, 255), outline="white", width=2)
        draw_text_with_halo(draw, (x+dx, y+dy), name, font_port, fill=(40, 40, 40), halo="white", halo_width=2)

    # --- Draw overnight route markers (small so they don't cover features) ---
    font_num = load_font(18, bold=True)
    for idx, (name, date_label, dx, dy) in enumerate(ROUTE_STOPS):
        lat, lon, *_ = PORTS[name]
        x, y = latlon_to_xy(lat, lon)

        if idx == 0:
            r = 14
            draw.ellipse([x-r, y-r, x+r, y+r], fill=(30, 30, 30, 255), outline="white", width=3)
            marker = "⚓"
        else:
            r = 14
            draw.ellipse([x-r, y-r, x+r, y+r], fill=(192, 57, 43, 255), outline="white", width=3)
            marker = str(idx)

        bbox = draw.textbbox((0, 0), marker, font=font_num)
        tw, th = bbox[2]-bbox[0], bbox[3]-bbox[1]
        draw.text((x - tw/2 - bbox[0], y - th/2 - bbox[1] - 1), marker, font=font_num, fill="white")

        # Leader line from marker edge to label pill
        lx, ly = x + dx, y + dy
        b1 = draw.textbbox((lx, ly), name, font=font_label)
        b2 = draw.textbbox((lx, ly + 26), date_label, font=font_small)
        left = min(b1[0], b2[0]) - 8
        top  = min(b1[1], b2[1]) - 5
        right = max(b1[2], b2[2]) + 8
        bottom = max(b1[3], b2[3]) + 5
        # leader from marker edge toward pill
        import math as _m
        cx, cy = (left + right) / 2, (top + bottom) / 2
        ang = _m.atan2(cy - y, cx - x)
        mx, my = x + _m.cos(ang) * r, y + _m.sin(ang) * r
        # clamp leader endpoint to nearest pill edge
        if abs(cx - x) > abs(cy - y):
            ex = left if cx > x else right
            ey = y + (ex - x) * (cy - y) / max(1, cx - x) if (cx - x) != 0 else cy
        else:
            ey = top if cy > y else bottom
            ex = x + (ey - y) * (cx - x) / max(1, cy - y) if (cy - y) != 0 else cx
        draw.line([(mx, my), (ex, ey)], fill=(120, 120, 120, 220), width=1)

        outline = (30, 30, 30, 230) if idx == 0 else (192, 57, 43, 230)
        draw.rectangle([left, top, right, bottom], fill=(255, 255, 255, 245), outline=outline, width=2)
        draw.text((lx, ly), name, font=font_label, fill=(30, 30, 30))
        date_color = (30, 30, 30) if idx == 0 else (192, 57, 43)
        draw.text((lx, ly + 26), date_label, font=font_small, fill=date_color)

    # --- Title & legend panel ---
    pw, ph = 460, 220
    draw.rectangle([20, 20, 20+pw, 20+ph], fill=(255, 255, 255, 240), outline=(60, 60, 60), width=2)
    draw.text((36, 30), "Ionian route · 18–25 April 2026", font=font_title, fill=(30, 30, 30))
    draw.text((36, 68), "Bavaria C45 · Lefkas Marina", font=font_label, fill=(100, 100, 100))

    ly = 110
    draw.ellipse([36, ly, 68, ly+32], fill=(192, 57, 43, 255), outline="white", width=3)
    draw.text((47, ly+4), "N", font=font_day, fill="white")
    draw.text((80, ly+2), "overnight stop (numbered)", font=font_label, fill=(30, 30, 30))

    draw_dashed_line(draw, (36, ly+50), (68, ly+50), fill=(192, 57, 43), width=5, dash=8, gap=4)
    draw.text((80, ly+38), "sailing route (real passage)", font=font_label, fill=(30, 30, 30))

    draw.ellipse([44, ly+75, 60, ly+91], fill=(39, 100, 140, 255), outline="white", width=2)
    draw.text((80, ly+72), "harbour / taverna quay", font=font_label, fill=(30, 30, 30))

    draw.rectangle([44, ly+103, 58, ly+117], fill=(39, 100, 140, 255), outline="white", width=1)
    draw.text((80, ly+100), "anchorage only", font=font_label, fill=(30, 30, 30))

    # --- Scale bar ---
    # 1 deg lon at ~38.5°N ≈ 87.0 km. 10 nm = 18.52 km.
    km_per_deg_lon = 87.0
    px_10nm = (18.52 / km_per_deg_lon) / (BBOX_E - BBOX_W) * WIDTH
    sx, sy = 60, HEIGHT - 100
    draw.line([(sx, sy), (sx + px_10nm, sy)], fill=(30, 30, 30), width=5)
    draw.line([(sx, sy-9), (sx, sy+9)], fill=(30, 30, 30), width=5)
    draw.line([(sx + px_10nm, sy-9), (sx + px_10nm, sy+9)], fill=(30, 30, 30), width=5)
    draw.line([(sx + px_10nm/2, sy-6), (sx + px_10nm/2, sy+6)], fill=(30, 30, 30), width=3)
    draw.text((sx-4, sy+14), "0", font=font_label, fill=(30, 30, 30))
    draw.text((sx + px_10nm/2 - 6, sy+14), "5", font=font_label, fill=(30, 30, 30))
    draw.text((sx + px_10nm - 22, sy+14), "10 nm", font=font_label, fill=(30, 30, 30))

    # --- North arrow ---
    nx, ny = WIDTH - 100, HEIGHT - 140
    draw.polygon([(nx, ny-34), (nx-16, ny+12), (nx, ny+2), (nx+16, ny+12)], fill=(192, 57, 43), outline=(30,30,30))
    draw.text((nx - 10, ny + 18), "N", font=font_day, fill=(30, 30, 30))

    # --- Attribution ---
    draw.text((WIDTH - 360, HEIGHT - 30), "© OpenStreetMap contributors · CARTO", font=font_small, fill=(100, 100, 100))

    out = Image.alpha_composite(base, overlay).convert("RGB")
    out.save(OUT, optimize=True)
    print(f"wrote {OUT} ({OUT.stat().st_size//1024} KB)")

if __name__ == "__main__":
    main()
