// SPDX-License-Identifier: (LGPL-2.1 OR BSD-2-Clause)
// Copyright (c) 2020 Wenbo Zhang
// Modified for PERCPU_HASH usage, timestamp selection, and print type fix
//
// Based on biolatency(8) from BCC by Brendan Gregg.
// 15-Jun-2020   Wenbo Zhang   Created this.
// 02-Apr-2025   Tanel Poder   Changes below:
//   Rely on built-in [io_]start_time_ns fields in Linux kernel
//   Remove IO insert/issue TPs and starts map
//   Mark "hists" map as per-CPU map

#include <argp.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h> // Needed for malloc/free/calloc
#include <string.h> // Needed for strerror/memset
#include <unistd.h>
#include <fcntl.h>
#include <time.h>
#include <errno.h>  // Needed for errno
#include <limits.h> // Needed for UINT_MAX check
#include <bpf/libbpf.h>
#include <sys/resource.h> // Needed for setrlimit
#include <bpf/bpf.h>
#include <bpf/btf.h>
#include "blk_types.h"
#include "biolatency.h" // Contains struct hist definition (must use unsigned long long)
#include "biolatency.skel.h"
#include "trace_helpers.h" // Contains print_log2_hist (expects unsigned int*)

#define ARRAY_SIZE(x) (sizeof(x) / sizeof(*(x)))

// Environment struct stores command line options
static struct env {
	char *disk;
	time_t interval;
	int times;
	bool timestamp;
	bool queued;
	bool per_disk;
	bool per_flag;
	bool milliseconds;
	bool verbose;
	char *cgroupspath;
	bool cg;
} env = {
	.interval = 99999999,
	.times = 99999999,
};

static volatile bool exiting;

// Command line argument parsing setup (argp)
const char *argp_program_version = "biolatency 0.4"; // Version bump
const char *argp_program_bug_address =
	"https://github.com/iovisor/bcc/tree/master/libbpf-tools";
const char argp_program_doc[] =
"Summarize block device I/O latency as a histogram (uses PERCPU_HASH).\n"
"\n"
"USAGE: biolatency [--help] [-T] [-m] [-Q] [-D] [-F] [-d DISK] [-c CG] [interval] [count]\n"
"\n"
"EXAMPLES:\n"
"    biolatency             # summarize block I/O latency as a histogram\n"
"    biolatency 1 10        # print 1 second summaries, 10 times\n"
"    biolatency -mT 1       # 1s summaries, milliseconds, and timestamps\n"
"    biolatency -Q          # include OS queued time in I/O time\n"
"    biolatency -D          # show each disk device separately\n"
"    biolatency -F          # show I/O flags separately\n"
"    biolatency -d sdc      # Trace sdc only\n"
"    biolatency -c CG       # Trace process under cgroupsPath CG\n";

static const struct argp_option opts[] = {
	{ "timestamp", 'T', NULL, 0, "Include timestamp on output", 0 },
	{ "milliseconds", 'm', NULL, 0, "Millisecond histogram", 0 },
	{ "queued", 'Q', NULL, 0, "Include OS queued time in I/O time", 0 },
	{ "disk", 'D', NULL, 0, "Print a histogram per disk device", 0 },
	{ "flag", 'F', NULL, 0, "Print a histogram per set of I/O flags", 0 },
	{ "disk",  'd', "DISK",  0, "Trace this disk only", 0 },
	{ "verbose", 'v', NULL, 0, "Verbose debug output", 0 },
	{ "cgroup", 'c', "/sys/fs/cgroup/unified", 0, "Trace process in cgroup path", 0 },
	{ NULL, 'h', NULL, OPTION_HIDDEN, "Show the full help", 0 },
	{},
};

