from pathlib import Path
import py_compile


def test_server_python_files_compile() -> None:
    for path in Path("AEGIS/server").rglob("*.py"):
        py_compile.compile(str(path), doraise=True)
