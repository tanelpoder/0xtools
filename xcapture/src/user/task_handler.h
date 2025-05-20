#ifndef __TASK_HANDLER_H
#define __TASK_HANDLER_H

#include <bpf/libbpf.h>
#include "xcapture.h"
#include "xcapture_user.h"

int handle_task_event(void *ctx, void *data, size_t data_sz);

#endif /* __TASK_HANDLER_H */
