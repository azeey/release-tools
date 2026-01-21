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

def analyze_significance(commits, files):
    """Analyze commit messages and files for significance."""
    significance = {"breaking": False, "features": 0, "fixes": 0}
    
    # Heuristic: only consider changes to source files as significant for releases
    source_extensions = (".cc", ".hh", ".cpp", ".hpp", ".c", ".h")
    has_source_changes = any(f.get("filename", "").endswith(source_extensions) for f in files)
    
    if not has_source_changes:
        return significance

    feature_keywords = ["add", "new", "implement", "support", "feature", "include"]
    fix_keywords = ["fix", "bug", "issue", "resolve", "correct", "prevent", "regression"]
    breaking_keywords = ["breaking change", "deprecate", "remove", "api change"]
    
    for c in commits:
        msg = c.get("commit", {}).get("message", "").lower()
        
        # Check for breaking changes
        if any(kw in msg for kw in breaking_keywords):
            significance["breaking"] = True
            
        # Check for features (at start of message or after a space)
        if any(msg.startswith(kw) or f" {kw}" in msg for kw in feature_keywords):
            significance["features"] += 1
        elif any(msg.startswith(kw) or f" {kw}" in msg for kw in fix_keywords):
            significance["fixes"] += 1
            
    return significance

def get_priority(commits_count, days_since_release, significance):
    """Determine release priority and reason."""
    if commits_count == 0:
        return 0, "None", "-"
    
    reasons = []
    score = 0
    
    if significance["breaking"]:
        score += 100
        reasons.append("Breaking changes")
    if significance["features"] > 0:
        score += 20 + (significance["features"] * 5)
        reasons.append(f"{significance['features']} features")
    if significance["fixes"] > 0:
        score += 10 + (significance["fixes"] * 2)
        reasons.append(f"{significance['fixes']} fixes")
        
    score += commits_count * 0.5
    if days_since_release != "N/A":
        if days_since_release > 180:
            score += 30
            reasons.append("> 6 months since release")
        elif days_since_release > 90:
            score += 15
            reasons.append("> 3 months since release")

    priority = "Low"
    if score >= 100:
        priority = "Critical"
    elif score >= 40:
        priority = "High"
    elif score >= 15:
        priority = "Medium"
        
    return score, priority, ", ".join(reasons) if reasons else "Minor changes"

