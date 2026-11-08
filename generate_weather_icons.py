import os
import math
from PIL import Image, ImageDraw, ImageFilter

OUTDIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "weather_icons")
os.makedirs(OUTDIR, exist_ok=True)

def glow(draw, base_img, color, radius):
    """Apply neon glow around shapes."""
    glow_layer = base_img.copy()
    glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(radius=radius))
    draw_glow = ImageDraw.Draw(glow_layer)
    return glow_layer

def save_icon(draw_fn, filename, size=96):
    base = Image.new("RGBA", (size, size), (0,0,0,0))
    draw = ImageDraw.Draw(base)

    # Draw main icon
    draw_fn(draw, size)

    # Glow pass
    glow_img = base.filter(ImageFilter.GaussianBlur(radius=8))

    # Composite glow + base
    final = Image.alpha_composite(glow_img, base)

    final.save(os.path.join(OUTDIR, filename))
    print("Saved:", filename)

# ---------------------------------------------------
# ICON DRAWING FUNCTIONS (NEON STYLE)
# ---------------------------------------------------

def icon_sun(draw, size):
    cx = cy = size//2
    r = size//4

    # Neon halo
    draw.ellipse((cx-r*1.6, cy-r*1.6, cx+r*1.6, cy+r*1.6),
                 fill=(255,200,0,40))

    # Core
    draw.ellipse((cx-r, cy-r, cx+r, cy+r),
                 fill=(255,220,0,255))

    # Rays
    for angle in range(0, 360, 30):
        dx = int(r*1.8 * math.cos(math.radians(angle)))
        dy = int(r*1.8 * math.sin(math.radians(angle)))
        draw.line((cx, cy, cx+dx, cy+dy),
                  fill=(255,180,0,255), width=6)

def icon_cloud(draw, size):
    # Glow cloud
    draw.ellipse((size*0.15, size*0.40, size*0.85, size*0.85),
                 fill=(180,220,255,40))
    draw.ellipse((size*0.05, size*0.55, size*0.75, size*0.95),
                 fill=(180,220,255,40))

    # Solid cloud
    draw.ellipse((size*0.20, size*0.45, size*0.80, size*0.85),
                 fill=(230,240,255,255))
    draw.ellipse((size*0.10, size*0.60, size*0.70, size*0.95),
                 fill=(230,240,255,255))

def icon_partly_cloudy(draw, size):
    icon_sun(draw, size)
    icon_cloud(draw, size)

def icon_fog(draw, size):
    for i in range(4):
        y = size*0.35 + i*size*0.15
        draw.line((size*0.1, y, size*0.9, y),
                  fill=(200,200,255,180), width=8)

def icon_drizzle(draw, size):
    # Glow (soft, thin)
    for i in range(3):
        x = size * (0.30 + i * 0.18)
        draw.line(
            (x, size * 0.30, x, size * 0.90),
            fill=(120, 200, 255, 120),
            width=12
        )

    # Solid drizzle streaks
    for i in range(3):
        x = size * (0.30 + i * 0.18)
        draw.line(
            (x, size * 0.30, x, size * 0.90),
            fill=(150, 220, 255, 255),
            width=4
        )

def icon_rain(draw, size):
    # Glow behind rain
    for i in range(4):
        x = size * (0.25 + i * 0.18)
        draw.line(
            (x, size * 0.20, x, size * 0.90),
            fill=(90, 180, 255, 150),
            width=20
        )

    # Solid rain streaks
    for i in range(4):
        x = size * (0.25 + i * 0.18)
        draw.line(
            (x, size * 0.20, x, size * 0.90),
            fill=(120, 210, 255, 255),
            width=8
        )


def icon_snow(draw, size):
    cx = size * 0.50
    cy = size * 0.50
    r = size * 0.28

    # Glow snowflake
    for angle in range(0, 360, 60):
        dx = r * math.cos(math.radians(angle))
        dy = r * math.sin(math.radians(angle))
        draw.line(
            (cx - dx, cy - dy, cx + dx, cy + dy),
            fill=(180, 240, 255, 150),
            width=18
        )

    # Solid snowflake
    for angle in range(0, 360, 60):
        dx = r * math.cos(math.radians(angle))
        dy = r * math.sin(math.radians(angle))
        draw.line(
            (cx - dx, cy - dy, cx + dx, cy + dy),
            fill=(220, 250, 255, 255),
            width=6
        )

