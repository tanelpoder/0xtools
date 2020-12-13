CC=gcc
PREFIX ?= /usr

# build
CFLAGS=-I include -Wall

# debuginfo included
CFLAGS_DEBUG=-I include -ggdb -Wall

# debug without compiler optimizations
CFLAGS_DEBUG0=-I include -ggdb -O0

all:
	$(CC) $(CFLAGS) -o bin/xcapture src/xcapture.c

debug:
	$(CC) $(CFLAGS_DEBUG) -o bin/xcapture src/xcapture.c

debug0:
	$(CC) $(CFLAGS_DEBUG0) -o bin/xcapture src/xcapture.c

install:
	install -m 0755 bin/xcapture ${PREFIX}/bin/xcapture
	install -m 0755 bin/psn ${PREFIX}/bin/psn
	install -m 0755 bin/schedlat ${PREFIX}/bin/schedlat
	install -m 0644 lib/proc.py ${PREFIX}/lib/proc.py
	install -m 0644 lib/psnreport.py ${PREFIX}/lib/psnreport.py
	install -m 0644 lib/argparse.py ${PREFIX}/lib/argparse.py

uninstall:
	rm -fv ${PREFIX}/bin/xcapture ${PREFIX}/bin/psn ${PREFIX}/bin/schedlat
	rm -fv ${PREFIX}/lib/proc.py ${PREFIX}/lib/psnreport.py ${PREFIX}/lib/argparse.py

clean:
	rm -f bin/xcapture
