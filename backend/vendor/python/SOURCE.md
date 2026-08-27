# Python 3.11 Windows installer provenance

Darkstar targets the official CPython 3.11 Windows x64 installer published by the Python Software Foundation.

- Version: Python 3.11.9
- Asset: `python-3.11.9-amd64.exe`
- Official source: `https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe`
- SHA-256: `5ee42c4eee1e6b4464bb23722f90b45303f79442df63083f05322f1785f5fdde`
- Expected Authenticode publisher: Python Software Foundation

Python 3.11.9 is the final Python 3.11 release for which python.org published Windows binary installers. Newer Python 3.11 security releases are source-only.

The installer is launched interactively. Darkstar does not pass silent-install or feature-selection switches; the user controls the official installer UI. Darkstar verifies both the pinned SHA-256 and the Windows Authenticode signature before execution.
