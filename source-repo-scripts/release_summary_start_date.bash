#!/usr/bin/env bash

set -e

# Print a markdown summary of a release (not Changelog.md entries), with its
# changelog and contributors. The script is designed to publish release summaries
# from the internal Open Robotics team to the Community (usually in the public forum).
#
# cd <path_to_source_code>
# bash release_summary.bash <date since last release>

START_DATE=$1

function debugecho() {
  echo "$@" 1>&2;
}

if [[ ! -f CMakeLists.txt  ]]; then
  echo "No CMakeLists.txt detected. Are you in an source repository?"
  exit 1
fi

# Get lib name from CMakeLists project ()
#LIB=$(sed -n 's/^project[[:space:]]*(\(ignition-\|gz-\)\?\([a-Z|_]*\)[0-9]*.*)/\2/p' CMakeLists.txt)
LIB=$(sed -n 's/^project[[:space:]]*(\([a-Z|_-]*[0-9]*\).*)/\1/p' CMakeLists.txt)
if [ -z "${LIB}" ]; then
  echo "Parsing of CMakeLists.txt project tag failed"
  echo "Probably an internal bug"
  exit 1
fi

git fetch --all --tags > /dev/null

TAGS=$(git log --no-walk --tags --pretty="%(describe:tags=true)" --since=$START_DATE | sort -r -V -t'_' -k2 )

for tag in $TAGS
do
  VERSION=${tag/*_}
  NEW=$VERSION

  MAJOR=${VERSION/%.*}
  LIB=${tag%_*}
  LIB_WITHOUT_VERSION=${LIB/[0-9]*/}
  debugecho  "---------------------------------"
  debugecho "VERSION: $VERSION"
  PREV_TAG=$(git log --no-walk=sorted --tags=$LIB* --pretty="%(describe:tags=true)" --until=$START_DATE | head -n1)
  PREV=${PREV_TAG/*_}
  debugecho "PREV VERSION: $PREV"

  NAME_FOR_TAGS=${LIB_WITHOUT_VERSION/_/-}
  debugecho  "NAME_FOR_TAGS: $NAME_FOR_TAGS"


  NAME_FOR_REPO=${NAME_FOR_TAGS/ignition/ign}
  NAME_FOR_REPO="${NAME_FOR_REPO/gazebo/sim}"
  debugecho  "NAME_FOR_REPO: $NAME_FOR_REPO"

  NAME_FOR_BRANCH=${NAME_FOR_TAGS/ignition/ign}
  NAME_FOR_BRANCH=${NAME_FOR_BRANCH/sdformat/sdf}
  debugecho  "NAME_FOR_BRANCH: $NAME_FOR_BRANCH"

  LIB_WITHOUT_PREFIX=${LIB_WITHOUT_VERSION/[a-z]*-/}
  NAME_FOR_TITLE="Gazebo ${LIB_WITHOUT_PREFIX^}"
  NAME_FOR_TITLE="${NAME_FOR_TITLE/Fuel_tools/Fuel Tools}"
  NAME_FOR_TITLE="${NAME_FOR_TITLE/Gazebo Sdformat/SDFormat}"
  NAME_FOR_TITLE="${NAME_FOR_TITLE/Gazebo Gazebo/Gazebo Sim}"
  debugecho  "NAME_FOR_TITLE: $NAME_FOR_TITLE"


  #if ! git checkout "${NAME_FOR_BRANCH}${MAJOR}"; then
  #  echo "Branch ${NAME_FOR_BRANCH}${MAJOR} was not found in the repository"
  #  exit 1
  #fi

  #git pull origin ${NAME_FOR_BRANCH}${MAJOR}

  echo ""
  echo ""
  echo ""
  echo ""
  echo "## $NAME_FOR_TITLE $VERSION"
  echo ""
  echo "## Changelog"
  echo ""
  echo "[Full changelog](https://github.com/gazebosim/${NAME_FOR_REPO}/blob/${NAME_FOR_BRANCH}${MAJOR}/Changelog.md)"
  echo ""
  #awk '/${NEW}/{ f = 1; next } /${PREV}/{ f = 0 } f' Changelog.md
  git show ${NAME_FOR_TAGS}${MAJOR}_${NEW}:Changelog.md | sed -n "/${NEW}/, /${PREV}/{ /${NEW}/! { /${PREV}/! p } }"
  echo ""
  echo "## Contributors"
  echo ""
  git log --pretty="%an" ${NAME_FOR_TAGS}${MAJOR}_${PREV}...${NAME_FOR_TAGS}${MAJOR}_${NEW} | sort | uniq | sed "s/.*/\*&\*/"
  echo ""
  echo "---"

done
exit 1
