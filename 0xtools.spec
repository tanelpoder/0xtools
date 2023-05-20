%define  debug_package %{nil}
# %define _unpackaged_files_terminate_build 0

%define ReleaseNumber 5
%define VERSION 1.2.3

Name:           0xtools
Version:        %{VERSION}
Release:        %{ReleaseNumber}%{?dist}
Source0:        0xtools-%{VERSION}.tar.gz
URL:            https://0x.tools/
Packager:       Tanel Poder <tanel@tanelpoder.com>
Summary:        Always-on Profiling for Production Systems
License:        GPL
Group: 	        System Environment
BuildArch:      %{_arch}

# Creators of these rpmspec/service files are below (Tanel just merged/customized them):

# Liyong <hungrybirder@gmail.com>
# Bart Sjerps (https://github.com/bsjerps)

# RPM build instructions:
# Have rpmbuild, gcc, make and rpmdevtools installed
# Optionally, update Version above to the latest release
#
# Download 0xtools source archive into SOURCES:
# spectool -g -R 0xtools.spec
# 
# Build package:
# rpmbuild -bb 0xtools.spec

# Prevent compiling .py files
%define __python  false

%description
0x.tools is a set of open-source utilities for analyzing application performance on Linux.
It has a goal of deployment simplicity and minimal dependencies, to reduce friction of systematic troubleshooting.
There’s no need to upgrade the OS, install kernel modules, heavy monitoring frameworks, Java agents or databases.
These tools also work on over-decade-old Linux kernels, like version 2.6.18 from 15 years ago.

0x.tools allow you to measure individual thread level activity, like thread sleep states,
currently executing system calls and kernel wait locations.

%prep
%setup -q

%build
make PREFIX=%{buildroot}/usr
make install PREFIX=%{buildroot}/usr

%install
install -m 0755 -d -p %{buildroot}/usr/bin
install -m 0755 -d -p %{buildroot}/usr/bin/%{name}
install -m 0755 -d -p %{buildroot}/usr/lib/%{name}
install -m 0755 -d -p %{buildroot}/usr/share/%{name}
install -m 0755 -d -p %{buildroot}/var/log/xcapture

install -m 0755 bin/run_xcpu.sh %{buildroot}/usr/bin/run_xcpu.sh
install -m 0755 bin/run_xcapture.sh %{buildroot}/usr/bin/run_xcapture.sh
install -m 0755 bin/schedlat %{buildroot}/usr/bin/schedlat
install -m 0755 bin/vmtop %{buildroot}/usr/bin/vmtop

cp -p doc/licenses/*  %{buildroot}/usr/share/%{name}
cp -p LICENSE %{buildroot}/usr/share/%{name}


## empty files to please %ghost section (we don't want precompiled)
## This ensures the object files also get cleaned up if we uninstall the RPM
#touch %{buildroot}/usr/lib/%{name}/{psnreport,psnproc,argparse}.pyc
#touch %{buildroot}/usr/lib/%{name}/{psnreport,psnproc,argparse}.pyo


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
%defattr(0755,root,root,0755)
%{_bindir}/psn
%{_bindir}/run_xcapture.sh
%{_bindir}/run_xcpu.sh
%{_bindir}/schedlat
%{_bindir}/xcapture
%{_bindir}/vmtop
/usr/lib/0xtools/*
/usr/lib/systemd/system/xcapture.service
/usr/lib/systemd/system/xcapture-restart.service
/usr/lib/systemd/system/xcapture-restart.timer

%defattr(0644,root,root,0755)
/usr/share/%{name}
%ghost /usr/lib/%{name}/*.pyc
%ghost /usr/lib/%{name}/*.pyo

%config(noreplace) /etc/default/xcapture
%dir /var/log/xcapture/

