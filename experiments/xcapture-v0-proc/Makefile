CC ?= gcc
PREFIX ?= /usr

# build
CFLAGS ?= -Wall

# debuginfo included
CFLAGS_DEBUG=-I include -ggdb -Wall

# debug without compiler optimizations
CFLAGS_DEBUG0=-I include -ggdb -O0

all:
	$(CC) $(CFLAGS) -I include -o bin/xcapture src/xcapture.c

debug:
	$(CC) $(CFLAGS_DEBUG) -o bin/xcapture src/xcapture.c

debug0:
	$(CC) $(CFLAGS_DEBUG0) -o bin/xcapture src/xcapture.c

install:
	install -m 0755 -d ${PREFIX}/bin
	install -m 0755 bin/xcapture ${PREFIX}/bin/xcapture

uninstall:
	rm -fv  ${PREFIX}/bin/xcapture

clean:
	rm -fv bin/xcapture
