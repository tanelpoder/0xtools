CC=gcc

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
	cp -v ./bin/xcapture /usr/bin/

uninstall:
	rm -fv /usr/bin/xcapture

clean:
	rm -f ./bin/xcapture

