
Query Examples
==============

As per [Always-on Profiling for Production Systems](https://0x.tools/), the primary tools for querying the CSV files are:

- grep
- awk
- cut
- sort
- uniq

While grep is primarily used for filtering, this can be done with awk as well.

Both awk and cut can be used to project columns.

The uniq utility is useful for group by, but also for sorting when counts are involved.


This command gets the count of occurrences of oraagent.bin, showing which is the most active.

```text
# awk -F, '/oraagent.bin/ { print $2 }' /var/log/xcapture/2020-12-03.15.csv | sort -n | uniq -c | sort -n
1 26652
80 3131
101 1543
123 13048
```

This same thing may also be done in awk:

```text
# awk -F, '/oraagent.bin/ { freq[$2]++ }END{for (key in freq){print freq[key] ": " key}}' /var/log/xcapture/2020-12-03.15.csv | sort -n
1: 26652
80: 3131
101: 1543
122: 13048
```

Here we can see the uniq list of call stacks for PID, along with the count for that stack:

```text
# awk -F, '/oraagent.bin/ && $2==13048 && $7=="[running]"  && $11 != "" { print $11 }' /var/log/xcapture/2020-12-03.15.csv | sort | uniq -c | sort -n
  1 ->retint_user()->prepare_exit_to_usermode()->exit_to_usermode_loop()
  3 ->SyS_nanosleep()->hrtimer_nanosleep()
  3 ->SyS_poll()->do_sys_poll()->poll_schedule_timeout()
  6 ->page_fault()->do_page_fault()->__do_page_fault()->call_rwsem_down_read_failed()
  8 ->SyS_read()->vfs_read()->__vfs_read()->pipe_read()->pipe_wait()
 90 ->SyS_futex()->do_futex()->futex_wait()->futex_wait_queue_me()
```

Breakdown for this command line

`awk -F, '/oraagent.bin/ && $2==13048 && $7=="[running]"  && $11 != "" { print $11 }' /var/log/xcapture/2020-12-03.15.csv | sort | uniq -c | sort -n`

get specify the field separator as a comma
  `awk -F, `

get only lines that contain oraagent.bin
  `'/oraagent.bin/ `

continue if the PID = 13048
  `&& $2==13048 `

continue if the SYSCALL = '[running]'
  `&& $7=="[running]"`

continue if KSTACK is not empty
  `&& $11 != "" `

print the KSTACK
  `{ print $11 }' `

this is the input file
  `/var/log/xcapture/2020-12-03.15.csv `

sort the output
  `| sort`

get a count per unique output
  `| uniq -c `

sort by the count of items
  `| sort -n`


Should you want to do more complex transformations to the data, you may want to use Perl or similar.


