from __future__ import annotations

import json
import math
import os
import platform
import random
import subprocess
import sys
import threading
import time
from pathlib import Path

import psutil

from PyQt6.QtCore import (
    QEasingCurve, QMimeData, QObject, QPointF, QRectF, QSize, Qt,
    QTimer, QUrl, pyqtSignal,
)
from PyQt6.QtGui import (
    QBrush, QColor, QDragEnterEvent, QDropEvent, QFont, QFontDatabase,
    QKeySequence, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap,
    QRadialGradient, QShortcut,
)
from PyQt6.QtWidgets import (
    QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QPushButton, QScrollArea, QSizePolicy, QTextEdit,
    QVBoxLayout, QWidget, QProgressBar,
)

def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent

BASE_DIR   = _base_dir()
CONFIG_DIR = BASE_DIR / "config"
API_FILE   = CONFIG_DIR / "api_keys.json"

_DEFAULT_W, _DEFAULT_H = 1280, 780
_MIN_W,     _MIN_H     = 1040, 640
_LEFT_W  = 220
_RIGHT_W = 288

_OS = platform.system()  # "Windows" | "Darwin" | "Linux"


class C:
    BG        = "#02030a"
    PANEL     = "rgba(4, 14, 24, 205)"
    PANEL2    = "rgba(8, 22, 36, 190)"
    BORDER    = "#17465f"
    BORDER_B  = "#20d7ff"
    BORDER_A  = "#7657ff"
    PRI       = "#18e5ff"
    PRI_DIM   = "#078aa8"
    PRI_GHO   = "#042b44"
    PURPLE    = "#9b5cff"
    PINK      = "#ff4fd8"
    ACC       = "#ff3d7f"
    ACC2      = "#ffc857"
    GREEN     = "#50ffb1"
    GREEN_D   = "#00aa55"
    RED       = "#ff3355"
    MUTED_C   = "#ff3366"
    TEXT      = "#9af7ff"
    TEXT_DIM  = "#5d8b9f"
    TEXT_MED  = "#7fd7ea"
    WHITE     = "#e8fbff"
    DARK      = "rgba(1, 5, 12, 185)"
    BAR_BG    = "#071625"


def qcol(h: str, a: int = 255) -> QColor:
    c = QColor(h); c.setAlpha(a); return c

