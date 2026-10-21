"""
Taskbar Spectrum - visualizador de audio para la barra de tareas de Windows.
by: 7elixHxtrs - https://github.com/7elixHxtrs

- Icono en la bandeja del sistema (doble clic = configuracion).
- Clic derecho sobre una barra del visualizador = abrir configuracion.
- La configuracion se guarda en %APPDATA%\\TaskbarSpectrum\\config.json

Requisitos (si se ejecuta como script):
    pip install numpy PyAudioWPatch pystray pillow
"""
import ctypes
import json
import logging
import os
import queue
import sys
import threading
import time
import tkinter as tk
import webbrowser
from ctypes import wintypes
from pathlib import Path
from tkinter import colorchooser, ttk

import numpy as np
import pyaudiowpatch as pyaudio
import pystray
from PIL import Image, ImageDraw

APP_NAME = "TaskbarSpectrum"
AUTHOR = "7elixHxtrs"
AUTHOR_URL = "https://github.com/7elixHxtrs"
CONFIG_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / APP_NAME
CONFIG_FILE = CONFIG_DIR / "config.json"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

FFT_SIZE = 2048
FMIN, FMAX = 40.0, 16000.0
SOUND_THRESHOLD = 2e-4
TRANSPARENT = "#010101"
FPS = 60

DEFAULTS = {
    "enabled": True,
    "visibility": "always",      # always | fullscreen | maximized
    "hide_silence": False,
    "silence_seconds": 3,
    "color": "#2ecc71",
    "width": 240,
    "height": 18,
    "height_auto": True,
    "bars": 32,
    "gap": 2,
    "opacity": 100,
    "offset_right": 255,         # distancia del visualizador al borde derecho
    "offset_y": 0,
    "gravity": 12,               # % de caida de las barras
}

VIS_LABELS = {
    "always": "Siempre visible",
    "fullscreen": "Ocultar en pantalla completa (juegos, video)",
    "maximized": "Ocultar con ventana maximizada o pantalla completa",
}

# ------------------------------------------------------------------ Win32
user32 = None
if sys.platform == "win32":
    user32 = ctypes.windll.user32

    class MONITORINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("rcMonitor", wintypes.RECT),
            ("rcWork", wintypes.RECT),
            ("dwFlags", wintypes.DWORD),
        ]

    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsIconic.argtypes = [wintypes.HWND]
    user32.IsZoomed.argtypes = [wintypes.HWND]
    user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
    user32.MonitorFromWindow.restype = wintypes.HANDLE
    user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MONITORINFO)]
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]

IGNORED_CLASSES = {
    "Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd",
    "NotifyIconOverflowWindow", "TopLevelWindowForOverflowXamlIsland",
}


def foreground_state():
    """Devuelve (maximizada, pantalla_completa) de la ventana activa."""
    hwnd = user32.GetForegroundWindow()
    if not hwnd or not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
        return False, False

    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if pid.value == os.getpid():
        return False, False

    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    if buf.value in IGNORED_CLASSES:
        return False, False

    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    mon = user32.MonitorFromWindow(hwnd, 2)  # MONITOR_DEFAULTTONEAREST
    mi = MONITORINFO()
    mi.cbSize = ctypes.sizeof(MONITORINFO)
    user32.GetMonitorInfoW(mon, ctypes.byref(mi))
    m = mi.rcMonitor
    fullscreen = (rect.left <= m.left and rect.top <= m.top
                  and rect.right >= m.right and rect.bottom >= m.bottom)
    maximized = bool(user32.IsZoomed(hwnd))
    return maximized, fullscreen


def taskbar_geometry():
    """Devuelve (ancho_pantalla, alto_barra, y_inicio_barra)."""
    sw = user32.GetSystemMetrics(0)
    sh = user32.GetSystemMetrics(1)
    work = wintypes.RECT()
    user32.SystemParametersInfoW(48, 0, ctypes.byref(work), 0)  # SPI_GETWORKAREA
    if work.top > 0:
        return sw, work.top, 0
    if sh - work.bottom > 0:
        return sw, sh - work.bottom, work.bottom
    return sw, 48, sh - 48  # barra vertical u oculta: valor por defecto


# ---------------------------------------------------------------- Config
def load_config():
    cfg = dict(DEFAULTS)
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        for k, v in data.items():
            if k in DEFAULTS and type(v) is type(DEFAULTS[k]):
                cfg[k] = v
    except Exception:
        pass
    return cfg


def save_config(cfg):
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    except Exception:
        logging.exception("No se pudo guardar la configuracion")


