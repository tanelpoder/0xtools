#ifndef __TRACKING_HANDLER_H
#define __TRACKING_HANDLER_H

#include <bpf/libbpf.h>
#include "xcapture.h"
#include "xcapture_user.h"

int handle_tracking_event(void *ctx, void *data, size_t data_sz);

#endif /* __TRACKING_HANDLER_H */
