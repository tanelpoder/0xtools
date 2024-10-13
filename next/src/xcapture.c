// SPDX-License-Identifier: (LGPL-2.1 OR BSD-2-Clause)
// Copyright 2024 Tanel Poder [0x.tools]

// This code layout is based on https://github.com/libbpf/libbpf-bootstrap

#include <stdio.h>
#include <unistd.h>
#include <pwd.h>
#include <bpf/bpf.h>
#include "xcapture.h"
#include "xcapture.skel.h"
#include <syscall_names.h>
#include <time.h>

// translate uid to user name
const char *getusername(uid_t uid)
{
  struct passwd *pw = getpwuid(uid);
  if (pw)
  {
    return pw->pw_name;
  }

  return "-";
}

static const char *get_task_state(__u32 state)
{
	switch (state & 0xFFF) {
	case 0x0000: return "RUNNING";
	case 0x0001: return "INTERRUPTIBLE";
	case 0x0002: return "UNINTERRUPTIBLE";
	case 0x0200: return "WAKING";
	case 0x0400: return "NOLOAD";
	case 0x0402: return "IDLE";
	case 0x0800: return "NEW";
	default: return "<unknown>";
	}
}


int main(int argc, char **argv)
{
	struct xcapture_bpf *skel;
	struct task_info buf;
	int iter_fd;
	ssize_t ret;
	int err;


	/* Open, load, and verify BPF application */
	skel = xcapture_bpf__open_and_load();
	if (!skel) {
		fprintf(stderr, "Failed to open and load BPF skeleton\n");
		goto cleanup;
	}

	/* Attach tracepoints */
	err = xcapture_bpf__attach(skel);
	if (err) {
		fprintf(stderr, "Failed to attach BPF skeleton\n");
		goto cleanup;
	}

	iter_fd = bpf_iter_create(bpf_link__fd(skel->links.get_tasks));
	if (iter_fd < 0) {
		err = -1;
		fprintf(stderr, "Failed to create iter\n");
		goto cleanup;
	}

	/* Print output (kernel pid printed as TID in userspace and kernel tgid as PID) */
	printf("%-23s  %7s  %7s  %-15s  %-16s  %-16s  %-16s  %-25s  %-16s  %s\n",
       "TIMESTAMP", "TID", "TGID", "STATE", "USER", "COMM", "EXE", "SYSCALL", "ARG0", "FILENAME");

    struct timespec ts;
    clock_gettime(CLOCK_REALTIME, &ts);
    char timestamp[64];
    struct tm *tm = localtime(&ts.tv_sec);
    strftime(timestamp, sizeof(timestamp), "%Y-%m-%d %H:%M:%S", tm);
    snprintf(timestamp + 19, sizeof(timestamp) - 19, ".%03ld", ts.tv_nsec / 1000000);

	while (true) {
		ret = read(iter_fd, &buf, sizeof(struct task_info));
		if (ret < 0) {
			if (errno == EAGAIN)
				continue;
			err = -errno;
			break;
		}
		if (ret == 0)
			break;

        printf("%-23s  %7d  %7d  %-15s  %-16s  %-16s  %-16s  %-25s  %-16llx  %s\n",
            timestamp, buf.pid, buf.tgid, get_task_state(buf.state), getusername(buf.euid), buf.comm, buf.exe_file,
            sysent0[buf.syscall_nr].name, buf.syscall_args[0], buf.filename[0] ? buf.filename : ""
        ); //
    }

    cleanup:
	/* Clean up */
	close(iter_fd);
	xcapture_bpf__destroy(skel);

	return err < 0 ? -err : 0;
}
