#!/bin/bash -x

# Knowing Script dir beware of symlink
[[ -L ${0} ]] && SCRIPT_DIR=$(readlink ${0}) || SCRIPT_DIR=${0}
SCRIPT_DIR="${SCRIPT_DIR%/*}"

if [[ -z ${ARCH} ]]; then
  echo "ARCH variable not set!"
  exit 1
fi

if [[ -z ${DISTRO} ]]; then
  echo "DISTRO variable not set!"
  exit 1
fi

. ${SCRIPT_DIR}/lib/_gazebo_version_hook.bash

export ABI_JOB_SOFTWARE_NAME="gazebo"
export ABI_JOB_REPOS="stable"
if ${NEED_PRERELEASE}; then
  ABI_JOB_REPOS="${ABI_JOB_REPOS} prerelease"
fi
export ABI_JOB_PKG_DEPENDENCIES_VAR_NAME="GAZEBO_BASE_DEPENDECIES"

. ${SCRIPT_DIR}/lib/generic-abi-base.bash
