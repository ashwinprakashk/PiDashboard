#!/usr/bin/env python3
import sys
import time, threading, datetime, tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk   # for background image scaling
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import RPi.GPIO as GPIO
import matplotlib.dates as mdates
from datetime import timedelta
from datetime import datetime
import math, random
from PIL import Image, ImageTk, ImageDraw
import numpy as np
from PIL import Image
from PIL import ImageDraw, ImageFilter
import datetime
import os, time, threading
import feedparser
import textwrap
import requests 
import datetime
from tkcalendar import Calendar
import subprocess

import json
import re

# Run from the script's own folder so images, icons and flag.txt are found
# no matter where the program is started from.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)

# Personal settings live in config.json (not in git). See config.example.json.
DEFAULT_CONFIG = {
    "latitude": 52.52,
    "longitude": 13.40,
    "scheduled_show": {"enabled": False, "times": [], "message": "Reminder!"}
}
def load_config():
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    path = os.path.join(BASE_DIR, "config.json")
    if os.path.exists(path):
        with open(path) as f:
            user = json.load(f)
        cfg.update({k: v for k, v in user.items() if k != "scheduled_show"})
        cfg["scheduled_show"].update(user.get("scheduled_show", {}))
    else:
        print("[INFO] config.json not found - using defaults from DEFAULT_CONFIG")
    return cfg
CONFIG = load_config()

# Asset folders
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
BG_DIR = os.path.join(ASSETS_DIR, "backgrounds")
IMG_DIR = os.path.join(ASSETS_DIR, "images")
ICON_DIR = os.path.join(ASSETS_DIR, "weather_icons")

def find_backgrounds():
    """Every .png/.jpg in assets/backgrounds, in natural order (background2 before background10)."""
    files = []
    if os.path.isdir(BG_DIR):
        files = [os.path.join(BG_DIR, f) for f in os.listdir(BG_DIR)
                 if f.lower().endswith((".png", ".jpg", ".jpeg"))]
    def key(path):
        stem = os.path.splitext(os.path.basename(path))[0]
        m = re.match(r"(.*?)(\d*)$", stem)
        return (m.group(1).lower(), int(m.group(2) or 0))
    return sorted(files, key=key)

def open_background(path):
    """Open a background, or a plain dark image if there are none."""
    if path is None:
        return Image.new("RGB", (1920, 600), "#1e2a38")
    return Image.open(path)

PWM_GPIO = 18
PWM_FREQ = 1000
UPDATE_INTERVAL = 1.0
TEMP_FILE = "/sys/class/thermal/thermal_zone0/temp"
FREQ_FILE = "/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq"

GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)
GPIO.setup(PWM_GPIO, GPIO.OUT, initial=GPIO.LOW)
pwm = GPIO.PWM(PWM_GPIO, PWM_FREQ)
pwm.start(0)


def fetch_weather_next3h_plus_tomorrow():
    url = (
        "https://api.open-meteo.com/v1/forecast?"
        f"latitude={CONFIG['latitude']}&longitude={CONFIG['longitude']}&"
        "hourly=temperature_2m,weathercode&"
        "daily=temperature_2m_max,temperature_2m_min,weathercode,sunrise,sunset&"
        "forecast_days=2"
    )

    try:
        data = requests.get(url, timeout=8).json()
        # --- Hourly forecast (next 3 hours) ---
        hours = data["hourly"]["time"]
        temps = data["hourly"]["temperature_2m"]
        codes = data["hourly"]["weathercode"]

        now = datetime.datetime.now().replace(minute=0, second=0, microsecond=0)

        next3 = []
        for i in range(len(hours)):
            t = datetime.datetime.fromisoformat(hours[i])
            if 0 <= (t - now).total_seconds() <= 3 * 3600:
                next3.append((t, temps[i], codes[i]))
        next3 = next3[:3]

        # --- Tomorrow forecast (daily) ---
        tomorrow_temp = data["daily"]["temperature_2m_max"][1]
        tomorrow_code = data["daily"]["weathercode"][1]

        tomorrow = ("Tomorrow", tomorrow_temp, tomorrow_code)

        return next3, tomorrow, data, True #Online

    except Exception as e:
        print("Weather fetch error:", e)
        # --- SAFE FALLBACKS ---
        now = datetime.datetime.now().replace(minute=0, second=0, microsecond=0)

        # Fake next 3 hours
        next3 = [
            (now, 0, 0),
            (now + datetime.timedelta(hours=1), 0, 0),
            (now + datetime.timedelta(hours=2), 0, 0),
        ]

        # Fake tomorrow
        tomorrow = ("Tomorrow", 0, 0)

        # Fake sunrise/sunset so your app doesn't crash
        fake_data = {
            "daily": {
                "sunrise": [(now.replace(hour=6, minute=0)).isoformat()],
                "sunset":  [(now.replace(hour=18, minute=0)).isoformat()],
            }
        }

        return next3, tomorrow, fake_data, False #Offline


def fetch_news_world():
    feed = feedparser.parse("https://news.google.com/rss?hl=en&gl=US&ceid=US:en&topic=w")
    return [entry.title for entry in feed.entries[:20]]

def fetch_news_tech():
    feed = feedparser.parse("https://news.google.com/rss?hl=en&gl=US&ceid=US:en&topic=tc")
    return [entry.title for entry in feed.entries[:20]]

def read_cpu_temp_c():
    try:
        return int(open(TEMP_FILE).read().strip())/1000.0
    except:
        return float('nan')

def read_cpu_freq_mhz():
    try:
        return int(open(FREQ_FILE).read().strip())/1000.0
    except:
        return float('nan')

def get_fan_speed():
    base_path = "/sys/devices/platform/cooling_fan/hwmon"

    try:
        # Loop through all hwmon directories
        for entry in os.listdir(base_path):
            hwmon_dir = os.path.join(base_path, entry)

            # Check if fan1_input exists here
            fan_file = os.path.join(hwmon_dir, "fan1_input")
            if os.path.isfile(fan_file):
                # Read the fan speed
                result = subprocess.run(['cat', fan_file], capture_output=True, text=True)
                fan_speed = result.stdout.strip()
                return f"Fan Speed: {fan_speed} RPM"

        return "Error: fan1_input not found in any hwmon directory"

    except Exception as e:
        return f"Error: {e}"

def temp_to_speed(temp_c):
    if temp_c != temp_c: return 0
    if temp_c < 45: return 0
    if temp_c >= 70: return 100
    frac = (temp_c-45)/(70-45)
    return max(20, min(100, 20+frac*80))

