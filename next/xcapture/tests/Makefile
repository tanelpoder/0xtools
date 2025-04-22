CC = gcc
CFLAGS = -Wall -Wextra -O2 -I..
LDFLAGS =

# Source files
SRCS = md5_test.c ../md5.c
OBJS = md5_test.o ../md5.o
TARGET = md5_test

.PHONY: all clean

all: $(TARGET)

$(TARGET): $(OBJS)
	$(CC) $(CFLAGS) $(OBJS) -o $(TARGET) $(LDFLAGS)

md5_test.o: md5_test.c ../md5.h
	$(CC) $(CFLAGS) -c $< -o $@

../md5.o: ../md5.c ../md5.h
	$(CC) $(CFLAGS) -c $< -o $@

clean:
	rm -f md5_test.o $(TARGET)
	# Don't remove md5.o from parent directory as it may be used elsewhere

# Special clean-all target if you want to clean everything including parent directory objects
clean-all: clean
	rm -f ../md5.o