// Parser function for arguments
static error_t parse_arg(int key, char *arg, struct argp_state *state)
{
	static int pos_args;

	switch (key) {
	case 'h':
		argp_state_help(state, stderr, ARGP_HELP_STD_HELP);
		break;
	case 'v':
		env.verbose = true;
		break;
	case 'm':
		env.milliseconds = true;
		break;
	case 'Q':
		env.queued = true; // This flag controls BPF logic now
		break;
	case 'D':
		env.per_disk = true;
		break;
	case 'F':
		env.per_flag = true;
		break;
	case 'T':
		env.timestamp = true;
		break;
	case 'c':
		env.cgroupspath = arg;
		env.cg = true;
		break;
	case 'd':
		env.disk = arg;
		if (strlen(arg) + 1 > DISK_NAME_LEN) {
			fprintf(stderr, "invaild disk name: too long\n");
			argp_usage(state);
		}
		break;
	case ARGP_KEY_ARG:
		errno = 0;
		if (pos_args == 0) {
			env.interval = strtol(arg, NULL, 10);
			if (errno || env.interval <= 0) { // Basic validation
				fprintf(stderr, "Invalid interval: %s\n", arg);
				argp_usage(state);
			}
		} else if (pos_args == 1) {
			env.times = strtol(arg, NULL, 10);
			if (errno || env.times <= 0) { // Basic validation
				fprintf(stderr, "Invalid times: %s\n", arg);
				argp_usage(state);
			}
		} else {
			fprintf(stderr,
				"unrecognized positional argument: %s\n", arg);
			argp_usage(state);
		}
		pos_args++;
		break;
	default:
		return ARGP_ERR_UNKNOWN;
	}
	return 0;
}

// libbpf logging callback
static int libbpf_print_fn(enum libbpf_print_level level, const char *format, va_list args)
{
	// Ignore debug messages unless -v is specified
	if (level == LIBBPF_DEBUG && !env.verbose)
		return 0;
	return vfprintf(stderr, format, args);
}

// Signal handler for graceful exit
static void sig_handler(int sig)
{
	exiting = true;
}

// Helper function to print readable command flags
static void print_cmd_flags(int cmd_flags)
{
	static struct { int bit; const char *str; } flags[] = {
		{ REQ_NOWAIT, "NoWait-" }, { REQ_BACKGROUND, "Background-" },
		{ REQ_RAHEAD, "ReadAhead-" }, { REQ_PREFLUSH, "PreFlush-" },
		{ REQ_FUA, "FUA-" }, { REQ_INTEGRITY, "Integrity-" },
		{ REQ_IDLE, "Idle-" }, { REQ_NOMERGE, "NoMerge-" },
		{ REQ_PRIO, "Priority-" }, { REQ_META, "Metadata-" },
		{ REQ_SYNC, "Sync-" },
	};
	static const char *ops[] = {
		[REQ_OP_READ] = "Read", [REQ_OP_WRITE] = "Write",
		[REQ_OP_FLUSH] = "Flush", [REQ_OP_DISCARD] = "Discard",
		[REQ_OP_SECURE_ERASE] = "SecureErase", [REQ_OP_ZONE_RESET] = "ZoneReset",
		[REQ_OP_WRITE_SAME] = "WriteSame", [REQ_OP_ZONE_RESET_ALL] = "ZoneResetAll",
		[REQ_OP_WRITE_ZEROES] = "WriteZeroes", [REQ_OP_ZONE_OPEN] = "ZoneOpen",
		[REQ_OP_ZONE_CLOSE] = "ZoneClose", [REQ_OP_ZONE_FINISH] = "ZoneFinish",
		[REQ_OP_SCSI_IN] = "SCSIIn", [REQ_OP_SCSI_OUT] = "SCSIOut",
		[REQ_OP_DRV_IN] = "DrvIn", [REQ_OP_DRV_OUT] = "DrvOut",
	};
	size_t i;

	printf("flags = ");
	for (i = 0; i < ARRAY_SIZE(flags); i++) {
		if (cmd_flags & flags[i].bit)
			printf("%s", flags[i].str);
	}
	// Check array bounds before accessing ops
	if ((cmd_flags & REQ_OP_MASK) < ARRAY_SIZE(ops) && ops[cmd_flags & REQ_OP_MASK])
		printf("%s", ops[cmd_flags & REQ_OP_MASK]);
	else
		printf("Unknown(%d)", cmd_flags & REQ_OP_MASK);
}