class FanClockApp:
    def is_night(self, now):
        return now < self.sunrise or now > self.sunset
    def update_news(self):
        world_headlines = fetch_news_world()
        #tech_headlines = fetch_news_tech()
        # Capture current time 
        self.reset_news_scroll()
        last_fetch_time = datetime.datetime.now().strftime("%A %H:%M")
        # Combine into one list with numbering 1–20
        headlines = world_headlines #+ tech_headlines
        self.update_news_plot(headlines, last_fetch_time)

        # Refresh every 30 minutes (1800,000 ms)
        self.root.after(1800000, self.update_news)

    def create_outlined_text(self, canvas, x, y, text, font, fill, outline="black"):
        offsets = [(-1,0),(1,0),(0,-1),(0,1),(-1,-1),(1,-1),(-1,1),(1,1)]
        outline_ids = []
        for dx, dy in offsets:
            outline_ids.append(canvas.create_text(
                x+dx, y+dy, anchor="nw", text=text, fill=outline, font=font
            ))
        main_id = canvas.create_text(x, y, anchor="nw", text=text, fill=fill, font=font)
        return outline_ids, main_id
    
    def launch_fireworks(self):
        # Choose a random center point
        cx = random.randint(100, self.root.winfo_width()-100)
        cy = random.randint(100, self.info_height-50)

        # Create particles
        particles = []
        for i in range(15):  # number of sparks
            angle = random.uniform(0, 360)
            dx = 5 * random.uniform(0.5, 1.0) * math.cos(math.radians(angle))
            dy = 5 * random.uniform(0.5, 1.0) * math.sin(math.radians(angle))
            color = random.choice(["red", "yellow", "orange", "cyan", "magenta", "white"])
            particle_size = random.randint(4, 8)  # bigger sparks, random size
            p = self.info_canvas.create_oval(
                cx, cy, cx+particle_size, cy+particle_size, fill=color, outline=""
            )
            particles.append((p, dx, dy, color))

        # Animate particles
        self.animate_fireworks(particles, 0)

    def draw_cloud(self, cx, cy, scale=0.2):
        """Draw a fluffy cartoon cloud at (cx, cy), scaled by factor."""
        parts = []
        shades = ["#ffffff", "#fdfdfd", "#eeeeee"]

        # Base offsets scaled
        base_offsets = [(-40,0), (-20,-10), (0,0), (20,-15), (40,0)]
        for ox, oy in base_offsets:
            # Scale both offset and size
            ox_scaled = int(ox * scale)
            oy_scaled = int(oy * scale)
            size = int(40 * scale * (0.8 + 0.4*random.random()))

            oval = self.info_canvas.create_oval(
                cx + ox_scaled, cy + oy_scaled,
                cx + ox_scaled + size, cy + oy_scaled + size,
                fill=random.choice(shades), outline="", tags="cloud"
            )
            parts.append(oval)

        return parts

    def draw_pirate_ship(self, cx, cy, scale=0.2):
        """Draw a complex cartoon pirate ship with curved hull, multiple masts, sails, and details, scaled down."""
        parts = []

        # Hull (curved)
        hull = self.info_canvas.create_polygon(
            cx, cy,
            cx+int(150*scale), cy,
            cx+int(130*scale), cy+int(55*scale),
            cx+int(20*scale), cy+int(55*scale),
            cx+int(-15*scale), cy+int(25*scale),
            fill="#a0522d", outline="#ffd27f", width=2, tags="pirate_ship"
        )
        parts.append(hull)

        # Deck line
        deck = self.info_canvas.create_line(cx+int(20*scale), cy, cx+int(130*scale), cy,
                                            fill="#4b2e2e", width=3, tags="pirate_ship")
        parts.append(deck)

        # === Foremast ===
        fore_mast = self.info_canvas.create_rectangle(cx+int(40*scale), cy-int(90*scale),
                                                    cx+int(45*scale), cy,
                                                    fill="#3b2f2f", outline="#ffe680", tags="pirate_ship")
        parts.append(fore_mast)
        fore_sail = self.info_canvas.create_polygon(
            cx+int(45*scale), cy-int(90*scale),
            cx+int(45*scale), cy-int(30*scale),
            cx+int(10*scale), cy-int(40*scale),
            fill="#fff8dc", outline="#ffcc00", tags="pirate_ship"
        )
        parts.append(fore_sail)

        # === Mainmast ===
        main_mast = self.info_canvas.create_rectangle(cx+int(85*scale), cy-int(130*scale),
                                                    cx+int(90*scale), cy,
                                                    fill="#3b2f2f", outline="#ffe680", tags="pirate_ship")
        parts.append(main_mast)
        main_sail_top = self.info_canvas.create_polygon(
            cx+int(90*scale), cy-int(130*scale),
            cx+int(90*scale), cy-int(80*scale),
            cx+int(40*scale), cy-int(90*scale),
            fill="#fff8dc", outline="#ffcc00", tags="pirate_ship"
        )
        main_sail_bottom = self.info_canvas.create_polygon(
            cx+int(90*scale), cy-int(80*scale),
            cx+int(90*scale), cy-int(30*scale),
            cx+int(40*scale), cy-int(40*scale),
            fill="#fff8dc", outline="#ffcc00", tags="pirate_ship"
        )
        parts.extend([main_sail_top, main_sail_bottom])

        # Crow’s nest
        crow_nest = self.info_canvas.create_oval(cx+int(80*scale), cy-int(140*scale),
                                                cx+int(100*scale), cy-int(125*scale),
                                                fill="#654321", outline="#222", tags="pirate_ship")
        parts.append(crow_nest)

        # === Mizzenmast (rear) ===
        mizzen_mast = self.info_canvas.create_rectangle(cx+int(120*scale), cy-int(90*scale),
                                                        cx+int(125*scale), cy,
                                                        fill="#3b2f2f", outline="#ffe680", tags="pirate_ship")
        parts.append(mizzen_mast)
        mizzen_sail = self.info_canvas.create_polygon(
            cx+int(125*scale), cy-int(90*scale),
            cx+int(125*scale), cy-int(40*scale),
            cx+int(95*scale), cy-int(50*scale),
            fill="#fff8dc", outline="#ffcc00", tags="pirate_ship"
        )
        parts.append(mizzen_sail)

        # Flags
        flag1 = self.info_canvas.create_polygon(cx+int(90*scale), cy-int(130*scale),
                                                cx+int(120*scale), cy-int(140*scale),
                                                cx+int(90*scale), cy-int(145*scale),
                                                fill="black", outline="#ff0000", tags="pirate_ship")
        skull1 = self.info_canvas.create_text(cx+int(105*scale), cy-int(142*scale),
                                            text="☠", fill="white",
                                            font=("DejaVu Sans Mono", int(12*scale), "bold"), tags="pirate_ship")
        parts.extend([flag1, skull1])

        flag2 = self.info_canvas.create_polygon(cx+int(125*scale), cy-int(90*scale),
                                                cx+int(150*scale), cy-int(100*scale),
                                                cx+int(125*scale), cy-int(105*scale),
                                                fill="red", outline="#ffcc00", tags="pirate_ship")
        parts.append(flag2)

        # Windows
        for wx in [30, 55, 80, 105]:
            win = self.info_canvas.create_oval(cx+int(wx*scale), cy+int(15*scale),
                                            cx+int(wx*scale)+int(15*scale), cy+int(30*scale),
                                            fill="#00bfff", outline="#ffffff", tags="pirate_ship")
            parts.append(win)

        # Cannons
        for cxn in [25, 50, 75, 100]:
            cannon = self.info_canvas.create_rectangle(cx+int(cxn*scale), cy+int(40*scale),
                                                    cx+int(cxn*scale)+int(12*scale), cy+int(47*scale),
                                                    fill="#333333", outline="#ff6600", tags="pirate_ship")
            parts.append(cannon)

        return parts


    def launch_pirate_scene(self):
        width = max(self.info_canvas.winfo_width(), 1)
        height = self.info_height

        # Start positions
        start_x = -150
        ship_y = int(height * 0.65)
        cloud_y = ship_y - 40

        # Draw ship + cloud
        ship_parts = self.draw_pirate_ship(start_x, ship_y)
        # Move cloud closer: reduce the +180 offset, align Y closer to ship
        cloud_parts = self.draw_cloud(start_x + 100, ship_y - 20, scale=1.0)

        # 👉 Immediately raise them above overlay
        for item in ship_parts + cloud_parts:
            self.info_canvas.tag_raise(item)

        # Animate them sailing across
        self.animate_pirate_scene(ship_parts, cloud_parts, x=start_x, y=ship_y, dx=6, bob_phase=0)

    def animate_pirate_scene(self, ship_parts, cloud_parts, x, y, dx, bob_phase):
        width = max(self.info_canvas.winfo_width(), 1)

        # Bobbing motion
        bob = int(4 * math.sin(bob_phase))
        def move_items(items, dx, dy):
            for item in items:
                self.info_canvas.move(item, dx, dy)

        move_items(ship_parts, dx, bob)
        move_items(cloud_parts, dx+2, bob//2)

        x_next = x + dx
        # 👉 Keep ship + cloud above overlay
        if hasattr(self, "overlay_item") and self.overlay_item:
            self.info_canvas.tag_raise("pirate_ship", self.overlay_item)
            self.info_canvas.tag_raise("cloud", self.overlay_item)

        if x_next < width + 200:
            self.root.after(50, lambda: self.animate_pirate_scene(
                ship_parts, cloud_parts, x_next, y, dx, bob_phase+0.25
            ))
        else:
            # Cleanup
            for item in ship_parts + cloud_parts:
                self.info_canvas.delete(item)

    def load_balloon_image(self, scale=0.1):
        img = Image.open(os.path.join(IMG_DIR, "hotairballon.png"))
        # Resize for scaling
        w, h = img.size
        img = img.resize((int(w*scale), int(h*scale)), Image.Resampling.LANCZOS)
        photo = ImageTk.PhotoImage(img)
        return photo

    def launch_hot_air_balloon(self):
        start_x = -150
        start_y = self.info_height + 50   # lower start so it has room

        self.balloon_photo = self.load_balloon_image(scale=0.45)
        balloon_item = self.info_canvas.create_image(
            start_x, start_y, image=self.balloon_photo, anchor="center", tags="hot_air_balloon"
        )

        # dx bigger, dy smaller
        self.animate_hot_air_balloon(balloon_item, start_x, start_y, dx=6, dy=2, bob_phase=0)



    def preload_balloon_images(self, scales):
        self.balloon_photos = []
        img = Image.open(os.path.join(IMG_DIR, "hotairballon.png"))
        w, h = img.size
        for s in scales:
            resized = img.resize((int(w*s), int(h*s)), Image.Resampling.LANCZOS)
            self.balloon_photos.append(ImageTk.PhotoImage(resized))

    def animate_hot_air_balloon(self, balloon_item, x, y, dx, dy, bob_phase):
        width = max(self.info_canvas.winfo_width(), 1)
        height = self.info_height

        # Bobbing motion
        bob = 2 * math.sin(bob_phase)

        # Next position (diagonal movement)
        x_next = x + dx
        y_next = y - dy + bob   # subtract dy so it rises

        # Update canvas position
        self.info_canvas.coords(balloon_item, float(x_next), float(y_next))

        # Keep above overlay
        if hasattr(self, "overlay_item") and self.overlay_item:
            self.info_canvas.tag_raise("hot_air_balloon", self.overlay_item)

        # Continue until off-screen
        if x_next < width + 200 and y_next > -300:  # allow more climb
            self.root.after(60, lambda: self.animate_hot_air_balloon(
                balloon_item, x_next, y_next, dx, dy, bob_phase+0.15
            ))
        else:
            self.info_canvas.delete(balloon_item)

    def schedule_balloon_hourly(self):
        now = datetime.datetime.now()
        # Next full hour
        next_hour = (now + datetime.timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        delay_ms = int((next_hour - now).total_seconds() * 1000)

        # Schedule launch at the next hour
        self.root.after(delay_ms, self._balloon_hourly_wrapper)

    def schedule_balloon_every_15(self):
        now = datetime.datetime.now()

        # Compute minutes to next quarter-hour
        minutes = now.minute
        next_quarter = (minutes // 15 + 1) * 15
        if next_quarter == 60:
            # Move to next hour
            next_time = (now + datetime.timedelta(hours=1)).replace(
                minute=0, second=0, microsecond=0
            )
        else:
            next_time = now.replace(
                minute=next_quarter, second=0, microsecond=0
            )
        delay_ms = int((next_time - now).total_seconds() * 1000)
        self.root.after(delay_ms, self._balloon_15min_wrapper)

    def _balloon_hourly_wrapper(self):
        # Reschedule for the next hour
        self.schedule_balloon_hourly()
        if self.schedule_running:
            return
        # Launch the balloon
        self.launch_hot_air_balloon()

    def _balloon_15min_wrapper(self):
        # Reschedule for the next hour
        self.schedule_balloon_every_15()
        if self.schedule_running:
            return
        # Launch the balloon
        self.launch_hot_air_balloon()

    def launch_rocket(self):
        cx = random.randint(50, self.root.winfo_width()-50)
        cy = self.info_height + 100

        # Rocket body
        body = self.info_canvas.create_rectangle(cx-3, cy-15, cx+3, cy, fill="", outline="")

        # Nose cone
        nose = self.info_canvas.create_polygon(cx-3, cy-15, cx+3, cy-15, cx, cy-22, fill="", outline="")

        # Fins
        left_fin = self.info_canvas.create_polygon(cx-3, cy, cx-8, cy+5, cx-3, cy+5, fill="", outline="")
        right_fin = self.info_canvas.create_polygon(cx+3, cy, cx+8, cy+5, cx+3, cy+5, fill="", outline="")

        rocket_parts = [body, nose, left_fin, right_fin]
        self.animate_rocket(rocket_parts, cx, cy, target_y=60)

    def on_click(self, event):
        widget = event.widget
        if isinstance(widget, tk.Button) and widget.cget("text") == "✖":
            return
        # Ignore clicks if a scheduled show is running
        if self.schedule_running:
            return
        # Call sequence instead of single rocket
        #self.launch_pirate_scene()
        self.launch_rocket_sequence("Rocket Show!!!")
        #self.launch_hot_air_balloon()

    def start_flag_checker(self):
        """Background thread to monitor flag.txt and trigger rocket sequence."""
        def check_flag_loop():
            while self.running:  # reuse your existing running flag
                if os.path.exists("flag.txt"):
                    with open("flag.txt") as f:
                        content = f.read().strip()
                    if content:  # only act if not empty
                        print("Message received:", content)
                        # Trigger rocket sequence with file contents as message
                        self.root.after(0, lambda msg=content: self.launch_rocket_sequence(msg))
                        # Reset after handling
                        open("flag.txt", "w").close()
                time.sleep(2)
        threading.Thread(target=check_flag_loop, daemon=True).start()

    def launch_rocket_sequence(self, message="Fireworks Show!"):
        # Show message in top bar
        self.message_label.config(text=message)

        # Fade in overlay first
        self.fade_in_overlay()

        # Launch 10 rockets, each 0.5s apart
        for i in range(10):
            self.root.after(i * 500, self.launch_rocket)

        # Fade out overlay and clear message after rockets finish
        # Add buffer (~6s) so last rockets can explode before fade out
        self.root.after(8000, lambda: (
            self.fade_out_overlay(),
            self.message_label.config(text="")
        ))

    def draw_booster(self, cx, cy):
        flame_color = random.choice(["yellow", "orange", "red"])
        size = random.randint(4, 8)
        flame = self.info_canvas.create_oval(cx-3, cy, cx+3, cy+size, fill=flame_color, outline="")
        self.root.after(100, lambda: self.info_canvas.delete(flame))

    def draw_smoke(self, cx, cy):
        smoke_color = random.choice(["#cccccc", "#bbbbbb", "#999999"])
        size = random.randint(6, 12)
        smoke = self.info_canvas.create_oval(cx-size//2, cy, cx+size//2, cy+size, fill=smoke_color, outline="")
        self.root.after(300, lambda: self.info_canvas.delete(smoke))


    def animate_fireworks(self, particles, step):
        if step > 10:  # shorter lifespan
            for p, _, _, _ in particles:
                self.info_canvas.delete(p)
            return

        # Fade factor: 1.0 → 0.0
        fade_factor = 1.0 - (step / 10.0)

        for p, dx, dy, color in particles:
            self.info_canvas.move(p, dx, dy)
            # Blend color with background (black) based on fade_factor
            # Target vibrant ember color
            target_r, target_g, target_b = self.root.winfo_rgb("#ffb366")

            # Original color
            r0, g0, b0 = self.root.winfo_rgb(color)

            # Interpolate between original and target
            r = int(((r0 * fade_factor) + (target_r * (1 - fade_factor))) / 256)
            g = int(((g0 * fade_factor) + (target_g * (1 - fade_factor))) / 256)
            b = int(((b0 * fade_factor) + (target_b * (1 - fade_factor))) / 256)

            faded = f"#{r:02x}{g:02x}{b:02x}"
            self.info_canvas.itemconfig(p, fill=faded)

        self.root.after(80, lambda: self.animate_fireworks(particles, step+1))

    def animate_rocket(self, rocket_parts, cx, cy, target_y):
        if cy <= target_y:
            for part in rocket_parts:
                self.info_canvas.delete(part)
            self.launch_fireworks_at(cx, cy)
            return

        # Move rocket upward
        for part in rocket_parts:
            self.info_canvas.move(part, 0, -10)

        # Booster + smoke
        self.draw_booster(cx, cy)
        self.draw_smoke(cx, cy+10)

        self.root.after(50, lambda: self.animate_rocket(rocket_parts, cx, cy-10, target_y))

    def flash_glow(self, cx, cy, size=150, step=0, glow_item=None):
        max_steps = 10
        alpha_base = int((1.0 - step/max_steps) * 255)  # brighter max alpha

        gradient = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(gradient)

        # Inner core (white)
        margin_core = size // 3
        draw.ellipse((margin_core, margin_core, size - margin_core, size - margin_core),
                    fill=(255, 255, 255, alpha_base))

        # Middle glow (yellow, stronger)
        margin_mid = size // 5
        draw.ellipse((margin_mid, margin_mid, size - margin_mid, size - margin_mid),
                    fill=(255, 255, 150, int(alpha_base * 0.8)))

        # Outer glow (orange, stronger)
        margin_outer = size // 8
        draw.ellipse((margin_outer, margin_outer, size - margin_outer, size - margin_outer),
                    fill=(255, 180, 100, int(alpha_base * 0.6)))

        gradient = gradient.filter(ImageFilter.GaussianBlur(radius=size//6))
        photo = ImageTk.PhotoImage(gradient)

        if glow_item is None:
            glow_item = self.info_canvas.create_image(cx, cy, image=photo, anchor="center")
        else:
            self.info_canvas.itemconfig(glow_item, image=photo)

        self.info_canvas.tag_raise(glow_item)

        if not hasattr(self, "glow_photos"):
            self.glow_photos = []
        self.glow_photos.append(photo)

        if step < max_steps:
            self.root.after(50, lambda: self.flash_glow(cx, cy, size, step+1, glow_item))
        else:
            self.info_canvas.delete(glow_item)

    def launch_fireworks_at(self, cx, cy):
        particles = []
        for i in range(20):
            angle = random.uniform(0, 360)
            dx = 4 * random.uniform(0.5, 1.5) * math.cos(math.radians(angle))
            dy = 4 * random.uniform(0.5, 1.5) * math.sin(math.radians(angle))
            color = random.choice(["red", "yellow", "orange", "cyan", "magenta", "white"])
            particle_size = random.randint(5, 10)
            p = self.info_canvas.create_oval(cx, cy, cx+particle_size, cy+particle_size,
                                         fill=color, outline="")
            particles.append((p, dx, dy, color))
        self.flash_glow(cx, cy, size=random.randint(120, 180))
        self.animate_fireworks(particles, 0)

    def __init__(self, root):
        self.root = root
        self.root.title("Raspberry Pi Fan & Clock Dashboard")
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        # ===== Full-screen =====
        self.is_fullscreen = True
        self.enter_fullscreen()
        self.root.bind("<Escape>", self.exit_fullscreen)
        self.root.bind("<F11>", self.toggle_fullscreen)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Info.TFrame", background="#222")
        style.configure("TButton", font=("DejaVu Sans Mono", 14), padding=6)

        # ===== Top bar =====
        topbar = ttk.Frame(root, padding=5, style="Info.TFrame")
        topbar.pack(side=tk.TOP, fill=tk.X)

        exit_btn = tk.Button(
            topbar, text="✖", command=self.on_close,
            font=("DejaVu Sans Mono", 14, "bold"),
            fg="white", bg="#ff6666",
            activebackground="#ff4d4d",
            activeforeground="white",
            relief="flat", padx=6, pady=2
        )
        exit_btn.pack(side=tk.RIGHT, padx=5, pady=2)

        # Logo
        logo_img = Image.open(os.path.join(IMG_DIR, "kaaspr.png"))
        logo_img = logo_img.resize((120, 40), Image.Resampling.LANCZOS)
        logo_photo = ImageTk.PhotoImage(logo_img)
        logo_label = tk.Label(topbar, image=logo_photo, bg="#222")
        logo_label.image = logo_photo
        logo_label.pack(side=tk.LEFT, padx=5)

        # Bind clicks
        self.root.bind("<Button-1>", self.on_click)

        self.message_label = tk.Label(
            topbar, text="", font=("DejaVu Sans Mono", 16, "bold"),
            fg="#ffcc66", bg="#222", padx=10, pady=2
        )
        self.message_label.pack(expand=True)

        # ===== Info section with Canvas background =====
        self.info_height = 200
        self.info_canvas = tk.Canvas(root, height=self.info_height, highlightthickness=0)
        self.info_canvas.pack(side=tk.TOP, fill=tk.X, pady=0)

        # Background images
        self.bg_files = find_backgrounds() or [None]
        self.bg_index = 0
        self.info_bg_orig = open_background(self.bg_files[self.bg_index])
        self.info_bg_photo = ImageTk.PhotoImage(self.info_bg_orig)
        self.info_bg_item = self.info_canvas.create_image(0, 0, anchor="nw", image=self.info_bg_photo)

        self.info_canvas.bind("<Configure>", self.resize_info_bg)
        self.rotate_background()

        # Clock + CPU info text
        self.clock_glow = self.info_canvas.create_text(
            20, 20, anchor="nw", text="", fill="#ffffff",
            font=("DejaVu Sans Mono", 28, "bold")
        )
        self.temp_text = self.info_canvas.create_text(
            20, 70, anchor="nw", text="", fill="#ffffff",
            font=("DejaVu Sans Mono", 18, "bold")
        )
        #self.freq_text = self.info_canvas.create_text(
        #    250, 70, anchor="nw", text="", fill="#99ff33",
        #    font=("DejaVu Sans Mono", 18, "bold")
        #)
        self.cpu_fan_text = self.info_canvas.create_text(
            250, 70, anchor="nw", text="", fill="#99ff33",
            font=("DejaVu Sans Mono", 18, "bold")
        )        
        self.fan_text = self.info_canvas.create_text(
            480, 70, anchor="nw", text="", fill="#ffcc00",
            font=("DejaVu Sans Mono", 18, "bold")
        )
        self.avg_text = self.info_canvas.create_text(
            20, 110, anchor="nw", text="", fill="#ffffff",
            font=("DejaVu Sans Mono", 16, "bold")
        )

        # Clock outline (must be here BEFORE update_loop)
        self.clock_outline, self.clock_text = self.create_outlined_text(
            self.info_canvas, 20, 20, "", ("DejaVu Sans Mono", 28, "bold"), fill="#ffffff"
        )

        # ===== Weather icons =====
        icon_path = ICON_DIR

        def load_icon(name):
            img = Image.open(f"{icon_path}/{name}.png").resize((40, 40), Image.Resampling.LANCZOS)
            return ImageTk.PhotoImage(img)

        self.weather_icons = {
            0: load_icon("sun"),
            1: load_icon("partly_cloudy"),
            2: load_icon("partly_cloudy"),
            3: load_icon("cloud"),
            45: load_icon("fog"),
            48: load_icon("fog"),
            51: load_icon("drizzle"),
            53: load_icon("drizzle"),
            55: load_icon("drizzle"),
            56: load_icon("drizzle"),
            57: load_icon("drizzle"),
            61: load_icon("rain"),
            63: load_icon("rain"),
            65: load_icon("rain"),
            66: load_icon("rain"),
            67: load_icon("rain"),
            71: load_icon("snow"),
            73: load_icon("snow"),
            75: load_icon("snow"),
            77: load_icon("snow"),
            80: load_icon("showers"),
            81: load_icon("showers"),
            82: load_icon("showers"),
            95: load_icon("thunder"),
            96: load_icon("thunder_hail"),
            99: load_icon("thunder_hail"),
        }
        self.weather_icons["sun"] = self.weather_icons[0]
        self.weather_icons["partly_cloudy"] = self.weather_icons[1]
        self.weather_icons["moon"] = load_icon("moon")
        self.weather_icons["night_partly_cloudy"] = load_icon("night_partly_cloudy")
        self.weather_icons["offline"] = load_icon("offline")

        self.weather_items = []
        self.root.after(300, self.update_weather_display)
        self.weather_online = True

        # === Graph + Calendar inside Matplotlib ===
        plt.style.use("dark_background")

        self.fig = plt.figure(figsize=(20, 7))
        gs = self.fig.add_gridspec(2, 2, width_ratios=[4, 1], height_ratios=[2, 1])
        self.fig.subplots_adjust(wspace=0.25)

        # LEFT: CPU graph
        self.ax_temp = self.fig.add_subplot(gs[0, 0])
        #self.ax_temp.tick_params(axis="x", labelrotation=30)
        self.ax_temp.set_title("CPU Temperature (°C)", color="white")
        self.ax_temp.set_ylabel("Temp °C", color="white")
        self.ax_temp.grid(True, color="#444")
        self.temp_line, = self.ax_temp.plot([], [], color="#e74c3c", linewidth=2, marker="o", markersize=4)
        self.temp_avg_line, = self.ax_temp.plot([], [], color="#f1c40f", linewidth=2, linestyle="--")

        # RIGHT: Calendar drawn inside Matplotlib
        self.ax_calendar = self.fig.add_subplot(gs[0, 1])
        self.ax_calendar.axis("off")

        # Calender
        import calendar, datetime
        from matplotlib.patches import Rectangle

        today = datetime.date.today()
        year = today.year
        month = today.month

        # Determine previous and next month
        prev_year = year if month > 1 else year - 1
        prev_month = month - 1 if month > 1 else 12
        next_year = year if month < 12 else year + 1
        next_month = month + 1 if month < 12 else 1

        prev_month_days = calendar.monthrange(prev_year, prev_month)[1]

        # Calendar matrix
        cal = calendar.monthcalendar(year, month)

        # Clear axis
        self.ax_calendar.clear()
        self.ax_calendar.axis("off")

        # Month name
        self.ax_calendar.text(
            0.5, 1.08,
            f"{calendar.month_name[month]} {year}",
            color="white", fontsize=14,
            ha="center", va="center",
            family="DejaVu Sans Mono"
        )

        # Layout settings
        start_x = 0.08
        start_y = 0.88
        dx = 0.2
        dy = 0.18

        # Weekday headers
        headers = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]
        for i, h in enumerate(headers):
            self.ax_calendar.text(
                start_x + i * dx, start_y,
                h,
                color="#cccccc",
                fontsize=12,
                ha="center", va="center",
                family="DejaVu Sans Mono"
            )

        # Draw grid + numbers
        self.calendar_cells = []  # store for animation

        for row_idx, week in enumerate(cal):
            for col_idx, day in enumerate(week):

                # Determine day number
                if day == 0:
                    # Previous or next month
                    if row_idx == 0:
                        day_num = prev_month_days - (week.count(0) - col_idx) + 1
                    else:
                        day_num = (col_idx + 1) - week.index(0)
                else:
                    day_num = day

                # Determine text color
                if day == 0:
                    text_color = "#555555"          # grey for other months
                else:
                    if col_idx >= 5:
                        text_color = "#8899ff"      # weekend
                    else:
                        text_color = "white"        # weekday

                # Draw day number
                txt = self.ax_calendar.text(
                    start_x + col_idx * dx,
                    start_y - (row_idx + 1) * dy,
                    f"{day_num}",
                    color=text_color,
                    fontsize=12,
                    ha="center", va="center",
                    family="DejaVu Sans Mono"
                )

                # Store for animation
                is_current_month = (day != 0)
                self.calendar_cells.append((day_num, txt, is_current_month))

        # BOTTOM: News scroller
        self.ax_news = self.fig.add_subplot(gs[1, :])
        self.ax_news.set_title("Top 5 News Headlines", color="white")
        self.ax_news.axis("off")

        self.fig.subplots_adjust(hspace=0.8)

        # Embed figure
        canvas = FigureCanvasTkAgg(self.fig, master=root)
        canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.canvas = canvas

        # ===== Rest of your original code =====
        self.temp_data = []
        self.time_data = []
        self.manual_var = tk.IntVar(value=-1)

        control = ttk.Frame(root, padding=10, style="Info.TFrame")
        control.pack(side=tk.TOP, fill=tk.X)
        ttk.Label(control, text="Manual override (0–100%)", background="#222", foreground="white").grid(row=0, column=0, sticky="w")
        self.manual_scale = ttk.Scale(control, from_=0, to=100, orient=tk.HORIZONTAL,
                                    command=self.on_manual_scale, length=300)
        self.manual_scale.grid(row=0, column=1, sticky="ew", padx=10)
        control.columnconfigure(1, weight=1)
        ttk.Button(control, text="Auto", command=self.set_auto).grid(row=0, column=2, padx=5)

        self.status = ttk.Label(
            root, text="System running...", anchor="w",
            font=("DejaVu Sans Mono", 12), foreground="#aaa", background="#222"
        )
        self.status.pack(side=tk.BOTTOM, fill=tk.X)

        self.schedule_rockets()
        self.running = True
        self.schedule_running = False
        self.update_loop()
        self.update_news()
        self.start_flag_checker()
        self.scroll_news()
        self.weather_items = []
        self.root.after(300, self.update_weather_display)

    def update_weather_display(self):
        # Remove old items
        for item in self.weather_items:
            self.info_canvas.delete(item)
        self.weather_items.clear()

        next3, tomorrow, weather_data, online  = fetch_weather_next3h_plus_tomorrow()
        self.weather_online = online
        
        if not next3:
            return
        daily = weather_data["daily"]
        self.sunrise = datetime.datetime.fromisoformat(daily["sunrise"][0])
        self.sunset  = datetime.datetime.fromisoformat(daily["sunset"][0])

        width = self.info_canvas.winfo_width()
        if width < 50:
            self.root.after(200, self.update_weather_display)
            return

        x0 = width - 260   # wider because 4 blocks now
        y0 = 10
        block_w = 60

        # --- Draw next 3 hours ---
        for i, (t, temp, code) in enumerate(next3):
            hour = t.strftime("%H:%M")
            now = datetime.datetime.now()
            if not self.weather_online:
                icon = self.weather_icons["offline"]
            else:
                if code == 0:  # clear sky
                    if self.is_night(now):
                        icon = self.weather_icons["moon"]
                    else:
                        icon = self.weather_icons["sun"]
                elif code in (1, 2):  # cloudy sky
                    if self.is_night(now):
                        icon = self.weather_icons["night_partly_cloudy"]
                    else:
                        icon = self.weather_icons["partly_cloudy"]                    
                else:
                    icon = self.weather_icons.get(code)
            # Icon
            icon_item = self.info_canvas.create_image(
                x0 + i * block_w,
                y0,
                anchor="nw",
                image=icon
            )
            self.weather_items.append(icon_item)

            # Text
            txt = f"{hour}\n{temp:.0f}°C"
            outline_ids, main_id = self.create_outlined_text(
                self.info_canvas,
                x0 + i * block_w,
                y0 + 35,
                txt,
                ("DejaVu Sans Mono", 12, "bold"),
                fill="white",
                outline="black"
            )
            self.weather_items.extend(outline_ids)
            self.weather_items.append(main_id)

        # --- Draw tomorrow forecast ---
        if tomorrow:
            label, temp, code = tomorrow
            if not self.weather_online:
                icon = self.weather_icons["offline"]
            else:
                icon = self.weather_icons.get(code)
            idx = 3  # 4th block

            # Icon
            icon_item = self.info_canvas.create_image(
                x0 + idx * block_w,
                y0,
                anchor="nw",
                image=icon
            )
            self.weather_items.append(icon_item)

            # Text
            txt = f"{label}\n{temp:.0f}°C"
            outline_ids, main_id = self.create_outlined_text(
                self.info_canvas,
                x0 + idx * block_w,
                y0 + 35,
                txt,
                ("DejaVu Sans Mono", 11, "bold"),
                fill="white",
                outline="black"
            )
            self.weather_items.extend(outline_ids)
            self.weather_items.append(main_id)
            # ---------------------------------------------------------
            # INSERT OFFLINE TEXT RIGHT HERE
            # ---------------------------------------------------------
            if not self.weather_online:
                offline_text = "OFFLINE MODE"
                outline_ids, main_id = self.create_outlined_text(
                    self.info_canvas,
                    x0,          # align with first weather block
                    y0 + 80,     # below icons + temperature text
                    offline_text,
                    ("DejaVu Sans Mono", 12, "bold"),
                    fill="orange",
                    outline="black"
                )
                self.weather_items.extend(outline_ids)
                self.weather_items.append(main_id)
            # ---------------------------------------------------------

        # Raise all items
        for item in self.weather_items:
            self.info_canvas.tag_raise(item)

        # Refresh every 30 minutes
        self.root.after(1800000, self.update_weather_display)

    def update_news_plot(self, headlines, last_fetch_time):
        # Clear the axis
        self.ax_news.clear()
        
        # Draw heading + timestamp on the same line 
        self.ax_news.text( 
            0.40, 1.20, # left side 
            "★ Top News", fontsize=16, color="#FFE4B5", # pastel yellow 
            va="center", ha="left", transform=self.ax_news.transAxes 
        ) 
        self.ax_news.text( 
            0.95, 1.20, # right side 
            f"(Last updated: {last_fetch_time})", fontsize=10, color="#ADD8E6", # pastel blue 
            va="center", ha="right", transform=self.ax_news.transAxes 
        )

        self.ax_news.axis("off")

        # Add two horizontal lines framing the heading (top and bottom)
        self.ax_news.hlines(
            y=[1.05, 0.95], xmin=0, xmax=1,
            colors="#FFE4B5", linewidth=2, alpha=0.8,
            transform=self.ax_news.transAxes
        )

        # Split into two groups: 1–10 and 11–20
        numbered_headlines = [f"{i+1}. {headline}" for i, headline in enumerate(headlines)]
        line1 = "   |   ".join(numbered_headlines[:10])
        line2 = "   |   ".join(numbered_headlines[10:20])

        # Padding values
        self.padding_left = 0.05
        self.padding_right = 0.95

        # First line (headlines 1–10)
        self.news_text1 = self.ax_news.text(
            self.padding_right, 0.55,
            line1,
            fontsize=14,
            color="#77DD77",          # pastel green
            va="center",
            ha="left",
            transform=self.ax_news.transAxes
        )

        # Second line (headlines 11–20)
        self.news_text2 = self.ax_news.text(
            self.padding_right, 0.10,
            line2,
            fontsize=14,
            color="#77DD77",          # pastel green
            va="center",
            ha="left",
            transform=self.ax_news.transAxes
        )

        self.canvas.draw_idle()

    def reset_news_scroll(self):
        # Reset both text objects to the starting X position
        for text_obj in [getattr(self, "news_text1", None),
                        getattr(self, "news_text2", None)]:
            if text_obj is not None:
                _, y = text_obj.get_position()
                text_obj.set_position((self.padding_right, y))

        self.canvas.draw_idle()

    def scroll_news(self):
        for text_obj in [getattr(self, "news_text1", None),
                        getattr(self, "news_text2", None)]:
            if text_obj is None:
                continue

            x, y = text_obj.get_position()
            # Smaller step for smoother motion
            text_obj.set_position((x - 0.004, y))

            renderer = self.canvas.get_renderer()
            bbox_text = text_obj.get_window_extent(renderer=renderer)
            bbox_axes = self.ax_news.get_window_extent(renderer=renderer)
            text_frac = bbox_text.width / bbox_axes.width

            if x < self.padding_left - text_frac:
                text_obj.set_position((self.padding_right, y))

        self.canvas.draw_idle()
        # Slightly longer interval for smoother redraws
        self.root.after(1, self.scroll_news)

    def update_news(self):
        world_headlines = fetch_news_world()
        tech_headlines = fetch_news_tech()
        self.reset_news_scroll()
        # Combine into one list with numbering 1–20
        headlines = world_headlines + tech_headlines
        last_fetch_time = datetime.datetime.now().strftime("%A %H:%M")
        self.update_news_plot(headlines, last_fetch_time)

        # Refresh every 30 minutes (18000,00 ms)
        self.root.after(1800000, self.update_news)


    def resize_info_bg(self, event):
        width = max(event.width, 1)
        height = self.info_height
        resized = self.info_bg_orig.resize((width, height), Image.Resampling.LANCZOS)
        self.info_bg_photo = ImageTk.PhotoImage(resized)
        self.info_canvas.itemconfig(self.info_bg_item, image=self.info_bg_photo)

    def test_fireworks(self):
        # Smooth fade in
        self.fade_in_overlay()

        for i in range(5):
            self.root.after(i * 500, self.launch_rocket)

        # Smooth fade out after fireworks finish
        self.root.after(6000, self.fade_out_overlay)

        # Schedule next run
        self.root.after(10000, self.test_fireworks)

    def schedule_rockets(self):
        now = datetime.datetime.now()
        current_time = now.strftime("%H:%M")

        # List of trigger times (24-hour format)
        show = CONFIG["scheduled_show"]
        trigger_times = show.get("times", [])

        if show.get("enabled") and current_time in trigger_times:
            self.start_rocket_show()

        # Check again in 30 seconds
        self.root.after(30000, self.schedule_rockets)

    def start_rocket_show(self):
        duration = 120000  # 2 minutes in ms
        interval = 500     # launch every 0.5 seconds

        self.schedule_running = True   # disable clicks during schedule

        # Show message in top bar
        self.message_label.config(text=CONFIG["scheduled_show"].get("message", ""))
        # Fade in overlay at start
        self.fade_in_overlay()

        end_time = datetime.datetime.now() + datetime.timedelta(milliseconds=duration)

        def launch_until():
            if datetime.datetime.now() < end_time:
                self.launch_rocket()
                self.root.after(interval, launch_until)
            else:
                # Fade out overlay when show ends
                self.root.after(29000, self.fade_out_overlay)
                # Keep message for 5 seconds after fireworks end
                self.root.after(29000, lambda: self.message_label.config(text=""))
                # ✅ Reset flag so clicks work again
                self.root.after(35000, lambda: setattr(self, "schedule_running", False))

        launch_until()

    def fade_overlay(self, step=0, direction=1):
        # direction: 1 = fade in (darker), -1 = fade out (lighter)
        max_steps = 10
        alpha = step / max_steps

        # Calculate stipple density (simulate transparency)
        stipples = ["gray12", "gray25", "gray50", "gray75"]  # lighter → darker
        index = min(int(alpha * (len(stipples)-1)), len(stipples)-1)

        # Remove old overlay if exists
        if hasattr(self, "bg_overlay") and self.bg_overlay:
            self.info_canvas.delete(self.bg_overlay)

        # Draw new overlay
        self.bg_overlay = self.info_canvas.create_rectangle(
            0, 0, self.root.winfo_width(), self.info_height,
            fill="black", stipple=stipples[index], outline=""
        )

        # Continue fading
        if step < max_steps:
            self.root.after(100, lambda: self.fade_overlay(step+1, direction))
        elif direction == -1:
            # Final removal
            self.info_canvas.delete(self.bg_overlay)
            self.bg_overlay = None

    def rotate_background(self):
        """Start fading to the next background image."""
        next_index = (self.bg_index + 1) % len(self.bg_files)
        next_img = open_background(self.bg_files[next_index])

        width = max(self.info_canvas.winfo_width(), 1)
        height = self.info_height

        # Resize both current and next to the same size
        self.info_bg_orig = self.info_bg_orig.resize((width, height), Image.Resampling.LANCZOS)
        next_img = next_img.resize((width, height), Image.Resampling.LANCZOS)

        # Ensure same mode
        self.info_bg_orig = self.info_bg_orig.convert("RGBA")
        next_img = next_img.convert("RGBA")

        # Store target and index
        self.fade_step = 0
        self.fade_target = next_img
        self.fade_index = next_index
        self._fade_to_next()

    def create_overlay(self, alpha):
        # alpha: 0.0 (transparent) → 1.0 (fully dark)
        width = max(self.info_canvas.winfo_width(), 1)
        height = self.info_height
        # Cap max darkness at ~100 (out of 255)
        max_alpha = 200
        overlay = Image.new("RGBA", (width, height), (0, 0, 0, int(alpha * max_alpha)))
        return ImageTk.PhotoImage(overlay)


    def fade_in_overlay(self, step=0):
        max_steps = 20
        alpha = step / max_steps
        self.overlay_photo = self.create_overlay(alpha)

        if hasattr(self, "overlay_item") and self.overlay_item:
            # Update existing overlay
            self.info_canvas.itemconfig(self.overlay_item, image=self.overlay_photo)
            self.info_canvas.tag_raise(self.overlay_item)
        else:
            # Create overlay for the first time
            self.overlay_item = self.info_canvas.create_image(
                0, 0, anchor="nw", image=self.overlay_photo
            )
            self.info_canvas.tag_raise(self.overlay_item)

        if step < max_steps:
            self.root.after(50, lambda: self.fade_in_overlay(step+1))

    def fade_out_overlay(self, step=0):
        if not hasattr(self, "overlay_item") or not self.overlay_item:
            return  # nothing to fade out

        max_steps = 20
        alpha = 1.0 - (step / max_steps)
        self.overlay_photo = self.create_overlay(alpha)
        self.info_canvas.itemconfig(self.overlay_item, image=self.overlay_photo)
        self.info_canvas.tag_raise(self.overlay_item)

        if step < max_steps:
            self.root.after(50, lambda: self.fade_out_overlay(step+1))
        else:
            self.info_canvas.delete(self.overlay_item)
            self.overlay_item = None

    def _fade_to_next(self):
        steps = 20
        alpha = self.fade_step / steps

        # Blend with guaranteed same size/mode
        blended = Image.blend(self.info_bg_orig, self.fade_target, alpha)
        self.info_bg_photo = ImageTk.PhotoImage(blended)
        self.info_canvas.itemconfig(self.info_bg_item, image=self.info_bg_photo)

        if self.fade_step < steps:
            self.fade_step += 1
            self.root.after(100, self._fade_to_next)
        else:
            # Finish transition
            self.bg_index = self.fade_index
            self.info_bg_orig = self.fade_target
            self.root.after(10000, self.rotate_background)

    # ===== Full-screen helpers =====
    def enter_fullscreen(self):
        self.root.overrideredirect(True)
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.root.geometry(f"{sw}x{sh}+0+0")

    def exit_fullscreen(self, event=None):
        self.is_fullscreen = False
        self.root.overrideredirect(False)
        self.root.attributes("-fullscreen", False)

    def toggle_fullscreen(self, event=None):
        self.is_fullscreen = not self.is_fullscreen
        if self.is_fullscreen:
            self.enter_fullscreen()
        else:
            self.exit_fullscreen()

    def on_manual_scale(self, value):
        v = int(float(value))
        self.manual_var.set(v)
        pwm.ChangeDutyCycle(v)
        self.info_canvas.itemconfig(self.fan_text, text=f"Fan Duty: {v}% (manual)")

    def set_auto(self):
        self.manual_var.set(-1)

    def _dynamic_ylim(self, ax, data, floor=None, ceil=None, min_span=5.0, pad_frac=0.10):
        """Adjust ax y-limits to fit data with padding, optional floor/ceil clamps."""
        if not data:
            return
        ymin = min(data)
        ymax = max(data)
        # Handle NaNs gracefully
        if ymin != ymin or ymax != ymax:
            return
        span = ymax - ymin
        if span < min_span:
            # Ensure a minimal visual span
            center = (ymin + ymax) / 2.0
            ymin = center - min_span / 2.0
            ymax = center + min_span / 2.0
            span = min_span
        pad = span * pad_frac
        lo = ymin - pad
        hi = ymax + pad
        if floor is not None:
            lo = max(lo, floor)
        if ceil is not None:
            hi = min(hi, ceil)
        # Avoid inverted limits
        if hi <= lo:
            hi = lo + min_span
        ax.set_ylim(lo, hi)

    def update_clock_text(self, new_text):
        for oid in self.clock_outline:
            self.info_canvas.itemconfig(oid, text=new_text)
        self.info_canvas.itemconfig(self.clock_text, text=new_text)
    
    def update_loop(self):
        import datetime
        if not self.running:
            return

        now = datetime.datetime.now()
        temp = read_cpu_temp_c()
        fanSpd = get_fan_speed()
        #freq = read_cpu_freq_mhz()
        # duty = self.manual_var.get()
        # if duty < 0:
        #     duty = temp_to_speed(temp)
        #     pwm.ChangeDutyCycle(duty)

        # Update canvas text items directly
        self.update_clock_text(now.strftime("%A %Y-%m-%d %I:%M:%S %p"))
        self.info_canvas.itemconfig(self.temp_text, text=f"CPU: {temp:.1f}°C")
        self.info_canvas.itemconfig(self.cpu_fan_text, text=fanSpd)
        #self.info_canvas.itemconfig(self.freq_text, text=f"Clock: {freq:.0f} MHz")        
        # self.info_canvas.itemconfig(self.fan_text, text=f"Fan Duty: {d:.0f}%")

        # Append new data
        self.time_data.append(now)
        self.temp_data.append(temp)
        # self.duty_data.append(duty)

        # Keep only last 60 seconds
        cutoff = now - timedelta(seconds=60)
        while self.time_data and self.time_data[0] < cutoff:
            self.time_data.pop(0)
            self.temp_data.pop(0)
            # self.duty_data.pop(0)

        # Update line data
        self.temp_line.set_data(self.time_data, self.temp_data)
        # self.duty_line.set_data(self.time_data, self.duty_data)

        # Clear old shading
        if hasattr(self, "temp_fill") and self.temp_fill:
            self.temp_fill.remove()
            self.temp_fill = None

        # Add new shading if data exists
        if self.time_data:
            self.temp_fill = self.ax_temp.fill_between(
                self.time_data, self.temp_data, color="#e74c3c", alpha=0.3, zorder=0
            )
            avg_temp = sum(self.temp_data) / len(self.temp_data)
            self.temp_avg_line.set_data(self.time_data, [avg_temp] * len(self.time_data))
            self.info_canvas.itemconfig(self.avg_text, text=f"Avg Temp: {avg_temp:.1f}°C ")

        # Format x-axis as time
        self.ax_temp.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))
        self.ax_temp.set_xlim(now - timedelta(seconds=60), now)

        # Dynamic Y-axis scaling
        self._dynamic_ylim(self.ax_temp, self.temp_data, floor=20.0, ceil=100.0,
                        min_span=5.0, pad_frac=0.10)
        # === Animate today's date highlight ===
        import datetime, time, math

        today = datetime.date.today()

        for day_num, txt, is_current_month  in self.calendar_cells:
            if is_current_month and day_num == today.day:
                # Pulse animation on text color (yellow glow)
                pulse = (math.sin(time.time() * 3) + 1) / 2  # 0–1
                glow = 0.6 + pulse * 0.4                   # 0.5–1.0 brightness
                scale = 1.0 + pulse * 0.4

                #txt.set_color((glow, glow, 0))  # animated yellow
                txt.set_fontweight("bold")
                txt.set_fontsize(14 * scale)
            else:
                # Reset non-today cells
                txt.set_fontsize(12)
                txt.set_fontweight("normal")
                pass

        self.canvas.draw_idle()

        # Schedule next update instead of sleeping
        self.root.after(int(UPDATE_INTERVAL * 1000), self.update_loop)

    def on_close(self):
        self.running = False
        pwm.ChangeDutyCycle(0)
        pwm.stop()
        GPIO.cleanup()
        self.root.destroy()
        sys.exit(0)

def main():
    root = tk.Tk()
    FanClockApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()