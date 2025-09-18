#!/bin/bash

# flam.sh: a simple wrapper that converts xintr output to be
# flamegraph visualizer-compatible and feeds it to flamelens

nostrip=0

if [[ "$1" == "-n" || "$1" == "--no-strip" ]]; then
    nostrip=1
    shift
fi

input="$1"

if [[ $nostrip -eq 1 ]]; then
    # Keep offsets
    cat $input \
      | cut -d'|' -f3 \
      | sort | uniq -c \
      | awk '{ print $2 " " $1 }' \
      | flamelens
else
    # Strip offsets (anything after +0x...)
    cat $input \
      | cut -d'|' -f3 \
      | sed -E 's/\+0x[0-9a-fA-F]+//g' \
      | sort | uniq -c \
      | awk '{ print $2 " " $1 }' \
      | flamelens
fi