class AnimatedBackground(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._tick = 0
        self._stars = [[random.random(), random.random(), random.uniform(0.12, 0.42), random.uniform(0.35, 1.1)] for _ in range(85)]
        self._particles = [[random.random(), random.random(), random.uniform(0.08, 0.28), random.uniform(0.8, 1.8)] for _ in range(38)]
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._step)
        self._timer.start(33)

    def _step(self):
        self._tick += 1
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        p.fillRect(self.rect(), QColor("#05070B"))

        t = self._tick * 0.012
        soft = QLinearGradient(0, 0, W, H)
        soft.setColorAt(0.0, QColor(5, 7, 11, 0))
        soft.setColorAt(0.45, QColor(12, 20, 36, 38 + int(14 * math.sin(t))))
        soft.setColorAt(1.0, QColor(12, 5, 28, 42))
        p.fillRect(self.rect(), QBrush(soft))

        for x, y, r, col in [
            (W * (0.12 + 0.025 * math.sin(t)), H * 0.12, W * 0.52, QColor(0, 210, 255, 72)),
            (W * (0.88 + 0.018 * math.cos(t * 0.7)), H * 0.90, W * 0.58, QColor(143, 83, 255, 78)),
        ]:
            rg = QRadialGradient(QPointF(x, y), r)
            rg.setColorAt(0.0, col)
            rg.setColorAt(0.45, QColor(col.red(), col.green(), col.blue(), col.alpha() // 3))
            rg.setColorAt(1.0, QColor(0, 0, 0, 0))
            p.fillRect(self.rect(), QBrush(rg))

        p.setPen(Qt.PenStyle.NoPen)
        for sx, sy, speed, size in self._particles:
            x = (sx * W + math.sin(t + sy * 8) * 18) % W
            y = (sy * H + self._tick * speed * 0.22) % H
            p.setBrush(QBrush(QColor(120, 235, 255, 32)))
            p.drawEllipse(QPointF(x, y), size, size)

        for sx, sy, speed, size in self._stars:
            alpha = 32 + int(46 * (0.5 + 0.5 * math.sin(self._tick * speed * 0.035 + sx * 11)))
            p.setBrush(QBrush(QColor(230, 248, 255, alpha)))
            p.drawEllipse(QPointF(sx * W, sy * H), size, size)

class _SysMetrics:
    def __init__(self):
        self.cpu  = 0.0
        self.mem  = 0.0
        self.net  = 0.0   
        self.gpu  = -1.0  
        self.tmp  = -1.0  
        self._lock = threading.Lock()
        self._last_net = psutil.net_io_counters()
        self._last_net_t = time.time()
        self._running = True
        t = threading.Thread(target=self._loop, daemon=True)
        t.start()

    def _loop(self):
        while self._running:
            try:
                self._update()
            except Exception:
                pass
            time.sleep(1.5)

    def _update(self):
        cpu = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory().percent

        nc  = psutil.net_io_counters()
        now = time.time()
        dt  = now - self._last_net_t
        if dt > 0:
            sent = (nc.bytes_sent - self._last_net.bytes_sent) / dt
            recv = (nc.bytes_recv - self._last_net.bytes_recv) / dt
            net  = (sent + recv) / (1024 * 1024)
        else:
            net = 0.0
        self._last_net   = nc
        self._last_net_t = now

        gpu = self._get_gpu()

        tmp = self._get_temp()

        with self._lock:
            self.cpu = cpu
            self.mem = mem
            self.net = net
            self.gpu = gpu
            self.tmp = tmp

    def _get_gpu(self) -> float:
        # NVIDIA
        try:
            r = subprocess.run(
                ["nvidia-smi", "--query-gpu=utilization.gpu",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=2
            )
            if r.returncode == 0:
                vals = [float(v.strip()) for v in r.stdout.strip().split("\n") if v.strip()]
                if vals:
                    return sum(vals) / len(vals)
        except Exception:
            pass

        # AMD (Linux)
        if _OS == "Linux":
            try:
                r = subprocess.run(
                    ["rocm-smi", "--showuse", "--csv"],
                    capture_output=True, text=True, timeout=2
                )
                if r.returncode == 0:
                    for line in r.stdout.strip().split("\n"):
                        parts = line.split(",")
                        if len(parts) >= 2:
                            try:
                                return float(parts[1].strip().replace("%", ""))
                            except ValueError:
                                pass
            except Exception:
                pass

            # Intel GPU (Linux)
            try:
                r = subprocess.run(
                    ["intel_gpu_top", "-J", "-s", "500"],
                    capture_output=True, text=True, timeout=1
                )
                if r.returncode == 0 and "Render/3D" in r.stdout:
                    import re
                    m = re.search(r'"busy":\s*([\d.]+)', r.stdout)
                    if m:
                        return float(m.group(1))
            except Exception:
                pass

        # macOS powermetrics GPU Engine
        if _OS == "Darwin":
            try:
                r = subprocess.run(
                    ["sudo", "-n", "powermetrics", "-n", "1", "-i", "500",
                     "--samplers", "gpu_power"],
                    capture_output=True, text=True, timeout=2
                )
                if r.returncode == 0 and "GPU" in r.stdout:
                    import re
                    m = re.search(r'GPU\s+Active:\s+([\d.]+)%', r.stdout)
                    if m:
                        return float(m.group(1))
            except Exception:
                pass

        return -1.0

    def _get_temp(self) -> float:
        try:
            temps = psutil.sensors_temperatures()
            candidates = ["coretemp", "k10temp", "cpu_thermal", "acpitz",
                          "cpu-thermal", "zenpower", "it8688"]
            for name in candidates:
                if name in temps:
                    entries = temps[name]
                    if entries:
                        return entries[0].current
            for entries in temps.values():
                if entries:
                    return entries[0].current
        except Exception:
            pass
        if _OS == "Darwin":
            try:
                r = subprocess.run(
                    ["osx-cpu-temp"], capture_output=True, text=True, timeout=2
                )
                if r.returncode == 0:
                    import re
                    m = re.search(r"([\d.]+)", r.stdout)
                    if m:
                        return float(m.group(1))
            except Exception:
                pass

        if _OS == "Windows":
            try:
                r = subprocess.run(
                    ["powershell", "-Command",
                     "(Get-WmiObject MSAcpi_ThermalZoneTemperature -Namespace root/wmi).CurrentTemperature"],
                    capture_output=True, text=True, timeout=3
                )
                if r.returncode == 0 and r.stdout.strip():
                    raw = float(r.stdout.strip().split("\n")[0])
                    return (raw / 10.0) - 273.15
            except Exception:
                pass

        return -1.0

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "cpu": self.cpu,
                "mem": self.mem,
                "net": self.net,
                "gpu": self.gpu,
                "tmp": self.tmp,
            }


_metrics = _SysMetrics()

class HudCanvas(QWidget):
    def __init__(self, face_path: str, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMinimumSize(560, 560)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.muted    = False
        self.speaking = False
        self.user_active = False
        self._user_active_until = 0.0
        self.state    = "INITIALISING"
        self.mode     = "Normal Mode"

        self._tick       = 0
        self._scale      = 1.0
        self._tgt_scale  = 1.0
        self._halo       = 55.0
        self._tgt_halo   = 55.0
        self._last_t     = time.time()
        self._scan       = 0.0
        self._scan2      = 180.0
        self._rings      = [0.0, 120.0, 240.0]
        self._pulses: list[float] = [0.0, 50.0, 100.0]
        self._blink      = True
        self._blink_tick = 0
        self._particles: list[list[float]] = []
        self._face_px: QPixmap | None = None
        self._load_face(face_path)

        self._tmr = QTimer(self)
        self._tmr.timeout.connect(self._step)
        self._tmr.start(16)

    def set_user_active(self, active: bool, hold_ms: int = 420):
        self.user_active = bool(active)
        if active:
            self._user_active_until = time.time() + hold_ms / 1000.0
        self.update()

    def _motion_active(self) -> bool:
        if self.user_active and time.time() <= self._user_active_until:
            return True
        if self.user_active and time.time() > self._user_active_until:
            self.user_active = False
        return False

    def _mode_color(self) -> str:
        mode = (self.mode or "").lower()
        state = (self.state or "").lower()
        if "error" in state:
            return C.RED
        if "gaming" in mode:
            return C.PURPLE
        if "productive" in mode or "work" in mode or "focus" in mode:
            return C.PRI
        if "listener" in mode or "friend" in mode:
            return C.GREEN
        return C.PRI

    def _load_face(self, path: str):
        try:
            from PIL import Image, ImageDraw
            import io
            img = Image.open(path).convert("RGBA")
            sz  = min(img.size)
            img = img.resize((sz, sz), Image.LANCZOS)
            mk  = Image.new("L", (sz, sz), 0)
            ImageDraw.Draw(mk).ellipse((2, 2, sz - 2, sz - 2), fill=255)
            img.putalpha(mk)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            px = QPixmap(); px.loadFromData(buf.getvalue())
            self._face_px = px
        except Exception:
            self._face_px = None

    def _step(self):
        self._tick += 1
        now = time.time()
        motion = self._motion_active()
        speaking_glow = self.speaking

        if now - self._last_t > (0.12 if motion else 0.7):
            if motion:
                self._tgt_scale = random.uniform(1.045, 1.10)
                self._tgt_halo  = random.uniform(135, 180)
            elif self.muted:
                self._tgt_scale = 1.0
                self._tgt_halo  = 18
            elif speaking_glow:
                self._tgt_scale = random.uniform(1.01, 1.025)
                self._tgt_halo  = random.uniform(80, 115)
            else:
                self._tgt_scale = 1.0
                self._tgt_halo  = 48
            self._last_t = now

        sp = 0.34 if motion else 0.10
        self._scale += (self._tgt_scale - self._scale) * sp
        self._halo  += (self._tgt_halo  - self._halo)  * sp

        if motion:
            for i, spd in enumerate([1.7, -1.15, 2.35]):
                self._rings[i] = (self._rings[i] + spd) % 360
            self._scan  = (self._scan  + 3.2) % 360
            self._scan2 = (self._scan2 - 2.1) % 360

            fw  = min(self.width(), self.height())
            lim = fw * 0.74
            self._pulses = [r + 4.8 for r in self._pulses if r + 4.8 < lim]
            if len(self._pulses) < 3 and random.random() < 0.10:
                self._pulses.append(0.0)

            if random.random() < 0.24:
                cx, cy = self.width() / 2, self.height() / 2
                ang = random.uniform(0, 2 * math.pi)
                r_s = fw * 0.28
                self._particles.append([
                    cx + math.cos(ang) * r_s, cy + math.sin(ang) * r_s,
                    math.cos(ang) * random.uniform(0.9, 2.4),
                    math.sin(ang) * random.uniform(0.9, 2.4) - 0.4, 1.0,
                ])
        else:
            self._pulses = [r * 0.985 for r in self._pulses if r > 8]

        self._particles = [
            [p[0]+p[2], p[1]+p[3], p[2]*0.97, p[3]*0.97, p[4]-0.028]
            for p in self._particles if p[4] > 0
        ]

        self._blink_tick += 1
        if self._blink_tick >= 38:
            self._blink = not self._blink
            self._blink_tick = 0
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(0, 0, 0, 0))

        W, H = self.width(), self.height()
        cx, cy = W / 2, H / 2
        fw = min(W, H)
        mode_col = self._mode_color()
        motion = self._motion_active()

        # grid dots
        p.setPen(QPen(qcol(C.PRI_GHO), 1))
        for x in range(0, 0, 48):
            for y in range(0, 0, 48):
                p.drawPoint(x, y)

        r_face = fw * 0.36

        # halo glow
        for i in range(10):
            r   = r_face * (1.8 - i * 0.08)
            frc = 1.0 - i / 10
            a   = max(0, min(255, int(self._halo * 0.085 * frc)))
            col = qcol(C.MUTED_C if self.muted else mode_col, a)
            p.setPen(QPen(col, 1.5)); p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))

        # pulse rings
        for pr in self._pulses:
            a   = max(0, int((230 if motion else 70) * (1.0 - pr / (fw * 0.74))))
            col = qcol(C.MUTED_C if self.muted else mode_col, a)
            p.setPen(QPen(col, 1.5)); p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QRectF(cx - pr, cy - pr, pr * 2, pr * 2))

        # spinning arc rings
        for idx, (r_frac, w_r, arc_l, gap) in enumerate(
            [(0.48, 3, 115, 78), (0.40, 2, 78, 55), (0.32, 1, 56, 40)]
        ):
            ring_r = fw * r_frac
            base   = self._rings[idx]
            a_val  = max(0, min(255, int(self._halo * (1.0 - idx * 0.18))))
            col    = qcol(C.MUTED_C if self.muted else mode_col, a_val)
            p.setPen(QPen(col, w_r)); p.setBrush(Qt.BrushStyle.NoBrush)
            angle = base
            rect  = QRectF(cx - ring_r, cy - ring_r, ring_r * 2, ring_r * 2)
            while angle < base + 360:
                p.drawArc(rect, int(angle * 16), int(arc_l * 16))
                angle += arc_l + gap

        # scanners
        sr = fw * 0.50
        sa = min(255, int(self._halo * 1.5))
        ex = 75 if motion else 38
        p.setPen(QPen(qcol(C.MUTED_C if self.muted else mode_col, sa), 2.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        srect = QRectF(cx - sr, cy - sr, sr * 2, sr * 2)
        p.drawArc(srect, int(self._scan * 16), int(ex * 16))
        p.setPen(QPen(qcol(C.ACC, sa // 2), 1.5))
        p.drawArc(srect, int(self._scan2 * 16), int(ex * 16))

        # tick marks
        t_out, t_in = fw * 0.497, fw * 0.474
        p.setPen(QPen(qcol(mode_col, 140), 1))
        for deg in range(0, 0, 10):
            rad = math.radians(deg)
            inn = t_in if deg % 30 == 0 else t_in + 6
            p.drawLine(
                QPointF(cx + t_out * math.cos(rad), cy - t_out * math.sin(rad)),
                QPointF(cx + inn  * math.cos(rad), cy - inn  * math.sin(rad)),
            )

        # crosshair
        ch_r, gap_h = fw * 0.51, fw * 0.16
        p.setPen(QPen(qcol(mode_col, 0), 1))
        p.drawLine(QPointF(cx - ch_r, cy), QPointF(cx - gap_h, cy))
        p.drawLine(QPointF(cx + gap_h, cy), QPointF(cx + ch_r, cy))
        p.drawLine(QPointF(cx, cy - ch_r), QPointF(cx, cy - gap_h))
        p.drawLine(QPointF(cx, cy + gap_h), QPointF(cx, cy + ch_r))

        # corner brackets
        bl = 24
        bc = qcol(C.PRI, 0)
        hl, hr = cx - fw // 2, cx + fw // 2
        ht, hb = cy - fw // 2, cy + fw // 2
        p.setPen(QPen(bc, 2))
        for bx, by, dx, dy in [(hl,ht,1,1),(hr,ht,-1,1),(hl,hb,1,-1),(hr,hb,-1,-1)]:
            p.drawLine(QPointF(bx, by), QPointF(bx + dx * bl, by))
            p.drawLine(QPointF(bx, by), QPointF(bx, by + dy * bl))

        # face
        if self._face_px:
            fsz    = int(fw * 0.72 * self._scale)
            scaled = self._face_px.scaled(
                fsz, fsz,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            p.drawPixmap(int(cx - fsz / 2), int(cy - fsz / 2), scaled)
        else:
            orb_r = int(fw * 0.33 * self._scale)
            oc    = (200, 0, 50) if self.muted else (0, 60, 110)
            for i in range(8, 0, -1):
                r2  = int(orb_r * i / 8)
                frc = i / 8
                a   = max(0, min(255, int(self._halo * 1.1 * frc)))
                p.setBrush(QBrush(QColor(int(oc[0]*frc), int(oc[1]*frc), int(oc[2]*frc), a)))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawEllipse(QRectF(cx - r2, cy - r2, r2 * 2, r2 * 2))
            p.setPen(QPen(qcol(mode_col, min(255, int(self._halo * 2))), 1))
            p.setFont(QFont("Courier New", 13, QFont.Weight.Bold))
            p.drawText(QRectF(cx - 80, cy - 14, 160, 28),
                       Qt.AlignmentFlag.AlignCenter, "REVO")

        # particles
        for pt in self._particles:
            a = max(0, min(255, int(pt[4] * 255)))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(qcol(mode_col, a)))
            p.drawEllipse(QPointF(pt[0], pt[1]), 2.5, 2.5)

        # waveform only; text status is shown once below the radar.
        sy = cy + fw * 0.40
        # waveform
        wy = sy + 30
        N, bw = 36, 8
        wx0 = (W - N * bw) / 2
        for i in range(N):
            if self.muted:
                hgt, cl = 2, qcol(C.MUTED_C)
            elif motion:
                hgt = random.randint(4, 24)
                cl  = qcol(mode_col) if hgt > 12 else qcol(C.PRI_DIM)
            else:
                hgt = 2
                cl  = qcol(C.BORDER, 120)
            p.fillRect(QRectF(wx0 + i * bw, wy + 20 - hgt, bw - 1, hgt), cl)

class MetricBar(QWidget):

    def __init__(self, label: str, color: str = C.PRI, parent=None):
        super().__init__(parent)
        self._label = label
        self._color = color
        self._value = 0.0       # 0-100
        self._text  = "--"
        self.setFixedHeight(44)
        self.setMinimumWidth(80)

    def set_value(self, pct: float, text: str):
        self._value = max(0.0, min(100.0, pct))
        self._text  = text
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()

        p.setBrush(QBrush(QColor(255, 255, 255, 18)))
        p.setPen(QPen(QColor(255, 255, 255, 22), 1))
        p.drawRoundedRect(QRectF(1, 1, W - 2, H - 2), 14, 14)

        bar_h = 7
        bar_y = H - bar_h - 9
        bar_w = W - 18
        bar_x = 9
        fill_w = int(bar_w * self._value / 100)

        p.setBrush(QBrush(QColor(255, 255, 255, 22)))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRectF(bar_x, bar_y, bar_w, bar_h), 4, 4)

        if fill_w > 0:
            grad = QLinearGradient(bar_x, 0, bar_x + bar_w, 0)
            grad.setColorAt(0.0, QColor(C.PRI))
            grad.setColorAt(1.0, QColor(C.PURPLE))
            p.setBrush(QBrush(grad))
            p.drawRoundedRect(QRectF(bar_x, bar_y, fill_w, bar_h), 4, 4)

        p.setFont(QFont("Inter", 8, QFont.Weight.Bold))
        p.setPen(QPen(QColor(210, 235, 244, 185), 1))
        p.drawText(QRectF(10, 6, 80, 17), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self._label)

        p.setFont(QFont("Space Grotesk", 10, QFont.Weight.Bold))
        p.setPen(QPen(QColor(235, 250, 255, 230), 1))
        p.drawText(QRectF(0, 5, W - 10, 18), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, self._text)


class LogWidget(QTextEdit):
    _sig = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setFont(QFont("Inter", 9))
        self.setStyleSheet(f"""
            QTextEdit {{
                background: rgba(255, 255, 255, 18);
                color: {C.WHITE};
                border: 1px solid rgba(255, 255, 255, 22);
                border-radius: 18px;
                padding: 10px;
                selection-background-color: rgba(24, 229, 255, 55);
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 8px;
                border: none;
            }}
            QScrollBar::handle:vertical {{
                background: rgba(255, 255, 255, 45);
                border-radius: 4px;
                min-height: 20px;
            }}
        """)
        self._queue: list[str] = []
        self._typing  = False
        self._text    = ""
        self._pos     = 0
        self._tag     = "sys"
        self._sig.connect(self._enqueue)

    def append_log(self, text: str):
        self._sig.emit(text)

    def _enqueue(self, text: str):
        self._append_bubble(text)

    def _clean_html(self, text: str) -> str:
        return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")

    def _append_bubble(self, text: str):
        tl = (text or "").lower()
        if tl.startswith("you:"):
            who, bg, border, align = "You", "rgba(255,255,255,0.10)", "rgba(255,255,255,0.12)", "right"
            body = text[4:].strip()
        elif tl.startswith("revo:"):
            who, bg, border, align = "REVO", "rgba(24,229,255,0.12)", "rgba(24,229,255,0.18)", "left"
            body = text[5:].strip()
        elif "err" in tl:
            who, bg, border, align = "System", "rgba(255,51,85,0.13)", "rgba(255,51,85,0.22)", "left"
            body = text
        else:
            who, bg, border, align = "Activity", "rgba(155,92,255,0.10)", "rgba(255,255,255,0.10)", "left"
            body = text
        html = (
            f'<div align="{align}" style="margin:8px 0;">'
            f'<div style="display:inline-block; max-width:86%; background:{bg}; border:1px solid {border}; border-radius:16px; padding:10px 12px;">'
            f'<div style="font-family:Inter; font-size:10px; color:#9fb6c8; margin-bottom:4px;">{who}</div>'
            f'<div style="font-family:Inter; font-size:13px; color:#eefcff; line-height:1.35;">{self._clean_html(body)}</div>'
            f'</div></div>'
        )
        self.moveCursor(self.textCursor().MoveOperation.End)
        self.insertHtml(html)
        self.insertHtml("<div style='height:4px;'></div>")
        self.ensureCursorVisible()


_FILE_ICONS = {
    "image":   ("IMG", "#00d4ff"), "video":   ("VID", "#ff6b00"),
    "audio":   ("AUD", "#cc44ff"), "pdf":     ("PDF", "#ff4444"),
    "word":    ("DOC", "#4488ff"), "excel":   ("XLS", "#44bb44"),
    "code":    ("CODE", "#ffcc00"), "archive": ("ZIP", "#ff8844"),
    "pptx":    ("PPT", "#ff6622"), "text":    ("TXT", "#aaaaaa"),
    "data":    ("DATA", "#88ddff"), "unknown": ("FILE", "#888888"),
}
_EXT_TO_CAT = {
    **dict.fromkeys(["jpg","jpeg","png","gif","webp","bmp","tiff","svg","ico"], "image"),
    **dict.fromkeys(["mp4","avi","mov","mkv","wmv","flv","webm","m4v"],         "video"),
    **dict.fromkeys(["mp3","wav","ogg","m4a","aac","flac","wma","opus"],        "audio"),
    **dict.fromkeys(["pdf"],                                                     "pdf"),
    **dict.fromkeys(["doc","docx"],                                              "word"),
    **dict.fromkeys(["xls","xlsx","ods"],                                        "excel"),
    **dict.fromkeys(["ppt","pptx"],                                              "pptx"),
    **dict.fromkeys(["py","js","ts","jsx","tsx","html","css","java","c","cpp",
                     "cs","go","rs","rb","php","swift","kt","sh","sql","lua"],   "code"),
    **dict.fromkeys(["zip","rar","tar","gz","7z","bz2","xz"],                   "archive"),
    **dict.fromkeys(["txt","md","rst","log"],                                    "text"),
    **dict.fromkeys(["csv","tsv","json","xml"],                                  "data"),
}

def _file_category(path: Path) -> str:
    return _EXT_TO_CAT.get(path.suffix.lower().lstrip("."), "unknown")

def _fmt_size(size: int) -> str:
    if   size < 1024:    return f"{size} B"
    elif size < 1024**2: return f"{size/1024:.1f} KB"
    elif size < 1024**3: return f"{size/1024**2:.1f} MB"
    else:                return f"{size/1024**3:.1f} GB"


class FileDropZone(QWidget):
    file_selected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(100)
        self._current_file: str | None = None
        self._hovering  = False
        self._drag_over = False
        self._dash_offset = 0.0
        self._anim_tmr = QTimer(self)
        self._anim_tmr.timeout.connect(self._animate)
        self._anim_tmr.start(40)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._canvas = _DropCanvas(self)
        layout.addWidget(self._canvas)

    def _animate(self):
        self._dash_offset = (self._dash_offset + 0.8) % 20
        self._canvas.update()

    def dragEnterEvent(self, e: QDragEnterEvent):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self._drag_over = True; self._canvas.update()

    def dragLeaveEvent(self, e):
        self._drag_over = False; self._canvas.update()

    def dropEvent(self, e: QDropEvent):
        self._drag_over = False
        urls = e.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if Path(path).is_file():
                self._set_file(path)
        self._canvas.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._browse()

    def enterEvent(self, e):
        self._hovering = True; self._canvas.update()

    def leaveEvent(self, e):
        self._hovering = False; self._canvas.update()

    def current_file(self) -> str | None:
        return self._current_file

    def clear_file(self):
        self._current_file = None; self._canvas.update()

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select a file for REVO", str(Path.home()),
            "All Files (*.*);;"
            "Images (*.jpg *.jpeg *.png *.gif *.webp *.bmp *.svg);;"
            "Documents (*.pdf *.docx *.txt *.md *.pptx);;"
            "Data (*.csv *.xlsx *.json *.xml);;"
            "Code (*.py *.js *.ts *.html *.css *.java *.cpp *.go);;"
            "Audio (*.mp3 *.wav *.ogg *.m4a *.aac *.flac);;"
            "Video (*.mp4 *.avi *.mov *.mkv *.wmv *.webm);;"
            "Archives (*.zip *.rar *.tar *.gz *.7z)",
        )
        if path:
            self._set_file(path)

    def _set_file(self, path: str):
        self._current_file = path
        self._canvas.update()
        self.file_selected.emit(path)


class _DropCanvas(QWidget):
    def __init__(self, zone: FileDropZone):
        super().__init__(zone)
        self._z = zone

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        z    = self._z
        W, H = self.width(), self.height()
        pad  = 6
        rect = QRectF(pad, pad, W - pad * 2, H - pad * 2)

        bg_col = qcol("#001a24" if z._drag_over else ("#001218" if z._hovering else C.PANEL))
        p.setBrush(QBrush(bg_col)); p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(rect, 6, 6)

        if z._current_file:   border_col = qcol(C.GREEN, 200)
        elif z._drag_over:    border_col = qcol(C.PRI, 230)
        elif z._hovering:     border_col = qcol(C.BORDER_B, 200)
        else:                 border_col = qcol(C.BORDER, 160)

        pen = QPen(border_col, 1.5, Qt.PenStyle.DashLine)
        pen.setDashOffset(z._dash_offset)
        p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(rect, 6, 6)

        if z._current_file:   self._paint_file(p, W, H)
        elif z._drag_over:    self._paint_drag_over(p, W, H)
        else:                 self._paint_idle(p, W, H, z._hovering)

    def _paint_idle(self, p, W, H, hover):
        cx, cy = W / 2, H / 2
        col = qcol(C.PRI_DIM if not hover else C.PRI)
        p.setPen(QPen(col, 2)); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawLine(QPointF(cx, cy - 14), QPointF(cx, cy + 4))
        p.drawLine(QPointF(cx - 8, cy - 6), QPointF(cx, cy - 14))
        p.drawLine(QPointF(cx + 8, cy - 6), QPointF(cx, cy - 14))
        p.drawLine(QPointF(cx - 14, cy + 4), QPointF(cx + 14, cy + 4))
        p.setFont(QFont("Inter", 8))
        p.setPen(QPen(qcol(C.PRI_DIM if not hover else C.TEXT), 1))
        p.drawText(QRectF(0, cy + 8, W, 16), Qt.AlignmentFlag.AlignCenter,
                   "")
        p.setFont(QFont("Inter", 7))
        p.setPen(QPen(qcol("#1a4a5a"), 1))
        p.drawText(QRectF(0, cy + 24, W, 14), Qt.AlignmentFlag.AlignCenter,
                   "")

    def _paint_drag_over(self, p, W, H):
        cx, cy = W / 2, H / 2
        p.setFont(QFont("Courier New", 20))
        p.setPen(QPen(qcol(C.PRI), 1))
        p.drawText(QRectF(0, cy - 24, W, 32), Qt.AlignmentFlag.AlignCenter, "DROP")
        p.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.PRI), 1))
        p.drawText(QRectF(0, cy + 12, W, 16), Qt.AlignmentFlag.AlignCenter, "Release to load")

    def _paint_file(self, p, W, H):
        path = Path(self._z._current_file)
        cat  = _file_category(path)
        icon, icon_col = _FILE_ICONS.get(cat, _FILE_ICONS["unknown"])
        size_str = _fmt_size(path.stat().st_size)
        ext_str  = path.suffix.upper().lstrip(".") or "FILE"

        block_x, block_w = 10, 60
        p.setFont(QFont("Segoe UI Emoji", 22) if _OS == "Windows" else QFont("Arial", 22))
        p.setPen(QPen(qcol(icon_col), 1))
        p.drawText(QRectF(block_x, 0, block_w, H), Qt.AlignmentFlag.AlignCenter, icon)

        tx = block_x + block_w + 6
        tw = W - tx - 38

        p.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.WHITE), 1))
        name = path.name if len(path.name) <= 34 else path.name[:31] + "..."
        p.drawText(QRectF(tx, H * 0.18, tw, 16),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, name)

        p.setFont(QFont("Inter", 7))
        p.setPen(QPen(qcol(C.TEXT_DIM), 1))
        p.drawText(QRectF(tx, H * 0.18 + 18, tw, 14),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   f"{ext_str}  -  {size_str}")

        p.setFont(QFont("Courier New", 6))
        p.setPen(QPen(qcol("#1e5c6a"), 1))
        par = str(path.parent)
        if len(par) > 42: par = "..." + par[-41:]
        p.drawText(QRectF(tx, H * 0.18 + 34, tw, 12),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, par)

        p.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.RED, 180), 1))
        p.drawText(QRectF(W - 34, 0, 28, H), Qt.AlignmentFlag.AlignCenter, "X")

    def mousePressEvent(self, e):
        z = self._z
        if z._current_file and e.pos().x() > self.width() - 34:
            z.clear_file()
        else:
            z.mousePressEvent(e)


