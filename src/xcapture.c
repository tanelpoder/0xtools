/* 
 *  0x.Tools xCapture - sample thread activity from Linux procfs [https://0x.tools]
 *  Copyright 2019-2021 Tanel Poder
 *
 *  This program is free software; you can redistribute it and/or modify
 *  it under the terms of the GNU General Public License as published by
 *  the Free Software Foundation; either version 2 of the License, or
 *  (at your option) any later version.
 *
 *  This program is distributed in the hope that it will be useful,
 *  but WITHOUT ANY WARRANTY; without even the implied warranty of
 *  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 *  GNU General Public License for more details.
 *
 *  You should have received a copy of the GNU General Public License along
 *  with this program; if not, write to the Free Software Foundation, Inc.,
 *  51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
 *
 *  SPDX-License-Identifier: GPL-2.0-or-later 
 *
 */

#define XCAP_VERSION "1.1.0"

#define _GNU_SOURCE

#include <stdio.h>
#include <stdlib.h>
#include <assert.h>
#include <string.h>
#include <errno.h>
#include <time.h>
#include <sys/time.h>
#include <dirent.h>
#include <fcntl.h>
#include <asm/unistd.h>
#include <linux/limits.h>  
#include <pwd.h>
#include <sys/stat.h>
#include <ctype.h>
#include <unistd.h>

#include <syscall_names.h>

#define WSP " \n" // whitespace
#define MAXFILEBUF 4096

int DEBUG = 0;

char filebuf[MAXFILEBUF]; // filebuf global temp area by design
char statbuf[MAXFILEBUF]; // filebuf global temp area by design (special for /proc/PID/stat value passing optimization)
char exclude_states[10] = "XZIS"; // do not show tasks in Sleeping state by default

char *output_dir = NULL;  // use stdout if output_dir is not set
int  header_printed = 0;
char output_format = 'S'; // S -> space-delimited fixed output format, C -> CSV
char outsep = ' ';
int  pad = 1;             // output field padding (for space-delimited fixed-width output)
  
const char *getusername(uid_t uid)
{
  struct passwd *pw = getpwuid(uid);
  if (pw)
  {
    return pw->pw_name;
  }

  return "-";
}


int readfile(int pid, int tid, const char *name, char *buf)
{
    int fd, bytes = 0;
    char path[256];

    tid ? sprintf(path, "/proc/%d/task/%d/%s", pid, tid, name) : sprintf(path, "/proc/%d/%s", pid, name);

    fd = open(path, O_RDONLY);
    if (fd == -1)  { 
        if (DEBUG) fprintf(stderr, "error opening file %s\n", path); 
        return -1;
    }

    bytes = read(fd, buf, MAXFILEBUF);
    close(fd);
   
    // handle errors, empty records and missing string terminators in input
    assert(bytes >= -1);
    switch (bytes) {
        case -1:
            if (DEBUG) fprintf(stderr, "read(%s) returned %d\n", path, bytes);
            buf[bytes] = '-';
            buf[bytes + 1] = 0;
            bytes = 2;
            break;
        case 0:
            buf[bytes] = '-';
            buf[bytes + 1] = 0;
            bytes = 2;
            break;
        case 1:
            buf[bytes] = 0;
            bytes = 2;
            break;
        default: // bytes >= 2
            if (bytes < MAXFILEBUF) 
                buf[bytes] = 0;
            else 
                buf[MAXFILEBUF-1] = 0;
    }
    return bytes;
}

int outputstack(char *str) {
    int i;

    // find the end and start of function name in the stack
    // example input lines (different number of fields): 
    //    [<ffffffff8528428c>] vfs_read+0x8c/0x130
    //    [<ffffffffc03b03f4>] xfs_file_fsync+0x224/0x240 [xfs]
    for (i=strlen(str)-1; i>=0; i--) {
        if (str[i] == '+') str[i] = '\0';
        if (str[i] == ' ' && str[i-1] == ']') { // ignore spaces _after_ the function name
            if (strcmp(str+i+1, "entry_SYSCALL_64_after_hwframe") &&
                strcmp(str+i+1, "do_syscall_64") &&
                strcmp(str+i+1, "0xffffffffffffffff\n")
            ) {
                fprintf(stdout, "->%s()", str+i+1); 
            }
        }
    }
    return 0;
}

