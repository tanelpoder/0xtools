## xcapture (and xtop) v3

Highly WIP dev area for libbpf and moden eBPF-based xcapture tool.

## building

Make sure you cd to the `next` directory.

```
cd next
```

To install the system packages (on Ubuntu 24.04) for compiling the binary, run:

```
sudo apt install libbpf-dev libbpf-tools clang llvm libbfd-dev libelf1 libelf-dev zlib1g-dev
```

On RHEL9:

```
sudo dnf install libbpf libbpf-tools clang elfutils-libelf elfutils-libelf-devel zlib-devel

```


To install required libbpf dependencies for the GitHub repo, run:

```
git submodule update --init --recursive
```

## running

```
cd src
make
sudo ./xcapture
```