class SetupOverlay(QWidget):
    done = pyqtSignal(str, str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            SetupOverlay {{
                background: rgba(0, 6, 10, 245);
                border: 1px solid {C.BORDER_B};
                border-radius: 6px;
            }}
        """)

        detected = {"darwin": "mac", "windows": "windows"}.get(
            _OS.lower(), "linux"
        )
        self._sel_os = detected

        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 22, 30, 22)
        layout.setSpacing(8)

        def _lbl(txt, font_size=9, bold=False, color=C.PRI,
                 align=Qt.AlignmentFlag.AlignCenter):
            w = QLabel(txt)
            w.setAlignment(align)
            w.setFont(QFont("Courier New", font_size,
                            QFont.Weight.Bold if bold else QFont.Weight.Normal))
            w.setStyleSheet(f"color: {color}; background: transparent;")
            return w

        layout.addWidget(_lbl("INITIALISATION REQUIRED", 13, True))
        layout.addWidget(_lbl("Configure REVO before first boot.", 9, color=C.PRI_DIM))
        layout.addSpacing(6)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER};"); layout.addWidget(sep)
        layout.addSpacing(4)

        layout.addWidget(_lbl("GEMINI API KEY", 8, color=C.TEXT_DIM,
                               align=Qt.AlignmentFlag.AlignLeft))
        self._key_input = QLineEdit()
        self._key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._key_input.setPlaceholderText("AIza...")
        self._key_input.setFont(QFont("Courier New", 10))
        self._key_input.setFixedHeight(32)
        self._key_input.setStyleSheet(f"""
            QLineEdit {{
                background: #000d12; color: {C.TEXT};
                border: 1px solid {C.BORDER}; border-radius: 14px; padding: 4px 8px;
            }}
            QLineEdit:focus {{ border: 1px solid rgba(24,229,255,0.75); background: rgba(255,255,255,0.11); }}
        """)
        layout.addWidget(self._key_input)
        layout.addSpacing(8)

        layout.addWidget(_lbl("OPENROUTER API KEY", 8, color=C.TEXT_DIM,
                       align=Qt.AlignmentFlag.AlignLeft))
        self._or_input = QLineEdit()
        self._or_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._or_input.setPlaceholderText("sk-or-...")
        self._or_input.setFont(QFont("Courier New", 10))
        self._or_input.setFixedHeight(32)
        self._or_input.setStyleSheet(f"""
            QLineEdit {{
                background: #000d12; color: {C.TEXT};
                border: 1px solid {C.BORDER}; border-radius: 14px; padding: 4px 8px;
            }}
            QLineEdit:focus {{ border: 1px solid {C.ACC2}; }}
        """)
        layout.addWidget(self._or_input)

        layout.addSpacing(12)

        sep2 = QFrame(); sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet(f"color: {C.BORDER};"); layout.addWidget(sep2)
        layout.addSpacing(4)

        layout.addWidget(_lbl("OPERATING SYSTEM", 8, color=C.TEXT_DIM,
                               align=Qt.AlignmentFlag.AlignLeft))
        det_name = {"windows": "Windows", "mac": "macOS", "linux": "Linux"}[detected]
        layout.addWidget(_lbl(f"Auto-detected: {det_name}", 8, color=C.ACC2,
                               align=Qt.AlignmentFlag.AlignLeft))

        os_row = QHBoxLayout(); os_row.setSpacing(6)
        self._os_btns: dict[str, QPushButton] = {}
        for key, label in [("windows","Windows"),("mac","macOS"),("linux","Linux")]:
            btn = QPushButton(label)
            btn.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
            btn.setFixedHeight(32)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _, k=key: self._sel(k))
            os_row.addWidget(btn)
            self._os_btns[key] = btn
        layout.addLayout(os_row)
        self._sel(detected)
        layout.addSpacing(12)

        init_btn = QPushButton("INITIALISE SYSTEMS")
        init_btn.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
        init_btn.setFixedHeight(36)
        init_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        init_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.PRI};
                border: 1px solid {C.PRI_DIM}; border-radius: 14px;
            }}
            QPushButton:hover {{
                background: {C.PRI_GHO}; border: 1px solid {C.PRI};
            }}
        """)
        init_btn.clicked.connect(self._submit)
        layout.addWidget(init_btn)

    def _sel(self, key: str):
        self._sel_os = key
        pal = {"windows":(C.PRI,"#001a22"),"mac":(C.ACC2,"#1a1400"),"linux":(C.GREEN,"#001a0d")}
        for k, btn in self._os_btns.items():
            if k == key:
                fg, bg = pal[k]
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: {fg}; color: {bg};
                        border: none; border-radius: 14px; font-weight: bold;
                    }}
                """)
            else:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: #000d12; color: {C.TEXT_DIM};
                        border: 1px solid {C.BORDER}; border-radius: 14px;
                    }}
                    QPushButton:hover {{ color: {C.TEXT}; border: 1px solid {C.BORDER_B}; }}
                """)

    def _submit(self):
        key = self._key_input.text().strip()
        or_key = self._or_input.text().strip()
        if not key:
            self._key_input.setStyleSheet(
                self._key_input.styleSheet() +
                f" QLineEdit {{ border: 1px solid {C.RED}; }}"
            )
            return
        if not or_key:
            self._or_input.setStyleSheet(
                self._or_input.styleSheet() +
                f" QLineEdit {{ border: 1px solid {C.RED}; }}"
            )
            return
        self.done.emit(key, or_key, self._sel_os)


