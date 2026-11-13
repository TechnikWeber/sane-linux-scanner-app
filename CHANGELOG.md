# Changelog

## [2.0.0] - 2026-11-13

* **RPM for Fedora:** `sudo dnf install ./scan2paperless-*.noarch.rpm` brings
  SANE, img2pdf and Tkinter along, recommends ImageMagick and sane-airscan,
  and adds the menu entry. The command is `scan2paperless`.
* **Driverless scanners:** eSCL / AirScan devices (`airscan:`), over the
  network or over USB with ipp-usb, next to vendor backends.
* **Treiber & Backends** window: which backend is in use, ipp-usb status and
  install, Brother brscan5 setup, a scan-button script for brscan-skey.
* **Erweiterte Optionen:** every option the scanner reports that the main
  window does not cover, saved per profile. Short geometry options (`-x`,
  `-l` …) as used by sane-airscan are recognised.
* The scanner is searched for at the first start; Brother devices come first,
  cameras (`v4l`) last. Defaults tuned for the Brother ADS-4300N.
