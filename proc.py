#  proc.py -- Linux Process Snapper by Tanel Poder
#  Copyright 2019 Tanel Poder
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

# structures defining /proc
import os, os.path
import re
import platform

system_timer_hz = os.sysconf('SC_CLK_TCK')

class ProcSource:
    def __init__(self, name, path, available_columns, stored_column_names, task_level=False, read_samples=lambda f: [f.read()], parse_sample=lambda self, sample: sample.split()):
        self.name = name
        self.path = path
        self.available_columns = available_columns
        self.task_level = task_level
        self.read_samples = read_samples
        self.parse_sample = parse_sample

        self.set_stored_columns(stored_column_names)



    def set_stored_columns(self, stored_column_names):
        col_name_i, schema_type_i, source_i, transform_i = range(4)
        self.stored_column_names = stored_column_names or [c[0] for c in self.available_columns]

        # find schema columns
        sample_cols = [('event_time', str), ('pid', int), ('task', int)]
        source_cols = [c for c in self.available_columns if c[col_name_i] in self.stored_column_names and c[col_name_i] not in dict(sample_cols) and c[1] is not None]
        self.schema_columns = sample_cols + source_cols

        column_indexes = dict([(c[col_name_i], c[source_i]) for c in self.available_columns])

        schema_extract_idx = [column_indexes[c[col_name_i]] for c in source_cols]
        schema_extract_convert = [c[schema_type_i] if len(c) == 3 else c[transform_i] for c in source_cols]
        self.schema_extract = zip(schema_extract_idx, schema_extract_convert)

        self.insert_sql = "INSERT INTO '%s' VALUES (%s)" % (self.name, ','.join(['?' for i in self.schema_columns]))


    def sample(self, event_time, pid, task):
        sample_path = self.path % (pid, task) if self.task_level else self.path % pid

        with open(sample_path) as f:
            full_sample = None
            raw_samples = self.read_samples(f)

            def create_row_sample(raw_sample):
                full_sample = self.parse_sample(self, raw_sample)

                # some syscall-specific code pushed down to general sampling function
                # call readlink() to get the file name for system calls that have a file descriptor as arg0
                filename = ''
                if self.name == 'syscall':
                    # special case: kernel threads show all-zero "syscall" on newer kernels like 4.x 
                    # otherwise it incorrectly looks like that kernel is in a "read" syscall (id=0 on x86_64)
                    if full_sample[0] == '-1' or full_sample == ['0', '0x0', '0x0', '0x0', '0x0', '0x0', '0x0', '0x0', '0x0']:
                        full_sample = ['kernel_thread', '0x0', '0x0', '0x0', '0x0', '0x0', '0x0', '0x0', '0x0']
                     
                    try:
                        syscall_id = full_sample[0]  # get string version of syscall number or "running" or "-1"
                    except (ValueError, IndexError) as e:
                        print 'problem extracting syscall id', self.name, 'sample:'
                        print full_sample
                        print
                        raise

                    if syscall_id in syscalls_with_fd_arg:
                        try:
                            arg0  = int(full_sample[1], 16)
                            # a hacky way for avoiding reading false file descriptors for kernel threads on older kernels
                            # (like 2.6.32) that show "syscall 0x0" for kernel threads + some random false arguments. TODO refactor this and kernel_thread translation above
                            if arg0 <= 65536:
                                filename = os.readlink("/proc/%s/fd/%s" % (pid, arg0)) + " " + special_fds.get(arg0, '')
                            else:
                                filename = 'fd over 65536'
                     
                        except (OSError) as e:
                            # file has been closed or process has disappeared
                            #print 'problem with translating fd to name /proc/%s/fd/%s' % (pid, arg0), 'sample:'
                            #print full_sample
                            #print 
                            filename = '-'

                full_sample += (filename,)
                         
                r =  [event_time, pid, task] + [convert(full_sample[idx]) for idx, convert in self.schema_extract]
                return r

            try:
                return [create_row_sample(rs) for rs in raw_samples]
            except (ValueError, IndexError) as e:
                print 'problem parsing', self.name, 'sample:'
                print raw_samples
                print
                raise


### stat ###
# process_state_name = {
#     'R': 'Running (ON CPU)',
#     'S': 'Sleeping (Interruptible)',
#     'D': 'Disk (Uninterruptible)',
#     'Z': 'Zombie',
#     'T': 'Traced/Stopped',
#     'W': 'Paging'
# }

