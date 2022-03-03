%define  debug_package %{nil}
# %define _unpackaged_files_terminate_build 0

%define ReleaseNumber 1
%define VERSION 1.2.0

Name:           0xtools
Version:        %{VERSION}
Release:        %{ReleaseNumber}%{?dist}
Source0:        0xtools-%{VERSION}.tar.gz
URL:            https://0x.tools/
Packager:       liyong <hungrybirder@gmail.com>
Summary:        Always-on Profiling for Production Systems
License:        GPL
Group: 	        System Environment
BuildArch:      %{_arch}

%description
0x.tools is a set of open-source utilities for analyzing application performance on Linux.
It has a goal of deployment simplicity and minimal dependencies, to reduce friction of systematic troubleshooting.
There’s no need to upgrade the OS, install kernel modules, heavy monitoring frameworks, Java agents or databases.
These tools also work on over-decade-old Linux kernels, like version 2.6.18 from 14 years ago.

%prep
%setup -q

%build
make

%install
mkdir -p %{buildroot}/usr/{bin,lib}
install -m 0755 bin/run_xcpu.sh %{buildroot}/usr/bin/run_xcpu.sh
install -m 0755 bin/run_xcapture.sh %{buildroot}/usr/bin/run_xcapture.sh
PREFIX=%{buildroot}/usr make install


install -d -m 0755  %{buildroot}/var/run/xcapture

# systemd service
install -Dp -m 0644 xcapture.default  $RPM_BUILD_ROOT/etc/default/xcapture
install -Dp -m 0644 xcapture.service  %{buildroot}/usr/lib/systemd/system/xcapture.service
install -Dp -m 0644 xcapture-restart.service  %{buildroot}/usr/lib/systemd/system/xcapture-restart.service
install -Dp -m 0644 xcapture-restart.timer  %{buildroot}/usr/lib/systemd/system/xcapture-restart.timer

%clean
rm -rf %{buildroot}

%post
/bin/systemctl daemon-reload
/bin/systemctl enable --now xcapture
/bin/systemctl enable --now xcapture-restart.timer

%preun
if [ "$1" -eq "0" ]
then
	/bin/systemctl disable --now xcapture
	/bin/systemctl disable --now xcapture-restart.timer
fi

%files
%{_bindir}/psn
%{_bindir}/run_xcapture.sh
%{_bindir}/run_xcpu.sh
%{_bindir}/schedlat
%{_bindir}/xcapture
/usr/lib/0xtools/*
/usr/lib/systemd/system/xcapture.service
/usr/lib/systemd/system/xcapture-restart.service
/usr/lib/systemd/system/xcapture-restart.timer
%config(noreplace) /etc/default/xcapture
%dir /var/run/xcapture/
