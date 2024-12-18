#!/usr/bin/env python3

# Copyright (C) 2024 Open Source Robotics Foundation
#
# Licensed under the Apache License, Version 2.0 (the "License")
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import argparse
import datetime
from typing import Optional, Union
import subprocess
import re

REPO_NAMES = {
    "gz-cmake": "Gazebo CMake",
    "gz-utils": "Gazebo Utils",
    "gz-tools": "Gazebo Tools",
    "gz-math": "Gazebo Math",
    "gz-plugin": "Gazebo Plugin",
    "gz-common": "Gazebo Common",
    "gz-msgs": "Gazebo Msgs",
    "sdformat": "libsdformat",
    "gz-fuel-tools": "Gazebo Fuel Tools",
    "gz-transport": "Gazebo Transport",
    "gz-physics": "Gazebo Physics",
    "gz-rendering": "Gazebo Rendering",
    "gz-sensors": "Gazebo Sensors",
    "gz-gui": "Gazebo GUI",
    "gz-sim": "Gazebo Sim",
    "gz-launch": "Gazebo Launch",
}


def ext_run(cmd: list):
    # print(f"Running: {' '.join(cmd)}")
    po = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out, err = po.communicate()
    if po.returncode != 0:
        print("Error running command (%s)." % (" ".join(cmd)))
        print("stdout: %s" % (out.decode()))
        print("stderr: %s" % (err.decode()))
        raise Exception("subprocess call failed")
    return out.decode()


def get_project_and_version_from_cmake(cmake_file: str):
    with open(cmake_file) as f:
        m = re.search(
            r"^project\W*\(\W*([a-z0-9-]*)\W*VERSION\W*([0-9.]*)",
            f.read(),
            re.MULTILINE,
        )
    if m:
        return m.groups()
    else:
        raise RuntimeError("Could not parse project and version from CMakeLists.txt")

def get_repo_from_project(project: str):
    repo = project.replace("ignition", "gz").replace("gazebo", "sim")
    # remove the version
    m = re.search("[a-z-_]*", repo)
    print(m)
    if not m:
        raise RuntimeError("Could not determine repo from project name")
    else:
        repo = m.group(0)
        return repo, REPO_NAMES[repo]


def calculate_new_version(bump: str, previous_version: str):

    new_version = [int(v) for v in previous_version.split(".")]
    if bump == "major":
        new_version[0] += 1
    elif bump == "minor":
        new_version[1] += 1
    elif bump == "patch":
        new_version[2] += 1
    return ".".join(map(str, new_version))


def extract_title_and_pr(title_with_pr: str):
    matcher = re.compile(r"(.*)\(.*#(\d*)\)$")
    m = re.match(matcher, title_with_pr)
    if not m:
        raise RuntimeError("Could not parse title and PR")
    else:
        title, pr = m.groups()
        title = title.strip()
        # Sometimes, the title has two PR numbers. The first number is the backport,
        # so we skip that.
        m2 = re.match(matcher, title)
        if m2:
            title = m2.group(0)
        return title.strip(), pr


def generate_changelog(prev_tag, repo)-> list[str]:
    commits = ext_run(
        ["git", "log", f"HEAD...{prev_tag}", "--no-merges", "--pretty=format:%h"]
    )
    commits_list = commits.split()
    # print("commits_list:", commits_list)

    changelog = []
    for commit in commits_list:
        # print("commit:", commit)
        title_with_pr = ext_run(["git", "log", "--format=%s", "-n", "1", commit]).strip()
        # Extract title and PR number
        try:
            title, pr = extract_title_and_pr(title_with_pr)
            entry = f"""\
1. {title}
    * [Pull request #{pr}](https://github.com/gazebosim/{repo}/pull/{pr})
"""
            changelog.append(entry)
        except RuntimeError:
            pass
    return changelog


def bump_version(bump: str, previous_version_input: Optional[str]):

    project, previous_version = get_project_and_version_from_cmake("CMakeLists.txt")
    repo, repo_name = get_repo_from_project(project)
    print("repo:", repo)
    if previous_version_input is not None:
        previous_version = previous_version_input

    print("previous version:", previous_version)

    new_version = calculate_new_version(bump, previous_version)
    print("new version:", new_version)

    if previous_version == new_version:
        print(
            f"Previous version {previous_version} and new version {new_version} should be different"
        )
        return

    prev_tag = f"{project}_{previous_version}"
    print("prev_tag:", prev_tag)
    changelog = generate_changelog(prev_tag, repo)
    changelog_str = "\n".join(changelog)
    date = datetime.date.today()
    changelog_title = f"### {repo_name} {new_version} ({date})"
    print(f"{changelog_title}\n\n{changelog_str}")


def main():
    parser = argparse.ArgumentParser(
        description="Bump the version of a package in all the necessary places \
                     (package.xml, CMakeLists.txt) to prepare it for a release.\
                     This also updates the Changelog file based on git logs.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--bump",
        choices=("major", "minor", "patch"),
        default="patch",
        help="The type of version bump",
    )
    parser.add_argument(
        "--previous",
        help="Previous version (e.g., 3.0.0). If left empty, the last tag found \
              using 'git describe --tags' will be used",
    )

    args = parser.parse_args()
    bump_version(args.bump, args.previous)


if __name__ == "__main__":
    main()