# https://github.com/torvalds/linux/blob/master/fs/proc/array.c
# State W (paging) is not used in kernels 2.6.x onwards
process_state_name = {
        'R': 'Running (ON CPU)',            #/* 0x00 */
        'S': 'Sleep (Interruptible)',       #/* 0x01 */
        'D': 'Disk (Uninterruptible)',      #/* 0x02 */
        'T': '(stopped)',                   #/* 0x04 */
        't': '(tracing stop)',              #/* 0x08 */
        'X': '(dead)',                      #/* 0x10 */
        'Z': '(zombie)',                    #/* 0x20 */
        'P': '(parked)',                    #/* 0x40 */
        #/* states beyond TASK_REPORT: */
        'I': '(idle)',                      #/* 0x80 */
}

def parse_stat_sample(proc_source, sample):
    tokens = raw_tokens = sample.split()

    # stitch together comm field of the form (word word)
    if raw_tokens[1][0] == '(' and raw_tokens[1][-1] != ')':
        tokens = raw_tokens[:2]
        raw_tokens = raw_tokens[2:]
        while tokens[-1][-1] != ')':
            tokens[-1] += ' ' + raw_tokens.pop(0)
        tokens.extend(raw_tokens)

    return tokens


trim_comm = re.compile('\d+')


stat = ProcSource('stat', '/proc/%s/task/%s/stat', [
    ('pid', int, 0),
    ('comm', str, 1, lambda c: re.sub(trim_comm, '*', c)),
    ('comm2', str, 1),
    ('state_id', str, 2),
    ('state', str, 2, lambda state_id: process_state_name.get(state_id, state_id)),
    ('ppid', int, 3),
    ('pgrp', int, 4),
    ('session', int, 5),
    ('tty_nr', int, 6),
    ('tpgid', int, 7),
    ('flags', None, 8),
    ('minflt', int, 9),
    ('cminflt', int, 10),
    ('majflt', int, 11),
    ('cmajflt', int, 12),
    ('utime', long, 13),
    ('stime', long, 14),
    ('cutime', long, 15),
    ('cstime', long, 16),
    ('utime_sec',  long, 13, lambda v: int(v) / system_timer_hz),
    ('stime_sec',  long, 14, lambda v: int(v) / system_timer_hz),
    ('cutime_sec', long, 15, lambda v: int(v) / system_timer_hz),
    ('cstime_sec', long, 16, lambda v: int(v) / system_timer_hz),
    ('priority', int, 17),
    ('nice', int, 18),
    ('num_threads', int, 19),
    ('itrealvalue', None, 20),
    ('starttime', long, 21),
    ('vsize', long, 22),
    ('rss', long, 23),
    ('rsslim', str, 24),
    ('startcode', None, 25),
    ('endcode', None, 26),
    ('startstack', None, 27),
    ('kstkesp', None, 28),
    ('kstkeip', None, 29),
    ('signal', None, 30),
    ('blocked', None, 31),
    ('sigignore', None, 32),
    ('sigcatch', None, 33),
    ('wchan', None, 34),
    ('nswap', None, 35),
    ('cnswap', None, 36),
    ('exit_signal', int, 37),
    ('processor', int, 38),
    ('rt_priority', int, 39),
    ('policy', None, 40),
    ('delayacct_blkio_ticks', long, 41),
    ('guest_time', int, 42),
    ('cgust_time', int, 43),
    ('start_data', None, 44),
    ('end_data', None, 45),
    ('start_brk', None, 46),
    ('arg_start', None, 47),
    ('arg_end', None, 48),
    ('env_start', None, 49),
    ('env_end', None, 50),
    ('exit_code', int, 51),
], None,
task_level=True,
parse_sample=parse_stat_sample)



### status ###
def parse_status_sample(proc_source, sample):
    lines = sample.split('\n')

    sample_values = []

    for line in [l for l in lines if l]:
        line_tokens = line.split()
        n, v = line_tokens[0][:-1].lower(), ' '.join(line_tokens[1:])
        n_kb = n + '_kb'

        # missing values take default parse function value: assume no order change, and that available_columns contains all possible field names
        while len(sample_values) < len(proc_source.available_columns) and proc_source.available_columns[len(sample_values)][0] not in (n, n_kb):
            parse_fn = proc_source.available_columns[len(sample_values)][1]
            sample_values.append(parse_fn())

        if len(sample_values) < len(proc_source.available_columns):
            sample_values.append(v)

    return sample_values


