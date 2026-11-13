Name:           scan2paperless
Version:        2.0.0
Release:        1%{?dist}
Summary:        Scan documents with SANE and hand them to Paperless
License:        MIT
URL:            https://github.com/TechnikWeber/sane-linux-scanner-app
Source0:        %{url}/archive/v%{version}/%{name}-%{version}.tar.gz
BuildArch:      noarch

BuildRequires:  python3-devel
BuildRequires:  desktop-file-utils
Requires:       python3-tkinter
Requires:       sane-backends
Requires:       /usr/bin/img2pdf
# rotating and compressing colour scans
Recommends:     ImageMagick
# driverless network/USB scanners (eSCL / AirScan)
Recommends:     sane-airscan
Suggests:       ipp-usb

%description
A lean scanning app for SANE scanners: scans from the feeder or the flatbed,
turns the pages into a PDF and drops it straight into the Paperless-ngx
consume folder. It reads the options the scanner offers and hides what it
does not support. The interface is in German.

%prep
%autosetup -n %{name}-%{version}

%build
# pure Python, nothing to build

%install
install -Dm644 scan2paperless_gui.py %{buildroot}%{_datadir}/%{name}/scan2paperless_gui.py
install -Dm755 /dev/stdin %{buildroot}%{_bindir}/%{name} <<'SH'
#!/bin/sh
exec /usr/bin/python3 -s %{_datadir}/%{name}/scan2paperless_gui.py "$@"
SH
desktop-file-install --dir=%{buildroot}%{_datadir}/applications share/%{name}.desktop
install -Dm644 share/io.github.technikweber.%{name}.metainfo.xml \
    %{buildroot}%{_metainfodir}/io.github.technikweber.%{name}.metainfo.xml

%files
%license LICENSE
%doc README.md CHANGELOG.md
%{_bindir}/%{name}
%{_datadir}/%{name}/
%{_datadir}/applications/%{name}.desktop
%{_metainfodir}/io.github.technikweber.%{name}.metainfo.xml

%changelog
* Fri Nov 13 2026 Philipp Weber - 2.0.0-1
- First packaged release: eSCL/AirScan, ipp-usb, Brother brscan5, advanced options
