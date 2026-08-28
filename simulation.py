"""
AHRS-I Instrument Panel (PyGame)
---------------------------------
Reads yaw / pitch / roll lines from the STM32L432KC over serial and renders
a live artificial horizon + heading indicator, cockpit-instrument style.

Expects each serial line as tab-separated floats in this order:
    yaw\tpitch\troll\n
which matches the firmware's printf block:
    printf("%f\t", MPU9255.yaw);
    printf("%f\t", MPU9255.pitch);
    printf("%f\t\n", MPU9255.roll);

Setup
-----
    pip install pygame pyserial

Then edit PORT_NAME below to match your Nucleo's COM port (Windows: "COM7",
macOS/Linux: something like "/dev/tty.usbmodemXXXX" or "/dev/ttyACM0"),
and run:
    python ahrs_pygame.py

If the serial port can't be opened, the panel falls back to a demo sweep
so you can check the rendering without hardware connected.
"""

import math
import sys
import time

import pygame

try:
    import serial
except ImportError:
    serial = None

# ---------------------------------------------------------------------------
# Configuration — edit these two lines for your setup
# ---------------------------------------------------------------------------
PORT_NAME = "COM7"      # <-- change to your Nucleo's COM port
BAUD_RATE = 115200

# ---------------------------------------------------------------------------
# Display / theme constants
# ---------------------------------------------------------------------------
WIDTH, HEIGHT = 920, 560
FPS = 60

COL_BG = (11, 12, 14)
COL_PANEL = (16, 17, 20)
COL_BEZEL = (38, 40, 47)
COL_BEZEL_DK = (12, 13, 16)
COL_SKY = (47, 111, 168)
COL_GROUND = (107, 74, 47)
COL_MARK = (242, 239, 230)
COL_AMBER = (232, 163, 61)
COL_DIM = (122, 127, 140)
COL_GREEN = (95, 174, 122)
COL_RED = (192, 67, 47)

GAUGE_RADIUS = 130
PX_PER_DEG = 3.0

FONT_NAME = None  # pygame default monospace-ish; swap for a .ttf if you have one


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


class SerialReader:
    """Reads yaw/pitch/roll lines from a serial port, non-blocking-ish."""

    def __init__(self, port_name, baud):
        self.ser = None
        self.buffer = ""
        self.connected = False
        if serial is None:
            print("pyserial not installed — running in demo mode. "
                  "Install with: pip install pyserial")
            return
        try:
            self.ser = serial.Serial(port_name, baud, timeout=0)
            self.connected = True
            print(f"Connected to {port_name} @ {baud} baud")
        except Exception as e:
            print(f"Could not open {port_name}: {e}\nRunning in demo mode.")

    def poll(self):
        """Returns (yaw, pitch, roll) if a full new line was parsed, else None."""
        if not self.connected:
            return None
        try:
            chunk = self.ser.read(self.ser.in_waiting or 1)
        except Exception:
            return None
        if not chunk:
            return None
        self.buffer += chunk.decode("utf-8", errors="ignore")

        result = None
        while "\n" in self.buffer:
            line, self.buffer = self.buffer.split("\n", 1)
            line = line.strip()
            if not line:
                continue
            parts = [p for p in line.split("\t") if p.strip() != ""]
            if len(parts) >= 3:
                try:
                    yaw, pitch, roll = (float(parts[0]), float(parts[1]), float(parts[2]))
                    result = (yaw, pitch, roll)
                except ValueError:
                    continue
        return result

    def close(self):
        if self.ser:
            try:
                self.ser.close()
            except Exception:
                pass