// this function changes the input str (tokenizes it in place)
int outputfields(char *str, char *mask, char *sep) {
    int i;
    char *field, *pos;

    // special case for stack trace handling, we don't want to split the input string before calling outputstack()
    if (mask[0] == 't')  
        return outputstack(str);

    for (i=0; i<strlen(mask); i++) {
        if ((field = strsep(&str, sep)) != NULL) {
            switch (mask[i]) {
                case '.': // skip field
                    break;
                case 'e': // extract Executable file name from full path
                    pos = strrchr(field, '/');
                    if (pos)
                        fprintf(stdout, "%s%c", pos, outsep);
                    else 
                        fprintf(stdout, "%s%c", field, outsep);
                    break;
                case 'E': // same as above, but wider output
                    pos = strrchr(field, '/');
                    if (pos)
                        fprintf(stdout, pad ? "%-20s%c" : "%s%c", pos+1, outsep);
                    else 
                        fprintf(stdout, pad ? "%-20s%c" : "%s%c", field, outsep);
                    break;
                case 'o': // just output string as is
                    fprintf(stdout, "%s%c", field, outsep);
                    break;
                case 'O': // just output string as is, padded to 25 chars
                    fprintf(stdout, pad ? "%-25s%c" : "%s%c", field, outsep);
                    break;
                case 'x': // print in hex
                    fprintf(stdout, pad ? "0x%llx " : "0x%llx%c", atoll(field), outsep);
                    break;
                case 's': // convert syscall number to name, the input starts with either:
                          //  >= 0 (syscall), -1 (in kernel without syscall) or 'running' (likely userspace)
                    fprintf(stdout, "%s%c", field[0]=='r' ? "[running]" : field[0]=='-' ? "[no_syscall]" : sysent0[atoi(field)].name, outsep);
                    break;
                case 'S': // same as above, but wider output
                    fprintf(stdout, pad ? "%-25s%c" : "%s%c", field[0]=='r' ? "[running]" : field[0]=='-' ? "[no_syscall]" : sysent0[atoi(field)].name, outsep);
                    break;
                case 't': // we shouldn't get here thanks to the if statement above
                    break;
                default:
                    fprintf(stderr, "Error: Wrong char '%c' in mask %s\n", mask[i], mask); 
                    exit(1);
             }       
        }
        else break;
    }

    return i;
}

// currently a fixed string, will make this dynamic together with command line option support
int outputheader(char *add_columns) {

    fprintf(stdout, pad ? "%-23s %7s %7s %-15s %-2s %-25s %-25s %-25s" : "%s,%s,%s,%s,%s,%s,%s,%s", 
            output_dir ? "TS" : "DATE       TIME", "PID", "TID", "USERNAME", "ST", "COMMAND", "SYSCALL", "WCHAN");
    if (strcasestr(add_columns, "exe"))     fprintf(stdout, pad ? " %-20s" : ",%s", "EXE");
    if (strcasestr(add_columns, "cmdline")) fprintf(stdout, pad ? " %-30s" : ",%s", "CMDLINE");
    if (strcasestr(add_columns, "kstack"))  fprintf(stdout, pad ? " %s"    : ",%s", "KSTACK");
    fprintf(stdout, "\n");
    return 1;
}

// partial entry happens when /proc/PID/stat disappears before we manage to read it
void outputprocpartial(int pid, int tid, char *sampletime, uid_t proc_uid, char *add_columns, char *message) {

    header_printed = header_printed ? 1 : outputheader(add_columns);

    fprintf(stdout, pad ? "%-23s %7d %7d %-15s %-2c %-25s %-25s %-25s" : "%s,%d,%d,%s,%c,%s,%s,%s", 
                    sampletime, pid, tid, getusername(proc_uid), '-', message, "-", "-");

    if (strcasestr(add_columns, "exe"))     fprintf(stdout, pad ? " %-20s" : ",%s", "-");
    if (strcasestr(add_columns, "cmdline")) fprintf(stdout, pad ? " %-30s" : ",%s", "-");
    if (strcasestr(add_columns, "kstack"))  fprintf(stdout, pad ? " %s"    : ",%s", "-");
    fprintf(stdout, "\n");
}