# ------------------------------------------------------------- Autostart
def autostart_command():
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    pyw = Path(sys.executable).with_name("pythonw.exe")
    exe = pyw if pyw.exists() else Path(sys.executable)
    return f'"{exe}" "{Path(__file__).resolve()}"'


def autostart_enabled():
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, APP_NAME)
            return True
    except OSError:
        return False


def set_autostart(enable):
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            if enable:
                winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, autostart_command())
            else:
                try:
                    winreg.DeleteValue(k, APP_NAME)
                except FileNotFoundError:
                    pass
    except OSError:
        logging.exception("No se pudo cambiar el inicio con Windows")


# ------------------------------------------------------------------ Icono
def make_icon_image(size=64):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=size // 6, fill=(12, 40, 48, 255))
    heights = [0.35, 0.65, 0.45, 0.9, 0.55, 0.75, 0.4]
    n = len(heights)
    pad = size * 0.14
    bw = (size - 2 * pad) / n
    for i, h in enumerate(heights):
        x0 = pad + i * bw + bw * 0.12
        x1 = pad + (i + 1) * bw - bw * 0.12
        y1 = size - pad
        y0 = y1 - h * (size - 2 * pad)
        d.rectangle([x0, y0, x1, y1], fill=(46, 204, 113, 255))
    return img


# ------------------------------------------------------------------ Audio
class AudioCapture:
    """Captura lo que suena por la salida de audio predeterminada (WASAPI loopback)."""

    def __init__(self):
        self.buffer = np.zeros(FFT_SIZE, dtype=np.float32)
        self.lock = threading.Lock()
        self.last_cb = 0.0
        self.rate = 48000
        self.pa = None
        self.stream = None

    def start(self):
        self.stop()
        pa = pyaudio.PyAudio()
        try:
            wasapi = pa.get_host_api_info_by_type(pyaudio.paWASAPI)
            dev = pa.get_device_info_by_index(wasapi["defaultOutputDevice"])
            if not dev.get("isLoopbackDevice"):
                for lb in pa.get_loopback_device_info_generator():
                    if dev["name"] in lb["name"]:
                        dev = lb
                        break
                else:
                    raise RuntimeError("No se encontro un dispositivo loopback")
            channels = int(dev["maxInputChannels"])
            self.rate = int(dev["defaultSampleRate"])

            def callback(in_data, frame_count, time_info, status):
                data = np.frombuffer(in_data, dtype=np.int16).astype(np.float32) / 32768.0
                mono = data.reshape(-1, channels).mean(axis=1)
                with self.lock:
                    self.buffer = np.concatenate((self.buffer, mono))[-FFT_SIZE:]
                self.last_cb = time.time()
                return (None, pyaudio.paContinue)

            self.stream = pa.open(
                format=pyaudio.paInt16, channels=channels, rate=self.rate, input=True,
                input_device_index=dev["index"], frames_per_buffer=512,
                stream_callback=callback,
            )
            self.pa = pa
            self.stream.start_stream()
        except Exception:
            try:
                pa.terminate()
            except Exception:
                pass
            self.pa = self.stream = None
            raise

    def stop(self):
        try:
            if self.stream is not None:
                self.stream.stop_stream()
                self.stream.close()
            if self.pa is not None:
                self.pa.terminate()
        except Exception:
            pass
        self.stream = None
        self.pa = None

    def frame(self):
        # WASAPI loopback no envia datos cuando no suena nada
        if time.time() - self.last_cb > 0.12:
            return None
        with self.lock:
            return self.buffer.copy()


class Analyzer:
    def __init__(self, capture):
        self.capture = capture
        self.window = np.hanning(FFT_SIZE).astype(np.float32)
        self.peak = 1e-3
        self.bars = 0
        self.rate = 0
        self.configure(DEFAULTS["bars"], capture.rate)

    def configure(self, bars, rate):
        self.bars, self.rate = bars, rate
        freqs = np.fft.rfftfreq(FFT_SIZE, 1.0 / rate)
        edges = np.geomspace(FMIN, min(FMAX, rate / 2 - 1), bars + 1)
        idx = np.searchsorted(freqs, edges)
        self.bands = [(int(idx[i]), int(max(idx[i + 1], idx[i] + 1))) for i in range(bars)]
        self.weights = np.linspace(1.0, 4.0, bars, dtype=np.float32)
        self.levels = np.zeros(bars, dtype=np.float32)

    def step(self, bars, gravity):
        if bars != self.bars or self.capture.rate != self.rate:
            self.configure(bars, self.capture.rate)

        frame = self.capture.frame()
        if frame is None:
            raw = np.zeros(self.bars, dtype=np.float32)
            loud = 0.0
        else:
            mag = np.abs(np.fft.rfft(frame * self.window)) / FFT_SIZE
            loud = float(mag.max())
            raw = np.array([mag[lo:hi].max() for lo, hi in self.bands], dtype=np.float32)
            raw = np.sqrt(raw * self.weights)

        cur = float(raw.max())
        self.peak = max(cur, self.peak * 0.995, 0.02)
        target = np.clip(raw / self.peak, 0.0, 1.0)
        self.levels = np.where(
            target > self.levels, target,
            self.levels - gravity * (self.levels - target) - 0.01)
        self.levels = np.clip(self.levels, 0.0, 1.0)
        return self.levels, loud


