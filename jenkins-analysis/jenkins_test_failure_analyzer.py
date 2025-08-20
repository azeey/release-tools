import jenkins
import argparse
import sys
import os
from requests.exceptions import RequestException

def _get_scm_base_url(actions):
    """
    Parses the build actions to find a base SCM URL (e.g., for GitHub).
    Converts SSH URLs to HTTPS for browser access.
    """
    for action in actions:
        if action and 'remoteUrls' in action and action['remoteUrls']:
            url = action['remoteUrls'][0]
            if url:
                # Convert ssh git url to http url (e.g., git@github.com:org/repo.git)
                if url.startswith('git@'):
                    url = url.replace(':', '/').replace('git@', 'https://')
                # Remove the .git suffix
                if url.endswith('.git'):
                    url = url[:-4]
                return url
    return None

def _extract_scm_details(build_info, scm_base_url):
    """
    Extracts SCM details like branch, and PR information from the build data
    by checking multiple common locations.
    """
    details = {
        'branch': 'N/A',
        'pr_id': 'N/A',
        'pr_url': '#',
    }

    # Method 1: Look for a specific PR action with a direct URL (most reliable)
    # e.g., from GitHub Branch Source or GitLab Branch Source plugins
    for action in build_info.get('actions', []):
        if not action: continue
        action_class = action.get('_class', '')
        if 'MergeRequestAction' in action_class or 'PullRequestAction' in action_class:
             if action.get('url'):
                details['pr_url'] = action['url']
             if action.get('id'):
                details['pr_id'] = str(action.get('id'))
             # Once we find a specific PR action, we can often stop.
             if details['pr_url'] != '#':
                 break

    # Method 2: Check build parameters if direct action not found
    if details['pr_url'] == '#':
        for action in build_info.get('actions', []):
            if action and 'parameters' in action:
                for param in action['parameters']:
                    if not param: continue
                    # Generic variables from plugins like GitHub/Bitbucket Branch Source
                    if param.get('name') == 'CHANGE_URL' and param.get('value'):
                        details['pr_url'] = param.get('value')
                    if param.get('name') == 'CHANGE_ID' and param.get('value'):
                        details['pr_id'] = str(param.get('value'))
                    if param.get('name') == 'BRANCH_NAME' and param.get('value'):
                        details['branch'] = param.get('value')
                    # Legacy ghprb plugin variables
                    if param.get('name') == 'ghprbPullLink' and param.get('value'):
                        details['pr_url'] = param.get('value')
                    if param.get('name') == 'ghprbPullId' and param.get('value'):
                        details['pr_id'] = str(param.get('value'))
                    if param.get('name') == 'ghprbTargetBranch' and param.get('value'):
                        details['branch'] = param.get('value')
    
    # Method 3: Fallback for branch name from SCM data
    if details['branch'] == 'N/A':
         for action in build_info.get('actions', []):
            if action and 'lastBuiltRevision' in action and action['lastBuiltRevision']:
                revision = action['lastBuiltRevision']
                if revision.get('branch'):
                    details['branch'] = revision['branch'][0].get('name', 'N/A')

    # Method 4: Construct URL as a last resort if we have an ID but no direct URL
    if scm_base_url and details['pr_id'] != 'N/A' and details['pr_url'] == '#':
        if 'gitlab' in scm_base_url:
            details['pr_url'] = f"{scm_base_url}/-/merge_requests/{details['pr_id']}"
        elif 'bitbucket' in scm_base_url:
            details['pr_url'] = f"{scm_base_url}/pull-requests/{details['pr_id']}"
        else: # Default to GitHub
            details['pr_url'] = f"{scm_base_url}/pull/{details['pr_id']}"
            
    return details

def list_tests_in_build(server, job_name, build_number_str):
    """
    Connects to Jenkins and lists all test names for a given build.
    This helps in finding the correct test name for analysis.
    """
    try:
        if build_number_str == 'last':
            print(f"Finding last build for job '{job_name}'...")
            job_info = server.get_job_info(job_name)
            if not job_info.get('lastBuild'):
                print(f"Error: No builds found for job '{job_name}'.")
                sys.exit(1)
            build_number = job_info['lastBuild']['number']
            print(f"Last build is #{build_number}.")
        else:
            build_number = int(build_number_str)

        print(f"Fetching test report for build #{build_number}...")
        test_report = server.get_build_test_report(job_name, build_number)

        if not test_report or not test_report.get('suites'):
            print(f"\nWarning: No test report found for job '{job_name}' build #{build_number}.")
            print("This could be because the build failed before tests ran, or tests are not configured for this job.")
            sys.exit(0)

        print("\n" + "="*80)
        print(f"Found the following tests in build #{build_number}:")
        print("="*80)
        
        test_names = set()
        for suite in test_report.get('suites', []):
            suite_name = suite.get('name')
            for case in suite.get('cases', []):
                case_name = case.get('name')
                if suite_name and case_name:
                    test_names.add(f"{suite_name}.{case_name}")
        
        if not test_names:
             print("No individual test cases found in the report.")
        else:
            # Sort and print for consistent output
            for name in sorted(list(test_names)):
                print(name)

        print("="*80)
        print("\nUse one of the above test names for failure analysis.")

    except jenkins.NotFoundException:
        print(f"Error: Build '{build_number_str}' or its test report not found for job '{job_name}'.")
        sys.exit(1)
    except jenkins.JenkinsException as e:
        print(f"\nAn error occurred while fetching test data: {e}")
        sys.exit(1)
    except (ValueError, TypeError):
        print(f"Error: Invalid build number '{build_number_str}'. Please provide a number or 'last'.")
        sys.exit(1)