status = ProcSource('status', '/proc/%s/status', [
    ('name', str, 0),
    ('umask', str, 1),
    ('state', str, 2), # remove duplicate with stat
    ('tgid', int, 3),
    ('ngid', int, 4),
    ('pid', int, 5),
    ('ppid', int, 6), # remove duplicate with stat
    ('tracerpid', int, 7),
    ('uid', int, 8, lambda v: int(v.split()[0])),
    ('gid', int, 9, lambda v: int(v.split()[0])),
    ('fdsize', int, 10),
    ('groups', str, 11),
    ('nstgid', str, 12),
    ('nspid', str, 13),
    ('nspgid', str, 14),
    ('nssid', str, 15),
    ('vmpeak_kb', int, 16, lambda v: int(v.split()[0])),
    ('vmsize_kb', int, 17, lambda v: int(v.split()[0])),
    ('vmlck_kb', int, 18, lambda v: int(v.split()[0])),
    ('vmpin_kb', int, 19, lambda v: int(v.split()[0])),
    ('vmhwm_kb', int, 20, lambda v: int(v.split()[0])),
    ('vmrss_kb', int, 21, lambda v: int(v.split()[0])),
    ('rssanon_kb', int, 22, lambda v: int(v.split()[0])),
    ('rssfile_kb', int, 23, lambda v: int(v.split()[0])),
    ('rssshmem_kb', int, 24, lambda v: int(v.split()[0])),
    ('vmdata_kb', int, 25, lambda v: int(v.split()[0])),
    ('vmstk_kb', int, 26, lambda v: int(v.split()[0])),
    ('vmexe_kb', int, 27, lambda v: int(v.split()[0])),
    ('vmlib_kb', int, 28, lambda v: int(v.split()[0])),
    ('vmpte_kb', int, 29, lambda v: int(v.split()[0])),
    ('vmpmd_kb', int, 30, lambda v: int(v.split()[0])),
    ('vmswap_kb', int, 31, lambda v: int(v.split()[0])),
    ('hugetlbpages_kb', int, 32, lambda v: int(v.split()[0])),
    ('threads', int, 33),
    ('sigq', str, 34),
    ('sigpnd', str, 35),
    ('shdpnd', str, 36),
    ('sigblk', str, 37),
    ('sigign', str, 38),
    ('sigcgt', str, 39),
    ('capinh', str, 40),
    ('capprm', str, 41),
    ('capeff', str, 42),
    ('capbnd', str, 43),
    ('capamb', str, 44),
    ('seccomp', int, 45),
    ('cpus_allowed', str, 46),
    ('cpus_allowed_list', str, 47),
    ('mems_allowed', str, 48),
    ('mems_allowed_list', str, 49),
    ('voluntary_ctxt_switches', int, 50),
    ('nonvoluntary_ctxt_switches', int, 51)
], None, task_level=False, parse_sample=parse_status_sample)


### syscall ###
def extract_system_call_ids(unistd_64_fh):
    syscall_id_to_name = {'running': '[running]', '-1': '[kernel_direct]', 'kernel_thread':'[kernel_thread]'}
    name_prefix = '__NR_'

    for line in unistd_64_fh.readlines():
        tokens = line.split()
        if tokens and len(tokens) == 3 and tokens[0] == '#define':
            _, s_name, s_id = tokens
            if s_name.startswith(name_prefix):
                s_name = s_name[len(name_prefix):]
                syscall_id_to_name[s_id] = s_name

    return syscall_id_to_name

# currently assuming all platforms are x86_64
def get_system_call_names():
    psn_dir=os.path.dirname(os.path.realpath(__file__))
    kernel_ver=platform.release().split('-')[0]
    unistd_64_paths = ['/usr/include/asm/unistd_64.h', '/usr/include/x86_64-linux-gnu/asm/unistd_64.h', '/usr/include/asm-x86_64/unistd.h', psn_dir+'/syscall_64_'+kernel_ver+'.h', psn_dir+'/syscall_64.h']
    for path in unistd_64_paths:
        try:
            with open(path) as f:
                return extract_system_call_ids(f)
        except IOError, e:
            pass

    raise Exception('unistd_64.h not found in' + ' or '.join(unistd_64_paths) + '.\n           You may need to "yum install kernel-headers" or "apt-get install libc6-dev"\n           until this dependency is removed in a newer pSnapper version')


