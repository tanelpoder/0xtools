// SPDX-License-Identifier: (LGPL-2.1 OR BSD-2-Clause)
// Copyright 2024-2038 Tanel Poder [0x.tools]

#ifndef CGROUP_CACHE_H
#define CGROUP_CACHE_H

#include <linux/types.h>
#include <stdbool.h>
#include <stdio.h>

#define CGROUP_CACHE_SIZE 4096  // Must be power of 2 for fast modulo
#define CGROUP_PATH_MAX 256

// Individual cache entry
typedef struct cgroup_entry {
    __u64 cgroup_id;
    char path[CGROUP_PATH_MAX];
    struct cgroup_entry *next;  // Chain for collision handling
} cgroup_entry_t;

// Cache statistics
typedef struct {
    int lookups;
    int hits;
    int misses;
    int collisions;
} cgroup_cache_stats_t;

// Initialize the global cache
void cgroup_cache_init(void);

// Lookup a cgroup by ID (returns NULL if not found)
const char* cgroup_cache_lookup(__u64 cgroup_id);

// Insert a new cgroup (returns 0 if already exists, 1 if new, -1 on error)
int cgroup_cache_insert(__u64 cgroup_id, const char *path);

// Check if cgroup is cached
bool cgroup_cache_contains(__u64 cgroup_id);

// Get cache statistics
void cgroup_cache_get_stats(cgroup_cache_stats_t *stats);

// Free all allocated memory
void cgroup_cache_destroy(void);

// Path resolution functions
int resolve_cgroup_path(__u64 cgroup_id, pid_t pid, char *path_out, size_t path_size);
int resolve_cgroup_from_proc(pid_t pid, char *path_out, size_t path_size);

// File output functions
FILE* open_cgroup_file(const char *output_dir);
void write_cgroup_entry(FILE *f, __u64 cgroup_id, const char *path);

#endif /* CGROUP_CACHE_H */