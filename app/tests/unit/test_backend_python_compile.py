import py_compile
import tempfile
from pathlib import Path


IGNORED_PARTS = {".venv", "__pycache__", ".pytest_cache"}


def _server_python_files() -> list[Path]:
    return [
        path
        for path in Path("app/server").rglob("*.py")
        if not any(part in IGNORED_PARTS for part in path.parts)
    ]


def test_server_python_files_compile() -> None:
    with tempfile.TemporaryDirectory() as cache_dir:
        for path in _server_python_files():
            relative_name = path.with_suffix(".pyc").as_posix().replace("/", "_")
            cfile = str(Path(cache_dir) / relative_name)
            py_compile.compile(str(path), cfile=cfile, doraise=True)
