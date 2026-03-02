cmake_minimum_required(VERSION 3.16)

project(xcapture VERSION 0.1.0 LANGUAGES C)

include(GNUInstallDirs)
include(CheckCSourceCompiles)

set(CMAKE_INSTALL_SYSCONFDIR "/etc" CACHE PATH "System configuration directory" FORCE)

set(XCAPTURE_HOST_PROCESSOR "${CMAKE_HOST_SYSTEM_PROCESSOR}")

set(XCAPTURE_RUST_TARGET "")

option(USE_BLAZESYM "Enable BlazeSym support" ON)
option(OLD_KERNEL_SUPPORT "Enable legacy kernel compatibility mode" OFF)

find_program(CLANG_EXECUTABLE clang REQUIRED)
find_program(MAKE_EXECUTABLE make REQUIRED)
find_program(BASH_EXECUTABLE bash REQUIRED)

if(USE_BLAZESYM)
    find_program(CARGO_EXECUTABLE cargo REQUIRED)
endif()

set(LIBBPF_BOOTSTRAP_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../libbpf-bootstrap")
set(LIBBPF_SRC "${LIBBPF_BOOTSTRAP_DIR}/libbpf/src")
set(BPFTOOL_SRC "${LIBBPF_BOOTSTRAP_DIR}/bpftool/src")
set(BLAZESYM_SRC "${LIBBPF_BOOTSTRAP_DIR}/blazesym")
set(XTOOLS_INC "${CMAKE_CURRENT_SOURCE_DIR}/../../include")
set(BOOTSTRAP_BUILD_DIR "${CMAKE_BINARY_DIR}/bootstrap")
set(GENERATED_SOURCE_DIR "${CMAKE_BINARY_DIR}/generated")

file(MAKE_DIRECTORY "${BOOTSTRAP_BUILD_DIR}")
file(MAKE_DIRECTORY "${GENERATED_SOURCE_DIR}")
file(MAKE_DIRECTORY "${CMAKE_BINARY_DIR}/_rpmtmp")

set(_bpf_uapi_dir "${LIBBPF_BOOTSTRAP_DIR}/libbpf/include/uapi")
set(_saved_required_includes "${CMAKE_REQUIRED_INCLUDES}")
list(APPEND CMAKE_REQUIRED_INCLUDES "${_bpf_uapi_dir}")
check_c_source_compiles(
"#include <linux/bpf.h>
int main(void) {
    union bpf_iter_link_info info = {0};
    info.task.tid = 0;
    info.task.pid = 0;
    return info.task.pid;
}"
HAVE_BPF_ITER_TASK_LINK_INFO)
set(CMAKE_REQUIRED_INCLUDES "${_saved_required_includes}")

if(HAVE_BPF_ITER_TASK_LINK_INFO)
    add_compile_definitions(HAVE_BPF_ITER_TASK_LINK_INFO)
else()
    message(STATUS "Kernel headers lack bpf_iter task link info; falling back to userspace TGID filtering")
endif()
if(OLD_KERNEL_SUPPORT)
    add_compile_definitions(OLD_KERNEL_SUPPORT)
endif()

# Architecture mapping for BPF target
string(TOLOWER "${CMAKE_SYSTEM_PROCESSOR}" ARCH_LOWER)
if(ARCH_LOWER STREQUAL "x86_64")
    set(BPF_TARGET_ARCH x86)
    set(XCAPTURE_RUST_TARGET "x86_64-unknown-linux-gnu")
elseif(ARCH_LOWER MATCHES "armv7" OR ARCH_LOWER STREQUAL "arm")
    set(BPF_TARGET_ARCH arm)
elseif(ARCH_LOWER STREQUAL "aarch64")
    set(BPF_TARGET_ARCH arm64)
    set(XCAPTURE_RUST_TARGET "aarch64-unknown-linux-gnu")
elseif(ARCH_LOWER STREQUAL "ppc64le")
    set(BPF_TARGET_ARCH powerpc)
elseif(ARCH_LOWER STREQUAL "mips64")
    set(BPF_TARGET_ARCH mips)
elseif(ARCH_LOWER STREQUAL "riscv64")
    set(BPF_TARGET_ARCH riscv)
elseif(ARCH_LOWER STREQUAL "loongarch64")
    set(BPF_TARGET_ARCH loongarch)
else()
    message(FATAL_ERROR "Unsupported architecture ${CMAKE_SYSTEM_PROCESSOR} for BPF target")
endif()

set(VMLINUX_HEADER "${CMAKE_CURRENT_SOURCE_DIR}/../libbpf-bootstrap/vmlinux.h/include/${BPF_TARGET_ARCH}/vmlinux.h")
if(NOT EXISTS "${VMLINUX_HEADER}")
    message(FATAL_ERROR "Missing vmlinux.h for architecture ${BPF_TARGET_ARCH} at ${VMLINUX_HEADER}")
endif()

# Build libbpf static library
set(LIBBPF_OUTPUT "${BOOTSTRAP_BUILD_DIR}/libbpf/libbpf.a")
set(LIBBPF_INSTALL_ROOT "${BOOTSTRAP_BUILD_DIR}/libbpf-install")
set(LIBBPF_BUILD_ENV CC=${CMAKE_C_COMPILER})
if(CMAKE_AR)
    list(APPEND LIBBPF_BUILD_ENV AR=${CMAKE_AR})
endif()
if(CMAKE_RANLIB)
    list(APPEND LIBBPF_BUILD_ENV RANLIB=${CMAKE_RANLIB})
endif()
if(CMAKE_LINKER)
    list(APPEND LIBBPF_BUILD_ENV LD=${CMAKE_LINKER})
endif()
if(CMAKE_NM)
    list(APPEND LIBBPF_BUILD_ENV NM=${CMAKE_NM})
endif()
if(CMAKE_OBJCOPY)
    list(APPEND LIBBPF_BUILD_ENV OBJCOPY=${CMAKE_OBJCOPY})
endif()
if(CMAKE_OBJDUMP)
    list(APPEND LIBBPF_BUILD_ENV OBJDUMP=${CMAKE_OBJDUMP})
endif()

add_custom_command(
    OUTPUT "${LIBBPF_OUTPUT}"
    COMMAND ${CMAKE_COMMAND} -E remove_directory "${LIBBPF_INSTALL_ROOT}"
    COMMAND ${CMAKE_COMMAND} -E make_directory "${LIBBPF_INSTALL_ROOT}"
    COMMAND ${CMAKE_COMMAND} -E make_directory "${BOOTSTRAP_BUILD_DIR}/libbpf"
    COMMAND ${CMAKE_COMMAND} -E env ${LIBBPF_BUILD_ENV} ${MAKE_EXECUTABLE}
            -C "${LIBBPF_SRC}"
            BUILD_STATIC_ONLY=1
            OBJDIR=${BOOTSTRAP_BUILD_DIR}/libbpf
            DESTDIR=${LIBBPF_INSTALL_ROOT}
            INCLUDEDIR=/include
            LIBDIR=/lib
            UAPIDIR=/include/uapi
            install
    COMMAND ${CMAKE_COMMAND} -E copy "${LIBBPF_INSTALL_ROOT}/lib/libbpf.a" "${LIBBPF_OUTPUT}"
    COMMAND ${CMAKE_COMMAND} -E remove_directory "${BOOTSTRAP_BUILD_DIR}/libbpf/include"
    COMMAND ${CMAKE_COMMAND} -E make_directory "${BOOTSTRAP_BUILD_DIR}/libbpf/include"
    COMMAND ${CMAKE_COMMAND} -E copy_directory "${LIBBPF_INSTALL_ROOT}/include" "${BOOTSTRAP_BUILD_DIR}/libbpf/include"
    DEPENDS ${LIBBPF_SRC}/Makefile
    COMMENT "Building libbpf"
    VERBATIM)
add_custom_target(libbpf_target DEPENDS "${LIBBPF_OUTPUT}")

# Build bpftool bootstrap binary
set(BPFTOOL_OUTPUT "${BOOTSTRAP_BUILD_DIR}/bpftool/bootstrap/bpftool")
add_custom_command(
    OUTPUT "${BPFTOOL_OUTPUT}"
    COMMAND ${CMAKE_COMMAND} -E make_directory "${BOOTSTRAP_BUILD_DIR}/bpftool"
    COMMAND ${MAKE_EXECUTABLE}
            ARCH=
            OUTPUT=${BOOTSTRAP_BUILD_DIR}/bpftool/
            -C "${BPFTOOL_SRC}" bootstrap
    DEPENDS ${BPFTOOL_SRC}/Makefile
    COMMENT "Building bpftool bootstrap binary"
    VERBATIM)
add_custom_target(bpftool_target DEPENDS "${BPFTOOL_OUTPUT}")

# Build BlazeSym static library when enabled
if(USE_BLAZESYM)
    set(BLAZESYM_OUTPUT "${BOOTSTRAP_BUILD_DIR}/blazesym/libblazesym_c.a")
    if(XCAPTURE_RUST_TARGET)
        string(REPLACE "-" "_" _rust_env_key "${XCAPTURE_RUST_TARGET}")
        string(TOUPPER "${_rust_env_key}" _rust_env_key)
        set(BLAZESYM_ENV CC_${_rust_env_key}=${CMAKE_C_COMPILER} CARGO_TARGET_${_rust_env_key}_LINKER=${CMAKE_C_COMPILER})
        if(CMAKE_AR)
            list(APPEND BLAZESYM_ENV AR=${CMAKE_AR} CARGO_TARGET_${_rust_env_key}_AR=${CMAKE_AR})
        endif()
        set(BLAZESYM_TARGET_LIB "${BOOTSTRAP_BUILD_DIR}/blazesym/target/${XCAPTURE_RUST_TARGET}/release/libblazesym_c.a")
    else()
        set(BLAZESYM_ENV)
        if(CMAKE_AR)
            list(APPEND BLAZESYM_ENV AR=${CMAKE_AR})
        endif()
        set(BLAZESYM_TARGET_LIB "${BOOTSTRAP_BUILD_DIR}/blazesym/target/release/libblazesym_c.a")
    endif()
    set(BLAZESYM_BUILD_CMD ${CARGO_EXECUTABLE} build --package=blazesym-c --release)
    if(XCAPTURE_RUST_TARGET)
        list(APPEND BLAZESYM_BUILD_CMD --target=${XCAPTURE_RUST_TARGET})
    endif()
    add_custom_command(
        OUTPUT "${BLAZESYM_OUTPUT}"
        COMMAND ${CMAKE_COMMAND} -E make_directory "${BOOTSTRAP_BUILD_DIR}/blazesym"
        COMMAND ${CMAKE_COMMAND} -E env CARGO_TARGET_DIR=${BOOTSTRAP_BUILD_DIR}/blazesym/target ${BLAZESYM_ENV} ${BLAZESYM_BUILD_CMD}
        COMMAND ${CMAKE_COMMAND} -E copy "${BLAZESYM_TARGET_LIB}" "${BLAZESYM_OUTPUT}"
        WORKING_DIRECTORY "${BLAZESYM_SRC}"
        DEPENDS "${BLAZESYM_SRC}/Cargo.toml"
        COMMENT "Building BlazeSym"
        VERBATIM)
    add_custom_target(blazesym_target DEPENDS "${BLAZESYM_OUTPUT}")
endif()

set(BPF_INCLUDE_DIRS
    "${BOOTSTRAP_BUILD_DIR}/libbpf/include"
    "${BOOTSTRAP_BUILD_DIR}/libbpf/include/uapi"
    "${LIBBPF_BOOTSTRAP_DIR}/libbpf/include"
    "${LIBBPF_BOOTSTRAP_DIR}/libbpf/include/uapi"
    "${LIBBPF_BOOTSTRAP_DIR}/vmlinux.h/include/${BPF_TARGET_ARCH}"
    "${CMAKE_CURRENT_SOURCE_DIR}/include"
    "${CMAKE_CURRENT_SOURCE_DIR}/src"
    "${CMAKE_CURRENT_SOURCE_DIR}/src/probes"
    "${CMAKE_CURRENT_SOURCE_DIR}/src/maps"
    "${CMAKE_CURRENT_SOURCE_DIR}/src/utils"
    "${CMAKE_CURRENT_SOURCE_DIR}/src/helpers"
    "${XTOOLS_INC}"
)
set(BPF_CLANG_FLAGS)
foreach(dir IN LISTS BPF_INCLUDE_DIRS)
    list(APPEND BPF_CLANG_FLAGS "-I${dir}")
endforeach()
if(OLD_KERNEL_SUPPORT)
    list(APPEND BPF_CLANG_FLAGS "-DOLD_KERNEL_SUPPORT")
endif()

# Add the clang resource include directory to the search list
execute_process(
    COMMAND ${CLANG_EXECUTABLE} -print-resource-dir
    OUTPUT_VARIABLE CLANG_RESOURCE_DIR
    OUTPUT_STRIP_TRAILING_WHITESPACE
)
if(CLANG_RESOURCE_DIR)
    list(APPEND BPF_CLANG_FLAGS "-idirafter" "${CLANG_RESOURCE_DIR}/include")
endif()
list(APPEND BPF_CLANG_FLAGS "-idirafter" "/usr/include")

set(BPF_COMMON_DEPS
    "${CMAKE_CURRENT_SOURCE_DIR}/include/xcapture.h"
    "${CMAKE_CURRENT_SOURCE_DIR}/src/maps/xcapture_maps_common.h"
    "${CMAKE_CURRENT_SOURCE_DIR}/src/maps/xcapture_maps_iorq_classic.h"
    "${CMAKE_CURRENT_SOURCE_DIR}/src/utils/xcapture_helpers.h"
    "${CMAKE_CURRENT_SOURCE_DIR}/src/helpers/file_helpers.h"
    "${CMAKE_CURRENT_SOURCE_DIR}/src/helpers/fd_helpers.h"
    "${CMAKE_CURRENT_SOURCE_DIR}/src/helpers/io_helpers.h"
    "${CMAKE_CURRENT_SOURCE_DIR}/src/helpers/tcp_helpers_simple.h"
)

function(build_bpf NAME SUBDIR SRC)
    set(OUTPUT_DIR "${GENERATED_SOURCE_DIR}/src/probes/${SUBDIR}")
    set(TMP_OBJ "${OUTPUT_DIR}/${NAME}.tmp.bpf.o")
    set(FINAL_OBJ "${OUTPUT_DIR}/${NAME}.bpf.o")
    set(SKEL_HEADER "${OUTPUT_DIR}/${NAME}.skel.h")
    add_custom_command(
        OUTPUT "${FINAL_OBJ}" "${SKEL_HEADER}"
        COMMAND ${CMAKE_COMMAND} -E make_directory "${OUTPUT_DIR}"
        COMMAND ${CLANG_EXECUTABLE} -target bpf -g -O2 -D__TARGET_ARCH_${BPF_TARGET_ARCH}
                ${BPF_CLANG_FLAGS}
                -c "${CMAKE_CURRENT_SOURCE_DIR}/${SRC}" -o "${TMP_OBJ}"
        COMMAND ${BPFTOOL_OUTPUT} gen object "${FINAL_OBJ}" "${TMP_OBJ}"
        COMMAND ${BASH_EXECUTABLE} -lc "'${BPFTOOL_OUTPUT}' gen skeleton '${FINAL_OBJ}' > '${SKEL_HEADER}'"
        DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/${SRC}" ${BPF_COMMON_DEPS} "${LIBBPF_OUTPUT}" "${BPFTOOL_OUTPUT}" "${VMLINUX_HEADER}"
        COMMENT "Building ${NAME} BPF program"
        VERBATIM)
    set(${NAME}_BPF_OBJECT "${FINAL_OBJ}" PARENT_SCOPE)
    set(${NAME}_BPF_SKEL "${SKEL_HEADER}" PARENT_SCOPE)
endfunction()

build_bpf(task task "src/probes/task/task.bpf.c")
set(TASK_BPF_SKEL "${task_BPF_SKEL}")

build_bpf(syscall syscall "src/probes/syscall/syscall.bpf.c")
set(SYSCALL_BPF_SKEL "${syscall_BPF_SKEL}")

build_bpf(iorq io "src/probes/io/iorq_hashmap.bpf.c")
set(IORQ_BPF_SKEL "${iorq_BPF_SKEL}")

add_custom_target(bpf_skeletons
    DEPENDS "${TASK_BPF_SKEL}" "${SYSCALL_BPF_SKEL}" "${IORQ_BPF_SKEL}")

add_executable(xcapture
    src/user/main.c
    src/user/task_handler.c
    src/user/tracking_handler.c
    src/user/socket_info.c
    src/user/syscall_info.c
    src/user/iorq_info.c
    src/user/columns.c
    src/user/cgroup_cache.c
    src/user/output_writer.c
)

add_dependencies(xcapture libbpf_target bpftool_target bpf_skeletons)
if(USE_BLAZESYM)
    add_dependencies(xcapture blazesym_target)
endif()

set(USERSPACE_INCLUDE_DIRS
    "${CMAKE_CURRENT_SOURCE_DIR}/include"
    "${CMAKE_CURRENT_SOURCE_DIR}/src"
    "${CMAKE_CURRENT_SOURCE_DIR}/src/user"
    "${GENERATED_SOURCE_DIR}/src/probes"
    "${XTOOLS_INC}"
    "${BOOTSTRAP_BUILD_DIR}/libbpf/include"
    "${LIBBPF_BOOTSTRAP_DIR}/libbpf/include"
    "${LIBBPF_BOOTSTRAP_DIR}/libbpf/include/uapi"
)
if(USE_BLAZESYM)
    list(APPEND USERSPACE_INCLUDE_DIRS "${BLAZESYM_SRC}/capi/include")
endif()

target_include_directories(xcapture PRIVATE ${USERSPACE_INCLUDE_DIRS})

target_compile_definitions(xcapture PRIVATE __TARGET_ARCH_${BPF_TARGET_ARCH})
if(USE_BLAZESYM)
    target_compile_definitions(xcapture PRIVATE USE_BLAZESYM)
endif()
if(OLD_KERNEL_SUPPORT)
    target_compile_definitions(xcapture PRIVATE OLD_KERNEL_SUPPORT)
endif()

target_compile_features(xcapture PRIVATE c_std_99)

target_compile_options(xcapture PRIVATE -Wall -Wextra -g)

target_link_directories(xcapture PRIVATE "${BOOTSTRAP_BUILD_DIR}/libbpf")

target_link_libraries(xcapture PRIVATE "${LIBBPF_OUTPUT}" elf z pthread dl rt m)
if(USE_BLAZESYM)
    target_link_libraries(xcapture PRIVATE "${BLAZESYM_OUTPUT}")
endif()

# Installation rules
install(TARGETS xcapture RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR})

