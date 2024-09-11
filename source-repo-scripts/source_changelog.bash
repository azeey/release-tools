#!/bin/bash
# Generates a list of changes since the last tagged version. 
#   bash source_changelog.bash
#
# Optionally, the previous version can be provided
# bash source_changelog.bash <PREV_VER>
#
#   E.g.
#   bash source_changelog.bash 3.0.0


usage() {
  echo "Usage: $0 [-h][-M][-m][-p] [from_version]" 1>&2
  echo "-M   Bump major version" 1>&2
  echo "-m   Bump minor version" 1>&2
  echo "-p   Bump patch version" 1>&2
  exit 1
}

while getopts "hMmp" arg; do
  case "$arg" in
    M) # Bump major
      bump_major=true
      ;;
    m) # Bump minor
      bump_minor=true
      ;;
    p) # Bump patch
      bump_patch=true
      ;;
    h | *)
      usage
      exit 0
      ;;
  esac
done

shift $((OPTIND - 1))

git fetch --tags

PREV_VER=${1:-$(git describe --tags --abbrev=0 | sed 's/.*_//')}
echo "Changes since $PREV_VER"
echo

declare -A repo_names=(
  ["gz-cmake"]="Gazebo CMake"
  ["gz-utils"]="Gazebo Utils"
  ["gz-tools"]="Gazebo Tools"
  ["gz-math"]="Gazebo Math"
  ["gz-plugin"]="Gazebo Plugin"
  ["gz-common"]="Gazebo Common"
  ["gz-msgs"]="Gazebo Msgs"
  ["sdformat"]="libsdformat"
  ["gz-fuel-tools"]="Gazebo Fuel Tools"
  ["gz-transport"]="Gazebo Transport"
  ["gz-physics"]="Gazebo Physics"
  ["gz-rendering"]="Gazebo Rendering"
  ["gz-sensors"]="Gazebo Sensors"
  ["gz-gui"]="Gazebo GUI"
  ["gz-sim"]="Gazebo Sim"
  ["gz-launch"]="Gazebo Launch"
)

ORIGIN_URL=$(git remote get-url origin)
REPO=$(basename ${ORIGIN_URL%.git})
REPO_NAME=${repo_names[$REPO]} || $REPO

if [[ $(git rev-parse --verify -q $PREV_VER) ]]
then
  PREV_TAG=$PREV_VER
else
  # Find tag that ends with _$PREV_VER
  PREV_TAG=$(git tag | grep "_${PREV_VER}$")
fi

NEW_VERSION=( ${PREV_VER//./ } )
if [[ $bump_major == true ]]; then
  ((NEW_VERSION[0]++))
  NEW_VERSION[1]=0
  NEW_VERSION[2]=0
elif [[ $bump_minor == true ]]; then
  ((NEW_VERSION[1]++))
  NEW_VERSION[2]=0
elif [[ $bump_patch == true ]]; then
  ((NEW_VERSION[2]++))
else
  NEW_VERSION=("X" "X" "X")
fi

NEW_VERSION_STR="${NEW_VERSION[0]}.${NEW_VERSION[1]}.${NEW_VERSION[2]}"


COMMITS=$(git log HEAD...${PREV_TAG} --no-merges --pretty=format:"%h")


echo "### $REPO_NAME $NEW_VERSION_STR (`date '+%Y-%m-%d'`)"
echo
for COMMIT in $COMMITS
do
  TITLE_FULL=$(git log --format="%s" -n 1 $COMMIT)
  TITLE=${TITLE_FULL% (\#*)}
  PR=${TITLE_FULL#*\#}
  PR=${PR%)}

  echo "1. $TITLE"
  echo "    * [Pull request #$PR](https://github.com/gazebosim/$REPO/pull/$PR)"
  echo ""
done