def process_builds_for_status(server, job_name, test_name, build_numbers):
    """
    Analyzes builds, finds a specific test, and reports its status (pass, fail, etc.)
    for each build where the test is found.
    """
    found_builds = []
    print(f"Analyzing the {len(build_numbers)} most recent builds for test status...")
    for build_number in build_numbers:
        print(f"Analyzing build #{build_number}...", end='\r', flush=True)
        try:
            test_report = server.get_build_test_report(job_name, build_number)
            if not test_report:
                continue

            test_found_in_build = False
            for suite in test_report.get('suites', []):
                suite_name = suite.get('name')
                for case in suite.get('cases', []):
                    case_name = case.get('name')
                    class_name = case.get('className')
                    if not (suite_name and case_name and class_name):
                        continue
                    
                    full_test_name = f"{suite_name}.{case_name}"
                    if full_test_name == test_name:
                        build_info = server.get_build_info(job_name, build_number)
                        build_url = build_info.get('url', '#')
                        scm_base_url = _get_scm_base_url(build_info.get('actions', []))
                        scm_details = _extract_scm_details(build_info, scm_base_url)

                        status = case.get('status', 'UNKNOWN')
                        # Jenkins test URL uses '/' instead of '.' for package/class structure
                        test_url_class_path = class_name.replace('.', '/')
                        test_url = f"{build_url}testReport/(root)/{test_url_class_path}/{case_name}"

                        found_builds.append({
                            'number': build_number,
                            'url': build_url,
                            'node': build_info.get('builtOn', 'N/A'),
                            'status': status,
                            'test_url': test_url,
                            **scm_details
                        })
                        test_found_in_build = True
                        break
                if test_found_in_build:
                    break
        except jenkins.NotFoundException:
            continue
        except jenkins.JenkinsException as e:
            print(f"\nCould not process build #{build_number}. Error: {e}")

    print(" " * 80, end='\r')
    print("\n" + "="*80)
    if found_builds:
        print(f"Analysis Complete. Found test '{test_name}' in {len(found_builds)} build(s):")
        print("\n| Build | Node | Branch | Pull Request | Status |")
        print("|:---|:---|:---|:---|:---|")

        for build in found_builds:
            pr_md = f"[#{build['pr_id']}]({build['pr_url']})" if build['pr_id'] != 'N/A' and build['pr_url'] != '#' else 'N/A'
            build_md = f"[`#{build['number']}`]({build['url']})"
            
            status_text = build['status']
            if build['status'] == 'PASSED':
                status_md = f"✅ [{status_text}]({build['test_url']})"
            elif build['status'] in ['FAILED', 'REGRESSION', 'ERROR']:
                status_md = f"❌ [{status_text}]({build['test_url']})"
            elif build['status'] == 'SKIPPED':
                status_md = f"⏭️ [{status_text}]({build['test_url']})"
            else:
                status_md = f"[{status_text}]({build['test_url']})"

            print(f"| {build_md} | {build['node']} | {build['branch']} | {pr_md} | {status_md} |")
    else:
        print(f"Analysis Complete. The test '{test_name}' was not found in any of the analyzed builds.")
    print("="*80)


