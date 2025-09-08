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
 * sudo ./bin/syscallargs --gen-fd-bitmap --syscalltbl ./next/xcapture/include/syscall_x86_64.tbl
 */

static const uint64_t syscall_fd_bitmap[SYSCALL_FD_BITMAP_SIZE] = {
    (1ULL << (  0 -   0))  /* read((unsigned int) fd) */
  | (1ULL << (  1 -   0))  /* write((unsigned int) fd) */
  | (1ULL << (  3 -   0))  /* close((unsigned int) fd) */
  | (1ULL << (  5 -   0))  /* newfstat((unsigned int) fd) */
  | (1ULL << (  8 -   0))  /* lseek((unsigned int) fd) */
  | (1ULL << ( 16 -   0))  /* ioctl((unsigned int) fd) */
  | (1ULL << ( 17 -   0))  /* pread64((unsigned int) fd) */
  | (1ULL << ( 18 -   0))  /* pwrite64((unsigned int) fd) */
  | (1ULL << ( 19 -   0))  /* readv((unsigned long) fd) */
  | (1ULL << ( 20 -   0))  /* writev((unsigned long) fd) */
  | (1ULL << ( 33 -   0))  /* dup2((unsigned int) oldfd) */
  | (1ULL << ( 40 -   0))  /* sendfile64((int) out_fd) */
  | (1ULL << ( 42 -   0))  /* connect((int) fd) */
  | (1ULL << ( 43 -   0))  /* accept((int) fd) */
  | (1ULL << ( 44 -   0))  /* sendto((int) fd) */
  | (1ULL << ( 45 -   0))  /* recvfrom((int) fd) */
  | (1ULL << ( 46 -   0))  /* sendmsg((int) fd) */
  | (1ULL << ( 47 -   0))  /* recvmsg((int) fd) */
  | (1ULL << ( 48 -   0))  /* shutdown((int) fd) */
  | (1ULL << ( 49 -   0))  /* bind((int) fd) */
  | (1ULL << ( 50 -   0))  /* listen((int) fd) */
  | (1ULL << ( 51 -   0))  /* getsockname((int) fd) */
  | (1ULL << ( 52 -   0))  /* getpeername((int) fd) */
  | (1ULL << ( 54 -   0))  /* setsockopt((int) fd) */
  | (1ULL << ( 55 -   0))  /* getsockopt((int) fd) */
  , (1ULL << ( 72 -  64))  /* fcntl((unsigned int) fd) */
  | (1ULL << ( 73 -  64))  /* flock((unsigned int) fd) */
  | (1ULL << ( 74 -  64))  /* fsync((unsigned int) fd) */
  | (1ULL << ( 75 -  64))  /* fdatasync((unsigned int) fd) */
  | (1ULL << ( 77 -  64))  /* ftruncate((unsigned int) fd) */
  | (1ULL << ( 78 -  64))  /* getdents((unsigned int) fd) */
  | (1ULL << ( 81 -  64))  /* fchdir((unsigned int) fd) */
  | (1ULL << ( 91 -  64))  /* fchmod((unsigned int) fd) */
  | (1ULL << ( 93 -  64))  /* fchown((unsigned int) fd) */
  , (1ULL << (138 - 128))  /* fstatfs((unsigned int) fd) */
  | (1ULL << (187 - 128))  /* readahead((int) fd) */
  | (1ULL << (190 - 128))  /* fsetxattr((int) fd) */
  , (1ULL << (193 - 192))  /* fgetxattr((int) fd) */
  | (1ULL << (196 - 192))  /* flistxattr((int) fd) */
  | (1ULL << (199 - 192))  /* fremovexattr((int) fd) */
  | (1ULL << (217 - 192))  /* getdents64((unsigned int) fd) */
  | (1ULL << (221 - 192))  /* fadvise64((int) fd) */
  | (1ULL << (232 - 192))  /* epoll_wait((int) epfd) */
  | (1ULL << (233 - 192))  /* epoll_ctl((int) epfd) */
  | (1ULL << (254 - 192))  /* inotify_add_watch((int) fd) */
  | (1ULL << (255 - 192))  /* inotify_rm_watch((int) fd) */
  , (1ULL << (257 - 256))  /* openat((int) dfd) */
  | (1ULL << (258 - 256))  /* mkdirat((int) dfd) */
  | (1ULL << (259 - 256))  /* mknodat((int) dfd) */
  | (1ULL << (260 - 256))  /* fchownat((int) dfd) */
  | (1ULL << (261 - 256))  /* futimesat((int) dfd) */
  | (1ULL << (262 - 256))  /* newfstatat((int) dfd) */
  | (1ULL << (263 - 256))  /* unlinkat((int) dfd) */
  | (1ULL << (264 - 256))  /* renameat((int) olddfd) */
  | (1ULL << (265 - 256))  /* linkat((int) olddfd) */
  | (1ULL << (267 - 256))  /* readlinkat((int) dfd) */
  | (1ULL << (268 - 256))  /* fchmodat((int) dfd) */
  | (1ULL << (269 - 256))  /* faccessat((int) dfd) */
  | (1ULL << (275 - 256))  /* splice((int) fd_in) */
  | (1ULL << (276 - 256))  /* tee((int) fdin) */
  | (1ULL << (277 - 256))  /* sync_file_range((int) fd) */
  | (1ULL << (278 - 256))  /* vmsplice((int) fd) */
  | (1ULL << (280 - 256))  /* utimensat((int) dfd) */
  | (1ULL << (281 - 256))  /* epoll_pwait((int) epfd) */
  | (1ULL << (282 - 256))  /* signalfd((int) ufd) */
  | (1ULL << (285 - 256))  /* fallocate((int) fd) */
  | (1ULL << (286 - 256))  /* timerfd_settime((int) ufd) */
  | (1ULL << (287 - 256))  /* timerfd_gettime((int) ufd) */
  | (1ULL << (288 - 256))  /* accept4((int) fd) */
  | (1ULL << (289 - 256))  /* signalfd4((int) ufd) */
  | (1ULL << (292 - 256))  /* dup3((unsigned int) oldfd) */
  | (1ULL << (295 - 256))  /* preadv((unsigned long) fd) */
  | (1ULL << (296 - 256))  /* pwritev((unsigned long) fd) */
  | (1ULL << (299 - 256))  /* recvmmsg((int) fd) */
  | (1ULL << (301 - 256))  /* fanotify_mark((int) fanotify_fd) */
  | (1ULL << (303 - 256))  /* name_to_handle_at((int) dfd) */
  | (1ULL << (304 - 256))  /* open_by_handle_at((int) mountdirfd) */
  | (1ULL << (306 - 256))  /* syncfs((int) fd) */
  | (1ULL << (307 - 256))  /* sendmmsg((int) fd) */
  | (1ULL << (308 - 256))  /* setns((int) fd) */
  | (1ULL << (313 - 256))  /* finit_module((int) fd) */
  | (1ULL << (316 - 256))  /* renameat2((int) olddfd) */
  , (1ULL << (320 - 320))  /* kexec_file_load((int) kernel_fd) */
  | (1ULL << (322 - 320))  /* execveat((int) fd) */
  | (1ULL << (326 - 320))  /* copy_file_range((int) fd_in) */
  | (1ULL << (327 - 320))  /* preadv2((unsigned long) fd) */
  | (1ULL << (328 - 320))  /* pwritev2((unsigned long) fd) */
  | (1ULL << (332 - 320))  /* statx((int) dfd) */
  , (1ULL << (424 - 384))  /* pidfd_send_signal((int) pidfd) */
  | (1ULL << (426 - 384))  /* io_uring_enter((unsigned int) fd) */
  | (1ULL << (427 - 384))  /* io_uring_register((unsigned int) fd) */
  | (1ULL << (428 - 384))  /* open_tree((int) dfd) */
  | (1ULL << (429 - 384))  /* move_mount((int) from_dfd) */
  | (1ULL << (431 - 384))  /* fsconfig((int) fd) */
  | (1ULL << (432 - 384))  /* fsmount((int) fs_fd) */
  | (1ULL << (433 - 384))  /* fspick((int) dfd) */
  | (1ULL << (436 - 384))  /* close_range((unsigned int) fd) */
  | (1ULL << (437 - 384))  /* openat2((int) dfd) */
  | (1ULL << (438 - 384))  /* pidfd_getfd((int) pidfd) */
  | (1ULL << (439 - 384))  /* faccessat2((int) dfd) */
  | (1ULL << (440 - 384))  /* process_madvise((int) pidfd) */
  | (1ULL << (441 - 384))  /* epoll_pwait2((int) epfd) */
  | (1ULL << (442 - 384))  /* mount_setattr((int) dfd) */
  | (1ULL << (443 - 384))  /* quotactl_fd((unsigned int) fd) */
  | (1ULL << (445 - 384))  /* landlock_add_rule((const int) ruleset_fd) */
  | (1ULL << (446 - 384))  /* landlock_restrict_self((const int) ruleset_fd) */
  , (1ULL << (448 - 448))  /* process_mrelease((int) pidfd) */
  | (1ULL << (451 - 448))  /* cachestat((unsigned int) fd) */
  | (1ULL << (452 - 448))  /* fchmodat2((int) dfd) */
};


#define SYSCALL_HAS_FD_ARG1(syscall_nr) ({ \
    int __has_fd = 0; \
    if ((syscall_nr) < 512) { \
        __has_fd = !!(syscall_fd_bitmap[(unsigned int)(syscall_nr) / 64] & (1ULL << ((unsigned int)(syscall_nr) % 64))); \
    } \
    __has_fd; \
})

#endif /* __XCAPTURE_SYSCALL_FD_BITMAP_H */
