Name:		psnapper
Summary:	Linux Process Snapper
Version:	0.14
Release:	2%{?dtap}
BuildArch:	noarch
URL:		https://tp.dev/psnapper
Source0:	%{name}-%{version}.tbz2
License:	Python
Group:		Outrun/Extras

# Prevent compiling .py files
%define	__python	false

# This package can be downloaded from the 'Outrun Extras' repo, i.e.:
# yum install http://yum.outrun.nl/outrun-extras.rpm
# yum install psnapper
# This also ensures you get new versions when you run 'yum update'.
#
# RPM building:
# Clone the git repo:
# git clone https://github.com/tanelpoder/psnapper.git
# cd to top of repository
# cd psnapper
# Create source archive:
# git ls-files -z | xargs -0 tar jcvf $(rpm --eval %_sourcedir)/psnapper-0.14.tbz2 --transform 's|^|psnapper/|'
# Build the package:
# rpmbuild -bb psnapper.spec

# defining macro %dtap as .~devel%(date +"%m%d%H%M") automagically
# appends .~devel<datestamp> to the release.
# leave %dtap empty to build the prod version
# Optionally change Group to something else like System/Tools
#
# psnapper written by Tanel Poder
# RPM Build SPEC, man page and bash completion file written by Bart Sjerps (bart@outrun.nl).

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
%setup -q -n %{name}

%install
rm -rf %{buildroot}
install -m 0755 -d %{buildroot}/etc/bash_completion.d
install -m 0755 -d %{buildroot}/usr/bin
install -m 0755 -d %{buildroot}/usr/share/man/man1
install -m 0755 -d %{buildroot}/usr/share/doc/%{name}
install -m 0755 -d %{buildroot}/usr/lib/%{name}

cp -p bin/psn %{buildroot}/usr/bin
cp -p bash_completion/psn.bash %{buildroot}/etc/bash_completion.d/
cp -p man1/* %{buildroot}/usr/share/man/man1/
cp -p *.py *.h psn %{buildroot}/usr/lib/%{name}/
cp -p CHANGELOG.md doc/licenses/Python-license.txt README.md %{buildroot}/usr/share/doc/%{name}/

# empty files to please %ghost section (we don't want precompiled)
touch %{buildroot}//usr/lib/%{name}/{report,proc,argparse}.pyc
touch %{buildroot}//usr/lib/%{name}/{report,proc,argparse}.pyo

%files
%defattr(0644,root,root)
/etc/bash_completion.d/psn.bash
/usr/share/doc/%{name}
/usr/share/man/man1/*
/usr/lib/%{name}/*.h
%ghost /usr/lib/%{name}/*.pyc
%ghost /usr/lib/%{name}/*.pyo
%defattr(0755,root,root)
/usr/lib/%{name}/*.py
/usr/lib/%{name}/psn
/usr/bin/psn