def icon_showers(draw, size):
    # Glow angled streaks
    for i in range(3):
        x = size * (0.30 + i * 0.22)
        draw.line(
            (x, size * 0.20, x - 20, size * 0.95),
            fill=(100, 180, 255, 150),
            width=20
        )

    # Solid angled streaks
    for i in range(3):
        x = size * (0.30 + i * 0.22)
        draw.line(
            (x, size * 0.20, x - 20, size * 0.95),
            fill=(120, 210, 255, 255),
            width=8
        )

def icon_thunder(draw, size):
    cx = size * 0.50
    cy = size * 0.55

    # --- 1. Lightning bolt shape (cleaner, sharper) ---
    bolt = [
        (cx - size*0.05, cy - size*0.10),
        (cx + size*0.05, cy - size*0.10),
        (cx,            cy + size*0.05),
        (cx + size*0.08, cy + size*0.05),
        (cx - size*0.02, cy + size*0.30),
        (cx + size*0.02, cy + size*0.10),
        (cx - size*0.08, cy + size*0.10),
    ]

    # --- 2. Neon glow BEHIND cloud ---
    draw.polygon(
        bolt,
        fill=(255, 240, 0, 120)   # strong yellow glow
    )

    # --- 3. Cloud (darker + semi-transparent) ---
    draw.ellipse(
        (size*0.20, size*0.40, size*0.80, size*0.80),
        fill=(170, 180, 200, 220)
    )
    draw.ellipse(
        (size*0.10, size*0.55, size*0.70, size*0.95),
        fill=(170, 180, 200, 220)
    )

    # --- 4. Cloud shadow (depth) ---
    draw.ellipse(
        (size*0.25, size*0.78, size*0.75, size*0.92),
        fill=(0, 0, 0, 40)
    )

    # --- 5. Solid lightning bolt ON TOP ---
    draw.polygon(
        bolt,
        fill=(255, 230, 0, 255)   # bright neon core
    )

    # --- 6. Inner highlight for extra punch ---
    draw.polygon(
        bolt,
        fill=(255, 255, 180, 180)
    )


def icon_thunder_hail(draw, size):
    # --- 1. Glow for hail ---
    hail_positions = [
        (size * 0.32, size * 0.82),
        (size * 0.45, size * 0.88),
        (size * 0.58, size * 0.82),
    ]
    for (x, y) in hail_positions:
        draw.ellipse((x - 10, y - 10, x + 10, y + 10),
                     fill=(255, 255, 255, 120))

    # --- 2. Glow for lightning ---
    bolt = [
        (size*0.48, size*0.60),
        (size*0.58, size*0.60),
        (size*0.52, size*0.78),
        (size*0.62, size*0.78),
        (size*0.42, size*0.95),
        (size*0.50, size*0.75),
        (size*0.40, size*0.75),
    ]
    draw.polygon(bolt, fill=(255, 240, 0, 120))

    # --- 3. Cloud ---
    draw.ellipse((size*0.20, size*0.45, size*0.80, size*0.85),
                 fill=(180,190,210,220))
    draw.ellipse((size*0.10, size*0.60, size*0.70, size*0.95),
                 fill=(180,190,210,220))

    # --- 4. Solid lightning ---
    draw.polygon(bolt, fill=(255, 230, 0, 255))

    # --- 5. Solid hail ---
    for (x, y) in hail_positions:
        draw.ellipse((x - 6, y - 6, x + 6, y + 6),
                     fill=(255, 255, 255, 255))


from PIL import Image, ImageDraw, ImageChops

def icon_moon(draw, size):
    cx = size * 0.5
    cy = size * 0.5
    r = size * 0.32

    # --- Outer glow (simple soft halo) ---
    draw.ellipse(
        (cx - r*1.6, cy - r*1.6, cx + r*1.6, cy + r*1.6),
        fill=(255, 220, 120, 40)
    )

    # --- Full moon circle ---
    draw.ellipse(
        (cx - r, cy - r, cx + r, cy + r),
        fill=(255, 230, 140, 255)
    )

    # --- Crescent cutout (shifted right) ---
    # This draws a circle the same color as the background (transparent)
    # Your generator uses a transparent RGBA canvas, so fill=(0,0,0,0) works.
    draw.ellipse(
        (cx - r*0.1, cy - r, cx + r*1.4, cy + r),
        fill=(0, 0, 0, 0)
    )