# -------------------------------------------------------------------- App
class App:
    def __init__(self):
        self.cfg = load_config()
        self.first_run = not CONFIG_FILE.exists()
        self.q = queue.Queue()
        self.running = True
        self.shown = False
        self.settings = None
        self.last_sound = time.time()
        self.last_vis = 0.0
        self.last_raise = 0.0
        self.rects = []

        # La raiz es una ventana invisible fuera de pantalla (duena de las demas)
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-alpha", 0.0)
        self.root.geometry("1x1+-5000+-5000")

        self.overlay = tk.Toplevel(self.root)
        self.overlay.withdraw()
        self.overlay.overrideredirect(True)
        self.overlay.configure(bg=TRANSPARENT)
        self.overlay.attributes("-transparentcolor", TRANSPARENT)
        self.canvas = tk.Canvas(self.overlay, bg=TRANSPARENT, highlightthickness=0)
        self.canvas.pack()
        self.canvas.bind("<Button-3>", lambda e: self.open_settings())

        self.capture = AudioCapture()
        self.analyzer = Analyzer(self.capture)
        self.levels = np.zeros(self.cfg["bars"], dtype=np.float32)

        self.make_tray()
        self.start_audio(notify=True)
        self.apply()

    # ---- utilidades
    def post(self, fn):
        self.q.put(fn)

    def start_audio(self, notify=False):
        try:
            self.capture.start()
            self.analyzer.configure(self.cfg["bars"], self.capture.rate)
        except Exception:
            logging.exception("No se pudo iniciar la captura de audio")
            if notify:
                try:
                    self.icon.notify("No se pudo capturar el audio del sistema.", "Taskbar Spectrum")
                except Exception:
                    pass

    # ---- bandeja
    def make_tray(self):
        menu = pystray.Menu(
            pystray.MenuItem("Configuración…", lambda i, it: self.post(self.open_settings), default=True),
            pystray.MenuItem("Mostrar visualizador", lambda i, it: self.post(self.toggle_enabled),
                             checked=lambda it: self.cfg["enabled"]),
            pystray.MenuItem("Reiniciar captura de audio", lambda i, it: self.post(self.start_audio)),
            pystray.MenuItem("Iniciar con Windows", lambda i, it: self.post(self.toggle_autostart),
                             checked=lambda it: autostart_enabled()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Salir", lambda i, it: self.post(self.quit)),
        )
        self.icon = pystray.Icon(APP_NAME, make_icon_image(64), "Taskbar Spectrum", menu)
        self.icon.run_detached()

    def toggle_enabled(self):
        self.cfg["enabled"] = not self.cfg["enabled"]
        save_config(self.cfg)
        self.icon.update_menu()

    def toggle_autostart(self):
        set_autostart(not autostart_enabled())
        self.icon.update_menu()

    # ---- ventana del visualizador
    def apply(self):
        c = self.cfg
        sw, tb_h, tb_y = taskbar_geometry()
        W = int(c["width"])
        H = max(8, tb_h - 12) if c["height_auto"] else int(c["height"])
        X = max(0, sw - int(c["offset_right"]) - W)
        Y = tb_y + (tb_h - H) // 2 + int(c["offset_y"])
        self.overlay.geometry(f"{W}x{H}+{X}+{Y}")
        self.canvas.config(width=W, height=H)
        self.overlay.attributes("-alpha", max(0.2, c["opacity"] / 100.0))
        self.W, self.H = W, H

        n = int(c["bars"])
        if n != self.analyzer.bars:
            self.analyzer.configure(n, self.capture.rate)
        gap = int(c["gap"])
        self.bar_w = max(1.0, (W - gap * (n - 1)) / n)
        self.gap = gap
        self.canvas.delete("all")
        self.rects = []
        for i in range(n):
            x0 = i * (self.bar_w + gap)
            self.rects.append(self.canvas.create_rectangle(
                x0, H - 2, x0 + self.bar_w, H, fill=c["color"], width=0))

    def draw(self, levels):
        H = self.H
        for i, r in enumerate(self.rects):
            x0 = i * (self.bar_w + self.gap)
            h = max(2.0, float(levels[i]) * (H - 2))
            self.canvas.coords(r, x0, H - h, x0 + self.bar_w, H)

    def set_visible(self, visible):
        if visible and not self.shown:
            self.overlay.deiconify()
            self.overlay.attributes("-topmost", True)
            self.shown = True
        elif not visible and self.shown:
            self.overlay.withdraw()
            self.shown = False

    def update_visibility(self, now):
        c = self.cfg
        want = c["enabled"]
        if want and c["visibility"] != "always":
            try:
                maximized, fullscreen = foreground_state()
            except Exception:
                maximized = fullscreen = False
            if fullscreen or (c["visibility"] == "maximized" and maximized):
                want = False
        if want and c["hide_silence"] and now - self.last_sound > c["silence_seconds"]:
            want = False
        self.set_visible(want)

    # ---- bucle principal
    def tick(self):
        try:
            while True:
                fn = self.q.get_nowait()
                try:
                    fn()
                except Exception:
                    logging.exception("Error en callback")
        except queue.Empty:
            pass
        if not self.running:
            return

        now = time.time()
        c = self.cfg
        if c["enabled"]:
            self.levels, loud = self.analyzer.step(int(c["bars"]), c["gravity"] / 100.0)
            if loud > SOUND_THRESHOLD:
                self.last_sound = now

        if now - self.last_vis >= 0.25:
            self.last_vis = now
            self.update_visibility(now)

        if self.shown:
            if now - self.last_raise >= 1.0:
                self.last_raise = now
                self.overlay.attributes("-topmost", True)
                self.overlay.lift()
            if len(self.levels) == len(self.rects):
                self.draw(self.levels)

        self.root.after(1000 // FPS, self.tick)

    def run(self):
        if self.first_run:
            save_config(self.cfg)
            # Si no viene del instalador, preguntar si quiere iniciar con Windows
            if "--installed" not in sys.argv and not autostart_enabled():
                # MB_YESNO | MB_ICONQUESTION | MB_TOPMOST
                answer = user32.MessageBoxW(
                    0,
                    "¿Quieres que Taskbar Spectrum se inicie automáticamente al encender el PC?\n\n"
                    "Podrás cambiarlo cuando quieras desde el icono de la bandeja.",
                    "Taskbar Spectrum", 0x4 | 0x20 | 0x40000)
                if answer == 6:  # IDYES
                    set_autostart(True)
                    self.icon.update_menu()
            try:
                self.icon.notify(
                    "Activo. Doble clic en el icono de la bandeja (o clic derecho en el "
                    "visualizador) para configurarlo.", "Taskbar Spectrum")
            except Exception:
                pass
        self.tick()
        self.root.mainloop()

    def quit(self):
        self.running = False
        save_config(self.cfg)
        self.capture.stop()
        try:
            self.icon.stop()
        except Exception:
            pass
        self.root.destroy()

    # ---- ventana de configuracion
    def close_settings(self):
        save_config(self.cfg)
        if self.settings is not None:
            self.settings.destroy()
            self.settings = None

    def reset_settings(self):
        self.cfg = dict(DEFAULTS)
        self.apply()
        self.close_settings()
        self.root.after(100, self.open_settings)

    def open_settings(self):
        if self.settings is not None and self.settings.winfo_exists():
            self.settings.deiconify()
            self.settings.lift()
            self.settings.focus_force()
            return

        win = tk.Toplevel(self.root)
        self.settings = win
        win.title("Taskbar Spectrum - Configuración")
        win.resizable(False, False)
        win.protocol("WM_DELETE_WINDOW", self.close_settings)
        frm = ttk.Frame(win, padding=14)
        frm.pack(fill="both", expand=True)
        frm.columnconfigure(1, weight=1)
        row = [0]
        cfg = self.cfg

        def check(text, key, extra=None):
            var = tk.BooleanVar(value=cfg[key])

            def cb():
                cfg[key] = var.get()
                self.apply()
                if extra:
                    extra()
            ttk.Checkbutton(frm, text=text, variable=var, command=cb).grid(
                row=row[0], column=0, columnspan=3, sticky="w", pady=3)
            row[0] += 1
            return var

        def slider(label, key, lo, hi, unit=""):
            ttk.Label(frm, text=label).grid(row=row[0], column=0, sticky="w", pady=4)
            val = ttk.Label(frm, width=8, anchor="e", text=f"{cfg[key]}{unit}")
            s = ttk.Scale(frm, from_=lo, to=hi, orient="horizontal", length=230, value=cfg[key])

            def on_move(v):
                n = int(float(v))
                cfg[key] = n
                val.config(text=f"{n}{unit}")
                self.apply()
            s.configure(command=on_move)
            s.grid(row=row[0], column=1, sticky="ew", padx=8)
            val.grid(row=row[0], column=2, sticky="e")
            row[0] += 1
            return s

        check("Mostrar visualizador", "enabled")

        ttk.Label(frm, text="Visibilidad").grid(row=row[0], column=0, sticky="w", pady=4)
        combo = ttk.Combobox(frm, state="readonly", width=46, values=list(VIS_LABELS.values()))
        combo.set(VIS_LABELS[cfg["visibility"]])

        def on_vis(_e):
            for k, v in VIS_LABELS.items():
                if v == combo.get():
                    cfg["visibility"] = k
        combo.bind("<<ComboboxSelected>>", on_vis)
        combo.grid(row=row[0], column=1, columnspan=2, sticky="w", padx=8)
        row[0] += 1

        check("Ocultar cuando no suena nada", "hide_silence")

        ttk.Label(frm, text="Color").grid(row=row[0], column=0, sticky="w", pady=6)
        swatch = tk.Label(frm, width=4, bg=cfg["color"], relief="solid", bd=1)
        swatch.grid(row=row[0], column=1, sticky="w", padx=8)

        def pick():
            res = colorchooser.askcolor(color=cfg["color"], parent=win, title="Color de las barras")
            if res and res[1]:
                cfg["color"] = res[1]
                swatch.config(bg=res[1])
                self.apply()
        ttk.Button(frm, text="Elegir…", command=pick).grid(row=row[0], column=2, sticky="e")
        row[0] += 1

        sw_max = user32.GetSystemMetrics(0)
        slider("Ancho", "width", 60, 800, " px")
        h_slider = None

        def refresh_height():
            if h_slider is not None:
                h_slider.state(["disabled"] if cfg["height_auto"] else ["!disabled"])

        check("Alto automático (según la barra de tareas)", "height_auto", refresh_height)
        h_slider = slider("Alto", "height", 8, 120, " px")
        refresh_height()
        slider("Cantidad de barras", "bars", 8, 96)
        slider("Espacio entre barras", "gap", 0, 8, " px")
        slider("Opacidad", "opacity", 20, 100, " %")
        slider("Distancia al borde derecho", "offset_right", 0, sw_max, " px")
        slider("Ajuste vertical", "offset_y", -40, 40, " px")
        slider("Caída de las barras", "gravity", 1, 50, " %")

        ttk.Separator(frm).grid(row=row[0], column=0, columnspan=3, sticky="ew", pady=8)
        row[0] += 1

        auto_var = tk.BooleanVar(value=autostart_enabled())

        def on_auto():
            set_autostart(auto_var.get())
            self.icon.update_menu()
        ttk.Checkbutton(frm, text="Iniciar con Windows", variable=auto_var, command=on_auto).grid(
            row=row[0], column=0, columnspan=3, sticky="w", pady=3)
        row[0] += 1

        credit = ttk.Label(frm, text=f"by: {AUTHOR}", foreground="#8a8a8a", cursor="hand2",
                           font=("Segoe UI", 9))
        credit.grid(row=row[0], column=0, sticky="sw", pady=(10, 0))
        credit.bind("<Button-1>", lambda e: webbrowser.open(AUTHOR_URL))
        credit.bind("<Enter>", lambda e: credit.config(foreground="#2ecc71"))
        credit.bind("<Leave>", lambda e: credit.config(foreground="#8a8a8a"))

        btns = ttk.Frame(frm)
        btns.grid(row=row[0], column=1, columnspan=2, sticky="e", pady=(10, 0))
        ttk.Button(btns, text="Restablecer", command=self.reset_settings).pack(side="left", padx=4)
        ttk.Button(btns, text="Reiniciar audio", command=self.start_audio).pack(side="left", padx=4)
        ttk.Button(btns, text="Cerrar", command=self.close_settings).pack(side="left", padx=4)

        win.update_idletasks()
        win.lift()
        win.focus_force()


# ------------------------------------------------------------------- main
def ensure_single_instance():
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = k32.CreateMutexW(None, False, "TaskbarSpectrumSingleton")
    if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
        return None
    return handle


def main():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=str(CONFIG_DIR / "app.log"), level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass
    mutex = ensure_single_instance()
    if mutex is None:
        return
    try:
        App().run()
    except Exception:
        logging.exception("Error fatal")
        raise


if __name__ == "__main__":
    main()
