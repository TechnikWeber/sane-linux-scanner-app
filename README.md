<img width="1318" height="769" alt="image" src="https://github.com/user-attachments/assets/3c57f368-0789-426d-9d7b-712d23f1d69c" />


# scan2paperless

Ein schlankes grafisches Scan-Programm für Linux, das über einen SANE-Scanner
Dokumente einliest, daraus ein PDF erzeugt und es direkt in den
**Paperless(-ngx)**-Consume-Ordner legt. Entwickelt und getestet mit einem
**Fujitsu fi-6130**, funktioniert aber mit jedem von SANE unterstützten Scanner.

Das Programm erkennt automatisch, welche Optionen der angeschlossene Scanner
beherrscht, und blendet nicht unterstützte Funktionen aus.

> Screenshot: `docs/screenshot.png` (gern ein eigenes Bild hier einfügen)

## Funktionen

- Scannen über den Einzug (Duplex, Vorder- oder Rückseite) oder Flachbett
- Farbe, Graustufen oder reines Schwarzweiß (Lineart)
- Automatische Erkennung der Scanner-Fähigkeiten über `scanimage -A`
- Automatisch zuschneiden, geraderücken, entrauschen und Leerseiten überspringen
- Seiten drehen (90/180/270°) und Farbscans optional als JPEG komprimieren
- Profile zum Speichern verschiedener Voreinstellungen
  (z. B. „Dokument Graustufen" vs. „Farbe Duplex")
- Dokumentname → wird zum Dateinamen und damit zum Titelvorschlag in Paperless
- Freies Feld für beliebige zusätzliche `scanimage`-Optionen
- Startmenü-Eintrag (.desktop) per Klick

## Voraussetzungen

- Python 3 mit Tkinter
- SANE (`scanimage`)
- `img2pdf`
- ImageMagick — nur nötig, wenn gedreht oder komprimiert wird

## Installation

### Fedora

```bash
sudo dnf install python3-tkinter sane-backends img2pdf ImageMagick
```

### Debian / Ubuntu

```bash
sudo apt install python3-tk sane-utils img2pdf imagemagick
```

### Arch Linux

```bash
sudo pacman -S tk sane img2pdf imagemagick
```

Anschließend das Repository klonen:

```bash
git clone https://github.com/<DEIN-NUTZERNAME>/scan2paperless.git
cd scan2paperless
```

## Scanner anschließen und prüfen

Der fi-6130 benötigt sein eigenes Netzteil und **keine** zusätzliche Firmware –
er läuft direkt über das SANE-`fujitsu`-Backend. Nach dem Anschließen prüfen:

```bash
scanimage -L
```

Erscheint dort dein Scanner (z. B. `fujitsu:fi-6130dj:...`), ist alles bereit.
Falls nicht, siehe [Fehlerbehebung](#fehlerbehebung).

## Benutzung

```bash
python3 scan2paperless_gui.py
```

1. Oben bei **Scanner** auf „Suchen" klicken — das Programm liest die
   Fähigkeiten des Geräts aus und füllt Quelle, Modus und Auflösung passend.
2. Unter **Ziel** den Paperless-Consume-Ordner auswählen.
3. Ein Profil wählen oder die Einstellungen anpassen und mit „Speichern" sichern.
4. Optional einen **Dokumentnamen** eingeben (gilt nur für den nächsten Scan).
5. Papier einlegen und auf **Scannen** klicken.

Das fertige PDF landet im Consume-Ordner; Paperless übernimmt von dort
automatisch Texterkennung (OCR) und Ablage.

### Empfohlene Einstellungen für Paperless

Für normale Papierdokumente sind **Graustufen bei 300 dpi** der beste
Kompromiss aus OCR-Qualität und Dateigröße. „Automatisch zuschneiden" und
„geraderücken" verbessern die Texterkennung. Farbe lohnt sich nur, wenn die
Farbe Information trägt (Stempel, Markierungen, Logos, Fotos).

### Zusatzoptionen

Über das Feld **Zusatzoptionen** lässt sich jede beliebige `scanimage`-Option
mitgeben, z. B. zur Doppeleinzug-Erkennung. Welche Optionen dein Gerät genau
kennt, zeigt der Knopf **„Optionen anzeigen"** oder direkt:

```bash
scanimage -A -d '<deine-geräte-kennung>'
```

## Konfiguration

Alle Einstellungen und Profile werden gespeichert unter:

```
~/.config/scan2paperless/config.json
```

## Kompatibilität

Das Programm ruft `scanimage` auf und funktioniert daher mit jedem
SANE-unterstützten Scanner. Optionen wie `swcrop`, `swdeskew`, `swdespeck`
und `swskip` gehören zum Fujitsu/Ricoh-Backend und werden bei anderen
Scannern automatisch ausgegraut. Innerhalb der Fujitsu-fi-Reihe
(fi-6140, fi-6240, fi-7160, iX500 …) läuft es praktisch identisch.

## Fehlerbehebung

**Scanner wird von `scanimage -L` nicht gefunden, aber `lsusb` zeigt ihn:**
einmal ab- und wieder anmelden (Geräterechte werden beim Login gesetzt) und
prüfen, dass in `/etc/sane.d/dll.conf` die Zeile `fujitsu` nicht auskommentiert
ist.

**`lsusb` zeigt den Scanner gar nicht / „Cannot enable, maybe the USB cable is
bad":** meist ein Kabel- oder Port-Problem. Anderes (kurzes) USB-Kabel und
einen anderen Port direkt am Rechner (kein Hub) probieren, Scanner-Netzteil
prüfen. Mit `sudo dmesg -w` beim Ein-/Ausstecken kontrollieren, ob ein Eintrag
mit `idVendor=04c5` erscheint.

**Seiten stehen auf dem Kopf:** entweder den Papierstapel andersherum einlegen
oder im Programm „Seiten drehen" mit 180° aktivieren.

**Leere Rückseiten im Duplex-Modus:** „Leerseiten überspringen (swskip)"
aktivieren oder bei einseitigen Dokumenten die Quelle „ADF Front" wählen.

## Geplant

- Seitenvorschau vor dem Ablegen

## Lizenz

[MIT](LICENSE).
