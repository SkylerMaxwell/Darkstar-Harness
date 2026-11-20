# SPDX-License-Identifier: LicenseRef-Darkstar-3.0
"""Moves commits between an agent's repository and Darkstar's vault.

The sandbox never sees the vault. Darkstar carries commits in git bundles
over stdin and stdout:

    darkstar-git receive          read a bundle on stdin; its branches become
                                  refs/remotes/vault/<branch>, its change requests
                                  refs/remotes/vault/requests/<id>
    darkstar-git send <branch>    write a bundle of <branch> with the commits the
                                  vault does not have yet; exit 3 when it has them all
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile

WORKSPACE = os.environ["DARKSTAR_WORKSPACE"]
BRANCH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,199}$")


def git(*args: str, **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", WORKSPACE, *args], **kwargs)


def receive() -> int:
    handle, bundle = tempfile.mkstemp(prefix="darkstar-in-", suffix=".bundle")
    try:
        with os.fdopen(handle, "wb") as target:
            shutil.copyfileobj(sys.stdin.buffer, target, 1024 * 1024)
        result = git("fetch", "--quiet", "--force", "--no-tags", bundle,
                     "+refs/heads/*:refs/remotes/vault/*", "+refs/requests/*:refs/remotes/vault/requests/*")
        return result.returncode
    finally:
        os.unlink(bundle)


def send(branch: str) -> int:
    if not BRANCH.match(branch) or ".." in branch:
        print("darkstar-git: invalid branch", file=sys.stderr)
        return 2
    ref = f"refs/heads/{branch}"
    fresh = git("rev-list", "--count", ref, "--not", "--remotes=vault", capture_output=True, text=True)
    if fresh.returncode != 0:
        sys.stderr.write(fresh.stderr)
        return fresh.returncode
    if int(fresh.stdout.strip() or "0") == 0:
        return 3
    handle, bundle = tempfile.mkstemp(prefix="darkstar-out-", suffix=".bundle")
    os.close(handle)
    try:
        created = git("bundle", "create", "--quiet", bundle, ref, "--not", "--remotes=vault", capture_output=True)
        if created.returncode != 0:
            sys.stderr.write(created.stderr.decode("utf-8", "replace"))
            return created.returncode
        with open(bundle, "rb") as source:
            shutil.copyfileobj(source, sys.stdout.buffer, 1024 * 1024)
        sys.stdout.buffer.flush()
        return 0
    finally:
        os.unlink(bundle)


def main(argv: list[str]) -> int:
    if argv[:1] == ["receive"]:
        return receive()
    if len(argv) == 2 and argv[0] == "send":
        return send(argv[1])
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
