"""Dev server launcher — sets AM_DB_PATH to the main repo root before starting.

Works correctly in git worktrees by using `git rev-parse --show-toplevel`
on the common git dir, which always resolves to the main repo regardless of
which worktree this script is run from.
"""

import os
import subprocess
import sys

_here = os.path.dirname(os.path.abspath(__file__))
_repo_root = os.path.dirname(_here)  # scripts/ is one level down

try:
    # --git-common-dir points to the shared .git dir across all worktrees
    common_git = subprocess.check_output(
        ["git", "rev-parse", "--git-common-dir"],
        cwd=_repo_root,
        text=True,
    ).strip()
    # common_git is either ".git" (main) or an absolute path (worktree)
    if not os.path.isabs(common_git):
        common_git = os.path.join(_repo_root, common_git)
    main_root = os.path.dirname(common_git)
    os.environ.setdefault("AM_DB_PATH", os.path.join(main_root, "am_discovery.db"))
except Exception:
    pass  # fall back to server.py's own default

server_py = os.path.join(_repo_root, "server.py")
sys.argv = [server_py, "--debug"] + sys.argv[1:]
with open(server_py) as f:
    exec(compile(f.read(), server_py, "exec"), {"__file__": server_py, "__name__": "__main__"})