// Function to read map, aggregate per-CPU values, and print histograms
static int print_log2_hists(struct bpf_map *hists, struct partitions *partitions)
{
	// lookup_key is used to find the *next* element after a given key
	// next_key stores the key found by get_next_key
	struct hist_key lookup_key = {}, next_key;
	const char *units = env.milliseconds ? "msecs" : "usecs";
	int err, fd = bpf_map__fd(hists);
	struct hist *percpu_hists = NULL; // Buffer for per-CPU raw data (unsigned long long)
	struct hist total_hist;           // Aggregated data (unsigned long long)
	int i, j;
	long ncpus;
	int get_next_key_ret; // Store return value
	size_t hist_size, expected_alloc_size; // Variables for sizes

	ncpus = libbpf_num_possible_cpus();
	if (ncpus <= 0) {
		fprintf(stderr, "ERROR: Failed to determine number of possible CPUs: %s\n",
			ncpus == 0 ? "Not available" : strerror(-ncpus));
		return -1; // Return error
	}

	// Debug allocation size
	hist_size = sizeof(struct hist); // Should be ncpus * sizeof(unsigned long long) now
	expected_alloc_size = ncpus * hist_size;
	fprintf(stderr, "DEBUG: ncpus=%ld, sizeof(struct hist)=%zu, attempting to allocate %zu bytes for per-CPU data\n",
			ncpus, hist_size, expected_alloc_size);

	percpu_hists = calloc(ncpus, hist_size); // Allocate based on correct size
	if (!percpu_hists) {
		fprintf(stderr, "ERROR: Failed to allocate memory for per-CPU histograms (%ld CPUs)\n", ncpus);
		return -ENOMEM; // Return error
	}

	fprintf(stderr, "DEBUG: Checking map fd %d for keys...\n", fd);

	// --- Get the very first key ---
	errno = 0; // Reset errno before the call
	get_next_key_ret = bpf_map_get_next_key(fd, NULL, &next_key);

	if (get_next_key_ret < 0) {
		if (errno == ENOENT) {
			 fprintf(stderr, "DEBUG: Map is empty (first get_next_key -> ENOENT).\n");
		} else {
			 fprintf(stderr, "ERROR: Failed on first get_next_key: ret=%d, errno=%d (%s)\n",
					 get_next_key_ret, errno, strerror(errno));
		}
		goto cleanup_loop; // Use goto to ensure percpu_hists is freed
	}

	// --- Loop processing the first key and all subsequent keys ---
	fprintf(stderr, "DEBUG: Starting map processing loop.\n");
	do {
		fprintf(stderr, "DEBUG: Processing key: dev=%u flags=%d\n", next_key.dev, next_key.cmd_flags);

		// --- Lookup, Aggregate, Print ---
		err = bpf_map_lookup_elem(fd, &next_key, percpu_hists);
		if (err < 0) {
			fprintf(stderr, "ERROR: Failed lookup for key (dev=%u flags=%d): %s\n",
				next_key.dev, next_key.cmd_flags, strerror(-err));
		} else {
			// Aggregate into total_hist (unsigned long long)
			memset(&total_hist, 0, sizeof(total_hist));
			unsigned long long current_key_total_count = 0;
			for (i = 0; i < ncpus; i++) {
				for (j = 0; j < MAX_SLOTS; j++) {
					total_hist.slots[j] += percpu_hists[i].slots[j];
				}
			}
			// Sum total count for checks/debug
			for (j = 0; j < MAX_SLOTS; j++) {
				 current_key_total_count += total_hist.slots[j];
			}
			fprintf(stderr, "DEBUG: Aggregated total count for this key: %llu\n", current_key_total_count);

			// Print if count > 0
			if (current_key_total_count > 0) {
				 const struct partition *partition = NULL;
				 bool printed_header = false;

				 // Print headers
				 if (env.per_disk) {
					 partition = partitions__get_by_dev(partitions, next_key.dev);
					 printf("\ndisk = %s\t", partition ? partition->name : "Unknown");
					 printed_header = true;
				 }
				 if (env.per_flag) {
					 if (printed_header) printf("\t");
					 print_cmd_flags(next_key.cmd_flags);
					 printed_header = true;
				 }
				 if (printed_header)
					 printf("\n");

				 // *** FIX: Create temporary array for print_log2_hist ***
				 unsigned int temp_slots[MAX_SLOTS];
				 bool truncated = false;
				 for (j = 0; j < MAX_SLOTS; j++) {
					 if (total_hist.slots[j] > UINT_MAX) {
						 temp_slots[j] = UINT_MAX;
						 truncated = true;
					 } else {
						 temp_slots[j] = (unsigned int)total_hist.slots[j];
					 }
				 }
				 if (truncated && env.verbose) { // Only print truncation warning if verbose
					 fprintf(stderr, "WARN: Histogram counts truncated for printing for key (dev=%u flags=%d).\n",
							 next_key.dev, next_key.cmd_flags);
				 }

				 // Call print_log2_hist with the temporary unsigned int array
				 print_log2_hist(temp_slots, MAX_SLOTS, units);
				 // *** END FIX ***

			} else {
				 fprintf(stderr, "DEBUG: Skipping print for key (dev=%u flags=%d) as total count is zero.\n", next_key.dev, next_key.cmd_flags);
			}
		}
		// --- End Lookup, Aggregate, Print ---

		// Prepare for the next iteration
		lookup_key = next_key;
		errno = 0;

		// Try to get the *next* key
		get_next_key_ret = bpf_map_get_next_key(fd, &lookup_key, &next_key);

	} while (get_next_key_ret == 0); // Continue while get_next_key succeeds

	// Check why the loop finished
	if (errno != ENOENT) {
		 fprintf(stderr, "ERROR: Failed on subsequent get_next_key: errno=%d (%s)\n", errno, strerror(errno));
	} else {
		 fprintf(stderr, "DEBUG: End of map iteration (get_next_key -> ENOENT).\n");
	}
	// --- End Map Processing Loop ---

cleanup_loop:
	// Cleanup allocated buffer
	free(percpu_hists);

	// --- Map clearing logic (delete all keys) ---
	fprintf(stderr, "DEBUG: Starting map cleanup loop.\n");
	lookup_key = (struct hist_key){}; // Reset lookup key for delete loop
	while (bpf_map_get_next_key(fd, &lookup_key, &next_key) == 0) {
		err = bpf_map_delete_elem(fd, &next_key);
		if (err < 0 && errno != ENOENT) {
		   fprintf(stderr, "WARN: Failed to delete key (dev=%u flags=%d): %s (errno %d)\n",
			   next_key.dev, next_key.cmd_flags, strerror(-err), errno);
		}
		lookup_key = next_key;
	}
	if (errno != ENOENT) {
		fprintf(stderr, "WARN: Error iterating map for deletion: %s (errno %d)\n", strerror(errno), errno);
	} else {
		 fprintf(stderr, "DEBUG: Finished map cleanup loop.\n");
	}

	return 0; // Return success from print_log2_hists
}