syscall_id_to_name = get_system_call_names()

# define syscalls for which we can look up filename from fd argument
syscall_name_to_id = dict((y,x) for x,y in syscall_id_to_name.iteritems())

syscalls_with_fd_arg = set([                   
    syscall_name_to_id['read']              
  , syscall_name_to_id['write']             
  , syscall_name_to_id['pread64']           
  , syscall_name_to_id['pwrite64']          
  , syscall_name_to_id['fsync']             
  , syscall_name_to_id['fdatasync']         
  , syscall_name_to_id['recvfrom']          
  , syscall_name_to_id['sendto']            
  , syscall_name_to_id['recvmsg']           
  , syscall_name_to_id['sendmsg']           
  , syscall_name_to_id['epoll_wait']        
  , syscall_name_to_id['ioctl']             
  , syscall_name_to_id['accept']            
  , syscall_name_to_id['accept4']            
])

special_fds = { 0:'(stdin) ', 1:'(stdout)', 2:'(stderr)' }

def parse_syscall_sample(proc_source, sample):
    tokens = sample.split()
    if tokens[0] == 'running':
        return (tokens[0], '', '', '', '', '', '', None, None)
    else:
        return tokens


trim_socket = re.compile('\d+')

syscall = ProcSource('syscall', '/proc/%s/task/%s/syscall', [
    ('syscall_id', int,  0, lambda sn: -2 if sn == 'running' else int(sn)),
    ('syscall',    str,  0, lambda sn: syscall_id_to_name[sn]),  # convert syscall_id via unistd_64.h into call name
    ('arg0',       str,  1),
    ('arg1',       str,  2),
    ('arg2',       str,  3),
    ('arg3',       str,  4),
    ('arg4',       str,  5),
    ('arg5',       str,  6),
    ('esp',        None, 7),                                        # stack pointer
    ('eip',        None, 8),                                        # program counter/instruction pointer
    ('filename',   str,  9, lambda fn: re.sub(trim_socket, '*', fn) if fn.split(':')[0] in ['socket','pipe'] else fn),  
    ('filename2',  str,  9),  
    ('basename',   str,  9, lambda fn: re.sub(trim_socket, '*', fn) if fn.split(':')[0] in ['socket','pipe'] else os.path.basename(fn)), # filename if syscall has fd as arg0
    ('dirname',    str,  9, lambda fn: re.sub(trim_socket, '*', fn) if fn.split(':')[0] in ['socket','pipe'] else os.path.dirname(fn)),  # filename if syscall has fd as arg0
], None,
task_level=True, parse_sample=parse_syscall_sample)


### get file name from file descriptor ###
#filename = ProcSource('fd', '/proc/%s/task/%s/fd', [('wchan', str, 0)], ['wchan'], task_level=True)

### process cmdline args ###
def parse_cmdline_sample(proc_source,sample):
    # the cmdline entry may have spaces in it and happens to have a \000 in the end
    # the split [] hack is due to postgres having some extra spaces in its cmdlines
    return [sample.split('\000')[0].strip()] 

cmdline = ProcSource('cmdline', '/proc/%s/task/%s/cmdline', [('cmdline', str, 0)], ['cmdline'], task_level=True, parse_sample=parse_cmdline_sample)

### wchan ###
wchan = ProcSource('wchan', '/proc/%s/task/%s/wchan', [('wchan', str, 0)], ['wchan'], task_level=True)


### io ###
def parse_io_sample(proc_source, sample):
    return [line.split()[1] if line else '' for line in sample.split('\n')]

io = ProcSource('io', '/proc/%s/task/%s/io', [
    ('rchar', int, 0),
    ('wchar', int, 1),
    ('syscr', int, 2),
    ('syscw', int, 3),
    ('read_bytes', int, 4),
    ('write_bytes', int, 5),
    ('cancelled_write_bytes', int, 6),
], None,
task_level=True,
parse_sample=parse_io_sample)



