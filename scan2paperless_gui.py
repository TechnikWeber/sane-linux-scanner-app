#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scan2paperless_gui.py  (Version 2)
==================================
Grafisches Scan-Programm für SANE-Scanner (entwickelt am Fujitsu fi-6130),
das ein PDF erzeugt und in den Paperless-Consume-Ordner legt.

Neu in Version 2:
  - Profile (gespeicherte Voreinstellungen) mit Anlegen/Speichern/Löschen
  - Automatische Erkennung der unterstützten Optionen über `scanimage -A`
    -> funktioniert dadurch auch mit anderen Scannern
  - Entrauschen (swdespeck), autom. Seitenlänge (ald), Helligkeit/Kontrast
  - Dokumentname -> Dateiname (= Paperless-Titelvorschlag)
  - Farbscans komprimieren (ImageMagick)
  - Freies Feld für Zusatzoptionen + "Optionen anzeigen" (scanimage -A)
  - Startmenü-Eintrag (.desktop) per Klick

Erweitern: Eine neue Einstellung wird zur Profil-Variable in DEFAULT_SETTINGS,
bekommt ein Widget in build_ui(), wird (falls scanner-abhängig) in
apply_capabilities() ein-/ausgeblendet und in build_scan_command() bzw.
scan_worker() verwendet.

Benötigt: python3-tkinter, sane-backends (scanimage), img2pdf,
          ImageMagick (nur für Drehen/Komprimieren).