class MainWindow(QMainWindow):
    _log_sig   = pyqtSignal(str)
    _state_sig = pyqtSignal(str)
    _setup_sig = pyqtSignal(str)
    _voice_activity_sig = pyqtSignal(bool)

    def __init__(self, face_path: str):
        super().__init__()
        self.setWindowTitle("REVO OS")
        self.setMinimumSize(_MIN_W, _MIN_H)
        self.resize(_DEFAULT_W, _DEFAULT_H)

        screen = QApplication.primaryScreen().availableGeometry()
        self.move(
            (screen.width()  - _DEFAULT_W) // 2,
            (screen.height() - _DEFAULT_H) // 2,
        )

        self.on_text_command  = None
        self._muted           = False
        self._current_file: str | None = None

        central = AnimatedBackground()
        central.setStyleSheet("background: transparent;")
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(10)
        root.addWidget(self._build_header())

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(14)

        self._left_panel = self._build_left_panel()
        body.addWidget(self._left_panel, stretch=0)

        self._center_panel = self._build_center_panel(face_path)
        body.addWidget(self._center_panel, stretch=8)

        self._right_panel = self._build_right_panel()
        body.addWidget(self._right_panel, stretch=0)

        root.addLayout(body, stretch=1)
        root.addWidget(self._build_footer())

        self._clock_tmr = QTimer(self)
        self._clock_tmr.timeout.connect(self._tick_clock)
        self._clock_tmr.start(1000)
        self._tick_clock()

        # Metrik gÃƒÂ¼ncelleme timer'Ã„Â±
        self._metric_tmr = QTimer(self)
        self._metric_tmr.timeout.connect(self._update_metrics)
        self._metric_tmr.start(2000)
        self._update_metrics()

        self._log_sig.connect(self._append_log_and_update)
        self._state_sig.connect(self._apply_state)
        self._setup_sig.connect(self._open_api_key_portal)
        self._voice_activity_sig.connect(self.set_user_voice_active)

        self._overlay: SetupOverlay | None = None
        self._ready = self._check_config()
        if not self._ready:
            self._show_setup()

        sc_mute = QShortcut(QKeySequence("F4"), self)
        sc_mute.activated.connect(self._toggle_mute)
        sc_full = QShortcut(QKeySequence("F11"), self)
        sc_full.activated.connect(self._toggle_fullscreen)

    def _toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._overlay and self._overlay.isVisible():
            ow, oh = 460, 390
            cw = self.centralWidget()
            self._overlay.setGeometry(
                (cw.width()  - ow) // 2,
                (cw.height() - oh) // 2,
                ow, oh,
            )

    def _update_metrics(self):
        snap = _metrics.snapshot()

        cpu = snap["cpu"]
        self._bar_cpu.set_value(cpu, f"{cpu:.0f}%")

        mem = snap["mem"]
        self._bar_mem.set_value(mem, f"{mem:.0f}%")

        net = snap["net"]
        net_str = f"{net*1024:.0f}KB/s" if net < 1.0 else f"{net:.1f}MB/s"
        self._bar_net.set_value(min(100, net * 10), net_str)

        gpu = snap["gpu"]
        self._bar_gpu.set_value(gpu if gpu >= 0 else 0, f"{gpu:.0f}%" if gpu >= 0 else "N/A")

        tmp = snap["tmp"]
        self._bar_tmp.set_value(min(100, tmp) if tmp >= 0 else 0, f"{tmp:.0f} C" if tmp >= 0 else "N/A")

        try:
            if _OS == "Windows":
                r = subprocess.run(
                    ["powershell", "-NoProfile", "-Command", "(Get-MpComputerStatus).RealTimeProtectionEnabled"],
                    capture_output=True, text=True, timeout=2, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
                )
                status = "Protected" if "True" in r.stdout else "Check"
            else:
                status = "N/A"
        except Exception:
            status = "Check"
        if hasattr(self, "_defender_lbl"):
            self._defender_lbl.setText(status)

        try:
            boot_t  = psutil.boot_time()
            elapsed = time.time() - boot_t
            h = int(elapsed // 3600)
            m = int((elapsed % 3600) // 60)
            self._uptime_lbl.setText(f"UP  {h:02d}:{m:02d}")
        except Exception:
            self._uptime_lbl.setText("UP  --:--")

        try:
            proc_count = len(psutil.pids())
            self._proc_lbl.setText(f"PROC  {proc_count}")
        except Exception:
            self._proc_lbl.setText("PROC  --")


    def _build_header(self) -> QWidget:
        w = QWidget()
        w.setObjectName("HeaderPanel")
        w.setFixedHeight(74)
        w.setStyleSheet("""
            #HeaderPanel {
                background: rgba(8, 14, 26, 0.68);
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 24px;
            }
        """)
        lay = QHBoxLayout(w)
        lay.setContentsMargins(22, 0, 22, 0)
        lay.setSpacing(16)

        logo = QLabel("REVO OS")
        logo.setFont(QFont("Orbitron", 15, QFont.Weight.Bold))
        logo.setStyleSheet(f"color: {C.PRI}; background: transparent; border: none;")
        lay.addWidget(logo, stretch=1)

        title_box = QVBoxLayout(); title_box.setSpacing(1)
        title = QLabel("REVO AI ASSISTANT")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setFont(QFont("Orbitron", 18, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {C.WHITE}; background: transparent; border: none;")
        title_box.addWidget(title)
        sub = QLabel("PERSONAL AI ASSISTANT")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setFont(QFont("Inter", 8, QFont.Weight.Bold))
        sub.setStyleSheet(f"color: {C.PRI_DIM}; background: transparent; border: none;")
        title_box.addWidget(sub)
        lay.addLayout(title_box, stretch=2)

        right = QVBoxLayout(); right.setSpacing(2)
        self._clock_lbl = QLabel("00:00:00")
        self._clock_lbl.setFont(QFont("Space Grotesk", 14, QFont.Weight.Bold))
        self._clock_lbl.setStyleSheet(f"color: {C.PRI}; background: transparent; border: none;")
        self._clock_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        right.addWidget(self._clock_lbl)
        self._date_lbl = QLabel("")
        self._date_lbl.setFont(QFont("Inter", 8))
        self._date_lbl.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent; border: none;")
        self._date_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        right.addWidget(self._date_lbl)
        self._header_mode_lbl = QLabel("Current Mode: Normal")
        self._header_mode_lbl.setFont(QFont("Inter", 8, QFont.Weight.Bold))
        self._header_mode_lbl.setStyleSheet(f"color: {C.WHITE}; background: transparent; border: none;")
        self._header_mode_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        right.addWidget(self._header_mode_lbl)
        lay.addLayout(right, stretch=1)
        return w


    def _tick_clock(self):
        self._clock_lbl.setText(time.strftime("%H:%M:%S"))
        self._date_lbl.setText(time.strftime("%a %d %b %Y"))

    def _build_left_panel(self) -> QWidget:
        w = QWidget()
        w.setObjectName("IdentityPanel")
        w.setFixedWidth(_LEFT_W)
        w.setStyleSheet("""
            #IdentityPanel {
                background: rgba(4, 14, 24, 0.56);
                border: 1px solid rgba(24,229,255,0.12);
                border-radius: 20px;
            }
        """)
        lay = QVBoxLayout(w)
        lay.setContentsMargins(16, 18, 16, 18)
        lay.setSpacing(12)

        title = QLabel("REVO")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setFont(QFont("Orbitron", 24, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {C.PRI}; background: transparent; border: none;")
        lay.addWidget(title)

        sub = QLabel("PERSONAL AI ASSISTANT")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setWordWrap(True)
        sub.setFont(QFont("Inter", 8, QFont.Weight.Bold))
        sub.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent; border: none;")
        lay.addWidget(sub)

        lay.addStretch(1)

        self._left_mode_lbl = QLabel("Current Mode\nNormal")
        self._left_mode_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._left_mode_lbl.setWordWrap(True)
        self._left_mode_lbl.setFont(QFont("Inter", 9, QFont.Weight.Bold))
        self._left_mode_lbl.setStyleSheet(f"color: {C.WHITE}; background: rgba(255,255,255,0.045); border: 1px solid rgba(255,255,255,0.07); border-radius: 16px; padding: 10px;")
        lay.addWidget(self._left_mode_lbl)

        self._left_task_lbl = QLabel("Current Task\nReady")
        self._left_task_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._left_task_lbl.setWordWrap(True)
        self._left_task_lbl.setFont(QFont("Inter", 8))
        self._left_task_lbl.setStyleSheet(f"color: {C.TEXT_MED}; background: rgba(255,255,255,0.035); border: 1px solid rgba(255,255,255,0.06); border-radius: 16px; padding: 10px;")
        lay.addWidget(self._left_task_lbl)

        self._bar_cpu = MetricBar("CPU", C.PRI); self._bar_cpu.hide()
        self._bar_gpu = MetricBar("GPU", C.PURPLE); self._bar_gpu.hide()
        self._bar_mem = MetricBar("RAM", C.ACC2); self._bar_mem.hide()
        self._bar_net = MetricBar("NETWORK", C.GREEN); self._bar_net.hide()
        self._bar_tmp = MetricBar("TEMP", C.ACC); self._bar_tmp.hide()
        self._defender_lbl = QLabel(""); self._defender_lbl.hide()
        self._uptime_lbl = QLabel(""); self._uptime_lbl.hide()
        self._proc_lbl = QLabel(""); self._proc_lbl.hide()
        self._memory_lbl = QLabel(""); self._memory_lbl.hide()
        self._tasks_lbl = QLabel(""); self._tasks_lbl.hide()
        self._voice_status_lbl = QLabel(""); self._voice_status_lbl.hide()
        self._voice_status_state = {"voice": "running", "ai": "running", "tts": "running", "memory": "running", "tts_engine": "", "current_voice": "", "queue_length": 0, "last_speech_time": 0}

        lay.addStretch(2)
        return w

    def _glass_card(self, title: str, body: str = "") -> QWidget:
        card = QWidget()
        card.setStyleSheet(f"""
            QWidget {{
                background: rgba(6, 18, 32, 175);
                border: 1px solid rgba(32, 215, 255, 80);
                border-radius: 10px;
            }}
        """)
        lay = QVBoxLayout(card); lay.setContentsMargins(10, 8, 10, 8); lay.setSpacing(4)
        t = QLabel(title)
        t.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        t.setStyleSheet(f"color: {C.PRI}; background: transparent; border: none;")
        lay.addWidget(t)
        b = QLabel(body)
        b.setFont(QFont("Segoe UI", 8))
        b.setWordWrap(True)
        b.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent; border: none;")
        lay.addWidget(b)
        return card

    def _build_center_panel(self, face_path: str) -> QWidget:
        w = QWidget()
        w.setObjectName("RadarPanel")
        w.setStyleSheet("""
            #RadarPanel {
                background: rgba(2, 10, 20, 0.42);
                border: 1px solid rgba(24,229,255,0.10);
                border-radius: 20px;
            }
        """)
        lay = QVBoxLayout(w)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(4)

        self.hud = HudCanvas(face_path)
        self.hud.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        lay.addWidget(self.hud, stretch=1)

        self._simple_state_lbl = QLabel("Listening...")
        self._simple_state_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._simple_state_lbl.setFont(QFont("Orbitron", 13, QFont.Weight.Bold))
        self._simple_state_lbl.setStyleSheet(f"color: {C.GREEN}; background: transparent; border: none;")
        lay.addWidget(self._simple_state_lbl)

        self._mode_lbl = QLabel("Current Mode: Normal")
        self._mode_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._mode_lbl.setFont(QFont("Inter", 8, QFont.Weight.Bold))
        self._mode_lbl.setStyleSheet(f"color: {C.PRI_DIM}; background: transparent; border: none;")
        lay.addWidget(self._mode_lbl)

        self._action_lbl = QLabel("Current Task: Ready")
        self._action_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._action_lbl.setWordWrap(True)
        self._action_lbl.setFont(QFont("Inter", 8))
        self._action_lbl.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent; border: none;")
        lay.addWidget(self._action_lbl)

        self._checklist_lbl = QLabel("")
        self._checklist_lbl.hide()
        return w


    def _build_right_panel(self) -> QWidget:
        w = QWidget()
        w.setObjectName("ChatPanel")
        w.setFixedWidth(_RIGHT_W)
        w.setStyleSheet("""
            #ChatPanel {
                background: rgba(8, 14, 26, 0.68);
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 24px;
            }
        """)
        lay = QVBoxLayout(w)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(12)

        title = QLabel("Conversation")
        title.setFont(QFont("Orbitron", 9, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {C.WHITE}; background: transparent; border: none;")
        lay.addWidget(title)

        self._log = LogWidget()
        lay.addWidget(self._log, stretch=1)

        self._drop_zone = FileDropZone()
        self._drop_zone.setMaximumHeight(76)
        self._drop_zone.file_selected.connect(self._on_file_selected)
        lay.addWidget(self._drop_zone)

        self._file_hint = QLabel("")
        self._file_hint.setFont(QFont("Inter", 7))
        self._file_hint.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent; border: none;")
        self._file_hint.setWordWrap(True)
        lay.addWidget(self._file_hint)

        lay.addLayout(self._build_input_row())

        self._mute_btn = QPushButton("Listening...")
        self._mute_btn.setFixedHeight(34)
        self._mute_btn.setFont(QFont("Inter", 9, QFont.Weight.Bold))
        self._mute_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._mute_btn.clicked.connect(self._toggle_mute)
        self._style_mute_btn()
        lay.addWidget(self._mute_btn)
        return w


    def _build_input_row(self) -> QHBoxLayout:
        row = QHBoxLayout(); row.setSpacing(10)
        self._input = QLineEdit()
        self._input.setPlaceholderText("Type a command or question...")
        self._input.setFont(QFont("Inter", 10))
        self._input.setFixedHeight(38)
        self._input.setStyleSheet(f"""
            QLineEdit {{
                background: rgba(255,255,255,0.08); color: {C.WHITE};
                border: 1px solid rgba(255,255,255,0.12); border-radius: 18px; padding: 8px 14px;
            }}
            QLineEdit:focus {{ border: 1px solid rgba(24,229,255,0.75); background: rgba(255,255,255,0.11); }}
        """)
        self._input.returnPressed.connect(self._send)
        row.addWidget(self._input)

        send = QPushButton(">")
        send.setFixedSize(38, 38)
        send.setFont(QFont("Inter", 13, QFont.Weight.Bold))
        send.setCursor(Qt.CursorShape.PointingHandCursor)
        send.setStyleSheet(f"""
            QPushButton {{
                background: {C.PANEL}; color: {C.PRI};
                border: 1px solid {C.PRI_DIM}; border-radius: 14px;
            }}
            QPushButton:hover {{ background: {C.PRI_GHO}; border: 1px solid {C.PRI}; }}
        """)
        send.clicked.connect(self._send)
        row.addWidget(send)
        return row

    def _build_footer(self) -> QWidget:
        w = QWidget()
        w.setFixedHeight(104)
        w.setStyleSheet("background: transparent; border: none;")
        outer = QHBoxLayout(w)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addStretch(1)

        dock = QWidget()
        dock.setObjectName("QuickDrawer")
        dock.setStyleSheet("""
            #QuickDrawer {
                background: rgba(4, 14, 24, 0.72);
                border: 1px solid rgba(24,229,255,0.12);
                border-radius: 18px;
            }
        """)
        box = QVBoxLayout(dock)
        box.setContentsMargins(10, 8, 10, 8)
        box.setSpacing(7)

        self._quick_extra_container = QWidget()
        first_row = QHBoxLayout(); first_row.setSpacing(8)
        second_row = QHBoxLayout(self._quick_extra_container); second_row.setContentsMargins(0, 0, 0, 0); second_row.setSpacing(8)

        actions = [
            ("Gaming", "gaming mode"), ("Productive", "productive mode"),
            ("Normal", "normal mode"), ("PC Scan", "pc health check karo"),
            ("Screenshot", "screenshot analyze karo"), ("Playlist", "open my playlist"),
            ("Valorant", "open valorant"), ("Discord", "open discord"),
            ("Job Hunter", "internship dhundo"), ("Companion", "companion mode"),
            ("Security", "security report"),
        ]

        for i, (label, cmd) in enumerate(actions):
            btn = self._make_quick_button(label, cmd)
            if i < 4:
                first_row.addWidget(btn)
            else:
                second_row.addWidget(btn)

        self._more_btn = self._make_quick_button("More", "")
        self._more_btn.clicked.disconnect()
        self._more_btn.clicked.connect(self._toggle_quick_drawer)
        first_row.addWidget(self._more_btn)

        box.addLayout(first_row)
        box.addWidget(self._quick_extra_container)
        self._quick_extra_container.hide()
        self._quick_drawer_open = False

        outer.addWidget(dock)
        outer.addStretch(1)
        return w

    def _make_quick_button(self, label: str, cmd: str) -> QPushButton:
        btn = QPushButton(label)
        btn.setFixedHeight(34)
        btn.setMinimumWidth(78)
        btn.setFont(QFont("Inter", 8, QFont.Weight.Bold))
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(255,255,255,0.055); color: {C.WHITE};
                border: 1px solid rgba(24,229,255,0.10); border-radius: 12px;
                padding: 0 10px;
            }}
            QPushButton:hover {{
                background: rgba(24,229,255,0.14); color: {C.PRI};
                border: 1px solid rgba(24,229,255,0.42);
            }}
        """)
        btn.clicked.connect(lambda _, c=cmd: self._quick_cmd(c))
        return btn

    def _toggle_quick_drawer(self):
        self._quick_drawer_open = not getattr(self, "_quick_drawer_open", False)
        self._quick_extra_container.setVisible(self._quick_drawer_open)
        self._more_btn.setText("Less" if self._quick_drawer_open else "More")


    def _append_log_and_update(self, text: str):
        raw = text or ""
        stripped = raw.strip()
        t = stripped.lower()
        hidden_prefixes = ("debug", "[stt", "[tts", "[ai", "[intent", "[watchdog", "sys:", "file:", "err:", "[website", "[shortcut", "[app")
        if t.startswith(hidden_prefixes):
            return

        if raw.startswith("You:") or raw.startswith("REVO:"):
            self._log.append_log(raw)

        if "gaming mode activated" in t or "gaming setup complete" in t:
            self._set_mode_ui("Current Mode: Gaming", "", "Gaming Mode")
            return
        if "productive mode activated" in t or "productive mode ready" in t:
            self._set_mode_ui("Current Mode: Productive", "", "Productive Mode")
            return
        if "normal mode restored" in t:
            self._set_mode_ui("Current Mode: Normal", "", "Normal Mode")
            return
        if raw.startswith("You:"):
            task = raw[4:].strip()[:80] or "Listening..."
            self._action_lbl.setText(f"Current Task: {task}")
            if hasattr(self, "_left_task_lbl"):
                self._left_task_lbl.setText(f"Current Task\n{task}")
            return
        if raw.startswith("REVO:"):
            task = raw[5:].strip().replace("\n", " ")[:80]
            if task and task.lower() not in ("speaking...", "listening...", "thinking..."):
                self._action_lbl.setText(f"Current Task: {task}")
                if hasattr(self, "_left_task_lbl"):
                    self._left_task_lbl.setText(f"Current Task\n{task}")
            return


    def _set_mode_ui(self, label: str, checklist: str, mode: str):
        display_mode = "Normal"
        if "Gaming" in mode:
            display_mode = "Gaming"
            color = C.PURPLE
            bg = "rgba(42, 6, 45, 150)"
        elif "Productive" in mode:
            display_mode = "Productive"
            color = C.PRI
            bg = "rgba(5, 22, 42, 150)"
        else:
            color = C.PRI
            bg = "rgba(5, 20, 34, 130)"
        self._mode_lbl.setText(f"Current Mode: {display_mode}")
        if hasattr(self, "_header_mode_lbl"):
            self._header_mode_lbl.setText(f"Current Mode: {display_mode}")
        self._checklist_lbl.setText("")
        if hasattr(self, "_left_mode_lbl"):
            self._left_mode_lbl.setText(f"Current Mode\n{display_mode}")
        self.hud.mode = mode
        self._mode_lbl.setStyleSheet(f"color: {color}; background: transparent; border: none; letter-spacing: 1px;")
        self._checklist_lbl.setStyleSheet(f"color: {C.WHITE}; background: {bg}; border: 1px solid rgba(255,255,255,0.08); border-radius: 16px; padding: 8px;")
        self.hud.update()

    def _on_file_selected(self, path: str):
        self._current_file = path
        p    = Path(path)
        cat  = _file_category(p)
        icon, _ = _FILE_ICONS.get(cat, _FILE_ICONS["unknown"])
        size = _fmt_size(p.stat().st_size)
        self._file_hint.setText(f"{p.name}")
        self._action_lbl.setText(f"Current Task: {p.name}")
        if self.on_text_command:
            msg = (
                f"[FILE_UPLOADED] path={path} | name={p.name} | "
                f"type={p.suffix.lstrip('.')} | size={size} | "
                f"Briefly tell the user you can see the file '{p.name}' "
                f"({size}) has been uploaded and ask what they'd like to do with it."
            )
            threading.Thread(target=self.on_text_command, args=(msg,), daemon=True).start()

    def _toggle_mute(self):
        self._muted = not self._muted
        self.hud.muted = self._muted
        self._style_mute_btn()
        if self._muted:
            self._apply_state("MUTED")
        else:
            self._apply_state("LISTENING")

    def _style_mute_btn(self):
        if self._muted:
            self._mute_btn.setText("Muted")
            self._mute_btn.setStyleSheet(f"""
                QPushButton {{
                    background: #140006; color: {C.MUTED_C};
                    border: 1px solid {C.MUTED_C}; border-radius: 14px;
                }}
            """)
        else:
            self._mute_btn.setText("Listening...")
            self._mute_btn.setStyleSheet(f"""
                QPushButton {{
                    background: #00140a; color: {C.GREEN};
                    border: 1px solid {C.GREEN}; border-radius: 14px;
                }}
                QPushButton:hover {{ background: #001f10; }}
            """)

    def _quick_cmd(self, cmd: str):
        self._input.setText(cmd)
        self._send()

    def _send(self):
        txt = self._input.text().strip()
        if not txt: return
        self._input.clear()
        self._log.append_log(f"You: {txt}")
        if self.on_text_command:
            threading.Thread(target=self.on_text_command, args=(txt,), daemon=True).start()

    def set_user_voice_active(self, active: bool):
        if hasattr(self, "hud"):
            self.hud.set_user_active(active)

    def _apply_state(self, state: str):
        self.hud.state    = state
        self.hud.speaking = (state == "SPEAKING")
        if hasattr(self, "_simple_state_lbl"):
            label_map = {"LISTENING": "Listening...", "THINKING": "Thinking...", "PROCESSING": "Thinking...", "SPEAKING": "Speaking...", "MUTED": "Muted"}
            self._simple_state_lbl.setText(label_map.get(state, f"{state.title()}..."))

    def _check_config(self) -> bool:
        if not API_FILE.exists(): return False
        try:
            d = json.loads(API_FILE.read_text(encoding="utf-8-sig"))
            return (bool(d.get("gemini_api_key")) and
                    bool(d.get("openrouter_api_key")) and
                    bool(d.get("os_system")))
        except Exception:
            return False

    def _show_setup(self):
        if self._overlay and self._overlay.isVisible():
            self._overlay.raise_()
            self._overlay.activateWindow()
            return
        ov = SetupOverlay(self.centralWidget())
        cw = self.centralWidget()
        ow, oh = 460, 430
        ov.setGeometry(
            (cw.width()  - ow) // 2,
            (cw.height() - oh) // 2,
            ow, oh,
        )
        ov.done.connect(self._on_setup_done)
        ov.show()
        self._overlay = ov

    def _open_api_key_portal(self, reason: str = ""):
        self._ready = False
        if reason:
            self._action_lbl.setText("Current Task: Setup")
        self._show_setup()

    # Change signature:
    def _on_setup_done(self, key: str, or_key: str, os_name: str):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        existing = {}
        if API_FILE.exists():
            try:
                existing = json.loads(API_FILE.read_text(encoding="utf-8-sig"))
            except Exception:
                existing = {}
        existing.update({
            "gemini_api_key":    key,
            "openrouter_api_key": or_key,
            "os_system":         os_name,
        })
        API_FILE.write_text(
            json.dumps(existing, indent=4),
            encoding="utf-8",
        )
        self._ready = True
        if self._overlay:
            self._overlay.hide()
            self._overlay = None
        self._apply_state("LISTENING")
        self._action_lbl.setText("Current Task: Ready")

class _RootShim:
    def __init__(self, app: QApplication):
        self._app = app
    def mainloop(self):
        self._app.exec()
    def protocol(self, *_):
        pass


class REVOUI:
    def __init__(self, face_path: str, size=None):
        self._app = QApplication.instance() or QApplication(sys.argv)
        self._app.setStyle("Fusion")
        self._win = MainWindow(face_path)
        self._win.show()
        self.root = _RootShim(self._app)

    @property
    def muted(self) -> bool:
        return self._win._muted

    @muted.setter
    def muted(self, v: bool):
        if v != self._win._muted:
            self._win._toggle_mute()

    @property
    def current_file(self) -> str | None:
        return self._win._drop_zone.current_file()

    @property
    def on_text_command(self):
        return self._win.on_text_command

    @on_text_command.setter
    def on_text_command(self, cb):
        self._win.on_text_command = cb

    def set_voice_status(self, voice=None, ai=None, tts=None, memory=None, **extra):
        target = getattr(self, "_win", self)
        if not hasattr(target, "_voice_status_state"):
            return
        updates = {"voice": voice, "ai": ai, "tts": tts, "memory": memory}
        updates.update(extra)
        for key, value in updates.items():
            if value is not None:
                target._voice_status_state[key] = value if key in ("queue_length", "last_speech_time") else str(value).lower()
        if hasattr(target, "_voice_status_lbl"):
            target._voice_status_lbl.hide()

    def set_state(self, state: str):
        self._win._state_sig.emit(state)

    def set_user_voice_active(self, active: bool):
        try:
            self._win._voice_activity_sig.emit(bool(active))
        except Exception:
            pass

    def write_log(self, text: str):
        self._win._log_sig.emit(text)

    def wait_for_api_key(self):
        while not self._win._ready:
            time.sleep(0.1)

    def open_api_key_portal(self, reason: str = ""):
        self._win._setup_sig.emit(reason)

    def start_speaking(self):
        self.set_state("SPEAKING")

    def stop_speaking(self):
        if not self.muted:
            self.set_state("LISTENING")







