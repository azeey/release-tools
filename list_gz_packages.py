import sys
import os
import re
import subprocess
import argparse

def get_metapackage_dependencies(release_name):
    metapkg = f"gz-{release_name}"
    dependencies = []
    
    try:
        # Run apt-cache depends
        cmd = ['apt-cache', 'depends', metapkg]
        result = subprocess.check_output(cmd, text=True)
    except subprocess.CalledProcessError:
        # Metapackage might not exist
        return []
    
    # Parse output
    # Lines look like: "  Depends: libgz-sim9-dev"
    re_dep = re.compile(r'^\s*Depends:\s+(\S+)')
    
    for line in result.splitlines():
        m = re_dep.match(line)
        if m:
            dep_pkg = m.group(1)
            dependencies.append(dep_pkg)
            
    return dependencies

def parse_lib_versions(dependency_packages):
    # Extract (lib_name, major_version) from package names
    # e.g. libgz-sim9-dev -> gz-sim, 9
    # python3-gz-sim9 -> gz-sim, 9
    # gz-tools2-dev -> gz-tools, 2
    
    # Regex: optional prefix (lib|python3-), then lib name (non-greedy), then digits, then optional suffix
    # We rely on the fact that the version number is the *last* sequence of digits before the suffix starts?
    # Or usually immediately follows the lib name.
    
    # Improved regex:
    # ^(?:lib|python3-)?  <- ignore common prefixes
    # (.+?)               <- lib name
    # (\d+)               <- major version
    # (?:-.*)?$           <- optional suffix (starts with -)
    
    # Note: "gz-tools2" -> prefix empty, lib "gz-tools", ver "2", suffix empty.
    # "libgz-utils2-cli-dev" -> prefix "lib", lib "gz-utils", ver "2", suffix "-cli-dev".
    
    regex = re.compile(r'^(?:lib|python3-)?(.+?)(\d+)(?:-.*)?$')
    
    lib_map = set() # Set of (name, version) tuples
    
    for pkg in dependency_packages:
        m = regex.match(pkg)
        if m:
            lib_name = m.group(1)
            major_ver = int(m.group(2))
            lib_map.add((lib_name, major_ver))
            
    return lib_map

def get_all_packages():
    try:
        # Run apt-cache pkgnames
        result = subprocess.check_output(['apt-cache', 'pkgnames'], text=True)
        return result.splitlines()
    except subprocess.CalledProcessError as e:
        print(f"Error running apt-cache: {e}", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError:
        print("Error: apt-cache command not found.", file=sys.stderr)
        sys.exit(1)

def match_packages(release_name, lib_versions, all_packages):
    results = []
    metapkg_name = f"gz-{release_name}"
    
    for pkg in all_packages:
        # 1. Check if it is the metapackage itself
        if pkg == metapkg_name:
            results.append((release_name, pkg))
            continue
            
        # 2. Check if it matches any lib+version
        for lib_name, major in lib_versions:
            # Pattern: lib_name + major + (end of string OR non-digit)
            # This ensures gz-sim9 matches gz-sim9, gz-sim9-dev
            # But gz-sim9 DOES NOT match gz-sim90
            
            # We check if "{lib_name}{major}" is present in pkg
            # AND the character immediately following it is not a digit.
            
            pattern = re.escape(lib_name) + str(major) + r'(\D|$)'
            if re.search(pattern, pkg):
                results.append((release_name, pkg))
                break 

    return results

def main():
    parser = argparse.ArgumentParser(description="List Gazebo packages for a specific release.")
    parser.add_argument("release", help="Gazebo release name (e.g. harmonic, ionic)")
    args = parser.parse_args()
    
    release_name = args.release
    
    # 1. Get dependencies of the release metapackage
    deps = get_metapackage_dependencies(release_name)
    if not deps:
        print(f"Error: Could not find dependencies for metapackage 'gz-{release_name}'. "
              f"Make sure 'gz-{release_name}' exists in the apt cache.", file=sys.stderr)
        sys.exit(1)
        
    # 2. Extract core libs and versions
    lib_versions = parse_lib_versions(deps)
    # Debug: print(f"Found libs: {lib_versions}", file=sys.stderr)
    
    # 3. Get all available packages
    all_pkgs = get_all_packages()
    
    # 4. Match
    matches = match_packages(release_name, lib_versions, all_pkgs)
    
    # 5. Sort and Print
    matches.sort(key=lambda x: (x[0], x[1]))
    
    for rel, pkg in matches:
        print(f"{rel}\t{pkg}")

if __name__ == "__main__":
    main()
