"""Dev server launcher — sets AM_DB_PATH to the main repo root before starting.

Works correctly in git worktrees by using `git rev-parse --show-toplevel`
on the common git dir, which always resolves to the main repo regardless of
which worktree this script is run from.

Imports server as a normal module rather than exec'ing it with ``__name__ ==
"__main__"``. Exec'ing creates two distinct module objects when the API
blueprints later ``import server`` — scheduler state set on one copy is
invisible to the other, causing bugs like ``/api/system/status`` returning a
stale ``_next_run_at``.
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

# Add repo root to sys.path so ``import server`` resolves.
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

# Forward remaining CLI args to server.main() via sys.argv.
sys.argv = ["server.py", "--debug"] + sys.argv[1:]

import server  # noqa: E402

server.main()
