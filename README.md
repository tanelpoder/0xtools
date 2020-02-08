# Linux Process Snapper

Linux Process Snapper (pSnapper, psn) is a Linux `/proc` profiler that works by sampling Linux task states and other metrics from `/proc/PID/task/TID` pseudofiles. pSnapper is a _passive sampling profiler_, it does not attach to your program to slow it down, nor alter your program execution path or signal handling (like `strace` may inadvertently do).

As pSnapper is just a python script reading /proc files, it does not require software installation, nor install any kernel modules. pSnapper does not even require root access in most cases. The exception is if you want to sample some “private” /proc files (like syscall, and kernel stack) of processes running under other users.

The current pSnapper version v0.15 is beta phase. I have many more features to add, some known issues to fix and the output & command line options may change.

More info at https://tanelpoder.com/psnapper