int outputprocentry(int pid, int tid, char *sampletime, uid_t proc_uid, char *add_columns) {

    int b;
    char task_status;         // used for early bailout, filtering by task status
    char sympath[64];
    char *fieldend;

    // if printing out only the /proc/PID entry (not TID), then we have just read the relevant stat file into filebuf
    // in the calling function. this callflow-dependent optimization avoids an 'expensive' /proc/PID/stat read
    b = tid ? readfile(pid, tid, "stat", statbuf) : strlen(statbuf); 
    fieldend = strstr(statbuf, ") ");

    if (b > 0 && fieldend) { // the 1st field end "not null" check is due to /proc not having read consistency (rarely in-flux values are shown as \0\0\0\0\0\0\0...

        // this task_status check operation has to come before any outputfields() calls as they modify filebuf global var
        task_status = *(fieldend + 2);  // find where the 3rd field - after a ")" starts

        if (!strchr(exclude_states, task_status)) {  // task status is not in X,Z,I (S)

            // only print header (in stdout mode) when there are any samples to report
            header_printed = header_printed ? 1 : outputheader(add_columns);

            fprintf(stdout, pad ? "%-23s %7d %7d %-15s %-2c " : "%s,%d,%d,%s,%c,", sampletime, pid, tid, getusername(proc_uid), task_status); 
            outputfields(statbuf, ".O", WSP);     // .O......x for PF_ flags

            b = readfile(pid, tid, "syscall", filebuf); 
            if (b > 0) { outputfields(filebuf, "S", WSP); } else { fprintf(stdout, pad ? "%-25s " : "%s,", "-"); }

            b = readfile(pid, tid, "wchan", filebuf);
            if (b > 0) { outputfields(filebuf, "O", ". \n"); } else { fprintf(stdout, pad ? "%-25s " : "%s,", "-"); }

            if (strcasestr(add_columns, "exe")) {
               tid ? sprintf(sympath, "/proc/%d/task/%d/exe", pid, tid) : sprintf(sympath, "/proc/%d/exe", pid);
               b = readlink(sympath, filebuf, PATH_MAX);
               if (b > 0) { filebuf[b] = 0 ; outputfields(filebuf, "E", WSP); } else { fprintf(stdout, pad ? "%-20s " : "%s,", "-"); }
            }

            if (strcasestr(add_columns, "cmdline")) {
                b = readfile(pid, tid, "cmdline", filebuf); // contains spaces and \0s within data TODO escape (or just print argv[0])
                if (b > 0) { fprintf(stdout, pad ? "%-30s%c" : "%s%c", filebuf, outsep); } else { fprintf(stdout, pad ? "%-30s%c" : "%s%c", "-", outsep); }
            }

            if (strcasestr(add_columns, "kstack")) {
                b = readfile(pid, tid, "stack", filebuf); 
                if (b > 0) { outputfields(filebuf, "t", WSP); } else { fprintf(stdout, "-"); }
            }

            fprintf(stdout, "\n");
        }
    }
    else {
        outputprocpartial(pid, tid, sampletime, proc_uid, add_columns, "[task_entry_lost(read)]");
        return 1;
    }

    return 0;
}

void printhelp() {
    const char *helptext =
    "by Tanel Poder [https://0x.tools]\n\n"
    "Usage:\n"
    "  xcapture [options]\n\n"
    "  By default, sample all /proc tasks in states R, D every second and print to stdout\n\n"
    "  Options:\n"
    "    -a             capture tasks in additional states, even the ones Sleeping (S)\n"
    "    -A             capture tasks in All states, including Zombie (Z), Exiting (X), Idle (I)\n"
    "    -c <c1,c2>     print additional columns (for example: -c exe,cmdline,kstack)\n"
    "    -d <N>         seconds between samples (default: 1.0)\n"
    "    -E <string>    custom task state Exclusion filter (default: XZIS)\n"
    "    -h             display this help message\n"
    "    -o <dirname>   write wide output into hourly CSV files in this directory instead of stdout\n";

    fprintf(stderr, "\n0x.Tools xcapture v%s %s\n", XCAP_VERSION, helptext);
}

float timedifference_msec(struct timeval t0, struct timeval t1)
{
    return (t1.tv_sec - t0.tv_sec) * 1000.0f + (t1.tv_usec - t0.tv_usec) / 1000.0f;
}

