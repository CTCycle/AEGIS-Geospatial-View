import ast
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


def _parse_server_file(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def test_server_python_files_do_not_define_nested_functions() -> None:
    violations: list[str] = []
    function_types = (ast.FunctionDef, ast.AsyncFunctionDef)

    for path in _server_python_files():
        tree = _parse_server_file(path)
        for node in ast.walk(tree):
            if not isinstance(node, function_types):
                continue
            for child in ast.iter_child_nodes(node):
                if isinstance(child, ast.ClassDef):
                    continue
                for descendant in ast.walk(child):
                    if isinstance(descendant, function_types):
                        violations.append(
                            f"{path}:{descendant.lineno}:{descendant.name}"
                        )

    assert violations == []


def test_server_python_files_do_not_import_inside_functions_or_classes() -> None:
    violations: list[str] = []
    boundary_types = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
    import_types = (ast.Import, ast.ImportFrom)

    for path in _server_python_files():
        tree = _parse_server_file(path)
        for node in ast.walk(tree):
            if not isinstance(node, boundary_types):
                continue
            for child in ast.walk(node):
                if child is node:
                    continue
                if isinstance(child, import_types):
                    violations.append(f"{path}:{child.lineno}")

    assert violations == []


def test_no_conditional_imports_in_server_python_files() -> None:
    violations: list[str] = []
    import_types = (ast.Import, ast.ImportFrom)

    for path in _server_python_files():
        tree = _parse_server_file(path)
        for parent in ast.walk(tree):
            for child in ast.iter_child_nodes(parent):
                setattr(child, "_parent", parent)
        for node in ast.walk(tree):
            if not isinstance(node, import_types):
                continue
            parent = getattr(node, "_parent", None)
            if not isinstance(parent, ast.Module):
                violations.append(f"{path}:{node.lineno}")

    assert violations == []


def test_server_python_files_do_not_exceed_1000_lines() -> None:
    violations: list[str] = []
    for path in _server_python_files():
        line_count = len(path.read_text(encoding="utf-8").splitlines())
        if line_count > 1000:
            violations.append(f"{path}:{line_count}")
    assert violations == []


def test_domain_layer_contains_no_runtime_or_configuration_modules() -> None:
    domain_path = Path("app") / "server" / "domain"
    assert not (domain_path / "settings.py").exists()
    assert not (domain_path / "job_state.py").exists()
