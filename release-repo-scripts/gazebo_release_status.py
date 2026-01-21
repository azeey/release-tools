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

def run_gh_api(args, input_data=None):
    """Run a gh api command and return the parsed JSON."""
    cmd = ["gh", "api"] + args
    result = subprocess.run(cmd, capture_output=True, text=True, input=input_data)
    if result.returncode != 0:
        sys.stderr.write(f"Error running gh api: {result.stderr}\n")
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None

def get_all_repos_data(repositories):
    """Get data for all repositories in a single GraphQL query."""
    query_header = ["query($owner: String!"]
    query_body = []
    variables = {"owner": "gazebosim"}
    
    for i, (repo_key, info) in enumerate(repositories.items()):
        url = info.get("url", "")
        if "github.com/" not in url:
            continue
        
        parts = url.split("github.com/")[1].split("/")
        owner = parts[0]
        repo = parts[1]
        branch = info.get("version")
        
        alias = f"repo_{i}"
        repo_var = f"repo_{i}"
        branch_var = f"branch_{i}"
        
        query_header.append(f", ${repo_var}: String!, ${branch_var}: String!")
        variables[repo_var] = repo
        variables[branch_var] = f"refs/heads/{branch}"
        
        query_body.append(f"""
          {alias}: repository(owner: $owner, name: ${repo_var}) {{
            name
            branchRef: ref(qualifiedName: ${branch_var}) {{
              target {{
                ... on Commit {{
                  oid
                  committedDate
                }}
              }}
            }}
            tags: refs(refPrefix: "refs/tags/", last: 100, orderBy: {{field: TAG_COMMIT_DATE, direction: ASC}}) {{
              nodes {{
                name
                target {{
                  oid
                  ... on Tag {{
                    target {{
                      ... on Commit {{
                        oid
                        committedDate
                      }}
                    }}
                  }}
                  ... on Commit {{
                    oid
                    committedDate
                  }}
                }}
              }}
            }}
          }}
        """)
    
    query_header.append(") {")
    full_query = "".join(query_header) + "\n".join(query_body) + "}"
    
    # Use stdin to pass variables to avoid shell limits
    payload = {
        "query": full_query,
        "variables": variables
    }
    
    data = run_gh_api(["graphql", "--input", "-"], input_data=json.dumps(payload))
    if not data or "data" not in data:
        return {}
    return data["data"]

def get_comparison(owner, repo, base, head):
    """Compare two refs using the REST API."""
    return run_gh_api([f"repos/{owner}/{repo}/compare/{base}...{head}"])

def calculate_days(date_str):
    """Calculate days since the given ISO date string."""
    if not date_str:
        return "N/A"
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        delta = datetime.now(timezone.utc) - dt
        return delta.days
    except (ValueError, TypeError):
        return "N/A"

def format_date(date_str):
    """Extract YYYY-MM-DD from ISO date string."""
    if not date_str:
        return ""
    return date_str.split("T")[0]

def main():
    parser = argparse.ArgumentParser(description="Check release status of Gazebo libraries.")
    parser.add_argument("collection", help="Collection name (e.g., harmonic, ionic, jetty)")
    parser.add_argument("-o", "--output", help="Output file name (default: stdout)")
    parser.add_argument("--get-changes", action="store_true", help="Include commit counts and file changes (requires REST API calls)")
    args = parser.parse_args()

    collection_data = fetch_collection(args.collection)
    repositories = collection_data.get("repositories", {})

    sys.stderr.write(f"Fetching data for {len(repositories)} repositories...\n")
    all_repo_data = get_all_repos_data(repositories)

    output_lines = []
    output_lines.append(f"# Gazebo Release Status: {args.collection.capitalize()}")
    output_lines.append("")
    
    header = [
        "Library", "Branch", "Latest Tag", "Latest Commit", 
        "Days Since Commit", "Days Since Release"
    ]
    if args.get_changes:
        header += ["Commits Since Release", "Files Changed", "Diff"]
        
    output_lines.append("| " + " | ".join(header) + " |")
    output_lines.append("| " + " | ".join(["---"] * len(header)) + " |")

    # Map aliases back to original repositories
    for i, (repo_key, info) in enumerate(repositories.items()):
        alias = f"repo_{i}"
        repo_info = all_repo_data.get(alias)
        if not repo_info:
            continue
            
        url = info.get("url", "")
        parts = url.split("github.com/")[1].split("/")
        owner = parts[0]
        repo = parts[1]
        branch = info.get("version")

        # Determine latest tag
        latest_tag = None
        release_date = None
        search_prefix = branch.replace('sdf', 'sdformat')
        
        matched_tags = []
        if repo_info.get("tags") and repo_info["tags"]["nodes"]:
            for tag_node in repo_info["tags"]["nodes"]:
                if tag_node["name"].startswith(search_prefix + "_"):
                    matched_tags.append(tag_node)
        
        if matched_tags:
            tag_node = matched_tags[-1]
            latest_tag = tag_node["name"]
            target = tag_node["target"]
            if "committedDate" in target:
                release_date = target["committedDate"]
            elif "target" in target and "committedDate" in target["target"]:
                release_date = target["target"]["committedDate"]

        branch_ref = repo_info.get("branchRef")
        if not branch_ref:
            latest_commit_oid = "N/A"
            latest_commit_date = None
        else:
            latest_commit_oid = branch_ref["target"]["oid"][:7]
            latest_commit_date = branch_ref["target"]["committedDate"]
        
        tag_str = latest_tag if latest_tag else "None"
        if release_date:
            tag_str += f" ({format_date(release_date)})"
            
        commit_str = f"`{latest_commit_oid}`"
        if latest_commit_date:
            commit_str += f" ({format_date(latest_commit_date)})"

        row = [
            repo,
            f"`{branch}`",
            tag_str,
            commit_str,
            str(calculate_days(latest_commit_date)),
            str(calculate_days(release_date))
        ]

        if args.get_changes:
            commits_since = "N/A"
            files_changed = "N/A"
            diff_url = "N/A"
            if latest_tag:
                comparison = get_comparison(owner, repo, latest_tag, branch)
                if comparison:
                    commits_since = comparison.get("total_commits", 0)
                    files_changed = len(comparison.get("files", []))
                    diff_url = f"[Diff]({comparison.get('html_url')})"
            row += [str(commits_since), str(files_changed), diff_url]

        output_lines.append("| " + " | ".join(row) + " |")

    markdown_output = "\n".join(output_lines)
    
    if args.output:
        with open(args.output, "w") as f:
            f.write(markdown_output)
    else:
        print(markdown_output)

if __name__ == "__main__":
    main()
