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

