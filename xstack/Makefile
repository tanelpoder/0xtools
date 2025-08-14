# SPDX-License-Identifier: (LGPL-2.1 OR BSD-2-Clause)
OUTPUT := .output
CLANG ?= clang
LLVM_STRIP ?= llvm-strip
LIBBPF_SRC := $(abspath ../libbpf-bootstrap/libbpf/src)
BPFTOOL_SRC := $(abspath ../libbpf-bootstrap/bpftool/src)
LIBBPF_OBJ := $(abspath $(OUTPUT)/libbpf.a)
BPFTOOL_OUTPUT ?= $(abspath $(OUTPUT)/bpftool)
BPFTOOL ?= $(BPFTOOL_OUTPUT)/bootstrap/bpftool
LIBBLAZESYM_SRC := $(abspath ../libbpf-bootstrap/blazesym/)
LIBBLAZESYM_INC := $(abspath $(LIBBLAZESYM_SRC)/capi/include)
LIBBLAZESYM_OBJ := $(abspath $(OUTPUT)/libblazesym_c.a)

ARCH ?= $(shell uname -m | sed 's/x86_64/x86/' \
			 | sed 's/arm.*/arm/' \
			 | sed 's/aarch64/arm64/' \
			 | sed 's/ppc64le/powerpc/' \
			 | sed 's/mips.*/mips/' \
			 | sed 's/riscv64/riscv/' \
			 | sed 's/loongarch64/loongarch/')

VMLINUX := ../libbpf-bootstrap/vmlinux.h/include/$(ARCH)/vmlinux.h

# Check for existence of vmlinux.h
ifeq ($(wildcard $(VMLINUX)),)
$(error vmlinux.h not found at $(VMLINUX). Please check libbpf-bootstrap setup)
endif

INCLUDES := -I$(OUTPUT) \
	    -I../libbpf-bootstrap/libbpf/include/uapi \
	    -I$(dir $(VMLINUX)) \
	    -I$(LIBBLAZESYM_INC) \
	    -I.

CFLAGS := -g -O2 -Wall
ALL_LDFLAGS := $(LDFLAGS) $(EXTRA_LDFLAGS)

# Optional BlazeSym support
USE_BLAZESYM ?= 1
ifeq ($(USE_BLAZESYM),1)
    CARGO := $(shell which cargo 2>/dev/null)
    ifeq ($(CARGO),)
        $(warning "Rust/Cargo not found. Disabling blazesym support")
        USE_BLAZESYM := 0
    else
        CFLAGS += -DUSE_BLAZESYM
        ALL_LDFLAGS += $(LIBBLAZESYM_OBJ) -lrt -ldl -lpthread -lm
        BLAZESYM_DEP := $(LIBBLAZESYM_OBJ)
    endif
else
    BLAZESYM_DEP :=
endif

APPS = xstack

# Get Clang's default includes on this system
CLANG_BPF_SYS_INCLUDES ?= $(shell $(CLANG) -v -E - </dev/null 2>&1 \
	| sed -n '/<...> search starts here:/,/End of search list./{ s| \(/.*\)|-idirafter \1|p }')

ifeq ($(V),1)
	Q =
	msg =
else
	Q = @
	msg = @printf '  %-8s %s%s\n' "$(1)" "$(2)" "$(if $(3), $(3))";
	MAKEFLAGS += --no-print-directory
endif

.PHONY: all
all: $(APPS)

.PHONY: clean
clean:
	$(call msg,CLEAN)
	$(Q)rm -rf $(OUTPUT) $(APPS)

.PHONY: cleanx
cleanx:
	$(call msg,CLEANX)
	$(Q)rm -f $(APPS) $(OUTPUT)/xstack.o $(OUTPUT)/xstack.skel.h $(OUTPUT)/xstack.bpf.o

$(OUTPUT) $(OUTPUT)/libbpf $(BPFTOOL_OUTPUT):
	$(call msg,MKDIR,$@)
	$(Q)mkdir -p $@

# Build libbpf
$(LIBBPF_OBJ): $(wildcard $(LIBBPF_SRC)/*.[ch] $(LIBBPF_SRC)/Makefile) | $(OUTPUT)/libbpf
	$(call msg,LIB,$@)
	$(Q)$(MAKE) -C $(LIBBPF_SRC) BUILD_STATIC_ONLY=1 \
		    OBJDIR=$(dir $@)/libbpf DESTDIR=$(dir $@) \
		    INCLUDEDIR= LIBDIR= UAPIDIR= \
		    install

# Build bpftool
$(BPFTOOL): | $(BPFTOOL_OUTPUT)
	$(call msg,BPFTOOL,$@)
	$(Q)$(MAKE) ARCH= CROSS_COMPILE= OUTPUT=$(BPFTOOL_OUTPUT)/ -C $(BPFTOOL_SRC) bootstrap

# Build BlazeSym if enabled
ifeq ($(USE_BLAZESYM),1)
$(LIBBLAZESYM_SRC)/target/release/libblazesym_c.a:
	$(call msg,CARGO,$@)
	$(Q)cd $(LIBBLAZESYM_SRC) && cargo build --package=blazesym-c --release

$(LIBBLAZESYM_OBJ): $(LIBBLAZESYM_SRC)/target/release/libblazesym_c.a | $(OUTPUT)
	$(call msg,LIB,$@)
	$(Q)cp $(LIBBLAZESYM_SRC)/target/release/libblazesym_c.a $@
endif

# Build BPF code
$(OUTPUT)/%.bpf.o: %.bpf.c $(LIBBPF_OBJ) $(wildcard %.h) $(VMLINUX) | $(OUTPUT)
	$(call msg,BPF,$@)
	$(Q)$(CLANG) -g -O2 -target bpf -D__TARGET_ARCH_$(ARCH) \
		     $(INCLUDES) $(CLANG_BPF_SYS_INCLUDES) \
		     -c $(filter %.c,$^) -o $@
	$(Q)$(LLVM_STRIP) -g $@ # strip useless DWARF info

# Generate BPF skeletons
$(OUTPUT)/%.skel.h: $(OUTPUT)/%.bpf.o | $(OUTPUT) $(BPFTOOL)
	$(call msg,GEN-SKEL,$@)
	$(Q)$(BPFTOOL) gen skeleton $< > $@

# Build user-space code (depends on skeleton)
$(OUTPUT)/xstack.o: xstack.c $(OUTPUT)/xstack.skel.h $(wildcard *.h) | $(OUTPUT)
	$(call msg,CC,$@)
	$(Q)$(CC) $(CFLAGS) $(INCLUDES) -c xstack.c -o $@

# Build application binary
xstack: $(OUTPUT)/xstack.o $(LIBBPF_OBJ) $(BLAZESYM_DEP)
	$(call msg,BINARY,$@)
	$(Q)$(CC) $(CFLAGS) $< $(LIBBPF_OBJ) $(ALL_LDFLAGS) -lelf -lz -o $@

# Keep intermediate files
.SECONDARY:

# Help target
help:
	@echo "Usage: make [target]"
	@echo ""
	@echo "Targets:"
	@echo "  all       - Build xstack (default)"
	@echo "  clean     - Remove all built files"
	@echo "  cleanx    - Remove only xstack binary (fast rebuild)"
	@echo "  help      - Show this help message"
	@echo ""
	@echo "Options:"
	@echo "  V=1              - Verbose build"
	@echo "  USE_BLAZESYM=0   - Build without blazesym support (default: 1)"