def draw_artificial_horizon(surface, center, radius, pitch, roll):
    cx, cy = center
    clip_rect = pygame.Rect(cx - radius, cy - radius, radius * 2, radius * 2)

    face = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
    fcx, fcy = radius, radius

    pitch_c = clamp(pitch, -35, 35)
    ty = pitch_c * PX_PER_DEG

    big = radius * 4
    world = pygame.Surface((big * 2, big * 2), pygame.SRCALPHA)
    wcx, wcy = big, big
    pygame.draw.rect(world, COL_SKY, (0, 0, big * 2, wcy))
    pygame.draw.rect(world, COL_GROUND, (0, wcy, big * 2, big * 2 - wcy))
    pygame.draw.line(world, COL_MARK, (0, wcy), (big * 2, wcy), 2)

    for d in range(-30, 31, 10):
        if d == 0:
            continue
        y = wcy - d * PX_PER_DEG
        halfw = 30 if d % 20 == 0 else 16
        pygame.draw.line(world, COL_MARK, (wcx - halfw, y), (wcx + halfw, y), 2)
        if d % 20 == 0:
            f = pygame.font.SysFont(FONT_NAME, 14)
            lbl = f.render(str(abs(d)), True, COL_MARK)
            world.blit(lbl, (wcx - halfw - 24, y - 8))
            world.blit(lbl, (wcx + halfw + 8, y - 8))

    rotated = pygame.transform.rotate(world, roll)
    rw, rh = rotated.get_size()
    dest_x = fcx - rw / 2
    dest_y = fcy - rh / 2 + ty * math.cos(math.radians(roll))
    dest_x += ty * math.sin(math.radians(roll))
    face.blit(rotated, (dest_x, dest_y))

    mask = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
    pygame.draw.circle(mask, (255, 255, 255, 255), (fcx, fcy), radius)
    face.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)

    for a in range(-60, 61, 10):
        rad = math.radians(a - 90)
        outer = radius - 6
        inner = radius - 18 if a % 30 == 0 else radius - 12
        x1 = fcx + outer * math.cos(rad)
        y1 = fcy + outer * math.sin(rad)
        x2 = fcx + inner * math.cos(rad)
        y2 = fcy + inner * math.sin(rad)
        pygame.draw.line(face, COL_MARK, (x1, y1), (x2, y2), 3 if a == 0 else 2)

    ptr_ang = math.radians(-roll)
    tip = (fcx + (radius - 24) * math.sin(ptr_ang) * -1, fcy - (radius - 24) * math.cos(ptr_ang))
    # simpler: pointer fixed at top, rotates with -roll around center
    p1 = rotate_point((fcx, fcy - radius + 6), (fcx, fcy), roll)
    p2 = rotate_point((fcx - 6, fcy - radius + 18), (fcx, fcy), roll)
    p3 = rotate_point((fcx + 6, fcy - radius + 18), (fcx, fcy), roll)
    pygame.draw.polygon(face, COL_AMBER, [p1, p2, p3])

    pygame.draw.line(face, (17, 17, 17), (fcx - 30, fcy), (fcx - 10, fcy), 5)
    pygame.draw.line(face, (17, 17, 17), (fcx + 10, fcy), (fcx + 30, fcy), 5)
    pygame.draw.line(face, COL_AMBER, (fcx - 30, fcy), (fcx - 10, fcy), 3)
    pygame.draw.line(face, COL_AMBER, (fcx + 10, fcy), (fcx + 30, fcy), 3)
    pygame.draw.circle(face, COL_AMBER, (fcx, fcy), 4)
    pygame.draw.circle(face, (17, 17, 17), (fcx, fcy), 4, 1)

    surface.blit(face, (cx - radius, cy - radius))
    draw_bezel(surface, center, radius)


def rotate_point(pt, origin, angle_deg):
    ox, oy = origin
    px, py = pt
    a = math.radians(-angle_deg)
    dx, dy = px - ox, py - oy
    rx = dx * math.cos(a) - dy * math.sin(a)
    ry = dx * math.sin(a) + dy * math.cos(a)
    return (ox + rx, oy + ry)


def draw_bezel(surface, center, radius):
    cx, cy = center
    pygame.draw.circle(surface, COL_BEZEL, (cx, cy), radius + 12, 8)
    pygame.draw.circle(surface, COL_BEZEL_DK, (cx, cy), radius + 4, 2)


def draw_heading_indicator(surface, center, radius, yaw):
    cx, cy = center
    face = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
    fcx, fcy = radius, radius

    pygame.draw.circle(face, (17, 19, 24), (fcx, fcy), radius)

    labels = {0: "N", 45: "NE", 90: "E", 135: "SE", 180: "S", 225: "SW", 270: "W", 315: "NW"}
    f_major = pygame.font.SysFont(FONT_NAME, 18, bold=True)
    f_minor = pygame.font.SysFont(FONT_NAME, 11)

    for a in range(0, 360, 15):
        disp_a = a - yaw
        rad = math.radians(disp_a - 90)
        major = a % 90 == 0
        semi = a % 45 == 0
        outer = radius - 6
        inner = radius - 20 if major else (radius - 14 if semi else radius - 10)
        x1 = fcx + outer * math.cos(rad)
        y1 = fcy + outer * math.sin(rad)
        x2 = fcx + inner * math.cos(rad)
        y2 = fcy + inner * math.sin(rad)
        pygame.draw.line(face, COL_MARK, (x1, y1), (x2, y2), 3 if major else 1)

        if a in labels:
            lx = fcx + (radius - 32) * math.cos(rad)
            ly = fcy + (radius - 32) * math.sin(rad)
            col = COL_AMBER if labels[a] == "N" else COL_MARK
            txt = f_major.render(labels[a], True, col)
            face.blit(txt, (lx - txt.get_width() / 2, ly - txt.get_height() / 2))
        elif a % 30 == 0:
            lx = fcx + (radius - 36) * math.cos(rad)
            ly = fcy + (radius - 36) * math.sin(rad)
            txt = f_minor.render(str(a), True, COL_DIM)
            face.blit(txt, (lx - txt.get_width() / 2, ly - txt.get_height() / 2))

    pygame.draw.polygon(
        face, COL_AMBER,
        [(fcx, fcy - radius + 6), (fcx - 8, fcy - radius + 22), (fcx + 8, fcy - radius + 22)]
    )
    pygame.draw.circle(face, COL_AMBER, (fcx, fcy), 4)
    pygame.draw.circle(face, (17, 17, 17), (fcx, fcy), 4, 1)

    mask = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
    pygame.draw.circle(mask, (255, 255, 255, 255), (fcx, fcy), radius)
    face.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)

    surface.blit(face, (cx - radius, cy - radius))
    draw_bezel(surface, center, radius)