"""

import json
import os
import re
import queue
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
from datetime import datetime
from pathlib import Path

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog

# ----------------------------------------------------------------------
# Konfiguration / Standardwerte
# ----------------------------------------------------------------------
CONFIG_DIR = Path.home() / ".config" / "scan2paperless"
CONFIG_FILE = CONFIG_DIR / "config.json"

# Einstellungen, die ein Profil ausmachen:
DEFAULT_SETTINGS = {
    "source": "ADF Duplex",
    "mode": "Gray",
    "resolution": "300",
    "rotate_enabled": True,
    "rotate_angle": "180",
    "skip_blank": True,
    "skip_threshold": "8",
    "swcrop": True,
    "swdeskew": True,
    "despeck_enabled": False,
    "despeck_value": "1",
    "ald": False,
    "paper_size": "A4",
    "paper_w": "210",
    "paper_h": "297",
    "reverse_order": True,
    "reverse_mode": "Komplett umkehren",
    "brightness": 0,
    "contrast": 0,
    "compress_color": False,
    "compress_quality": "75",
    "extra_options": "",
}

# Beispielprofile beim ersten Start:
SEED_PROFILES = {
    "Dokument (Graustufen)": {**DEFAULT_SETTINGS},
    "Farbe": {**DEFAULT_SETTINGS, "mode": "Color", "skip_blank": False,
              "compress_color": True},
}

DEFAULT_CONFIG = {
    "device": "fujitsu:fi-6130dj:202618",
    "consume_dir": str(Path.home() / "paperless" / "consume"),
    "active_profile": "Dokument (Graustufen)",
    "profiles": SEED_PROFILES,
}

SOURCES = ["ADF Duplex", "ADF Front", "ADF Back", "Flatbed"]
MODES = ["Color", "Gray", "Lineart"]
RESOLUTIONS = ["150", "200", "300", "400", "600"]
ANGLES = ["90", "180", "270"]
REVERSE_MODES = ["Komplett umkehren", "Blattweise (Duplex paarweise)"]

# Papiergrößen in mm (Breite, Höhe). "Eigene" nutzt die Felder paper_w/paper_h,
# "Aus" gibt gar keine Größe an den Scanner weiter.
PAPER_SIZES = {
    "A4": ("210", "297"),
    "A5": ("148", "210"),
    "Letter": ("216", "279"),
    "Legal": ("216", "356"),
    "Eigene": None,
    "Aus (Scanner-Standard)": "off",
}


# ----------------------------------------------------------------------
# Hilfsfunktionen ohne GUI
# ----------------------------------------------------------------------
def has_imagemagick():
    return bool(shutil.which("magick") or shutil.which("mogrify"))


def im_rotate(path, angle):
    """Datei in-place drehen (IM6: mogrify, IM7: magick mogrify)."""
    if shutil.which("mogrify"):
        subprocess.run(["mogrify", "-rotate", str(angle), str(path)], check=True)
    else:
        subprocess.run(["magick", "mogrify", "-rotate", str(angle), str(path)], check=True)


def im_to_jpeg(src, dst, quality):
    """TIFF -> JPEG konvertieren (zum Verkleinern von Farbscans)."""
    if shutil.which("convert"):
        subprocess.run(["convert", str(src), "-quality", str(quality), str(dst)], check=True)
    else:
        subprocess.run(["magick", str(src), "-quality", str(quality), str(dst)], check=True)


def list_devices():
    """Alle SANE-Geräte abfragen."""
    try:
        out = subprocess.run(["scanimage", "--formatted-device-list=%d%n"],
                             capture_output=True, text=True, timeout=60).stdout
    except Exception:
        return []
    devs = [l.strip() for l in out.splitlines() if l.strip()]
    devs.sort(key=lambda d: ("fujitsu" not in d.lower(), d))
    return devs


def query_options_raw(device):
    """Rohausgabe von `scanimage -A` für ein Gerät."""
    try:
        r = subprocess.run(["scanimage", "-A", "-d", device],
                           capture_output=True, text=True, timeout=60)
        return (r.stdout or "") + (r.stderr or "")
    except Exception as e:
        return f"(Fehler beim Abfragen: {e})"


def parse_capabilities(text):
    """`scanimage -A`-Ausgabe in ein Dict name -> Infos zerlegen."""
    caps = {}
    for line in text.splitlines():
        m = re.match(r'^\s+--([a-zA-Z][a-zA-Z0-9-]*)(.*)$', line)
        if not m:
            continue
        name = m.group(1)
        rest = m.group(2).strip()
        spec = re.sub(r'\s*\[[^\]]*\]\s*$', '', rest).strip()  # [default]/[inactive] entfernen
        info = {"type": "other", "choices": [], "min": None, "max": None}
        if "yes|no" in spec:
            info["type"] = "bool"
        elif "|" in spec:
            info["type"] = "enum"
            info["choices"] = [c.strip() for c in spec.strip("[]= ").split("|") if c.strip()]
        else:
            rng = re.search(r'(-?\d+(?:\.\d+)?)\.\.(-?\d+(?:\.\d+)?)', spec)
            if rng:
                info["type"] = "range"
                info["min"] = float(rng.group(1))
                info["max"] = float(rng.group(2))
        caps[name] = info
    return caps


def resolution_choices(caps):
    presets = [150, 200, 300, 400, 600]
    info = caps.get("resolution")
    if not info:
        return [str(p) for p in presets]
    if info["type"] == "enum":
        vals = sorted({int(re.search(r'\d+', c).group())
                       for c in info["choices"] if re.search(r'\d+', c)})
        return [str(v) for v in vals] if vals else [str(p) for p in presets]
    if info["type"] == "range" and info["max"]:
        return [str(p) for p in presets if p <= info["max"]]
    return [str(p) for p in presets]


# ----------------------------------------------------------------------
# Hauptanwendung
# ----------------------------------------------------------------------
class ScanApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Scan → Paperless")
        self.root.minsize(1000, 560)

        self.log_queue = queue.Queue()
        self.scanning = False
        self.caps = {}          # erkannte Scanner-Optionen
        self.opt_widgets = {}   # name -> Liste von Widgets zum Ein-/Ausblenden

        self.cfg = self.load_config()

        # globale Variablen (nicht Teil der Profile)
        self.var_device = tk.StringVar(value=self.cfg["device"])
        self.var_consume = tk.StringVar(value=self.cfg["consume_dir"])
        self.var_profile = tk.StringVar(value=self.cfg["active_profile"])
        self.var_doc_name = tk.StringVar(value="")  # pro Scan, wird nicht gespeichert

        # Profil-Einstellungen als Variablen
        self.vars = {}
        self._make_setting_vars()

        self.build_ui()
        self.load_profile_into_vars(self.var_profile.get())
        self.update_paper_fields()
        self.poll_log()
        # Optionen des Standardgeräts im Hintergrund erkennen
        self.refresh_capabilities()

    # ---------------- Variablen anlegen ----------------
    def _make_setting_vars(self):
        s = DEFAULT_SETTINGS
        self.vars = {
            "source": tk.StringVar(value=s["source"]),
            "mode": tk.StringVar(value=s["mode"]),
            "resolution": tk.StringVar(value=s["resolution"]),
            "rotate_enabled": tk.BooleanVar(value=s["rotate_enabled"]),
            "rotate_angle": tk.StringVar(value=s["rotate_angle"]),
            "skip_blank": tk.BooleanVar(value=s["skip_blank"]),
            "skip_threshold": tk.StringVar(value=s["skip_threshold"]),
            "swcrop": tk.BooleanVar(value=s["swcrop"]),
            "swdeskew": tk.BooleanVar(value=s["swdeskew"]),
            "despeck_enabled": tk.BooleanVar(value=s["despeck_enabled"]),
            "despeck_value": tk.StringVar(value=s["despeck_value"]),
            "ald": tk.BooleanVar(value=s["ald"]),
            "paper_size": tk.StringVar(value=s["paper_size"]),
            "paper_w": tk.StringVar(value=s["paper_w"]),
            "paper_h": tk.StringVar(value=s["paper_h"]),
            "reverse_order": tk.BooleanVar(value=s["reverse_order"]),
            "reverse_mode": tk.StringVar(value=s["reverse_mode"]),
            "brightness": tk.IntVar(value=s["brightness"]),
            "contrast": tk.IntVar(value=s["contrast"]),
            "compress_color": tk.BooleanVar(value=s["compress_color"]),
            "compress_quality": tk.StringVar(value=s["compress_quality"]),
            "extra_options": tk.StringVar(value=s["extra_options"]),
        }

    # ---------------- Config laden/speichern ----------------
    def load_config(self):
        cfg = json.loads(json.dumps(DEFAULT_CONFIG))  # tiefe Kopie
        try:
            if CONFIG_FILE.exists():
                data = json.loads(CONFIG_FILE.read_text())
                if "profiles" not in data:
                    # Migration: alte flache Konfig in ein Profil packen
                    prof = {k: data.get(k, v) for k, v in DEFAULT_SETTINGS.items()}
                    cfg["profiles"] = {"Standard": prof}
                    cfg["active_profile"] = "Standard"
                    cfg["device"] = data.get("device", cfg["device"])
                    cfg["consume_dir"] = data.get("consume_dir", cfg["consume_dir"])
                else:
                    cfg.update(data)
        except Exception:
            pass
        return cfg

    def save_config(self):
        self.cfg["device"] = self.var_device.get()
        self.cfg["consume_dir"] = self.var_consume.get()
        self.cfg["active_profile"] = self.var_profile.get()
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            CONFIG_FILE.write_text(json.dumps(self.cfg, indent=2, ensure_ascii=False))
        except Exception as e:
            self.log(f"!! Konnte Einstellungen nicht speichern: {e}")

    # ---------------- Profile ----------------
    def collect_settings(self):
        return {k: var.get() for k, var in self.vars.items()}

    def load_profile_into_vars(self, name):
        prof = self.cfg["profiles"].get(name)
        if not prof:
            return
        for k, var in self.vars.items():
            if k in prof:
                var.set(prof[k])

    def on_profile_selected(self, *_):
        self.load_profile_into_vars(self.var_profile.get())
        self.apply_capabilities(self.caps)
        self.update_paper_fields()

    def on_paper_selected(self, *_):
        size = self.vars["paper_size"].get()
        dims = PAPER_SIZES.get(size)
        if isinstance(dims, tuple):  # Standardgröße -> Felder füllen
            self.vars["paper_w"].set(dims[0])
            self.vars["paper_h"].set(dims[1])
        self.update_paper_fields()

    def update_paper_fields(self):
        """Eingabefelder für eigene Maße nur bei 'Eigene' bearbeitbar machen."""
        editable = self.vars["paper_size"].get() == "Eigene"
        state = "normal" if editable else "disabled"
        for w in (getattr(self, "ent_pw", None), getattr(self, "ent_ph", None)):
            if w is not None:
                try:
                    w.configure(state=state)
                except tk.TclError:
                    pass

    def save_current_profile(self):
        name = self.var_profile.get()
        self.cfg["profiles"][name] = self.collect_settings()
        self.save_config()
        self.log(f">> Profil '{name}' gespeichert.")

    def new_profile(self):
        name = simpledialog.askstring("Neues Profil", "Name des Profils:", parent=self.root)
        if not name:
            return
        self.cfg["profiles"][name] = self.collect_settings()
        self.cmb_profile["values"] = list(self.cfg["profiles"].keys())
        self.var_profile.set(name)
        self.save_config()
        self.log(f">> Profil '{name}' angelegt.")

    def delete_profile(self):
        name = self.var_profile.get()
        if len(self.cfg["profiles"]) <= 1:
            messagebox.showinfo("Hinweis", "Das letzte Profil kann nicht gelöscht werden.")
            return
        if not messagebox.askyesno("Löschen", f"Profil '{name}' löschen?"):
            return
        self.cfg["profiles"].pop(name, None)
        names = list(self.cfg["profiles"].keys())
        self.cmb_profile["values"] = names
        self.var_profile.set(names[0])
        self.load_profile_into_vars(names[0])
        self.save_config()
        self.log(f">> Profil '{name}' gelöscht.")

    # ---------------- Oberfläche ----------------
    def build_ui(self):
        pad = {"padx": 6, "pady": 3}
        outer = ttk.Frame(self.root, padding=10)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(3, weight=1)  # Protokollzeile darf wachsen

        # zwei gleich breite Spalten nebeneinander
        cols = ttk.Frame(outer)
        cols.grid(row=0, column=0, sticky="ew")
        cols.columnconfigure(0, weight=1, uniform="col")
        cols.columnconfigure(1, weight=1, uniform="col")
        left = ttk.Frame(cols)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        left.columnconfigure(0, weight=1)
        right = ttk.Frame(cols)
        right.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        right.columnconfigure(0, weight=1)

        # ---- Scanner & Profil (links) ----
        g = ttk.LabelFrame(left, text="Scanner & Profil", padding=8)
        g.grid(sticky="ew", pady=4)
        g.columnconfigure(1, weight=1)

        ttk.Label(g, text="Scanner:").grid(row=0, column=0, sticky="w", **pad)
        self.cmb_device = ttk.Combobox(g, textvariable=self.var_device,
                                       values=[self.var_device.get()])
        self.cmb_device.grid(row=0, column=1, sticky="ew", **pad)
        ttk.Button(g, text="Suchen", command=self.refresh_devices).grid(row=0, column=2, **pad)

        ttk.Label(g, text="Profil:").grid(row=1, column=0, sticky="w", **pad)
        self.cmb_profile = ttk.Combobox(g, textvariable=self.var_profile, state="readonly",
                                        values=list(self.cfg["profiles"].keys()))
        self.cmb_profile.grid(row=1, column=1, sticky="ew", **pad)
        self.cmb_profile.bind("<<ComboboxSelected>>", self.on_profile_selected)
        pf = ttk.Frame(g)
        pf.grid(row=1, column=2, **pad)
        ttk.Button(pf, text="Speichern", width=10, command=self.save_current_profile).pack(side="left")
        ttk.Button(pf, text="Neu", width=5, command=self.new_profile).pack(side="left", padx=2)
        ttk.Button(pf, text="Löschen", width=8, command=self.delete_profile).pack(side="left")

        # ---- Scan-Einstellungen (links) ----
        g = ttk.LabelFrame(left, text="Scan-Einstellungen", padding=8)
        g.grid(sticky="ew", pady=4)
        g.columnconfigure(1, weight=1)

        ttk.Label(g, text="Quelle:").grid(row=0, column=0, sticky="w", **pad)
        self.cmb_source = ttk.Combobox(g, textvariable=self.vars["source"], values=SOURCES, state="readonly")
        self.cmb_source.grid(row=0, column=1, columnspan=2, sticky="ew", **pad)

        ttk.Label(g, text="Farbmodus:").grid(row=1, column=0, sticky="w", **pad)
        self.cmb_mode = ttk.Combobox(g, textvariable=self.vars["mode"], values=MODES, state="readonly")
        self.cmb_mode.grid(row=1, column=1, columnspan=2, sticky="ew", **pad)

        ttk.Label(g, text="Auflösung (dpi):").grid(row=2, column=0, sticky="w", **pad)
        self.cmb_res = ttk.Combobox(g, textvariable=self.vars["resolution"], values=RESOLUTIONS)
        self.cmb_res.grid(row=2, column=1, columnspan=2, sticky="ew", **pad)

        ttk.Label(g, text="Papiergröße:").grid(row=3, column=0, sticky="w", **pad)
        self.cmb_paper = ttk.Combobox(g, textvariable=self.vars["paper_size"],
                                      values=list(PAPER_SIZES.keys()), state="readonly")
        self.cmb_paper.grid(row=3, column=1, columnspan=2, sticky="ew", **pad)
        self.cmb_paper.bind("<<ComboboxSelected>>", self.on_paper_selected)

        # Felder für eigene Maße (nur bei "Eigene" aktiv)
        cf = ttk.Frame(g)
        cf.grid(row=4, column=1, columnspan=2, sticky="w", **pad)
        ttk.Label(cf, text="B:").pack(side="left")
        self.ent_pw = ttk.Entry(cf, textvariable=self.vars["paper_w"], width=6)
        self.ent_pw.pack(side="left", padx=(2, 8))
        ttk.Label(cf, text="H (mm):").pack(side="left")
        self.ent_ph = ttk.Entry(cf, textvariable=self.vars["paper_h"], width=6)
        self.ent_ph.pack(side="left", padx=2)

        cb = ttk.Checkbutton(g, text="Seitenlänge automatisch erkennen (ald)", variable=self.vars["ald"])
        cb.grid(row=5, column=0, columnspan=3, sticky="w", **pad)
        self.opt_widgets["ald"] = [cb]

        ttk.Label(g, text="Helligkeit:").grid(row=6, column=0, sticky="w", **pad)
        sc_b = tk.Scale(g, from_=-127, to=127, orient="horizontal", variable=self.vars["brightness"])
        sc_b.grid(row=6, column=1, columnspan=2, sticky="ew", **pad)
        self.opt_widgets["brightness"] = [sc_b]

        ttk.Label(g, text="Kontrast:").grid(row=7, column=0, sticky="w", **pad)
        sc_c = tk.Scale(g, from_=-127, to=127, orient="horizontal", variable=self.vars["contrast"])
        sc_c.grid(row=7, column=1, columnspan=2, sticky="ew", **pad)
        self.opt_widgets["contrast"] = [sc_c]

        # ---- Aufbereitung (rechts) ----
        g = ttk.LabelFrame(right, text="Aufbereitung", padding=8)
        g.grid(sticky="ew", pady=4)
        g.columnconfigure(1, weight=1)

        cb = ttk.Checkbutton(g, text="Automatisch zuschneiden (swcrop)", variable=self.vars["swcrop"])
        cb.grid(row=0, column=0, columnspan=3, sticky="w", **pad)
        self.opt_widgets["swcrop"] = [cb]

        cb = ttk.Checkbutton(g, text="Automatisch geraderücken (swdeskew)", variable=self.vars["swdeskew"])
        cb.grid(row=1, column=0, columnspan=3, sticky="w", **pad)
        self.opt_widgets["swdeskew"] = [cb]

        cb = ttk.Checkbutton(g, text="Entrauschen (swdespeck), Punktgröße:", variable=self.vars["despeck_enabled"])
        cb.grid(row=2, column=0, columnspan=2, sticky="w", **pad)
        sp = ttk.Spinbox(g, from_=1, to=15, width=5, textvariable=self.vars["despeck_value"])
        sp.grid(row=2, column=2, **pad)
        self.opt_widgets["swdespeck"] = [cb, sp]

        cb = ttk.Checkbutton(g, text="Leerseiten überspringen (swskip), Schwelle %:", variable=self.vars["skip_blank"])
        cb.grid(row=3, column=0, columnspan=2, sticky="w", **pad)
        en = ttk.Entry(g, textvariable=self.vars["skip_threshold"], width=6)
        en.grid(row=3, column=2, **pad)
        self.opt_widgets["swskip"] = [cb, en]

        ttk.Checkbutton(g, text="Seiten drehen (ImageMagick) um",
                        variable=self.vars["rotate_enabled"]).grid(row=4, column=0, columnspan=2, sticky="w", **pad)
        ttk.Combobox(g, textvariable=self.vars["rotate_angle"], values=ANGLES,
                     state="readonly", width=6).grid(row=4, column=2, **pad)

        ttk.Checkbutton(g, text="Farbscans komprimieren (JPEG-Qualität %):",
                        variable=self.vars["compress_color"]).grid(row=5, column=0, columnspan=2, sticky="w", **pad)
        ttk.Spinbox(g, from_=40, to=95, width=5, textvariable=self.vars["compress_quality"]).grid(row=5, column=2, **pad)

        ttk.Checkbutton(g, text="Seitenreihenfolge umkehren (letzte Seite zuerst eingezogen)",
                        variable=self.vars["reverse_order"]).grid(row=6, column=0, columnspan=3, sticky="w", **pad)
        ttk.Label(g, text="Umkehr-Modus:").grid(row=7, column=0, sticky="w", **pad)
        ttk.Combobox(g, textvariable=self.vars["reverse_mode"], values=REVERSE_MODES,
                     state="readonly").grid(row=7, column=1, columnspan=2, sticky="ew", **pad)

        ttk.Label(g, text="Zusatzoptionen:").grid(row=8, column=0, sticky="w", **pad)
        ttk.Entry(g, textvariable=self.vars["extra_options"]).grid(row=8, column=1, columnspan=2, sticky="ew", **pad)

        # ---- Ziel (rechts) ----
        g = ttk.LabelFrame(right, text="Ziel", padding=8)
        g.grid(sticky="ew", pady=4)
        g.columnconfigure(1, weight=1)

        ttk.Label(g, text="Dokumentname:").grid(row=0, column=0, sticky="w", **pad)
        ttk.Entry(g, textvariable=self.var_doc_name).grid(row=0, column=1, columnspan=2, sticky="ew", **pad)

        ttk.Label(g, text="Paperless-Ordner:").grid(row=1, column=0, sticky="w", **pad)
        ttk.Entry(g, textvariable=self.var_consume).grid(row=1, column=1, sticky="ew", **pad)
        ttk.Button(g, text="…", width=3, command=self.choose_dir).grid(row=1, column=2, **pad)

        # ---- Aktionen (volle Breite) ----
        bar = ttk.Frame(outer)
        bar.grid(row=1, column=0, sticky="ew", pady=6)
        bar.columnconfigure(0, weight=1)
        self.btn_scan = ttk.Button(bar, text="Scannen", command=self.start_scan)
        self.btn_scan.grid(row=0, column=0, sticky="ew", padx=2)
        ttk.Button(bar, text="Optionen anzeigen", command=self.show_options).grid(row=0, column=1, padx=2)
        ttk.Button(bar, text="Startmenü-Eintrag", command=self.create_desktop_entry).grid(row=0, column=2, padx=2)

        # ---- Protokoll (volle Breite) ----
        ttk.Label(outer, text="Protokoll:").grid(row=2, column=0, sticky="w")
        self.txt_log = tk.Text(outer, height=7, wrap="word", state="disabled")
        self.txt_log.grid(row=3, column=0, sticky="nsew")

    # ---------------- Capabilities ----------------
    def refresh_capabilities(self):
        dev = self.var_device.get()
        if not dev:
            return
        self.log(">> Lese Scanner-Fähigkeiten …")
        def worker():
            caps = parse_capabilities(query_options_raw(dev))
            self.root.after(0, lambda: self._caps_ready(caps))
        threading.Thread(target=worker, daemon=True).start()

    def _caps_ready(self, caps):
        self.caps = caps
        self.apply_capabilities(caps)
        if caps:
            self.log(f">> {len(caps)} Optionen erkannt.")
        else:
            self.log("!! Konnte Optionen nicht lesen – nutze Standardwerte.")

    def apply_capabilities(self, caps):
        if not caps:
            return
        if "source" in caps and caps["source"]["choices"]:
            self.cmb_source["values"] = caps["source"]["choices"]
        if "mode" in caps and caps["mode"]["choices"]:
            self.cmb_mode["values"] = caps["mode"]["choices"]
        self.cmb_res["values"] = resolution_choices(caps)

        for opt, widgets in self.opt_widgets.items():
            state = "normal" if opt in caps else "disabled"
            for w in widgets:
                try:
                    w.configure(state=state)
                except tk.TclError:
                    pass

    # ---------------- kleine Aktionen ----------------
    def choose_dir(self):
        d = filedialog.askdirectory(initialdir=self.var_consume.get() or str(Path.home()))
        if d:
            self.var_consume.set(d)

    def refresh_devices(self):
        self.log(">> Suche Scanner …")
        def worker():
            devs = list_devices()
            self.root.after(0, lambda: self._set_devices(devs))
        threading.Thread(target=worker, daemon=True).start()

    def _set_devices(self, devs):
        if devs:
            self.cmb_device["values"] = devs
            fuj = next((d for d in devs if "fujitsu" in d.lower()), devs[0])
            self.var_device.set(fuj)
            self.log(f">> {len(devs)} Gerät(e) gefunden.")
            self.refresh_capabilities()
        else:
            self.log("!! Kein Scanner gefunden. Eingeschaltet und verbunden?")

    def show_options(self):
        dev = self.var_device.get()
        self.log(f">> scanimage -A für {dev}:")
        def worker():
            raw = query_options_raw(dev)
            self.root.after(0, lambda: self.log(raw.strip()))
        threading.Thread(target=worker, daemon=True).start()

    def create_desktop_entry(self):
        script = os.path.abspath(sys.argv[0])
        content = (
            "[Desktop Entry]\n"
            "Type=Application\n"
            "Name=Scan zu Paperless\n"
            "Comment=Dokumente scannen und an Paperless übergeben\n"
            f"Exec=python3 {shlex.quote(script)}\n"
            "Icon=scanner\n"
            "Terminal=false\n"
            "Categories=Office;Scanning;\n"
        )
        dest = Path.home() / ".local" / "share" / "applications" / "scan2paperless.desktop"
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content)
            os.chmod(dest, 0o755)
            self.log(f">> Startmenü-Eintrag angelegt: {dest}")
            messagebox.showinfo("Fertig", "Eintrag im Startmenü angelegt.\n"
                                          "Eventuell einmal ab- und anmelden, bis er erscheint.")
        except Exception as e:
            self.log(f"!! Konnte Eintrag nicht anlegen: {e}")

    def log(self, msg):
        self.log_queue.put(str(msg))

    def poll_log(self):
        while not self.log_queue.empty():
            msg = self.log_queue.get_nowait()
            self.txt_log.configure(state="normal")
            self.txt_log.insert("end", msg + "\n")
            self.txt_log.see("end")
            self.txt_log.configure(state="disabled")
        self.root.after(150, self.poll_log)

    # ---------------- scanimage-Befehl ----------------
    def supported(self, opt):
        """True, wenn die Option unterstützt wird – oder wenn wir es (noch) nicht wissen."""
        return (not self.caps) or (opt in self.caps)

    def build_scan_command(self, batch_pattern):
        v = self.vars
        cmd = ["scanimage", "-d", self.var_device.get(),
               "--source", v["source"].get(),
               "--mode", v["mode"].get(),
               "--resolution", v["resolution"].get(),
               "--format=tiff", f"--batch={batch_pattern}"]
        if v["swcrop"].get() and self.supported("swcrop"):
            cmd.append("--swcrop=yes")
        if v["swdeskew"].get() and self.supported("swdeskew"):
            cmd.append("--swdeskew=yes")
        if v["despeck_enabled"].get() and self.supported("swdespeck"):
            cmd += ["--swdespeck", str(v["despeck_value"].get())]
        if v["skip_blank"].get() and self.supported("swskip"):
            cmd += ["--swskip", str(v["skip_threshold"].get())]
        if v["ald"].get() and self.supported("ald"):
            cmd.append("--ald=yes")
        # Papiergröße (feste Maße verhindern abgeschnittene Seiten)
        size = v["paper_size"].get()
        if size != "Aus (Scanner-Standard)":
            w, h = v["paper_w"].get().strip(), v["paper_h"].get().strip()
            if w and self.supported("page-width"):
                cmd += ["--page-width", w]
            if h and self.supported("page-height"):
                cmd += ["--page-height", h]
        if int(v["brightness"].get()) != 0 and self.supported("brightness"):
            cmd += ["--brightness", str(v["brightness"].get())]
        if int(v["contrast"].get()) != 0 and self.supported("contrast"):
            cmd += ["--contrast", str(v["contrast"].get())]
        extra = v["extra_options"].get().strip()
        if extra:
            cmd += shlex.split(extra)
        return cmd

    def output_path(self):
        consume = Path(self.var_consume.get()).expanduser()
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        name = self.var_doc_name.get().strip()
        if name:
            safe = re.sub(r'[^\w\-. ]', "_", name).strip()
            fname = f"{safe}_{ts}.pdf"
        else:
            fname = f"scan_{ts}.pdf"
        return consume, consume / fname

    # ---------------- Scan starten ----------------
    def start_scan(self):
        if self.scanning:
            return
        if not shutil.which("scanimage"):
            messagebox.showerror("Fehler", "scanimage nicht gefunden – sane-backends installieren.")
            return
        if not shutil.which("img2pdf"):
            messagebox.showerror("Fehler", "img2pdf nicht gefunden – img2pdf installieren.")
            return
        need_im = self.vars["rotate_enabled"].get() or \
            (self.vars["compress_color"].get() and self.vars["mode"].get() == "Color")
        if need_im and not has_imagemagick():
            messagebox.showerror("Fehler", "ImageMagick fehlt (für Drehen/Komprimieren).\n"
                                           "'sudo dnf install ImageMagick' oder Optionen abschalten.")
            return

        self.save_config()
        self.scanning = True
        self.btn_scan.configure(state="disabled", text="Scanne …")
        threading.Thread(target=self.scan_worker, daemon=True).start()

    def scan_worker(self):
        try:
            with tempfile.TemporaryDirectory() as work:
                pattern = os.path.join(work, "page_%03d.tiff")
                cmd = self.build_scan_command(pattern)
                self.log(">> Scanne über den Einzug …")
                proc = subprocess.run(cmd, capture_output=True, text=True)
                if proc.returncode not in (0, 7) and proc.stderr:
                    self.log("scanimage: " + proc.stderr.strip())

                pages = sorted(Path(work).glob("page_*.tiff"))
                if not pages:
                    self.log("!! Keine Seiten gescannt. Liegt Papier im Einzug?")
                    return
                self.log(f">> {len(pages)} Seite(n) gescannt.")

                if self.vars["reverse_order"].get():
                    mode = self.vars["reverse_mode"].get()
                    if mode.startswith("Blattweise") and len(pages) % 2 == 0:
                        # Duplex-Sonderfall: paarweise umkehren (Vorder-/Rückseite zusammen)
                        pairs = [pages[i:i + 2] for i in range(0, len(pages), 2)]
                        pages = [p for pair in reversed(pairs) for p in pair]
                    else:
                        # Standard: komplette Umkehrung der Seitenfolge
                        pages = list(reversed(pages))
                    self.log(f">> Seitenreihenfolge umgekehrt ({mode}).")

                if self.vars["rotate_enabled"].get():
                    angle = self.vars["rotate_angle"].get()
                    self.log(f">> Drehe Seiten um {angle}° …")
                    for p in pages:
                        im_rotate(p, angle)

                final_pages = pages
                if self.vars["compress_color"].get() and self.vars["mode"].get() == "Color":
                    q = self.vars["compress_quality"].get()
                    self.log(f">> Komprimiere Farbseiten (JPEG {q}) …")
                    jpgs = []
                    for p in pages:
                        j = p.with_suffix(".jpg")
                        im_to_jpeg(p, j, q)
                        jpgs.append(j)
                    final_pages = jpgs

                consume, out = self.output_path()
                consume.mkdir(parents=True, exist_ok=True)
                self.log(">> Erstelle PDF …")
                subprocess.run(["img2pdf", *[str(p) for p in final_pages], "-o", str(out)], check=True)
                self.log(f">> Fertig: {out}")
                self.log(">> Paperless verarbeitet das Dokument automatisch.")
        except subprocess.CalledProcessError as e:
            self.log(f"!! Fehler: {e}")
        except Exception as e:
            self.log(f"!! Unerwarteter Fehler: {e}")
        finally:
            self.root.after(0, self._scan_done)

    def _scan_done(self):
        self.scanning = False
        self.btn_scan.configure(state="normal", text="Scannen")


def main():
    root = tk.Tk()
    try:
        ttk.Style().theme_use("clam")
    except tk.TclError:
        pass
    ScanApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
