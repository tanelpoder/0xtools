#!/usr/bin/env bash
set -euo pipefail

# Simple smoke tests for xtop --testmode combinations

: "${XCAPTURE_DATADIR:=~/dev/0xtools-next/xcapture/out}"
FROM_TS=${FROM_TS:-"2025-09-04T00:30:00"}
TO_TS=${TO_TS:-"2025-09-04T00:45:00"}

echo "Using XCAPTURE_DATADIR=$XCAPTURE_DATADIR"
echo "Time range: $FROM_TS .. $TO_TS"
echo

run() {
  echo "==== $*"
  eval "$@"
  echo
}

# 1) Table, histogram + peek first row
run "./xtop --testmode -d '$XCAPTURE_DATADIR' \
  --from '$FROM_TS' --to '$TO_TS' --limit 10 \
  -g 'state,username' -l 'sc.p95_us,sclat_histogram' \
  --peek"

# 2) Table, no-reorder, peek row 2
run "./xtop --testmode -d '$XCAPTURE_DATADIR' \
  --from '$FROM_TS' --to '$TO_TS' --limit 10 \
  -g 'state,syscall' -l 'sclat_histogram' \
  --no-reorder --peek 2"

# 3) CSV with peek
run "./xtop --testmode --format csv -d '$XCAPTURE_DATADIR' \
  --from '$FROM_TS' --to '$TO_TS' --limit 5 \
  -g 'state,username' -l 'sclat_histogram' \
  --peek"

# 4) JSON with peek row 1
run "./xtop --testmode --format json -d '$XCAPTURE_DATADIR' \
  --from '$FROM_TS' --to '$TO_TS' --limit 5 \
  -g 'state,username' -l 'sclat_histogram' \
  --peek 1"

# 5) I/O histogram (if present in data), no peek
run "./xtop --testmode -d '$XCAPTURE_DATADIR' \
  --from '$FROM_TS' --to '$TO_TS' --limit 10 \
  -g 'devname,username' -l 'io.p95_us,iolat_histogram'"

echo "All testmode smoke runs executed."

# 6) extra_info peek (if extra_info present)
run "./xtop --testmode -d '$XCAPTURE_DATADIR' \
  --from '$FROM_TS' --to '$TO_TS' --limit 5 \
  -g 'state,username,extra_info' \
  --peek"
