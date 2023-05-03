#!/bin/bash
# Example: git log ...ignition-utils1_1.4.0 --pretty=format:"%h" | xargs -L1 bash ~/ws/release/release-tools/source-repo-scripts/format_commits.bash
COMMITS=$1

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
