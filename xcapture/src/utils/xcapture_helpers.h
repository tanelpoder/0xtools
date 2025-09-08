// Handle kernel version differences in task state field
struct task_struct___post514 {
    unsigned int __state;
} __attribute__((preserve_access_index));

struct task_struct___pre514 {
    long state;
} __attribute__((preserve_access_index));

struct fred_info___check {
    long unsigned int edata;
} __attribute__((preserve_access_index));

// Simple BPF-compatible hash function for stack traces
// Uses FNV-1a hash algorithm which is simple and effective
static __u64 __always_inline get_stack_hash(__u64 *stack, int stack_len)
{
    if (!stack || stack_len <= 0)
        return 0;
    
    // FNV-1a 64-bit offset basis and prime
    __u64 hash = 0xcbf29ce484222325ULL;  // FNV offset basis
    const __u64 fnv_prime = 0x100000001b3ULL;
    
    // Hash each address in the stack - unrolled for BPF verifier
    if (stack_len > 0 && 0 < MAX_STACK_LEN) {
        hash ^= stack[0];
        hash *= fnv_prime;
    }
    if (stack_len > 1 && 1 < MAX_STACK_LEN) {
        hash ^= stack[1];
        hash *= fnv_prime;
    }
    if (stack_len > 2 && 2 < MAX_STACK_LEN) {
        hash ^= stack[2];
        hash *= fnv_prime;
    }
    if (stack_len > 3 && 3 < MAX_STACK_LEN) {
        hash ^= stack[3];
        hash *= fnv_prime;
    }
    if (stack_len > 4 && 4 < MAX_STACK_LEN) {
        hash ^= stack[4];
        hash *= fnv_prime;
    }
    if (stack_len > 5 && 5 < MAX_STACK_LEN) {
        hash ^= stack[5];
        hash *= fnv_prime;
    }
    if (stack_len > 6 && 6 < MAX_STACK_LEN) {
        hash ^= stack[6];
        hash *= fnv_prime;
    }
    if (stack_len > 7 && 7 < MAX_STACK_LEN) {
        hash ^= stack[7];
        hash *= fnv_prime;
    }
    if (stack_len > 8 && 8 < MAX_STACK_LEN) {
        hash ^= stack[8];
        hash *= fnv_prime;
    }
    if (stack_len > 9 && 9 < MAX_STACK_LEN) {
        hash ^= stack[9];
        hash *= fnv_prime;
    }
    if (stack_len > 10 && 10 < MAX_STACK_LEN) {
        hash ^= stack[10];
        hash *= fnv_prime;
    }
    if (stack_len > 11 && 11 < MAX_STACK_LEN) {
        hash ^= stack[11];
        hash *= fnv_prime;
    }
    if (stack_len > 12 && 12 < MAX_STACK_LEN) {
        hash ^= stack[12];
        hash *= fnv_prime;
    }
    if (stack_len > 13 && 13 < MAX_STACK_LEN) {
        hash ^= stack[13];
        hash *= fnv_prime;
    }
    if (stack_len > 14 && 14 < MAX_STACK_LEN) {
        hash ^= stack[14];
        hash *= fnv_prime;
    }
    if (stack_len > 15 && 15 < MAX_STACK_LEN) {
        hash ^= stack[15];
        hash *= fnv_prime;
    }
    if (stack_len > 16 && 16 < MAX_STACK_LEN) {
        hash ^= stack[16];
        hash *= fnv_prime;
    }
    if (stack_len > 17 && 17 < MAX_STACK_LEN) {
        hash ^= stack[17];
        hash *= fnv_prime;
    }
    if (stack_len > 18 && 18 < MAX_STACK_LEN) {
        hash ^= stack[18];
        hash *= fnv_prime;
    }
    if (stack_len > 19 && 19 < MAX_STACK_LEN) {
        hash ^= stack[19];
        hash *= fnv_prime;
    }
    
    return hash;
}

// Helper function to get disk information from request
static struct gendisk __always_inline *get_disk(struct request *rq)
{
    struct gendisk *disk = NULL;
    struct request_queue *q = BPF_CORE_READ(rq, q);

    if (q) {
        disk = BPF_CORE_READ(q, disk);
    }

    return disk; // will be NULL if (!q)
}
