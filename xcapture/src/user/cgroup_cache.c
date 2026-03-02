// SPDX-License-Identifier: (LGPL-2.1 OR BSD-2-Clause)
// Copyright 2024-2038 Tanel Poder [0x.tools]

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include "cgroup_cache.h"
#include "xcapture_user.h"

// Global cache instance
static struct {
    cgroup_entry_t *buckets[CGROUP_CACHE_SIZE];
    int total_entries;
    cgroup_cache_stats_t stats;
} g_cgroup_cache = {0};

// Simple hash function for cgroup IDs
static inline unsigned int hash_cgroup_id(__u64 cgroup_id) {
    // Multiplicative hash with golden ratio constant
    return (cgroup_id * 2654435761ULL) & (CGROUP_CACHE_SIZE - 1);
}

// Initialize the cache
void cgroup_cache_init(void) {
    memset(&g_cgroup_cache, 0, sizeof(g_cgroup_cache));
}

// Lookup a cgroup by ID
const char* cgroup_cache_lookup(__u64 cgroup_id) {
    unsigned int hash = hash_cgroup_id(cgroup_id);
    cgroup_entry_t *entry = g_cgroup_cache.buckets[hash];
    
    g_cgroup_cache.stats.lookups++;
    
    while (entry) {
        if (entry->cgroup_id == cgroup_id) {
            g_cgroup_cache.stats.hits++;
            return entry->path;
        }
        entry = entry->next;
    }
    
    g_cgroup_cache.stats.misses++;
    return NULL;
}

// Insert a new cgroup
int cgroup_cache_insert(__u64 cgroup_id, const char *path) {
    unsigned int hash = hash_cgroup_id(cgroup_id);
    cgroup_entry_t *entry = g_cgroup_cache.buckets[hash];
    
    // Check if already exists
    while (entry) {
        if (entry->cgroup_id == cgroup_id) {
            return 0;  // Already cached
        }
        entry = entry->next;
    }
    
    // Allocate new entry
    entry = malloc(sizeof(cgroup_entry_t));
    if (!entry) {
        return -1;  // Memory allocation failed
    }
    
    entry->cgroup_id = cgroup_id;
    strncpy(entry->path, path, CGROUP_PATH_MAX - 1);
    entry->path[CGROUP_PATH_MAX - 1] = '\0';
    
    // Insert at head of chain (collision handling)
    if (g_cgroup_cache.buckets[hash] != NULL) {
        g_cgroup_cache.stats.collisions++;
    }
    entry->next = g_cgroup_cache.buckets[hash];
    g_cgroup_cache.buckets[hash] = entry;
    
    g_cgroup_cache.total_entries++;
    return 1;  // New entry added
}

// Check if cgroup is cached
bool cgroup_cache_contains(__u64 cgroup_id) {
    return cgroup_cache_lookup(cgroup_id) != NULL;
}

// Get cache statistics
void cgroup_cache_get_stats(cgroup_cache_stats_t *stats) {
    if (stats) {
        *stats = g_cgroup_cache.stats;
    }
}

// Free all allocated memory
void cgroup_cache_destroy(void) {
    for (int i = 0; i < CGROUP_CACHE_SIZE; i++) {
        cgroup_entry_t *entry = g_cgroup_cache.buckets[i];
        while (entry) {
            cgroup_entry_t *next = entry->next;
            free(entry);
            entry = next;
        }
    }
    memset(&g_cgroup_cache, 0, sizeof(g_cgroup_cache));
}

// Resolve cgroup path from /proc/[pid]/cgroup
int resolve_cgroup_from_proc(pid_t pid, char *path_out, size_t path_size) {
    char proc_path[64];
    FILE *f;
    char line[512];
    
    snprintf(proc_path, sizeof(proc_path), "/proc/%d/cgroup", pid);
    
    f = fopen(proc_path, "r");
    if (!f) {
        return -1;  // Cannot open file (process may have exited)
    }
    
    while (fgets(line, sizeof(line), f)) {
        // Look for cgroup v2 entry (starts with "0::")
        if (strncmp(line, "0::", 3) == 0) {
            char *cgroup_path = line + 3;
            
            // Remove trailing newline
            char *newline = strchr(cgroup_path, '\n');
            if (newline) {
                *newline = '\0';
            }
            
            // Copy to output buffer
            strncpy(path_out, cgroup_path, path_size - 1);
            path_out[path_size - 1] = '\0';
            
            fclose(f);
            return 0;
        }
    }
    
    fclose(f);
    return -1;  // No cgroup v2 entry found
}

// Main resolution function that tries multiple methods
int resolve_cgroup_path(__u64 cgroup_id, pid_t pid, char *path_out, size_t path_size) {
    // First, check the cache
    const char *cached_path = cgroup_cache_lookup(cgroup_id);
    if (cached_path) {
        strncpy(path_out, cached_path, path_size - 1);
        path_out[path_size - 1] = '\0';
        return 0;
    }
    
    // Try to resolve from /proc/[pid]/cgroup
    if (pid > 0) {
        if (resolve_cgroup_from_proc(pid, path_out, path_size) == 0) {
            // Cache the result
            cgroup_cache_insert(cgroup_id, path_out);
            return 0;
        }
    }
    
    // Future: Could add other resolution methods here
    // - Walk /sys/fs/cgroup/ to find matching inode
    // - Use cgroup ID to path mapping if available
    
    return -1;  // Could not resolve
}

// Open cgroup output file
FILE* open_cgroup_file(const char *output_dir) {
    char filename[512];
    time_t now = time(NULL);
    struct tm *tm = localtime(&now);
    
    snprintf(filename, sizeof(filename), "%s/xcapture_cgroups_%04d-%02d-%02d.%02d.csv",
             output_dir,
             tm->tm_year + 1900, tm->tm_mon + 1, tm->tm_mday,
             tm->tm_hour);
    
    // Check if file exists and has size > 0
    FILE *f = fopen(filename, "r");
    bool need_header = true;
    if (f) {
        fseek(f, 0, SEEK_END);
        need_header = (ftell(f) == 0);
        fclose(f);
    }
    
    // Open for append
    f = fopen(filename, "a");
    if (f && need_header) {
        fprintf(f, "CGROUP_ID,CGROUP_PATH\n");
    }
    
    return f;
}

// Write cgroup entry to file
void write_cgroup_entry(FILE *f, __u64 cgroup_id, const char *path) {
    if (f) {
        fprintf(f, "%llu,%s\n", cgroup_id, path);
        fflush(f);
    }
}