def draw_readouts(surface, font_label, font_val, yaw, pitch, roll):
    items = [("PITCH", f"{pitch:6.1f}", "deg"), ("ROLL", f"{roll:6.1f}", "deg"),
             ("HEADING", f"{yaw % 360:6.1f}", "deg")]
    total_w = 260 * len(items)
    start_x = WIDTH / 2 - total_w / 2
    y = HEIGHT - 74
    for i, (label, val, unit) in enumerate(items):
        x = start_x + i * 260
        lbl_s = font_label.render(label, True, COL_DIM)
        val_s = font_val.render(val, True, COL_AMBER)
        unit_s = font_label.render(unit, True, COL_DIM)
        surface.blit(lbl_s, (x + 130 - lbl_s.get_width() / 2, y))
        surface.blit(val_s, (x + 130 - val_s.get_width() / 2, y + 20))
        surface.blit(unit_s, (x + 130 + val_s.get_width() / 2 + 6, y + 30))
        if i < len(items) - 1:
            pygame.draw.line(surface, (36, 38, 44), (x + 250, y - 4), (x + 250, y + 50), 1)


def draw_status(surface, font, connected):
    txt = "LIVE — CONNECTED" if connected else "DEMO MODE"
    col = COL_GREEN if connected else COL_AMBER
    dot_col = col
    pygame.draw.circle(surface, dot_col, (WIDTH - 190, 34), 5)
    s = font.render(txt, True, COL_DIM)
    surface.blit(s, (WIDTH - 175, 27))


def main():
    pygame.init()
    pygame.display.set_caption("AHRS-I Instrument Panel")
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    clock = pygame.time.Clock()

    font_title = pygame.font.SysFont(FONT_NAME, 22, bold=True)
    font_sub = pygame.font.SysFont(FONT_NAME, 13)
    font_label = pygame.font.SysFont(FONT_NAME, 12)
    font_val = pygame.font.SysFont(FONT_NAME, 24, bold=True)
    font_status = pygame.font.SysFont(FONT_NAME, 13)

    reader = SerialReader(PORT_NAME, BAUD_RATE)

    yaw, pitch, roll = 0.0, 0.0, 0.0
    demo_t = 0.0

    running = True
    while running:
        dt = clock.tick(FPS) / 1000.0

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False

        reading = reader.poll()
        if reading is not None:
            yaw, pitch, roll = reading
        elif not reader.connected:
            demo_t += dt
            pitch = math.sin(demo_t * 0.6) * 18
            roll = math.sin(demo_t * 0.4 + 1) * 28
            yaw = (demo_t * 14) % 360

        screen.fill(COL_BG)

        title = font_title.render("AHRS-I", True, COL_MARK)
        screen.blit(title, (24, 20))
        sub = font_sub.render("STM32L432KC / MPU9250 - live attitude & heading", True, COL_DIM)
        screen.blit(sub, (24, 46))
        draw_status(screen, font_status, reader.connected)

        gap = 100
        cy = HEIGHT / 2 - 10
        cx1 = WIDTH / 2 - GAUGE_RADIUS - gap / 2
        cx2 = WIDTH / 2 + GAUGE_RADIUS + gap / 2

        lbl1 = font_label.render("ARTIFICIAL HORIZON", True, COL_DIM)
        lbl2 = font_label.render("HEADING INDICATOR", True, COL_DIM)
        screen.blit(lbl1, (cx1 - lbl1.get_width() / 2, cy - GAUGE_RADIUS - 34))
        screen.blit(lbl2, (cx2 - lbl2.get_width() / 2, cy - GAUGE_RADIUS - 34))

        draw_artificial_horizon(screen, (cx1, cy), GAUGE_RADIUS, pitch, roll)
        draw_heading_indicator(screen, (cx2, cy), GAUGE_RADIUS, yaw)

        draw_readouts(screen, font_label, font_val, yaw, pitch, roll)

        pygame.display.flip()

    reader.close()
    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()