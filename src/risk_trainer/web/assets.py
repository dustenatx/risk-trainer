"""Content-versioned static files (PRD R12).

CloudFront caches /static/* with the managed CachingOptimized policy, which leaves query strings
out of the cache key, so the version goes in the path: /static/<version>/app.css.
"""

import hashlib
import os
import re
from pathlib import Path

from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

VERSION_LENGTH = 12
_VERSION_PATTERN = re.compile(rf"[0-9a-f]{{{VERSION_LENGTH}}}")
CACHE_CURRENT = "public, max-age=31536000, immutable"
CACHE_OTHER_VERSION = "no-store"


def asset_version(static_dir: Path) -> str:
    """Hash every file under the static folder, so any change gives a new version."""
    digest = hashlib.sha256()
    files = sorted(
        (path for path in static_dir.rglob("*") if path.is_file()),
        key=lambda path: path.relative_to(static_dir).as_posix(),
    )
    for path in files:
        digest.update(path.relative_to(static_dir).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()[:VERSION_LENGTH]


class VersionedStaticFiles(StaticFiles):
    """Serves /static/<version>/<file>, leaving all file lookup to StaticFiles.

    The current version is cached for a year. Any other well-formed version (a page rendered
    just before a deploy) gets the current file with no-store, so the edge never keeps an error
    or an old key for long. Anything else is a 404.
    """

    def __init__(self, *, directory: Path, version: str) -> None:
        super().__init__(directory=directory)
        self.version = version

    async def get_response(self, path: str, scope: Scope) -> Response:
        version, separator, rest = path.partition(os.sep)
        if not separator or not _VERSION_PATTERN.fullmatch(version):
            raise HTTPException(status_code=404)
        response = await super().get_response(rest, scope)
        response.headers["cache-control"] = (
            CACHE_CURRENT if version == self.version else CACHE_OTHER_VERSION
        )
        return response
