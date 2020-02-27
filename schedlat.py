#!/usr/bin/env python

# Copyright 2020 Tanel Poder.
# Licensed under the Apache License, Version 2.0 (the "License")
#
# Name:    schedlat.py (v0.1)
# Purpose: display % of time a process spent in CPU runqueue 
#          (scheduling latency)
# Usage:   ./schedlat.py PID
#
#          %CPU shows % of time the task spent on CPU
#          %LAT shows % of time the task spent trying to get onto CPU (in runqueue)
#          %SLP shows the delta (not on CPU, not in runqueue, thus sleeping/waiting)
#
# Other:   More info at https://tanelpoder.com

from __future__ import print_function
from datetime import datetime
import time, sys

if len(sys.argv) != 2:
  print("usage: " + sys.argv[0] + " PID")
  exit(1)

pid=sys.argv[1]

with open('/proc/' + pid + '/comm', 'r') as f:
  print("SchedLat by Tanel Poder (https://tanelpoder.com)\n\nPID=" + pid + " COMM=" + f.read())

print("%-20s %6s %6s %6s" % ("TIMESTAMP", "%CPU", "%LAT", "%SLP"))

while True:
  with open('/proc/' + pid + '/schedstat' , 'r') as f:
    #t1=datetime.now()
    t1=time.time() 
    (cpu_ns1, lat_ns1, dontcare) = f.read().split()
    time.sleep(1)
    f.seek(0)
    #t2=datetime.now()
    t2=time.time()
    (cpu_ns2, lat_ns2, dontcare) = f.read().split()
  
  cpu=(int(cpu_ns2)-int(cpu_ns1))/(t2-t1)/10000000
  lat=(int(lat_ns2)-int(lat_ns1))/(t2-t1)/10000000
   
  print("%-20s %6.1f %6.1f %6.1f" % (datetime.fromtimestamp(t2).strftime("%Y-%m-%d %H:%M:%S"), cpu, lat, 100-(cpu+lat)))

