#!/bin/bash -x
set -e

[[ -L ${0} ]] && SCRIPT_LIBDIR=$(readlink ${0}) || SCRIPT_LIBDIR=${0}
SCRIPT_LIBDIR="${SCRIPT_LIBDIR%/*}"

export PATH="/usr/local/bin:$PATH"

PKG_DIR=${WORKSPACE}/pkgs

echo '# BEGIN SECTION: check variables'
if [ -z "${PULL_REQUEST_URL}" ]; then
    echo PULL_REQUEST_URL not specified
    exit -1
fi
echo '# END SECTION'

echo '# BEGIN SECTION: clean up environment'
rm -fr ${PKG_DIR} && mkdir -p ${PKG_DIR}
. ${SCRIPT_LIBDIR}/_homebrew_cleanup.bash
echo '# END SECTION'

echo '# BEGIN SECTION: run test-bot'
# return always true since audit fails to run gzserver
# can not find a way of disabling it
bash -c "brew test-bot             \
    --tap=osrf/simulation \
    --bottle              \
    --ci-pr               \
    --verbose ${PULL_REQUEST_URL}" || true
echo '# END SECTION'

echo '# BEGIN SECTION: export bottle'
if [[ $(find . -name *.bottle.*) | wc -l -lt 2 ]]; then
 echo "Can not find the two bottle files"
 exit -1
fi
mv *.bottle.tar.gz ${PKG_DIR}
mv *.bottle.rb ${PKG_DIR}
echo '# END SECTION'
