#!/bin/bash

[ $# -ne 3 ] && echo Usage $0 numjobs /dev/DEVICENAME BLOCKSIZE && exit 1

fio --readonly --name=onessd \
    --filename=$2 \
    --filesize=100% --bs=$3 --direct=1 --overwrite=0 \
    --rw=randread --random_generator=lfsr \
    --numjobs=$1 --time_based=1 --runtime=3600 \
    --ioengine=io_uring --registerfiles --fixedbufs \
    --iodepth=256 --iomem=shmhuge --thread \
    --iodepth_batch_submit=16 --iodepth_batch_complete_min=16 --iodepth_batch_complete_max=16 \
    --gtod_reduce=1 --group_reporting --minimal


