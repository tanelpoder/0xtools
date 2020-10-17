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
	# for now the temporary "install" method is with symlinks
	ln -s `pwd`/bin/xcapture /usr/bin/xcapture
	ln -s `pwd`/bin/psn /usr/bin/psn
	ln -s `pwd`/bin/schedlat /usr/bin/schedlat

uninstall:
	rm -fv /usr/bin/xcapture
	rm -fv /usr/bin/psn
	rm -fv /usr/bin/schedlat

clean:
	rm -f ./bin/xcapture

