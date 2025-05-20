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