configure_file(packaging/systemd/xcapture.service.in "${CMAKE_CURRENT_BINARY_DIR}/xcapture.service" @ONLY)

set(SYSTEMD_UNIT_DIR "" CACHE STRING "systemd unit directory (relative to CMAKE_INSTALL_PREFIX)")
if(SYSTEMD_UNIT_DIR STREQUAL "")
    if(EXISTS "/usr/lib/systemd/system")
        set(SYSTEMD_UNIT_DIR "lib/systemd/system")
    else()
        set(SYSTEMD_UNIT_DIR "usr/lib/systemd/system")
    endif()
endif()

install(FILES "${CMAKE_CURRENT_BINARY_DIR}/xcapture.service"
        DESTINATION "${SYSTEMD_UNIT_DIR}")

install(FILES packaging/tmpfiles.d/xcapture.conf
        DESTINATION "lib/tmpfiles.d")

install(FILES packaging/etc/xcapture.conf
        DESTINATION ${CMAKE_INSTALL_SYSCONFDIR}
        RENAME xcapture.conf.example)

# CPack configuration
set(CPACK_GENERATOR "DEB;RPM")
set(CPACK_PACKAGE_NAME "xcapture")
set(CPACK_PACKAGE_VENDOR "0xtools")
set(CPACK_PACKAGE_CONTACT "support@0xtools.io")
set(CPACK_PACKAGE_DESCRIPTION_SUMMARY "High-performance Linux system monitor built on eBPF")
set(CPACK_PACKAGE_VERSION ${PROJECT_VERSION})
set(CPACK_DEBIAN_PACKAGE_MAINTAINER "0xtools")
set(CPACK_DEBIAN_PACKAGE_DEPENDS "libelf1, zlib1g, libcap2-bin, systemd")
set(CPACK_DEBIAN_PACKAGE_CONTROL_EXTRA
    "${CMAKE_CURRENT_SOURCE_DIR}/packaging/scripts/postinst;${CMAKE_CURRENT_SOURCE_DIR}/packaging/scripts/postrm;${CMAKE_CURRENT_SOURCE_DIR}/packaging/scripts/conffiles")