def generate_html(collection_name, header, rows):
    """Generate a complete HTML page with sorting and styling."""
    priority_colors = {
        "Critical": "#f8d7da",
        "High": "#fff3cd",
        "Medium": "#e2e3e5",
        "Low": "#d4edda",
        "None": "#ffffff"
    }
    
    html_template = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Gazebo Release Status: {collection_name.capitalize()}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; color: #333; max-width: 1200px; margin: 0 auto; padding: 20px; background-color: #f4f7f6; }}
        h1 {{ color: #2c3e50; text-align: center; }}
        .container {{ background: white; padding: 20px; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); overflow-x: auto; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 20px; font-size: 14px; }}
        th {{ background-color: #2c3e50; color: white; padding: 12px; text-align: left; cursor: pointer; position: sticky; top: 0; }}
        th:hover {{ background-color: #34495e; }}
        th::after {{ content: ' ↕'; font-size: 10px; opacity: 0.5; }}
        td {{ padding: 10px; border-bottom: 1px solid #eee; }}
        tr:hover {{ filter: brightness(0.95); }}
        .priority-Critical {{ background-color: {priority_colors["Critical"]}; }}
        .priority-High {{ background-color: {priority_colors["High"]}; }}
        .priority-Medium {{ background-color: {priority_colors["Medium"]}; }}
        .priority-Low {{ background-color: {priority_colors["Low"]}; }}
        code {{ background: #f8f9fa; padding: 2px 4px; border-radius: 4px; font-family: monospace; border: 1px solid #ddd; }}
        a {{ color: #3498db; text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
        .timestamp {{ font-size: 12px; color: #666; display: block; margin-top: 4px; }}
        .meta-info {{ margin-bottom: 20px; text-align: center; color: #7f8c8d; }}
    </style>
</head>
<body>
    <h1>Gazebo Release Status: {collection_name.capitalize()}</h1>
    <p class="meta-info">Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC</p>
    <div class="container">
        <table id="statusTable">
            <thead>
                <tr>
                    {"".join(f"<th>{h}</th>" for h in header)}
                </tr>
            </thead>
            <tbody>
"""
    for _, row in rows:
        # Check if priority column exists (index 6 if --get-changes)
        priority = "None"
        if len(row) > 6:
            priority = row[6]
        
        html_template += f'                <tr class="priority-{priority}">\n'
        for i, cell in enumerate(row):
            # Format markdown-style links and codes for HTML
            content = cell
            if "[" in content and "](" in content:
                # Simple markdown link to HTML link
                import re
                content = re.sub(r'\[([^\]]+)\]\(([^\)]+)\)', r'<a href="\2" target="_blank">\1</a>', content)
            
            if "`" in content:
                content = content.replace("`", "<code>").replace("`", "</code>") # simplistic but works for our format

            # Special handling for dates in parentheses to make them look better
            if "(" in content and ")" in content:
                 content = content.replace(" (", '<br><span class="timestamp">').replace(")", "</span>")

            html_template += f"                    <td>{content}</td>\n"
        html_template += "                </tr>\n"

    html_template += """
            </tbody>
        </table>
    </div>
    <script>
        document.addEventListener('DOMContentLoaded', function() {
            const getCellValue = (tr, idx) => tr.children[idx].innerText || tr.children[idx].textContent;
            const comparer = (idx, asc) => (a, b) => ((v1, v2) => 
                v1 !== '' && v2 !== '' && !isNaN(v1) && !isNaN(v2) ? v1 - v2 : v1.toString().localeCompare(v2)
                )(getCellValue(asc ? a : b, idx), getCellValue(asc ? b : a, idx));

            document.querySelectorAll('th').forEach(th => th.addEventListener('click', (() => {
                const table = th.closest('table');
                const tbody = table.querySelector('tbody');
                Array.from(tbody.querySelectorAll('tr'))
                    .sort(comparer(Array.from(th.parentNode.children).indexOf(th), this.asc = !this.asc))
                    .forEach(tr => tbody.appendChild(tr) );
            })));
        });
    </script>
</body>
</html>
"""
    return html_template

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

    header = [
        "Library", "Branch", "Latest Tag", "Latest Commit", 
        "Days Since Commit", "Days Since Release"
    ]
    if args.get_changes:
        header += ["Priority", "Reason", "Commits Since", "Files Changed", "Diff"]
        
    rows = []

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

        days_since_release = calculate_days(release_date)
        row = [
            repo,
            f"`{branch}`",
            tag_str,
            commit_str,
            str(calculate_days(latest_commit_date)),
            str(days_since_release)
        ]

        priority_score = 0
        if args.get_changes:
            commits_since = 0
            files_changed = 0
            diff_url = "N/A"
            priority = "None"
            reason = "-"
            
            if latest_tag:
                comparison = get_comparison(owner, repo, latest_tag, branch)
                if comparison:
                    commits_since = comparison.get("total_commits", 0)
                    files = comparison.get("files", [])
                    files_changed = len(files)
                    diff_url = f"[Diff]({comparison.get('html_url')})"
                    
                    significance = analyze_significance(comparison.get("commits", []), files)
                    priority_score, priority, reason = get_priority(commits_since, days_since_release, significance)
            
            row += [priority, reason, str(commits_since), str(files_changed), diff_url]

        rows.append((priority_score, row))

    # Sort rows by priority score descending
    rows.sort(key=lambda x: x[0], reverse=True)

    html_output = generate_html(args.collection, header, rows)
    
    if args.output:
        with open(args.output, "w") as f:
            f.write(html_output)
    else:
        print(html_output)

if __name__ == "__main__":
    main()
