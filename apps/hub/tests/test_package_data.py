"""The pages the server hands out must be in the package, not only in the source tree.

pip, pipx and the Windows installer copy only what `package-data` lists. A file the server serves but the
package leaves out is a 404 there: the page loads without its style and script.
"""

import fnmatch
import tomllib
from pathlib import Path

from hub import server


def test_every_served_static_file_is_packaged():
    root = Path(__file__).resolve().parents[1]
    data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    globs = data["tool"]["setuptools"]["package-data"]["hub"]
    for name, _kind, _cacheable in server.STATIC.values():
        rel = f"web/{name}"
        assert (root / "src" / "hub" / rel).is_file(), f"{rel} is served but missing from the source tree"
        assert any(fnmatch.fnmatch(rel, g) for g in globs), f"{rel} is served but not listed in package-data"