set(CPACK_RPM_PACKAGE_REQUIRES "libelf, zlib, libcap, systemd")
set(CPACK_RPM_POST_INSTALL_SCRIPT_FILE "${CMAKE_CURRENT_SOURCE_DIR}/packaging/scripts/postinst")
set(CPACK_RPM_POST_UNINSTALL_SCRIPT_FILE "${CMAKE_CURRENT_SOURCE_DIR}/packaging/scripts/postrm")
set(CPACK_RPM_PACKAGE_LICENSE "MIT")
set(CPACK_RPM_PACKAGE_GROUP "System Environment/Base")
set(CPACK_RPM_PACKAGE_URL "https://github.com/0xtools/0xtools-next")
set(CPACK_RPM_PACKAGE_DESCRIPTION "xcapture is a high-performance Linux system monitor that uses eBPF to sample tasks and track syscalls and I/O events.")
set(CPACK_RPM_PACKAGE_SUMMARY "High-performance Linux system monitor")
set(CPACK_RPM_PACKAGE_CONFIG_FILES "/etc/xcapture.conf")
set(CPACK_RPM_SPEC_MORE_DEFINE "%define _tmppath ${CMAKE_BINARY_DIR}/_rpmtmp")

set(_pkg_arch "${CMAKE_SYSTEM_PROCESSOR}")
if(CMAKE_SYSTEM_PROCESSOR STREQUAL "x86_64")
    set(CPACK_DEBIAN_PACKAGE_ARCHITECTURE "amd64")
    set(CPACK_RPM_PACKAGE_ARCHITECTURE "x86_64")
    set(_pkg_arch "amd64")
elseif(CMAKE_SYSTEM_PROCESSOR STREQUAL "aarch64")
    set(CPACK_DEBIAN_PACKAGE_ARCHITECTURE "arm64")
    set(CPACK_RPM_PACKAGE_ARCHITECTURE "aarch64")
    set(_pkg_arch "arm64")
endif()

set(CPACK_PACKAGE_FILE_NAME "${CPACK_PACKAGE_NAME}-${CPACK_PACKAGE_VERSION}-${_pkg_arch}")

include(CPack)
