Name:		psnapper
Summary:	Linux Process Snapper
Version:	0.14
Release:	1%{?dtap}
BuildArch:	noarch
URL:		https://tp.dev/psnapper
Source0:	%{name}-%{version}.zip
License:	Python
Group:		Outrun/Extras

# This package can be downloaded from the 'Outrun Extras' repo, i.e.:
# yum install http://yum.outrun.nl/outrun-extras.rpm
# yum install psnapper
# This also ensures you get new versions when you run 'yum update'.
#
# RPM building:
# defining macro %dtap as .~devel%(date +"%m%d%H%M") automagically
# appends .~devel<datestamp> to the release.
# leave %dtap empty to build the prod version
# Optionally change Group to something else like System/Tools
# Download ZIP file using this command:
# wget https://github.com/tanelpoder/psnapper/archive/master.zip -O $(rpm --eval %_sourcedir)/psnapper-0.14.zip
#
# psnapper written by Tanel Poder
# RPM Build SPEC file written by Bart Sjerps (bart@outrun.nl).

%description
Linux Process Snapper (pSnapper, psn) is a Linux '/proc' profiler that works by sampling
Linux task states and other metrics from '/proc/PID/task/TID' pseudofiles.
pSnapper is a passive sampling profiler, it does not attach to your program
to slow it down, nor alter your program execution path or signal
handling (like 'strace' may inadvertently do).

As pSnapper is just a python script reading /proc files, it does not require software
installation, nor install any kernel modules. pSnapper does not even require root
access in most cases. The exception is if you want to sample some "private" /proc
files (like syscall, and kernel stack) of processes running under other users.

The current, initial release version v0.11 is between alpha & beta stage.
I have many more features to add, some known issues to fix
and the output & command line options may change.

%prep
%setup -q -n psnapper-master

%install
rm -rf %{buildroot}

install -m 0755 -d %{buildroot}/usr/share/doc/%{name}
install -m 0755 -d %{buildroot}/usr/lib/%{name}
install -m 0755 -d %{buildroot}/usr/bin

install -m 0755 -pt %{buildroot}/usr/lib/%{name}/ *.py *.h psn
install -m 0755 -pt %{buildroot}/usr/share/doc/%{name}/ CHANGELOG.md doc/licenses/Python-license.txt README.md

# empty files to please %ghost section
touch %{buildroot}//usr/lib/%{name}/{report,proc,argparse}.pyc
touch %{buildroot}//usr/lib/%{name}/{report,proc,argparse}.pyo

# wrapper script so we can call psn from anywhere
cat <<- 'EOF' > %{buildroot}/usr/bin/psn
	#!/bin/bash
	exec /usr/lib/%{name}/psn "$@"
	EOF

# Exit here prevents building and packaging *.pyc and *.pyo files
# We want them as ghost files so they are not distro dependent
exit 0

%files
/usr/share/doc/%{name}
/usr/lib/%{name}
%ghost /usr/lib/%{name}/*.pyc
%ghost /usr/lib/%{name}/*.pyo
%defattr(0755,root,root)
/usr/bin/psn
