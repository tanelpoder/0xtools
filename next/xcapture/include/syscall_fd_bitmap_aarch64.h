#ifndef __XCAPTURE_SYSCALL_FD_BITMAP_H
#define __XCAPTURE_SYSCALL_FD_BITMAP_H

/*
 * Define bitmap for syscalls that have fd as first argument
 * Each bit position corresponds to a syscall number
 * Using 8 * uint64_t for syscalls 0-511
 */
#define SYSCALL_FD_BITMAP_SIZE  (512 / 64)

/*
 * Initialize the bitmap with syscalls that have fd as first argument
 * Each entry in this array represents a 64-bit chunk of the bitmap
 *
 * The list is generated using latest 0x.tools syscallargs (1.0.4)
 * using the syscall_x86_64.tbl file from latest linux kernel source
 *
 * sudo syscallargs --gen-fd-bitmap --syscalltbl include/syscall_aarch64.tbl
 */

static const uint64_t syscall_fd_bitmap[SYSCALL_FD_BITMAP_SIZE] = {
    (1ULL << (  7 -   0)) /* fsetxattr((int) fd) */
  | (1ULL << ( 10 -   0)) /* fgetxattr((int) fd) */
  | (1ULL << ( 13 -   0)) /* flistxattr((int) fd) */
  | (1ULL << ( 16 -   0)) /* fremovexattr((int) fd) */
  | (1ULL << ( 21 -   0)) /* epoll_ctl((int) epfd) */
  | (1ULL << ( 22 -   0)) /* epoll_pwait((int) epfd) */
  | (1ULL << ( 24 -   0)) /* dup3((unsigned int) oldfd) */
  | (1ULL << ( 25 -   0)) /* fcntl((unsigned int) fd) */
  | (1ULL << ( 27 -   0)) /* inotify_add_watch((int) fd) */
  | (1ULL << ( 28 -   0)) /* inotify_rm_watch((int) fd) */
  | (1ULL << ( 29 -   0)) /* ioctl((unsigned int) fd) */
  | (1ULL << ( 32 -   0)) /* flock((unsigned int) fd) */
  | (1ULL << ( 33 -   0)) /* mknodat((int) dfd) */
  | (1ULL << ( 34 -   0)) /* mkdirat((int) dfd) */
  | (1ULL << ( 35 -   0)) /* unlinkat((int) dfd) */
  | (1ULL << ( 37 -   0)) /* linkat((int) olddfd) */
  | (1ULL << ( 38 -   0)) /* renameat((int) olddfd) */
  | (1ULL << ( 44 -   0)) /* fstatfs((unsigned int) fd) */
  | (1ULL << ( 46 -   0)) /* ftruncate((unsigned int) fd) */
  | (1ULL << ( 47 -   0)) /* fallocate((int) fd) */
  | (1ULL << ( 48 -   0)) /* faccessat((int) dfd) */
  | (1ULL << ( 50 -   0)) /* fchdir((unsigned int) fd) */
  | (1ULL << ( 52 -   0)) /* fchmod((unsigned int) fd) */
  | (1ULL << ( 53 -   0)) /* fchmodat((int) dfd) */
  | (1ULL << ( 54 -   0)) /* fchownat((int) dfd) */
  | (1ULL << ( 55 -   0)) /* fchown((unsigned int) fd) */
  | (1ULL << ( 56 -   0)) /* openat((int) dfd) */
  | (1ULL << ( 57 -   0)) /* close((unsigned int) fd) */
  | (1ULL << ( 61 -   0)) /* getdents64((unsigned int) fd) */
  | (1ULL << ( 62 -   0)) /* lseek((unsigned int) fd) */
  | (1ULL << ( 63 -   0)) /* read((unsigned int) fd) */
  , (1ULL << ( 64 -  64)) /* write((unsigned int) fd) */
  | (1ULL << ( 65 -  64)) /* readv((unsigned long) fd) */
  | (1ULL << ( 66 -  64)) /* writev((unsigned long) fd) */
  | (1ULL << ( 67 -  64)) /* pread64((unsigned int) fd) */
  | (1ULL << ( 68 -  64)) /* pwrite64((unsigned int) fd) */
  | (1ULL << ( 69 -  64)) /* preadv((unsigned long) fd) */
  | (1ULL << ( 70 -  64)) /* pwritev((unsigned long) fd) */
  | (1ULL << ( 71 -  64)) /* sendfile64((int) out_fd) */
  | (1ULL << ( 74 -  64)) /* signalfd4((int) ufd) */
  | (1ULL << ( 75 -  64)) /* vmsplice((int) fd) */
  | (1ULL << ( 76 -  64)) /* splice((int) fd_in) */
  | (1ULL << ( 77 -  64)) /* tee((int) fdin) */
  | (1ULL << ( 78 -  64)) /* readlinkat((int) dfd) */
  | (1ULL << ( 79 -  64)) /* newfstatat((int) dfd) */
  | (1ULL << ( 80 -  64)) /* newfstat((unsigned int) fd) */
  | (1ULL << ( 82 -  64)) /* fsync((unsigned int) fd) */
  | (1ULL << ( 83 -  64)) /* fdatasync((unsigned int) fd) */
  | (1ULL << ( 84 -  64)) /* sync_file_range((int) fd) */
  , (1ULL << (200 - 192)) /* bind((int) fd) */
  | (1ULL << (201 - 192)) /* listen((int) fd) */
  | (1ULL << (202 - 192)) /* accept((int) fd) */
  | (1ULL << (203 - 192)) /* connect((int) fd) */
  | (1ULL << (204 - 192)) /* getsockname((int) fd) */
  | (1ULL << (205 - 192)) /* getpeername((int) fd) */
  | (1ULL << (206 - 192)) /* sendto((int) fd) */
  | (1ULL << (207 - 192)) /* recvfrom((int) fd) */
  | (1ULL << (208 - 192)) /* setsockopt((int) fd) */
  | (1ULL << (209 - 192)) /* getsockopt((int) fd) */
  | (1ULL << (210 - 192)) /* shutdown((int) fd) */
  | (1ULL << (211 - 192)) /* sendmsg((int) fd) */
  | (1ULL << (212 - 192)) /* recvmsg((int) fd) */
  | (1ULL << (213 - 192)) /* readahead((int) fd) */
  | (1ULL << (223 - 192)) /* fadvise64_64((int) fd) */
  | (1ULL << (242 - 192)) /* accept4((int) fd) */
  , (1ULL << (263 - 256)) /* fanotify_mark((int) fanotify_fd) */
  | (1ULL << (264 - 256)) /* name_to_handle_at((int) dfd) */
  | (1ULL << (265 - 256)) /* open_by_handle_at((int) mountdirfd) */
  | (1ULL << (267 - 256)) /* syncfs((int) fd) */
  | (1ULL << (268 - 256)) /* setns((int) fd) */
  | (1ULL << (269 - 256)) /* sendmmsg((int) fd) */
  | (1ULL << (273 - 256)) /* finit_module((int) fd) */
  | (1ULL << (276 - 256)) /* renameat2((int) olddfd) */
  | (1ULL << (281 - 256)) /* execveat((int) fd) */
  | (1ULL << (285 - 256)) /* copy_file_range((int) fd_in) */
  | (1ULL << (286 - 256)) /* preadv2((unsigned long) fd) */
  | (1ULL << (287 - 256)) /* pwritev2((unsigned long) fd) */
  | (1ULL << (291 - 256)) /* statx((int) dfd) */
  | (1ULL << (294 - 256)) /* kexec_file_load((int) kernel_fd) */
  , (1ULL << (410 - 384)) /* timerfd_gettime((int) ufd) */
  | (1ULL << (411 - 384)) /* timerfd_settime((int) ufd) */
  | (1ULL << (412 - 384)) /* utimensat((int) dfd) */
  | (1ULL << (417 - 384)) /* recvmmsg((int) fd) */
  | (1ULL << (424 - 384)) /* pidfd_send_signal((int) pidfd) */
  | (1ULL << (426 - 384)) /* io_uring_enter((unsigned int) fd) */
  | (1ULL << (427 - 384)) /* io_uring_register((unsigned int) fd) */
  | (1ULL << (428 - 384)) /* open_tree((int) dfd) */
  | (1ULL << (429 - 384)) /* move_mount((int) from_dfd) */
  | (1ULL << (431 - 384)) /* fsconfig((int) fd) */
  | (1ULL << (432 - 384)) /* fsmount((int) fs_fd) */
  | (1ULL << (433 - 384)) /* fspick((int) dfd) */
  | (1ULL << (436 - 384)) /* close_range((unsigned int) fd) */
  | (1ULL << (437 - 384)) /* openat2((int) dfd) */
  | (1ULL << (438 - 384)) /* pidfd_getfd((int) pidfd) */
  | (1ULL << (439 - 384)) /* faccessat2((int) dfd) */
  | (1ULL << (440 - 384)) /* process_madvise((int) pidfd) */
  | (1ULL << (441 - 384)) /* epoll_pwait2((int) epfd) */
  | (1ULL << (442 - 384)) /* mount_setattr((int) dfd) */
  | (1ULL << (443 - 384)) /* quotactl_fd((unsigned int) fd) */
  | (1ULL << (445 - 384)) /* landlock_add_rule((const int) ruleset_fd) */
  | (1ULL << (446 - 384)) /* landlock_restrict_self((const int) ruleset_fd) */
  , (1ULL << (448 - 448)) /* process_mrelease((int) pidfd) */
  | (1ULL << (451 - 448)) /* cachestat((unsigned int) fd) */
  | (1ULL << (452 - 448)) /* fchmodat2((int) dfd) */
};


#define SYSCALL_HAS_FD_ARG1(syscall_nr) ({ \
    int __has_fd = 0; \
    if ((syscall_nr) < 512) { \
        __has_fd = !!(syscall_fd_bitmap[(syscall_nr) / 64] & (1ULL << ((syscall_nr) % 64))); \
    } \
    __has_fd; \
})

#endif /* __XCAPTURE_SYSCALL_FD_BITMAP_H */