def icon_night_partly_cloudy(draw, size):
    cx = size * 0.5
    cy = size * 0.5

    # --- Draw moon (shifted upward) ---
    r = size * 0.28

    # Glow
    draw.ellipse(
        (cx - r*1.6, cy - r*1.6 - size*0.12,
         cx + r*1.6, cy + r*1.6 - size*0.12),
        fill=(255, 220, 120, 40)
    )

    # Full moon
    draw.ellipse(
        (cx - r, cy - r - size*0.12,
         cx + r, cy + r - size*0.12),
        fill=(255, 230, 140, 255)
    )

    # Crescent cutout
    draw.ellipse(
        (cx - r*0.1, cy - r - size*0.12,
         cx + r*1.4, cy + r - size*0.12),
        fill=(0, 0, 0, 0)
    )

    # --- Draw cloud (shifted downward) ---
    cloud_w = size * 0.65
    cloud_h = size * 0.35
    cloud_y = cy + size * 0.10  # shift down

    # Glow
    draw.ellipse(
        (cx - cloud_w*0.55, cloud_y - cloud_h*0.55,
         cx + cloud_w*0.55, cloud_y + cloud_h*0.55),
        fill=(180, 200, 255, 40)
    )

    # Main cloud body
    draw.ellipse(
        (cx - cloud_w*0.5, cloud_y - cloud_h*0.5,
         cx + cloud_w*0.5, cloud_y + cloud_h*0.5),
        fill=(230, 240, 255, 255)
    )

    # Cloud bumps
    bump_r = cloud_h * 0.45

    draw.ellipse(
        (cx - cloud_w*0.3 - bump_r, cloud_y - bump_r,
         cx - cloud_w*0.3 + bump_r, cloud_y + bump_r),
        fill=(230, 240, 255, 255)
    )

    draw.ellipse(
        (cx + cloud_w*0.1 - bump_r, cloud_y - bump_r,
         cx + cloud_w*0.1 + bump_r, cloud_y + bump_r),
        fill=(230, 240, 255, 255)
    )

def icon_offline(draw, size):
    cx = size * 0.5
    cy = size * 0.55

    # --- Neon red glow background ---
    draw.ellipse(
        (cx - size*0.45, cy - size*0.45,
         cx + size*0.45, cy + size*0.45),
        fill=(255, 60, 60, 40)
    )

    # --- WiFi arcs (greyed out) ---
    arc_color = (200, 200, 200, 255)
    glow_color = (255, 80, 80, 80)

    # Outer arc
    draw.arc(
        (cx - size*0.35, cy - size*0.35,
         cx + size*0.35, cy + size*0.35),
        start=200, end=340,
        fill=glow_color, width=14
    )
    draw.arc(
        (cx - size*0.35, cy - size*0.35,
         cx + size*0.35, cy + size*0.35),
        start=200, end=340,
        fill=arc_color, width=6
    )

    # Middle arc
    draw.arc(
        (cx - size*0.25, cy - size*0.25,
         cx + size*0.25, cy + size*0.25),
        start=200, end=340,
        fill=glow_color, width=14
    )
    draw.arc(
        (cx - size*0.25, cy - size*0.25,
         cx + size*0.25, cy + size*0.25),
        start=200, end=340,
        fill=arc_color, width=6
    )

    # Inner arc
    draw.arc(
        (cx - size*0.15, cy - size*0.15,
         cx + size*0.15, cy + size*0.15),
        start=200, end=340,
        fill=glow_color, width=14
    )
    draw.arc(
        (cx - size*0.15, cy - size*0.15,
         cx + size*0.15, cy + size*0.15),
        start=200, end=340,
        fill=arc_color, width=6
    )

    # Dot
    draw.ellipse(
        (cx - size*0.05, cy + size*0.05,
         cx + size*0.05, cy + size*0.15),
        fill=arc_color
    )

    # --- Red slash (offline indicator) ---
    draw.line(
        (cx - size*0.40, cy - size*0.40,
         cx + size*0.40, cy + size*0.40),
        fill=(255, 80, 80, 255),
        width=10
    )
    draw.line(
        (cx - size*0.40, cy - size*0.40,
         cx + size*0.40, cy + size*0.40),
        fill=(255, 80, 80, 80),
        width=20
    )


# ---------------------------------------------------
# GENERATE ALL ICONS
# ---------------------------------------------------

save_icon(icon_sun, "sun.png")
save_icon(icon_partly_cloudy, "partly_cloudy.png")
save_icon(icon_cloud, "cloud.png")
save_icon(icon_fog, "fog.png")
save_icon(icon_drizzle, "drizzle.png")
save_icon(icon_rain, "rain.png")
save_icon(icon_snow, "snow.png")
save_icon(icon_showers, "showers.png")
save_icon(icon_thunder, "thunder.png")
save_icon(icon_thunder_hail, "thunder_hail.png")
save_icon(icon_moon, "moon.png")
save_icon(icon_night_partly_cloudy, "night_partly_cloudy.png")
save_icon(icon_offline, "offline.png")
print("\n✅ Neon weather icons generated in:", OUTDIR)
