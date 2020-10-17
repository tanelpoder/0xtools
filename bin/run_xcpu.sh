#!/bin/bash

#  0x.Tools by Tanel Poder [https://0x.tools]
#  Copyright 2019-2020 Tanel Poder
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#  
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#  
#  You should have received a copy of the GNU General Public License
#  along with this program.  If not, see <https://www.gnu.org/licenses/>.

FREQUENCY=1 # 1 Hz sampling
SUDO=sudo # change to empty string if running without sudo
NICE=-5
SLEEP=60
PERF=/usr/bin/perf

if [ $# -ne 1 ]; then
  echo "Usage: $0 output_dir"
  exit 1
fi

logger "$0 Starting up outdir=$1 nice=$NICE"

while true ; do
    $SUDO nice -n $NICE $PERF record -g -F $FREQUENCY -a \
                --switch-output=1m \
                --timestamp-filename \
                --timestamp \
                -o $1/xcpu
    
    # we only get here should perf be terminated, try to restart
    logger "$0 terminated with $?, attempting to restart in $SLEEP seconds"
    sleep $SLEEP
done

