# scan2paperless

<p>
  <img alt="Status: stable" src="https://img.shields.io/badge/status-stable-brightgreen">
  <a href="https://github.com/TechnikWeber/sane-linux-scanner-app/releases/latest"><img alt="Download" src="https://img.shields.io/github/v/release/TechnikWeber/sane-linux-scanner-app?label=download&color=2ea44f"></a>
  <a href="https://github.com/TechnikWeber/sane-linux-scanner-app/actions/workflows/ci.yml"><img alt="Build" src="https://img.shields.io/github/actions/workflow/status/TechnikWeber/sane-linux-scanner-app/ci.yml?branch=main&label=build"></a>
  <img alt="Platform: Linux" src="https://img.shields.io/badge/platform-Linux-blue">
  <img alt="Python 3 + Tkinter" src="https://img.shields.io/badge/python-3%20%2B%20Tkinter-informational">
  <img alt="UI language: German" src="https://img.shields.io/badge/UI-Deutsch-informational">
  <a href="LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-green"></a>
</p>

A lean graphical scanning app for Linux: it scans documents through any SANE scanner,
turns them into a PDF and drops it straight into the **Paperless(-ngx)** consume folder.
Developed with a **Fujitsu fi-6130** and a **Brother ADS-4300N**, it works with every
scanner SANE supports, including driverless eSCL / AirScan devices.

The app detects automatically which options the connected scanner offers and hides
functions it does not support.

<img width="1318" height="769" alt="scan2paperless: scanner, target folder, profile and scan settings" src="https://github.com/user-attachments/assets/3c57f368-0789-426d-9d7b-712d23f1d69c" />

## Features

- Scan from the feeder (duplex, front or back) or the flatbed
- Colour, greyscale or pure black and white (lineart)
- Detects the scanner's capabilities automatically via `scanimage -A`
- Automatic cropping, deskewing, despeckling and skipping of blank pages
- Rotate pages (90/180/270°) and optionally compress colour scans as JPEG
- Profiles for different presets (e.g. "document greyscale" vs. "colour duplex")
- Document name → becomes the file name and with that the title suggestion in Paperless
- **Erweiterte Optionen** (advanced options): every option the scanner reports that the
  main window does not cover, saved per profile
- **Treiber & Backends** (drivers and backends): shows which backend is in use, checks
  and installs ipp-usb (driverless scanning over USB), helps set up Brother brscan5 and
  writes a script for the scan button on the device (brscan-skey)
- Free field for any additional `scanimage` options

The interface is in German.

## Installation

**Fedora:** download `scan2paperless-*.noarch.rpm` from the
[latest release](https://github.com/TechnikWeber/sane-linux-scanner-app/releases/latest) and

```bash
sudo dnf install ./scan2paperless-*.noarch.rpm
```

It pulls in SANE, `img2pdf` and Tkinter, recommends ImageMagick and sane-airscan, and
adds **Scan zu Paperless** to the application menu. From a terminal: `scan2paperless`.
`sudo dnf remove scan2paperless` takes it away again; your settings stay in
`~/.config/scan2paperless`.

**Other distributions:** install the requirements, then run the script from a clone.

| Distribution | Requirements |
|---|---|
| Debian / Ubuntu | `sudo apt install python3-tk sane-utils img2pdf imagemagick sane-airscan` |
| Arch Linux | `sudo pacman -S tk sane img2pdf imagemagick sane-airscan` |

```bash
git clone https://github.com/TechnikWeber/sane-linux-scanner-app.git
cd sane-linux-scanner-app
python3 scan2paperless_gui.py
```

The button **Startmenü-Eintrag** in the app adds a menu entry pointing to the clone.
ImageMagick is only needed for rotating or compressing.

## Connect and check the scanner

The fi-6130 needs its own power supply and **no** extra firmware — it runs directly with
SANE's `fujitsu` backend. After connecting it, check:

```bash
scanimage -L
```

If your scanner shows up there (e.g. `fujitsu:fi-6130dj:...`), everything is ready. If not,
see [Troubleshooting](#troubleshooting).

Network scanners such as the Brother ADS-4300N show up driverless as `airscan:...` with
sane-airscan; over USB they need `ipp-usb` (the app's **Treiber & Backends** window
installs it). Brother's own driver brscan5 adds a second entry `brother5:...` with extra
functions; both can be installed side by side, pick one at **Scanner**.

## Usage

Start **Scan zu Paperless** from the menu (or `scan2paperless`, or
`python3 scan2paperless_gui.py` in the clone).

1. At **Scanner**, click "Suchen" (search) — the app reads the device's capabilities and
   fills in source, mode and resolution accordingly.
2. Under **Ziel** (target), choose the Paperless consume folder.
3. Choose a profile or adjust the settings and save them with "Speichern".
4. Optionally enter a **document name** (applies to the next scan only).
5. Load the paper and click **Scannen**.

The finished PDF lands in the consume folder; Paperless takes over text recognition (OCR)
and filing from there.

### Recommended settings for Paperless

For normal paper documents, **greyscale at 300 dpi** is the best compromise between OCR
quality and file size. Automatic cropping and deskewing improve text recognition. Colour is
only worth it when the colour carries information (stamps, highlighting, logos, photos).

### Extra options

The **Zusatzoptionen** (extra options) field passes any `scanimage` option, e.g. for
double-feed detection. Which options your device knows is shown by the button **"Optionen
anzeigen"**, or directly:

```bash
scanimage -A -d '<your-device-id>'
```

## Configuration

All settings and profiles are stored in:

```
~/.config/scan2paperless/config.json
```

## Compatibility

The app calls `scanimage` and therefore works with every SANE-supported scanner. Options
such as `swcrop`, `swdeskew`, `swdespeck` and `swskip` belong to the Fujitsu/Ricoh backend
and are greyed out automatically for other scanners. Within the Fujitsu fi series (fi-6140,
fi-6240, fi-7160, iX500 …) it works practically the same.

## Troubleshooting

**`scanimage -L` does not find the scanner, but `lsusb` shows it:** log out and back in once
(device permissions are set at login) and check that the line `fujitsu` is not commented
out in `/etc/sane.d/dll.conf`.

**`lsusb` does not show the scanner at all / "Cannot enable, maybe the USB cable is bad":**
usually a cable or port problem. Try another (short) USB cable and another port directly on
the computer (no hub), check the scanner's power supply. Watch `sudo dmesg -w` while
plugging in and out for an entry with `idVendor=04c5`.

**Pages are upside down:** either load the stack the other way round or enable "rotate
pages" by 180° in the app.

**Blank backs in duplex mode:** enable "skip blank pages (swskip)", or choose the source
"ADF Front" for single-sided documents.

## Planned

- Page preview before filing

## License

[MIT](LICENSE).
