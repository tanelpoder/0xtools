# SPDX-License-Identifier: (LGPL-2.1 OR BSD-2-Clause)
OUTPUT := .output
CLANG ?= clang
LIBBPF_SRC := $(abspath ../libbpf-bootstrap/libbpf/src)
BPFTOOL_SRC := $(abspath ../libbpf-bootstrap/bpftool/src)
LIBBPF_OBJ := $(abspath $(OUTPUT)/libbpf.a)
BPFTOOL_OUTPUT ?= $(abspath $(OUTPUT)/bpftool)
BPFTOOL ?= $(BPFTOOL_OUTPUT)/bootstrap/bpftool
LIBBLAZESYM_SRC := $(abspath ../libbpf-bootstrap/blazesym/)
LIBBLAZESYM_INC := $(abspath $(LIBBLAZESYM_SRC)/capi/include)
LIBBLAZESYM_OBJ := $(abspath $(OUTPUT)/libblazesym_c.a)

# 0xtools main include dir for syscall_nr to name translation etc
XTOOLS_INC := $(abspath ../../include)

ARCH ?= $(shell uname -m | sed 's/x86_64/x86/' \
			 | sed 's/arm.*/arm/' \
			 | sed 's/aarch64/arm64/' \
			 | sed 's/ppc64le/powerpc/' \
			 | sed 's/mips.*/mips/' \
			 | sed 's/riscv64/riscv/' \
			 | sed 's/loongarch64/loongarch/')
VMLINUX := ../libbpf-bootstrap/vmlinux.h/include/$(ARCH)/vmlinux.h

INCLUDES := -I$(OUTPUT) \
	    -I../libbpf-bootstrap/libbpf/include/uapi \
	    -I$(dir $(VMLINUX)) \
	    -I$(LIBBLAZESYM_INC) \
	    -I$(XTOOLS_INC) \
	    -I. \
	    -Iinclude \
	    -Isrc \
	    -Isrc/probes \
	    -Isrc/maps \
	    -Isrc/utils \
	    -Isrc/user \
	    -I$(OUTPUT)/src/probes

CFLAGS := -g -Wall
ALL_LDFLAGS := $(LDFLAGS) $(EXTRA_LDFLAGS)

APPS = xcapture

# Define BPF source files with their full paths
BPF_SRCS := src/probes/task/task.bpf.c \
	    src/probes/syscall/syscall.bpf.c \
	    src/probes/io/iorq.bpf.c

# Define BPF object and skeleton paths explicitly to avoid confusion
BPF_OBJS := $(patsubst %.bpf.c,$(OUTPUT)/%.bpf.o,$(BPF_SRCS))
BPF_SKELS := $(patsubst $(OUTPUT)/%.bpf.o,$(OUTPUT)/%.skel.h,$(BPF_OBJS))

# Explicitly define the object files needed for the final binary
OBJS := $(OUTPUT)/src/user/main.o $(OUTPUT)/src/utils/md5.o \
	$(OUTPUT)/src/user/task_handler.o $(OUTPUT)/src/user/tracking_handler.o

# Get Clang's default includes on this system
CLANG_BPF_SYS_INCLUDES ?= $(shell $(CLANG) -v -E - </dev/null 2>&1 \
	| sed -n '/<...> search starts here:/,/End of search list./{ s| \(/.*\)|-idirafter \1|p }')

ifeq ($(V),1)
	Q =
	msg =
else
	Q = @
	msg = @printf '  %-8s %s%s\n' \
		      "$(1)" \
		      "$(patsubst $(abspath $(OUTPUT))/%,%,$(2))" \
		      "$(if $(3), $(3))";
	MAKEFLAGS += --no-print-directory
endif

define allow-override
  $(if $(or $(findstring environment,$(origin $(1))),\
	    $(findstring command line,$(origin $(1)))),,\
    $(eval $(1) = $(2)))
endef

$(call allow-override,CC,$(CROSS_COMPILE)cc)
$(call allow-override,LD,$(CROSS_COMPILE)ld)

.PHONY: all
all: $(APPS)

