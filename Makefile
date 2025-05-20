CC ?= gcc
PREFIX ?= /usr

install:
	install -m 0755 -d ${PREFIX}/bin
	install -m 0755 bin/psn ${PREFIX}/bin/psn
	install -m 0755 -d ${PREFIX}/lib/0xtools
	install -m 0644 lib/0xtools/psnproc.py ${PREFIX}/lib/0xtools/psnproc.py
	install -m 0644 lib/0xtools/psnreport.py ${PREFIX}/lib/0xtools/psnreport.py
	install -m 0644 lib/0xtools/argparse.py ${PREFIX}/lib/0xtools/argparse.py
	install -m 0755 bin/schedlat ${PREFIX}/bin/schedlat
	install -m 0755 bin/vmtop ${PREFIX}/bin/vmtop
	install -m 0755 bin/syscallargs ${PREFIX}/bin/syscallargs
	install -m 0755 bin/tracepointargs ${PREFIX}/bin/tracepointargs
	install -m 0755 bin/cpumhz ${PREFIX}/bin/cpumhz
	install -m 0755 bin/cpumhzturbo ${PREFIX}/bin/cpumhzturbo
	install -m 0755 bin/cpuactturbo ${PREFIX}/bin/cpuactturbo
	install -m 0755 bin/lsds ${PREFIX}/bin/lsds

uninstall:
	rm -fv  ${PREFIX}/bin/psn
	rm -fv  ${PREFIX}/bin/schedlat ${PREFIX}/bin/vmtop ${PREFIX}/bin/syscallargs ${PREFIX}/bin/tracepointargs
	rm -fv  ${PREFIX}/bin/cpumhz ${PREFIX}/bin/cpumhzturbo ${PREFIX}/bin/cpuactturbo ${PREFIX}/bin/lsds
	rm -fv  ${PREFIX}/lib/0xtools/psnproc.py ${PREFIX}/lib/0xtools/psnreport.py ${PREFIX}/lib/0xtools/argparse.py
	rm -rfv ${PREFIX}/lib/0xtools 

