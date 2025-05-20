#!/bin/bash

PROJECT_NAME="0xtools"

if [ 0 -eq $# ]; then
	echo ""
	echo "    Usage: ./release.sh tag_or_commitid [tag_or_commitid...]"
	echo ""
	exit 1
fi

for name in "$@"; do
	target_type=$(git cat-file -t "${name}" 2>/dev/null)
	if [[ -z "${target_type}" ]]; then
		echo "${name} is invalid, ignored."
		continue
	fi

	suffix=""
	if expr "${target_type}" : "^commit" >/dev/null; then
		suffix=$(git rev-parse --short=8 "${name}")
	elif expr "${target_type}" : "^tag" >/dev/null; then
		suffix="${name}"
	else
		echo "${name} is neither a commit nor a tag!"
		continue
	fi
	target_name="${PROJECT_NAME}-${suffix}"
	echo "archiving ${target_name}"
	git archive -9 --format=tar.gz --prefix="${target_name}"/ "${name}" >"${target_name}".tar.gz
	echo "finish ${target_name}"
done