### net/dev ### (not accounted at process level)
def read_net_samples(fh):
    return fh.readlines()[2:]


def parse_net_sample(proc_source, sample):
    fields = sample.split()
    fields[0] = fields[0][:-1]
    return fields


net = ProcSource('net', '/proc/%s/task/%s/net/dev', [
    ('iface', str, 0),
    ('rx_bytes', str, 1),
    ('rx_packets', str, 2),
    ('rx_errs', str, 3),
    ('rx_drop', str, 4),
    ('rx_fifo', str, 5),
    ('rx_frame', str, 6),
    ('rx_compressed', str, 7),
    ('rx_multicast', str, 8),
    ('tx_bytes', str, 9),
    ('tx_packets', str, 10),
    ('tx_errs', str, 11),
    ('tx_drop', str, 12),
    ('tx_fifo', str, 13),
    ('tx_colls', str, 14),
    ('tx_carrier', str, 15),
    ('tx_compressed', str, 16),
], None,
read_samples=read_net_samples,
parse_sample=parse_net_sample)



### stack ###
def read_stack_samples(fh):
    result = ''

    # reverse stack and ignore the (reversed) top frame 0xfffffffffffff
    #                          |  |
    #                          v  v
    for x in fh.readlines()[::-1][1:]:
        func = x.split(' ')[1].split('+')[0]
        if func not in ['entry_SYSCALL_64_after_hwframe','do_syscall_64']:
            if result:          # skip writing the 1st "->" 
                result += '->'  
            result += func + '()'

    return [result or '-']


stack = ProcSource('stack', '/proc/%s/task/%s/stack', [
    ('kstack', str, 0),
], None,
task_level=True,
read_samples=read_stack_samples)



### smaps ###
def read_smaps_samples(fh):
    samples = []
    current_sample = ''
    for line in fh.readlines():
        current_sample += line
        if line[:7] == 'VmFlags':
            samples.append(current_sample)
            current_sample = ''
    return samples


def parse_smaps_sample(proc_source, sample):
    sample_values = []
    sample_lines = [l for l in sample.split('\n') if l != '']

    header_tokens = sample_lines[0].split()
    sample_values.extend(header_tokens[:5])
    sample_values.append(' '.join(header_tokens[5:]))

    for line in sample_lines[1:-1]:
        n, kb, _ = line.split()
        n = n[:-1].lower() + '_kb'

        # missing values take default parse function value: assume no order change, and that available_columns contains all possible field names
        while len(sample_values) < len(proc_source.available_columns) and n != proc_source.available_columns[len(sample_values)][0]:
            parse_fn = proc_source.available_columns[len(sample_values)][1]
            sample_values.append(parse_fn())

        if len(sample_values) < len(proc_source.available_columns):
            sample_values.append(kb)

    while len(sample_values) < len(proc_source.available_columns) - 1:
        parse_fn = proc_source.available_columns[len(sample_values)][1]
        sample_values.append(parse_fn())

    sample_values.append(' '.join(sample_lines[-1].split()[1:]))
    return sample_values


smaps = ProcSource('smaps', '/proc/%s/smaps', [
    ('address_range', str, 0),
    ('perms', str, 1),
    ('offset', str, 2),
    ('dev', str, 3),
    ('inode', int, 4),
    ('pathname', str, 5),
    ('size_kb', int, 6),
    ('rss_kb', int, 7),
    ('pss_kb', int, 8),
    ('shared_clean_kb', int, 9),
    ('shared_dirty_kb', int, 10),
    ('private_clean_kb', int, 11),
    ('private_dirty_kb', int, 12),
    ('referenced_kb', int, 13),
    ('anonymous_kb', int, 14),
    ('anonhugepages_kb', int, 15),
    ('shmempmdmapped_kb', int, 16),
    ('shared_hugetld_kb', int, 17),
    ('private_hugetld_kb', int, 18),
    ('swap_kb', int, 19),
    ('swappss_kb', int, 20),
    ('kernelpagesize_kb', int, 21),
    ('mmupagesize_kb', int, 22),
    ('locked_kb', int, 23),
    ('vmflags', str, 24),
], None,
task_level=False,
read_samples=read_smaps_samples,
parse_sample=parse_smaps_sample)




all_sources = [stat, status, syscall, wchan, io, smaps, stack, cmdline]

