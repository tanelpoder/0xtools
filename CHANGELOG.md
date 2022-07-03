# 0x.tools changelog

1.1.0
======================
* general
  - using semantic versioning now (major.minor.patch)
  - in the future, will update version numbers in a specific tool only when it was updated

* pSnapper
  - `psn` works with python 3 now too (uses whereever the "/usr/bin/env python" command points to)

* xcapture
 - Fixed xcapture compiler warnings shown on newer gcc versions
 - More precise sampling interval (account for sampling busy-time and subtract that from next sleep duration)
 - Under 1 sec sleep durations supported (For example `-d 0.1` for sampling at 10 Hz)

* make/install
 - by default, executables go to `/usr/bin` now
 - python libraries go under PREFIX/lib/0xtools now
 - use PREFIX option in makefile to adjust the installation root
 - makefile uses the `install` command instead of the `ln -s` hack for installing files
 - `make uninstall` removes installed files

0.18
======================
* New column
  - `filenamesum` column strips numbers out of filenames to summarize events against similar files

0.16
======================
* New script
  - schedlat.py - show scheduling latency of a single process

0.15
======================
* Minor changes only
  - Handle SIGPIPE to not get `IOError: [Errno 32] Broken pipe` error when piping pSnapper output to other tools like "head"
  - Change the info link tp.dev/psnapper to tanelpoder.com/psnapper

0.14
======================
* report file names that are accessed with I/O syscalls with arg0 as the file descriptor
  - example: `sudo psn -G syscall,filename`
  - works with read, write, pread, fsync, recvmsg, sendmsg etc, but not with batch io syscalls like io_submit(), select() that may submit multiple fds per call

* no need to install kernel-headers package anymore as pSnapper now has the unistd.h file bundled with the install
  - no more exceptions complaining about missing unistd_64.h file
  - pSnapper still tries to use the unistd.h file from a standard /usr/include location, but falls back to the bundled one if the file is missing. this should help with using pSnapper on other platforms too (different processor architectures, including 32bit vs 64bit versions of the same architecture have different syscall numbers

* pSnapper can now run on RHEL5 equivalents (2.6.18 kernel), however with separately installed python26 or later, as I haven't "downgraded" pSnapper's python code to work with python 2.4 (yet)
  - you could install python 2.6 or 2.7 manually in your own directory or use the EPEL package: (yum install epel-release ; yum install python26 )
  - you will also need to uncomment the 2nd line in psn script (use #!/usr/bin/env/python26 instead of python)
  - note that 2.6.18 kernel doesnt provide syscall,file name and kstack sampling (but wchan is available)



0.13
======================
* kernel stack summary reporting - new column `kstack`
* wider max column length (for kstack)
* add `--list` option to list all available columns
* replace digits from `comm` column by default to collapse different threads of the same thing into one. you can use `comm2` to see the unedited process comm.