int main(int argc, char **argv)
{
    char outbuf[BUFSIZ];
    char outpath[PATH_MAX];
    char dirpath[PATH_MAX]; // used for /proc stuff only, so no long paths
    DIR *pd, *td;
    struct dirent *pde, *tde; // process level and thread/task level directory entries in /proc

    char timebuf[80], usec_buf[6];
    struct timeval tmnow,loop_iteration_start_time,loop_iteration_end_time;
    float loop_iteration_msec;
    float sleep_for_msec;
    struct tm *tm;
    int prevhour = -1; // used for detecting switch to a new hour for creating a new output file
    int interval_msec = 1000;

    struct stat s;
    uid_t proc_uid;

    int nthreads = 0;
    int mypid = getpid();

    // argument handling
    char *add_columns = "";   // keep "" as a default value and not NULL
    int c;

    while ((c = getopt (argc, argv, "aAc:d:E:ho:")) != -1)
        switch (c) {
            case 'a':
                strncpy(exclude_states, "XZI", sizeof(exclude_states));
                break;
            case 'A':
                strncpy(exclude_states, "", sizeof(exclude_states));
                break;
            case 'c':
                add_columns = optarg;
                break;
            case 'd':
                interval_msec = atof(optarg) * 1000;
                if (interval_msec <= 0 || interval_msec > 3600000) {
                    fprintf(stderr, "Option -d has invalid value for capture interval - %s (%d)\n", optarg, interval_msec);
                    return 1;
                }
                break;
            case 'E':
                strncpy(exclude_states, optarg, sizeof(exclude_states));
                break;
            case 'h':
                printhelp();
                exit(1);
                break;
            case 'o':
                output_dir = optarg;
                output_format = 'C'; // CSV
                outsep = ',';
                pad = 0;
                if (!strlen(add_columns)) add_columns = "exe,kstack";
                break;
            case '?':
                if (strchr("cEd", optopt))
                    fprintf(stderr, "Option -%c requires an argument.\n", optopt);
                else if (isprint (optopt))
                    fprintf(stderr, "Unknown option `-%c'.\n", optopt);
                else
                    fprintf(stderr, "Unknown option character `\\x%x'.\n", optopt);
                return 1;
            default:
                abort();
        }
    // end argument handling

    setbuf(stdout, outbuf);

    fprintf(stderr, "\n0xTools xcapture v%s by Tanel Poder [https://0x.tools]\n\nSampling /proc...\n\n", XCAP_VERSION);

    while (1) {

        gettimeofday(&tmnow, NULL);
        gettimeofday(&loop_iteration_start_time, NULL);
        tm = localtime(&tmnow.tv_sec);

        if (output_dir) {
            if (prevhour != tm->tm_hour) {
                strftime(timebuf, 30, "%Y-%m-%d.%H", tm);
                snprintf(outpath, sizeof(outpath), "%s/%s.csv", output_dir, timebuf);
                if (!freopen(outpath, "a", stdout)) { fprintf(stderr, "Error opening output file\n"); exit(1); };
                setbuf(stdout, outbuf); // is this needed after freopen?
                prevhour = tm->tm_hour;
                header_printed = outputheader(add_columns);
            }
        }
        else {
            header_printed = 0; // dynamic stdout header printing decision is made later on
        }

        strftime(timebuf, 30, pad ? "%Y-%m-%d %H:%M:%S" : "%Y-%m-%d %H:%M:%S", tm); // currently same format for both outputs
        strcat(timebuf, ".");
        sprintf(usec_buf, "%03d", (int)tmnow.tv_usec/1000); // ms resolution should be ok for infrequent sampling
        strcat(timebuf, usec_buf);

        pd = opendir("/proc");
        if (!pd) { fprintf(stderr, "/proc listing error='%s', this shouldn't happen\n", strerror(errno)); exit(1); } 

        while ((pde = readdir(pd))) { // /proc/PID
            if (pde->d_name[0] >= '0' && pde->d_name[0] <= '9' && atoi(pde->d_name) != mypid) {
                sprintf(dirpath, "/proc/%s", pde->d_name);
                proc_uid = stat(dirpath, &s) ? -1 : s.st_uid;

 
                // if not multithreaded, read current /proc/PID/x files for efficiency. "nthreads" is 20th field in proc/PID/stat
                if (readfile(atoi(pde->d_name), 0, "stat", statbuf) > 0) { 
                    sscanf(statbuf, "%*s %*s %*s %*s %*s %*s %*s %*s %*s %*s %*s %*s %*s %*s %*s %*s %*s %*s %*s %u", &nthreads);

                    if (nthreads > 1) {
                        sprintf(dirpath, "/proc/%s/task", pde->d_name);

                        td = opendir(dirpath);
                        if (td) {

                            while ((tde = readdir(td))) { // proc/PID/task/TID
                                if (tde->d_name[0] >= '0' && tde->d_name[0] <= '9') {
                                    outputprocentry(atoi(pde->d_name), atoi(tde->d_name), timebuf, proc_uid, add_columns); 
                                }
                            }
                        }
                        else {
                            outputprocpartial(atoi(pde->d_name), -1, timebuf, proc_uid, add_columns, "[task_entry_lost(list)]");
                        }
                        closedir(td);
                    } 
                    else { // nthreads <= 1, therefore pid == tid
                        outputprocentry(atoi(pde->d_name), atoi(pde->d_name), timebuf, proc_uid, add_columns);
                    }

                } // readfile(statbuf)
                else {
                    outputprocpartial(atoi(pde->d_name), -1, timebuf, proc_uid, add_columns, "[proc_entry_lost(list)]");
                    if (DEBUG) fprintf(stderr, "proc entry disappeared /proc/%s/stat, len=%zu, errno=%s\n", pde->d_name, strlen(statbuf), strerror(errno));
                }
            }
        }
        closedir(pd);

        if (!output_dir && header_printed) fprintf(stdout, "\n");

        fflush(stdout);

        // sleep for the requested interval minus time spent taking the previous sample
        gettimeofday(&loop_iteration_end_time, NULL);
        loop_iteration_msec = timedifference_msec(loop_iteration_start_time, loop_iteration_end_time);
        sleep_for_msec = interval_msec - loop_iteration_msec;
        if (sleep_for_msec > 0) usleep(sleep_for_msec * 1000);
      
    }

    return 0;
}
