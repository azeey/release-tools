#!/usr/bin/env python3

# Copyright (C) 2026 Open Source Robotics Foundation
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

import argparse
import json
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone

try:
    import yaml
except ImportError:
    print("Error: PyYAML is required. Install it with 'pip install pyyaml'")
    sys.exit(1)

def fetch_collection(collection_name):
    """Fetch the collection YAML from gazebodistro."""
    url = f"https://raw.githubusercontent.com/gazebo-tooling/gazebodistro/master/collection-{collection_name}.yaml"
    try:
        with urllib.request.urlopen(url) as response:
            return yaml.safe_load(response.read())
    except Exception as e:
        print(f"Error fetching collection '{collection_name}' from {url}: {e}")
        sys.exit(1)

def run_gh_api(args):
    """Run a gh api command and return the parsed JSON."""
    cmd = ["gh", "api"] + args
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None

def get_repo_data(owner, repo, branch):
    """Get latest release and branch information using GraphQL."""
    query = """
    query($owner: String!, $repo: String!, $branch: String!) {
      repository(owner: $owner, name: $repo) {
        branchRef: ref(qualifiedName: $branch) {
          target {
            ... on Commit {
              oid
              committedDate
            }
          }
        }
        latestRelease {
          tagName
          publishedAt
          tagCommit {
            oid
          }
        }
        tags: refs(refPrefix: "refs/tags/", last: 100, orderBy: {field: TAG_COMMIT_DATE, direction: ASC}) {
          nodes {
            name
            target {
              oid
              ... on Tag {
                target {
                  ... on Commit {
                    oid
                    committedDate
                  }
                }
              }
              ... on Commit {
                oid
                committedDate
              }
            }
          }
        }
      }
    }
    """
    
    # We use -F to pass variables to avoid shell escaping issues with complex queries
    graphql_args = [
        "graphql",
        "-f", f"query={query}",
        "-F", f"owner={owner}",
        "-F", f"repo={repo}",
        "-F", f"branch=refs/heads/{branch}"
    ]
    
    data = run_gh_api(graphql_args)
    if not data or "data" not in data:
        return None
    return data["data"]["repository"]

def get_comparison(owner, repo, base, head):
    """Compare two refs using the REST API."""
    # base is usually the tag, head is the branch
    return run_gh_api([f"repos/{owner}/{repo}/compare/{base}...{head}"])

def calculate_days(date_str):
    """Calculate days since the given ISO date string."""
    if not date_str:
        return "N/A"
    dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    delta = datetime.now(timezone.utc) - dt
    return delta.days

def main():
    parser = argparse.ArgumentParser(description="Check release status of Gazebo libraries.")
    parser.add_argument("collection", help="Collection name (e.g., harmonic, ionic, jetty)")
    parser.add_argument("-o", "--output", help="Output file name (default: stdout)")
    args = parser.parse_args()

    collection_data = fetch_collection(args.collection)
    repositories = collection_data.get("repositories", {})

    output_lines = []
    output_lines.append(f"# Gazebo Release Status: {args.collection.capitalize()}")
    output_lines.append("")
    header = [
        "Library", "Branch", "Latest Tag", "Latest Commit", 
        "Days Since Commit", "Days Since Release", 
        "Commits Since Release", "Files Changed", "Diff"
    ]
    output_lines.append("| " + " | ".join(header) + " |")
    output_lines.append("| " + " | ".join(["---"] * len(header)) + " |")

    for repo_name, info in repositories.items():
        if info.get("type") != "git":
            continue
        
        # Extract owner and repo from URL
        url = info.get("url", "")
        if "github.com/" not in url:
            continue
        
        parts = url.split("github.com/")[1].split("/")
        owner = parts[0]
        repo = parts[1]
        branch = info.get("version")

        sys.stderr.write(f"Processing {repo} ({branch})...\n")

        repo_info = get_repo_data(owner, repo, branch)
        if not repo_info:
            sys.stderr.write(f"  Failed to get info for {repo}\n")
            continue

        # Determine latest tag/release
        latest_tag = None
        release_date = None
        
        # Try to find a tag that matches the branch prefix
        # branch is like 'gz-cmake3', tags are like 'gz-cmake3_3.0.0'
        # branch 'sdf14' matches tags 'sdformat14_14.0.0'
        search_prefix = branch.replace('sdf', 'sdformat')
        
        matched_tags = []
        if repo_info.get("tags") and repo_info["tags"]["nodes"]:
            for tag_node in repo_info["tags"]["nodes"]:
                tag_name = tag_node["name"]
                if tag_name.startswith(search_prefix + "_"):
                    matched_tags.append(tag_node)
        
        if matched_tags:
            # Since we used ASC order and 'last: 100', the most recent tags are at the end
            tag_node = matched_tags[-1]
            latest_tag = tag_node["name"]
            target = tag_node["target"]
            if "committedDate" in target:
                release_date = target["committedDate"]
            elif "target" in target and "committedDate" in target["target"]:
                release_date = target["target"]["committedDate"]
        elif repo_info.get("latestRelease"):
            # Fallback to latestRelease if it looks related or if we found no matched tags
            lr_tag = repo_info["latestRelease"]["tagName"]
            if lr_tag.startswith(search_prefix + "_"):
                latest_tag = lr_tag
                release_date = repo_info["latestRelease"]["publishedAt"]

        # If still no tag found, use the global latest as a last resort
        if not latest_tag and repo_info.get("latestRelease"):
            latest_tag = repo_info["latestRelease"]["tagName"]
            release_date = repo_info["latestRelease"]["publishedAt"]
        elif not latest_tag and repo_info.get("tags") and repo_info["tags"]["nodes"]:
            tag_node = repo_info["tags"]["nodes"][0]
            latest_tag = tag_node["name"]
            # date extraction...

        # Latest commit on branch
        branch_ref = repo_info.get("branchRef")
        if not branch_ref:
            sys.stderr.write(f"  Branch {branch} not found in {repo}\n")
            continue
        
        latest_commit_oid = branch_ref["target"]["oid"]
        latest_commit_date = branch_ref["target"]["committedDate"]
        
        days_since_commit = calculate_days(latest_commit_date)
        days_since_release = calculate_days(release_date)

        commits_since = "N/A"
        files_changed = "N/A"
        diff_url = "N/A"

        if latest_tag:
            comparison = get_comparison(owner, repo, latest_tag, branch)
            if comparison:
                commits_since = comparison.get("total_commits", 0)
                files_changed = len(comparison.get("files", []))
                diff_url = f"[Diff]({comparison.get('html_url')})"
            else:
                # Maybe tag is not in branch history?
                diff_url = f"[{latest_tag}...{branch}](https://github.com/{owner}/{repo}/compare/{latest_tag}...{branch})"

        row = [
            repo,
            f"`{branch}`",
            latest_tag if latest_tag else "None",
            f"`{latest_commit_oid[:7]}`",
            str(days_since_commit),
            str(days_since_release),
            str(commits_since),
            str(files_changed),
            diff_url
        ]
        output_lines.append("| " + " | ".join(row) + " |")

    markdown_output = "\n".join(output_lines)
    
    if args.output:
        with open(args.output, "w") as f:
            f.write(markdown_output)
    else:
        print(markdown_output)

if __name__ == "__main__":
    main()