.PHONY: clean
clean:
	$(call msg,CLEAN)
	$(Q)rm -rf $(OUTPUT) $(APPS)

# remove only xcapture output (not libbpf, bpftool etc)
.PHONY: cleanx
cleanx:
	$(call msg,CLEANX, xcapture artifacts)
	$(Q)rm -f $(APPS)
	$(Q)rm -rf $(OUTPUT)/src

# Create all needed output directories
$(OUTPUT) $(OUTPUT)/libbpf $(BPFTOOL_OUTPUT):
	$(call msg,MKDIR,$@)
	$(Q)mkdir -p $@

# Output directories for various components
$(OUTPUT)/src/user:
	$(call msg,MKDIR,$@)
	$(Q)mkdir -p $@

$(OUTPUT)/src/probes/task:
	$(call msg,MKDIR,$@)
	$(Q)mkdir -p $@

$(OUTPUT)/src/probes/syscall:
	$(call msg,MKDIR,$@)
	$(Q)mkdir -p $@

$(OUTPUT)/src/probes/io:
	$(call msg,MKDIR,$@)
	$(Q)mkdir -p $@

$(OUTPUT)/src/helpers:
	$(call msg,MKDIR,$@)
	$(Q)mkdir -p $@

$(OUTPUT)/src/utils:
	$(call msg,MKDIR,$@)
	$(Q)mkdir -p $@

