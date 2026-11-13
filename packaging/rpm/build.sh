#!/usr/bin/env bash
# Builds dist/scan2paperless-<version>-1.<dist>.noarch.rpm on Fedora.
# Installs its build dependencies when run as root (CI container).
set -euo pipefail

root="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/../.." && pwd)"
cd "$root"
name=scan2paperless
version="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' scan2paperless_gui.py)"
spec_version="$(sed -n 's/^Version: *//p' packaging/rpm/$name.spec)"
[ "$version" = "$spec_version" ] || { echo "version mismatch: $version vs spec $spec_version" >&2; exit 1; }

if [ "$(id -u)" = 0 ]; then
    dnf install -y -q rpm-build python3-devel desktop-file-utils tar
fi

top="$root/build/rpm"
rm -rf "$top"
mkdir -p "$top/SOURCES" "$root/dist"
tar --exclude=./build --exclude=./dist --exclude=./.git \
    --transform "s|^\./|$name-$version/|" \
    -czf "$top/SOURCES/$name-$version.tar.gz" .
rpmbuild -bb --define "_topdir $top" packaging/rpm/$name.spec
cp "$top"/RPMS/noarch/*.rpm "$root/dist/"
ls -l "$root/dist"
