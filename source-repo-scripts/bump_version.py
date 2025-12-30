#!/usr/bin/env python3

# Copyright (C) 2025 Open Source Robotics Foundation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Bumps the major version in the source code of a Gazebo library. It updates the following files:
# - CMakeLists.txt
# - package.xml
# - Changelog.md
# - Migration.md
#
# The changes will be committed to a branch after confirming with the user.
#
# NOTE: This assumes that the VERSION_SUFFIX is set to PRE1 already.

import re
import subprocess
import sys


def replace_in_file(file_path, old_str, new_str):
    """Replace a string in a file."""
    with open(file_path, "r") as f:
        content = f.read()
    content = content.replace(old_str, new_str)
    with open(file_path, "w") as f:
        f.write(content)


def main():
    """Main function."""
    # Get current version from package.xml
    old_version = None
    with open("package.xml", "r") as f:
        content = f.read()
        match = re.search(r"<version>(\d+\.\d+\.\d+)</version>", content)
        if match:
            old_version = match.group(1)
        else:
            print("Error: Could not find version in package.xml")
            sys.exit(1)

    # Calculate new version
    major, _, _ = old_version.split(".")
    new_version = f"{int(major) + 1}.0.0"
    new_version_pre = f"{new_version}~pre1"

    # Get the current branch name
    previous_branch = (
        subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"])
        .decode("utf-8")
        .strip()
    )

    # Create and checkout a new branch
    branch_name = f"bump_main_{new_version}"
    print(f"Creating new branch: {branch_name}")
    subprocess.check_call(["git", "checkout", "-b", branch_name])

    project_name = None
    # Find project name in CMakeLists.txt
    with open("CMakeLists.txt", "r") as f:
        content = f.read()
        match = re.search(r"project\(([^ ]+)", content)
        if match:
            project_name = match.group(1)
        else:
            print("Error: Could not find project name in CMakeLists.txt")
            sys.exit(1)

    # 1. Update CMakeLists.txt
    print("Updating CMakeLists.txt")
    replace_in_file(
        "CMakeLists.txt",
        f"project({project_name} VERSION {old_version})",
        f"project({project_name} VERSION {new_version})",
    )

    # 2. Update package.xml
    print("Updating package.xml")
    replace_in_file(
        "package.xml",
        f"<version>{old_version}</version>",
        f"<version>{new_version}</version>",
    )

    # 3. Update Changelog.md
    print("Updating Changelog.md")
    with open("Changelog.md", "r") as f:
        content = f.read()

    changelog_project_name = None
    for line in content.splitlines():
        if line.startswith("#"):
            match = re.search(r"#+ (.*) \d+", line)
            if match:
                changelog_project_name = match.group(1)
                break

    if not changelog_project_name:
        changelog_project_name = project_name.replace("-", " ").title()

    new_changelog_header = f"## {changelog_project_name} {new_version.split('.')[0]}.x\n\n### {changelog_project_name} {new_version} (20XX-XX-XX)\n\n"
    with open("Changelog.md", "w") as f:
        f.write(new_changelog_header + content)

    # 4. Update Migration.md
    print("Updating Migration.md")
    with open("Migration.md", "r") as f:
        content = f.read()

    new_migration_header = f"\n## {changelog_project_name} {old_version.split('.')[0]}.X to {new_version.split('.')[0]}.X\n\n"
    # Insert after the first h2 header
    lines = content.splitlines()
    found_h2 = False
    for i, line in enumerate(lines):
        if line.startswith("##"):
            lines.insert(i, new_migration_header)
            found_h2 = True
            break
    if not found_h2:
        lines.append(new_migration_header)

    with open("Migration.md", "w") as f:
        f.write("\n".join(lines))

    # 5. Show git diff
    print("\nShowing git diff:")
    subprocess.run(["git", "diff"])

    # 6. Ask for confirmation
    confirm = input("\nApply changes and commit? (y/n): ")
    if confirm.lower() != "y":
        print("Aborting. Rolling back changes.")
        subprocess.run(["git", "checkout", previous_branch])
        subprocess.run(["git", "branch", "-D", branch_name])
        sys.exit(0)

    # 7. Add and commit
    print("Adding and committing changes.")
    commit_message = f"Bump main to {new_version_pre}"
    subprocess.run(
        ["git", "add", "CMakeLists.txt", "package.xml", "Changelog.md", "Migration.md"]
    )
    subprocess.run(["git", "commit", "-m", commit_message, "--signoff"])

    print("\nDone.")


if __name__ == "__main__":
    main()