# Build libbpf
$(LIBBPF_OBJ): $(wildcard $(LIBBPF_SRC)/*.[ch] $(LIBBPF_SRC)/Makefile) | $(OUTPUT)/libbpf
	$(call msg,LIB,$@)
	$(Q)$(MAKE) -C $(LIBBPF_SRC) BUILD_STATIC_ONLY=1 \
		    OBJDIR=$(patsubst %/,%,$(dir $@))"/libbpf" \
		    DESTDIR=$(patsubst %/,%,$(dir $@)) \
		    INCLUDEDIR= LIBDIR= UAPIDIR= \
		    install

# Build bpftool
$(BPFTOOL): | $(BPFTOOL_OUTPUT)
	$(call msg,BPFTOOL,$@)
	$(Q)$(MAKE) ARCH= CROSS_COMPILE= OUTPUT=$(BPFTOOL_OUTPUT)/ -C $(BPFTOOL_SRC) bootstrap

# Generic rule for building BPF objects
$(OUTPUT)/src/probes/task/task.bpf.o: src/probes/task/task.bpf.c \
		include/xcapture.h src/maps/xcapture_maps.h src/utils/xcapture_helpers.h src/helpers/file_helpers.h \
		$(LIBBPF_OBJ) $(VMLINUX) | $(OUTPUT)/src/probes/task $(BPFTOOL)
	$(call msg,BPF,$@)
	$(Q)$(CLANG) -g -O2 -target bpf -D__TARGET_ARCH_$(ARCH) \
		     $(INCLUDES) $(CLANG_BPF_SYS_INCLUDES) \
		     -c $< -o $(patsubst %.bpf.o,%.tmp.bpf.o,$@)
	$(Q)$(BPFTOOL) gen object $@ $(patsubst %.bpf.o,%.tmp.bpf.o,$@)

$(OUTPUT)/src/probes/syscall/syscall.bpf.o: src/probes/syscall/syscall.bpf.c include/xcapture.h src/maps/xcapture_maps.h $(LIBBPF_OBJ) $(VMLINUX) | $(OUTPUT)/src/probes/syscall $(BPFTOOL)
	$(call msg,BPF,$@)
	$(Q)$(CLANG) -g -O2 -target bpf -D__TARGET_ARCH_$(ARCH) \
		     $(INCLUDES) $(CLANG_BPF_SYS_INCLUDES) \
		     -c $< -o $(patsubst %.bpf.o,%.tmp.bpf.o,$@)
	$(Q)$(BPFTOOL) gen object $@ $(patsubst %.bpf.o,%.tmp.bpf.o,$@)

$(OUTPUT)/src/probes/io/iorq.bpf.o: src/probes/io/iorq.bpf.c include/xcapture.h src/maps/xcapture_maps.h $(LIBBPF_OBJ) $(VMLINUX) | $(OUTPUT)/src/probes/io $(BPFTOOL)
	$(call msg,BPF,$@)
	$(Q)$(CLANG) -g -O2 -target bpf -D__TARGET_ARCH_$(ARCH) \
		     $(INCLUDES) $(CLANG_BPF_SYS_INCLUDES) \
		     -c $< -o $(patsubst %.bpf.o,%.tmp.bpf.o,$@)
	$(Q)$(BPFTOOL) gen object $@ $(patsubst %.bpf.o,%.tmp.bpf.o,$@)

# Generate BPF skeletons
$(OUTPUT)/src/probes/task/task.skel.h: $(OUTPUT)/src/probes/task/task.bpf.o | $(BPFTOOL)
	$(call msg,GEN,$@)
	$(Q)$(BPFTOOL) gen skeleton $< > $@

$(OUTPUT)/src/probes/syscall/syscall.skel.h: $(OUTPUT)/src/probes/syscall/syscall.bpf.o | $(BPFTOOL)
	$(call msg,GEN,$@)
	$(Q)$(BPFTOOL) gen skeleton $< > $@

$(OUTPUT)/src/probes/io/iorq.skel.h: $(OUTPUT)/src/probes/io/iorq.bpf.o | $(BPFTOOL)
	$(call msg,GEN,$@)
	$(Q)$(BPFTOOL) gen skeleton $< > $@

# Build md5.o
$(OUTPUT)/src/utils/md5.o: src/utils/md5.c src/utils/md5.h | $(OUTPUT)/src/utils
	$(call msg,CC,$@)
	$(Q)$(CC) $(CFLAGS) $(INCLUDES) -c $< -o $@

# Define specific dependencies for main.o
MAIN_DEPS := src/user/main.c \
	     include/xcapture.h \
	     include/xcapture_user.h \
	     src/utils/md5.h \
	     $(OUTPUT)/src/probes/task/task.skel.h \
	     $(OUTPUT)/src/probes/syscall/syscall.skel.h \
	     $(OUTPUT)/src/probes/io/iorq.skel.h


# Ringbuf event handlers
$(OUTPUT)/src/user/task_handler.o: src/user/task_handler.c src/user/task_handler.h | $(OUTPUT)/src/user
	$(call msg,CC,$@)
	$(Q)$(CC) $(CFLAGS) $(INCLUDES) -c $< -o $@

$(OUTPUT)/src/user/tracking_handler.o: src/user/tracking_handler.c src/user/tracking_handler.h | $(OUTPUT)/src/user
	$(call msg,CC,$@)
	$(Q)$(CC) $(CFLAGS) $(INCLUDES) -c $< -o $@

# Build main.o with explicit dependency on all BPF skeletons
$(OUTPUT)/src/user/main.o: $(MAIN_DEPS) | $(OUTPUT)/src/user
	$(call msg,CC,$@)
	$(Q)$(CC) $(CFLAGS) $(INCLUDES) -D__TARGET_ARCH_$(ARCH) -c src/user/main.c -o $@

# Build final binary with explicit objects
xcapture: $(OBJS) $(LIBBPF_OBJ) | $(OUTPUT)
	$(call msg,BINARY,$@)
	$(Q)$(CC) $(CFLAGS) -D__TARGET_ARCH_$(ARCH) $^ $(ALL_LDFLAGS) -lelf -lz -o $@

# Print debug info (useful for troubleshooting)
.PHONY: debug
debug:
	@echo "BPF_SRCS: $(BPF_SRCS)"
	@echo "BPF_OBJS: $(BPF_OBJS)"
	@echo "BPF_SKELS: $(BPF_SKELS)"
	@echo "OBJS: $(OBJS)"
	@echo "MAIN_DEPS: $(MAIN_DEPS)"
	@ls -la $(OUTPUT)/src/probes/task/ 2>/dev/null || echo "Task probe directory not created yet"

# delete failed targets
.DELETE_ON_ERROR:

# keep intermediate (.skel.h, .bpf.o, etc) targets
.SECONDARY:
