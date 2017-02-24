#!/bin/bash -x

# Knowing Script dir beware of symlink
[[ -L ${0} ]] && SCRIPT_DIR=$(readlink ${0}) || SCRIPT_DIR=${0}
SCRIPT_DIR="${SCRIPT_DIR%/*}"

export GPU_SUPPORT_NEEDED=true

INSTALL_JOB_PREINSTALL_HOOK="""
# import the SRC repo
echo \"deb http://srcsim.gazebosim.org/src ${DISTRO} main\" >\\
                                           /etc/apt/sources.list.d/src.list
apt-key adv --keyserver ha.pool.sks-keyservers.net --recv-keys D2486D2DD83DB69272AFE98867170598AF249743
wget -qO - http://srcsim.gazebosim.org/src/src.key | sudo apt-key add -
sudo apt-get update
"""

INSTALL_JOB_POSTINSTALL_HOOK="""
echo '# BEGIN SECTION: testing by running qual1 launch file'
update-alternatives --set java /usr/lib/jvm/java-8-openjdk-amd64/jre/bin/java
mkdir -p ~/.gazebo/models
mkdir ~/valkyrie
wget -O /tmp/control.tar.gz http://models.gazebosim.org/control_console/model.tar.gz && tar xvf /tmp/control.tar.gz -C ~/.gazebo/models

. /opt/ros/indigo/setup.bash
. /opt/nasa/indigo/setup.bash

TEST_START=\`date +%s\`
timeout --preserve-status 400 roslaunch srcsim qual1.launch extra_gazebo_args:=\"-r\" init:=\"true\" || true
TEST_END=\`date +%s\`
DIFF=\`echo \"\$TEST_END - \$TEST_START\" | bc\`

if [ \$DIFF -lt 400 ]; then
   echo 'The test took less than 400s. Something bad happened'
   exit 1
fi
echo '# END SECTION'
"""
# Need bc to proper testing and parsing the time
export DEPENDENCY_PKGS DEPENDENCY_PKGS="wget bc"

. ${SCRIPT_DIR}/lib/generic-install-base.bash
