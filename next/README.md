## xcapture (and xtop) v3

Ready for 3.0.0-alpha release prep


## building

Make sure you cd to the `next` directory.

```
cd next
```

To install the system packages (on Ubuntu 24.04) for compiling the binary, run:

```
sudo apt install make gcc pkg-config libbpf-dev libbpf-tools clang llvm libbfd-dev libelf1 libelf-dev zlib1g-dev
```

On RHEL9:

```
sudo dnf install libbpf libbpf-tools clang llvm-devel binutils-devel elfutils-libelf elfutils-libelf-devel zlib-devel

```


To install required libbpf dependencies for the GitHub repo, run:

```
git submodule update --init --recursive
```

## running

```
cd xcapture
make
sudo ./xcapture
```

You can also run `./xcapture --help` to get some idea of its current functionality.