def process_builds_for_failures(server, job_name, test_name, build_numbers):
    failed_builds = []
    print(f"Analyzing the {len(build_numbers)} most recent builds...")
    for build_number in build_numbers:
        print(f"Analyzing build #{build_number}...", end='\r', flush=True)
        try:
            test_report = server.get_build_test_report(job_name, build_number)

            if not test_report:
                continue

            for suite in test_report.get('suites', []):
                suite_name = suite.get('name')
                for case in suite.get('cases', []):
                    case_name = case.get('name')
                    class_name = case.get('className')
                    if not (suite_name and case_name and class_name):
                        continue

                    full_test_name = f"{suite_name}.{case_name}"
                    if full_test_name == test_name and case.get('status') in ['FAILED', 'REGRESSION', 'ERROR']:
                        
                        build_info = server.get_build_info(job_name, build_number)
                        build_url = build_info.get('url', '#')
                        scm_base_url = _get_scm_base_url(build_info.get('actions', []))
                        scm_details = _extract_scm_details(build_info, scm_base_url)

                        test_url_class_path = class_name.replace('.', '/')
                        test_url = f"{build_url}testReport/{test_url_class_path}/{case_name}"

                        failed_builds.append({
                            'number': build_number,
                            'url': build_url,
                            'node': build_info.get('builtOn', 'N/A'),
                            'test_url': test_url,
                            **scm_details
                        })
                        break 
                else:
                    continue
                break

        except jenkins.NotFoundException:
            continue
        except jenkins.JenkinsException as e:
            print(f"\nCould not process build #{build_number}. Error: {e}")
    
    print(" " * 80, end='\r')

    print("\n" + "="*80)
    if failed_builds:
        print(f"Analysis Complete. Found {len(failed_builds)} build(s) where test '{test_name}' failed:")
        print("\n| Build | Node | Branch | Pull Request | Status |")
        print("|:---|:---|:---|:---|:---|")
        
        for build in failed_builds:
            pr_md = f"[#{build['pr_id']}]({build['pr_url']})" if build['pr_id'] != 'N/A' and build['pr_url'] != '#' else 'N/A'
            build_md = f"[`#{build['number']}`]({build['url']})"
            status_md = f"❌ [FAILED]({build['test_url']})"

            print(f"| {build_md} | {build['node']} | {build['branch']} | {pr_md} | {status_md} |")
    else:
        print(f"Analysis Complete. The test '{test_name}' did not fail in any of the analyzed builds.")
    print("="*80)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Analyze Jenkins job history for a specific test failure or list tests from a build.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument('jenkins_url', help="URL of the Jenkins instance (e.g., http://jenkins.example.com:8080)")
    parser.add_argument('job_name', help="Full name of the Jenkins job (e.g., 'MyProject/main')")
    parser.add_argument('test_name', nargs='?', default=None, help="The exact name of the test case to analyze (e.g., 'com.my.tests.MyTest.my_test_case'). Required unless using --list-tests.")

    parser.add_argument('-u', '--username', help="Your Jenkins username.", default=None)
    parser.add_argument('--max-builds', type=int, default=50, help="The maximum number of recent builds to analyze. (Default: 50)")
    
    parser.add_argument('--list-tests', action='store_true', help="List all available test names from a build and exit. Helps find the correct test name.")
    parser.add_argument('--build-number', help="Build number to inspect with --list-tests (e.g., 123). Defaults to the latest build.", default='last')
    parser.add_argument('--show-status', action='store_true', help="List all builds containing the test and show its pass/fail status.")

    args = parser.parse_args()

    token = os.environ.get('JENKINS_API_TOKEN')
    if not token:
        print("Error: The JENKINS_API_TOKEN environment variable is not set.")
        print("Please set it to your Jenkins API token before running the script.")
        sys.exit(1)

    username = args.username if args.username else input("Enter Jenkins Username: ")
    
    if not username:
        print("Error: A username is required.")
        sys.exit(1)

    print(f"Attempting to connect to Jenkins at {args.jenkins_url}...")
    try:
        server = jenkins.Jenkins(args.jenkins_url, username=username, password=token)
        user = server.get_whoami()
        print(f"Successfully connected to Jenkins as '{user['fullName']}'.")
    except jenkins.JenkinsException as e:
        print(f"Error: Failed to connect to Jenkins. Please check URL and credentials.")
        print(f"Jenkins API Error: {e}")
        sys.exit(1)
    except RequestException as e:
        print(f"Error: Network issue connecting to Jenkins at {args.jenkins_url}.")
        print(f"Error details: {e}")
        sys.exit(1)

    if args.list_tests:
        list_tests_in_build(server, args.job_name, args.build_number)
        sys.exit(0)

    if not args.test_name:
        parser.error('The `test_name` argument is required unless you use the --list-tests flag.')

    try:
        print(f"Fetching build history for job '{args.job_name}'...")
        job_info = server.get_job_info(args.job_name, depth=1)
        build_numbers = [build['number'] for build in job_info.get('builds', [])][:args.max_builds]
        
        if not build_numbers:
            print("No builds found for this job.")
            sys.exit(0)

        if args.show_status:
            process_builds_for_status(server, args.job_name, args.test_name, build_numbers)
        else:
            process_builds_for_failures(server, args.job_name, args.test_name, build_numbers)

    except jenkins.NotFoundException:
        print(f"Error: Job '{args.job_name}' not found on the Jenkins server.")
        sys.exit(1)
    except jenkins.JenkinsException as e:
        print(f"Error: Failed to retrieve job information for '{args.job_name}'.")
        print(f"Jenkins API Error: {e}")
        sys.exit(1)

