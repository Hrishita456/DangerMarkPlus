"""Lambda-only filesystem setup; application and analysis logic stay unchanged."""
import os
import shutil
from pathlib import Path

cache = Path('/tmp/danger-mark/artifacts')
if not cache.exists():
    cache.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree('/opt/pilot-artifacts', cache)
    # Source files can have owner-only modes; this invocation owns its copy.
    for path in cache.rglob('*'):
        path.chmod(0o700 if path.is_dir() else 0o600)
os.execvp('python', ['python', '/app/infra/container_start.py'])
