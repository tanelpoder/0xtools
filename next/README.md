## xcapture (and xtop) v3

Highly WIP dev area for libbpf and moden eBPF-based xcapture tool.

## building

Make sure you cd to the `next` directory.

```
cd next
```

To install required libbpf dependencies, run:

```
git submodule update --init --recursive
```

## running

```
cd src
make
sudo ./xcapture
```
