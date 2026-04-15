"""
create_solution.py - Creates a lightweight solution repo with sparse checkout
Usage: ./create_solution.py <solution-name> <commit-or-range> path1 path2 ...
Example: ./create_solution.py my-service "HEAD~5..HEAD" api/src/services/mod-fed.ts api/src/routes/mod-fed.ts
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

import git

SOLUTION_DIR = Path.home() / ".bookmarks/Projects/ChronoIndex/Current" / args.solution_name

def resolve_commit(repo_path: Path, ref: str) -> str:
    """Resolve a git ref (commit hash, branch, HEAD~N, etc.) to a full commit hash."""
    try:
        repo = git.Repo(repo_path)
        commit = repo.commit(ref)
        return commit.hexsha
    except Exception as e:
        print(f"Error resolving '{ref}': {e}", file=sys.stderr)
        sys.exit(1)

def run_git(cwd: Path, *args):
    """Run git command and return output, exit on failure."""
    result = subprocess.run(["git"] + list(args), cwd=cwd, capture_output=True, text=True)
    print(result)
    if result.returncode != 0:
        print(f"Git command failed: git {' '.join(args)}\n{result.stderr}", file=sys.stderr)
        sys.exit(1)
    return result.stdout.strip()

def is_git_repo(dir: Path):
    repo_root = run_git(dir, "-C", dir, "rev-parse", "--git-dir")

    return Path(repo_root).is_relative_to(repo_root)

def main():
    parser = argparse.ArgumentParser(description="Create a sparse solution repository from a commit range.")
    parser.add_argument("solution_name", help="Name of the solution (subdirectory under ~/code-solutions)")
    parser.add_argument("commit_spec", help="Commit or range (e.g., 'abc123' or 'HEAD~5..HEAD')")
    parser.add_argument("paths", nargs="+", help="Exact file paths to include (relative to repo root)")
    args = parser.parse_args()

    source_repo = Path.cwd()
    if not is_git_repo(source_repo):
        print("Error: Current directory is not a git repository", file=sys.stderr)
        sys.exit(1)

    SOLUTION_DIR.mkdir(parents=True, exist_ok=True)

    # Parse commit range
    if ".." in args.commit_spec:
        start_ref, end_ref = args.commit_spec.split("..")
        start_commit = resolve_commit(source_repo, start_ref)
        end_commit = resolve_commit(source_repo, end_ref)
        is_range = True
    else:
        end_commit = resolve_commit(source_repo, args.commit_spec)
        start_commit = None
        is_range = False

    print(f"Creating solution '{args.solution_name}' from commit {end_commit}")

    # Clone with no checkout
    try:
        repo = git.Repo.clone_from(f"file://{source_repo}", SOLUTION_DIR, no_checkout=True)
    except Exception as e:
        print(f"Clone failed: {e}", file=sys.stderr)
        sys.exit(1)

    # Enable sparse checkout (non-cone mode)
    run_git(SOLUTION_DIR, "sparse-checkout", "init", "--no-cone")

    # Set exact file paths (strip leading './' if any)
    patterns = [p.lstrip("./") for p in args.paths]
    with open(SOLUTION_DIR / ".git" / "info" / "sparse-checkout", "w") as f:
        print(patterns)
        for pattern in patterns:
            f.write(pattern + "\n")

    # Reapply sparse checkout to ensure it takes effect
    run_git(SOLUTION_DIR, "sparse-checkout", "reapply")

    # Checkout the desired commit
    run_git(SOLUTION_DIR, "checkout", end_commit)

    # Create a branch for the solution
    branch_name = f"solution/{args.solution_name}"
    run_git(SOLUTION_DIR, "checkout", "-b", branch_name)

    # Optionally fetch start commit if range was given
    if is_range and start_commit:
        run_git(SOLUTION_DIR, "fetch", "origin", start_commit)

    # Write metadata
    meta_dir = SOLUTION_DIR / ".solution-meta"
    meta_dir.mkdir(exist_ok=True)
    metadata = {
        "name": args.solution_name,
        "created": subprocess.check_output(["date", "-Iseconds"]).decode().strip(),
        "original_spec": args.commit_spec,
        "commit": end_commit,
        "start_commit": start_commit,
        "paths": patterns,
        "original_remote": str(source_repo),
    }
    with open(meta_dir / "config.json", "w") as f:
        json.dump(metadata, f, indent=2)

    # Clean up (optional)
    run_git(SOLUTION_DIR, "reflog", "expire", "--expire=now", "--all")
    run_git(SOLUTION_DIR, "gc", "--prune=now")

    print(f"\n✅ Solution created at: {SOLUTION_DIR}")
    print(f"   Working directory contains only: {', '.join(patterns)}")
    print(f"   Repository size: {subprocess.check_output(['du', '-sh', str(SOLUTION_DIR / '.git')]).decode().split()[0]}")
    print("\nTo later update this solution from the source repo:")
    print(f"  cd {SOLUTION_DIR} && git fetch origin && git merge origin/main")

if __name__ == "__main__":
    main()
