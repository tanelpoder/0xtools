Name:		0xtools
Summary:	Always-on Profiling for Production Systems
Version:	1.1.3
Release:	1
BuildArch:	x86_64
URL:		https://0x.tools/
Source0:	https://github.com/tanelpoder/0xtools/archive/v%{version}.tar.gz
License:	GPLv2
Group:		Applications/System

# Prevent compiling .py files
%define	__python	false

# Author: Bart Sjerps (https://github.com/bsjerps)
# 
# RPM build instructions:
# Have rpmbuild, gcc, make and rpmdevtools installed
# Optionally, update Version above to the latest release
#
# Download 0xtools source archive into SOURCES:
# spectool -g -R 0xtools.spec
# 
# Build package:
# rpmbuild -bb 0xtools.spec

%description
0x.tools is a set of open-source utilities for analyzing application performance on Linux. It has a goal
of deployment simplicity and minimal dependencies, to reduce friction of systematic troubleshooting.
There’s no need to upgrade the OS, install kernel modules, heavy monitoring frameworks, Java agents or databases.
These tools also work on over-decade-old Linux kernels, like version 2.6.18 from 14 years ago.

0x.tools allow you to measure individual thread level activity, like thread sleep states,
currently executing system calls and kernel wait locations. Additionally, you can drill down into CPU usage
of any thread or the system as a whole. You can be systematic in your troubleshooting - no need for
guessing or clever metric-voodoo tricks with traditional system-level statistics.

Usage info and more details here:
* https://0x.tools

Twitter:
* https://twitter.com/0xtools

Author:
* https://tanelpoder.com/about


%prep
%setup -q 

%install
install -m 0755 -d %{buildroot}/usr/bin
install -m 0755 -d %{buildroot}/usr/lib/%{name}
install -m 0755 -d %{buildroot}/usr/share/%{name}

make PREFIX=%{buildroot}/usr
make install PREFIX=%{buildroot}/usr
cp -p doc/licenses/*  %{buildroot}/usr/share/%{name}
cp -p LICENSE %{buildroot}/usr/share/%{name}

# empty files to please %ghost section (we don't want precompiled)
# This ensures the object files also get cleaned up if we uninstall the RPM
touch %{buildroot}//usr/lib/%{name}/{psnreport,proc,argparse}.pyc
touch %{buildroot}//usr/lib/%{name}/{psnreport,proc,argparse}.pyo


%files
%defattr(0755,root,root,0755)
/usr/bin/*
%dir /usr/lib/0xtools
/usr/lib/0xtools/*.py
%defattr(0644,root,root,0755)
/usr/share/%{name}
%ghost /usr/lib/%{name}/*.pyc
%ghost /usr/lib/%{name}/*.pyo