// Main function
int main(int argc, char **argv)
{
	struct partitions *partitions = NULL;
	const struct partition *partition; // Used for -d flag validation
	static const struct argp argp = {
		.options = opts,
		.parser = parse_arg,
		.doc = argp_program_doc,
	};
	struct biolatency_bpf *obj = NULL; // Initialize object pointer
	struct tm *tm;
	char ts[32];
	time_t t;
	int err = 0; // Initialize error status
	int idx, cg_map_fd;
	int cgfd = -1; // Cgroup file descriptor

	// Parse command line arguments
	err = argp_parse(&argp, argc, argv, 0, NULL, NULL);
	if (err)
		return err;

	// Set libbpf print function
	libbpf_set_print(libbpf_print_fn);

	// Open BPF application
	obj = biolatency_bpf__open();
	if (!obj) {
		fprintf(stderr, "ERROR: Failed to open BPF object\n");
		return 1;
	}

	// Load partition info
	partitions = partitions__load();
	if (!partitions) {
		fprintf(stderr, "ERROR: Failed to load partitions info\n");
		err = -1;
		goto cleanup;
	}

	/* Initialize global data (filtering options) */
	if (env.disk) {
		partition = partitions__get_by_name(partitions, env.disk);
		if (!partition) {
			fprintf(stderr, "ERROR: Invalid partition name: %s\n", env.disk);
			err = -1;
			goto cleanup;
		}
		obj->rodata->filter_dev = true;
		obj->rodata->targ_dev = partition->dev;
	}
	obj->rodata->targ_per_disk = env.per_disk;
	obj->rodata->targ_per_flag = env.per_flag;
	obj->rodata->targ_ms = env.milliseconds;
	obj->rodata->targ_queued = env.queued;
	obj->rodata->filter_cg = env.cg;

	// Set autoload options (ensure correct program is loaded)
	bpf_program__set_autoload(obj->progs.block_rq_complete_btf, true);

	// Load BPF program into kernel
	err = biolatency_bpf__load(obj);
	if (err) {
		fprintf(stderr, "ERROR: Failed to load BPF object: %d (%s)\n", err, strerror(-err));
		goto cleanup;
	}

	/* Update cgroup map if -c flag used */
	if (env.cg) {
		idx = 0;
		cg_map_fd = bpf_map__fd(obj->maps.cgroup_map);
		if (cg_map_fd < 0) {
			fprintf(stderr, "ERROR: Failed to get cgroup_map fd: %s\n", strerror(errno));
			err = -1;
			goto cleanup;
		}
		cgfd = open(env.cgroupspath, O_RDONLY);
		if (cgfd < 0) {
			fprintf(stderr, "ERROR: Failed opening Cgroup path %s: %s\n", env.cgroupspath, strerror(errno));
			err = -errno;
			goto cleanup;
		}
		err = bpf_map_update_elem(cg_map_fd, &idx, &cgfd, BPF_ANY);
		if (err) {
			err = -err;
			fprintf(stderr, "ERROR: Failed adding target cgroup to map: %s\n", strerror(-err));
			goto cleanup;
		}
	}

	// Attach BPF programs
	err = biolatency_bpf__attach(obj);
	if (err) {
		fprintf(stderr, "ERROR: Failed to attach BPF programs: %d (%s)\n", err, strerror(-err));
		goto cleanup;
	}

	// Setup signal handling
	signal(SIGINT, sig_handler);
	signal(SIGTERM, sig_handler);

	printf("Tracing block device I/O... Hit Ctrl-C to end.\n");

	/* Main loop */
	while (!exiting && env.times-- > 0) {
		sleep(env.interval);
		printf("\n");

		if (env.timestamp) {
			time(&t);
			tm = localtime(&t);
			strftime(ts, sizeof(ts), "%H:%M:%S", tm);
			printf("%-8s\n", ts);
		}

		// Print histograms for this interval
		err = print_log2_hists(obj->maps.hists, partitions);
		if (err) {
			fprintf(stderr, "WARN: Error printing histograms, exiting.\n");
			break;
		}

		if (exiting) // Check again after printing
			break;
	}

cleanup:
	fprintf(stderr, "Exiting.\n");
	biolatency_bpf__destroy(obj);
	partitions__free(partitions);
	if (cgfd >= 0)
		close(cgfd);

	return err != 0; // Return non-zero on error
}

