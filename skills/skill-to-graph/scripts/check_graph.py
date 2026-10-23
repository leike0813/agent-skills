"""Statically check a generated LangGraph application without importing it."""
from argparse import RawDescriptionHelpFormatter
import ast
import json
import os
from pathlib import Path
import sys
import tokenize

from _cli import Failure, Parser, run


CONFIG_NAME = "langgraph.json"
SKIPPED_DIRS = {".git", ".venv", "venv", "__pycache__", "node_modules", "build", "dist"}


def invalid(detail, path):
    raise Failure(6, "invalid-artifact", detail, path)


def local_path(root, value, label, kind=None):
    """Return an application-local path, rejecting values that cannot travel with it."""
    if not isinstance(value, str) or not value:
        invalid(f"{label} must be a non-empty path", CONFIG_NAME)
    path = root / value
    if not path.resolve().is_relative_to(root):
        invalid(f"{label} must stay inside the application directory", path)
    expected = {"file": path.is_file(), "directory": path.is_dir()}.get(kind)
    if expected is False:
        invalid(f"{label} does not exist as a {kind}", path)
    return path


def check_entry(root, value, label):
    """Check a file or determinable local module entry.

    Returns the entry string when it names an external module, which static
    checks cannot locate; the caller records it as unresolvable.
    """
    if not isinstance(value, str) or value.count(":") != 1:
        invalid(f"{label} must use path.py:object or module:object", CONFIG_NAME)
    location, object_name = value.split(":", 1)
    if not location or not object_name or object_name != object_name.strip():
        invalid(f"{label} must name an object", CONFIG_NAME)
    if location.endswith(".py"):
        local_path(root, location, label, "file")
        return None
    if "/" in location or not all(part.isidentifier() for part in location.split(".")):
        invalid(f"{label} must use path.py:object or module:object", CONFIG_NAME)
    first = location.split(".", 1)[0]
    if not (root / first).exists() and not (root / f"{first}.py").is_file():
        return value  # An external installed module is outside static inspection.
    module = root.joinpath(*location.split(".")).with_suffix(".py")
    package = root.joinpath(*location.split(".")) / "__init__.py"
    if not module.is_file() and not package.is_file():
        invalid(f"{label} points to a missing local module", CONFIG_NAME)
    return None


def check_config(root, config):
    if not isinstance(config, dict):
        invalid("langgraph.json must contain a JSON object", CONFIG_NAME)

    unresolved = {}

    def note_entry(label, value):
        external = check_entry(root, value, label)
        if external is not None:
            unresolved[label] = external

    graphs = config.get("graphs")
    if not isinstance(graphs, dict) or not graphs:
        invalid("graphs must be a non-empty object", CONFIG_NAME)
    for graph_id, graph in graphs.items():
        if not isinstance(graph_id, str) or not graph_id:
            invalid("graph IDs must be non-empty strings", CONFIG_NAME)
        value = graph.get("path") if isinstance(graph, dict) else graph
        if not isinstance(value, str):
            invalid(f"graphs.{graph_id} must be a path string or an object with path", CONFIG_NAME)
        note_entry(f"graphs.{graph_id}", value)

    source = config.get("source")
    dependencies = config.get("dependencies")
    if source is not None:
        if dependencies is not None:
            invalid("source and dependencies are mutually exclusive", CONFIG_NAME)
        if (not isinstance(source, dict) or source.get("kind") != "uv"
                or not isinstance(source.get("package"), str) or not source["package"]
                or config.get("python_version") is None):
            invalid("source must be a uv object with package and python_version", CONFIG_NAME)
        local_path(root, source.get("root"), "source.root", "directory")
    else:
        if not isinstance(dependencies, list):
            invalid("dependencies must be an array when source is absent", CONFIG_NAME)
        for dependency in dependencies:
            if not isinstance(dependency, str) or not dependency:
                invalid("dependencies must contain non-empty strings", CONFIG_NAME)
            if dependency == "." or dependency.startswith(("./", "../")):
                local_path(root, dependency, f"dependency {dependency}", "directory")

    env = config.get("env")
    if isinstance(env, str):
        local_path(root, env, "env", "file")
    elif env is not None and not isinstance(env, dict):
        invalid("env must be a path or an object", CONFIG_NAME)

    pip_config = config.get("pip_config_file")
    if pip_config is not None:
        local_path(root, pip_config, "pip_config_file", "file")

    for key in ("auth", "encryption"):
        resource = config.get(key)
        if resource is None:
            continue
        if not isinstance(resource, dict) or "path" not in resource:
            invalid(f"{key} must be an object with path", CONFIG_NAME)
        note_entry(f"{key}.path", resource["path"])
    for key in ("checkpointer", "http"):
        resource = config.get(key)
        if isinstance(resource, dict) and "path" in resource:
            note_entry(f"{key}.path", resource["path"])
        if isinstance(resource, dict) and key == "http" and "app" in resource:
            note_entry("http.app", resource["app"])
    return graphs, unresolved


def python_files(root):
    def unreadable(exc):
        raise exc
    for directory, dirs, files in os.walk(root, onerror=unreadable):
        current = Path(directory)
        dirs[:] = sorted(name for name in dirs
                         if name not in SKIPPED_DIRS and not (current == root and name == "source"))
        for name in sorted(files):
            if name.endswith(".py"):
                yield current / name


def check(directory):
    root = Path(directory).resolve()
    if not root.is_dir():
        raise Failure(5, "io-error", "Application directory does not exist", root)
    config_path = root / CONFIG_NAME
    if not config_path.is_file():
        invalid("langgraph.json is required", CONFIG_NAME)
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        invalid(f"Invalid JSON: {exc.msg} at line {exc.lineno}", CONFIG_NAME)

    graphs, unresolved = check_config(root, config)
    checked = [CONFIG_NAME]
    for path in python_files(root):
        relative = path.relative_to(root).as_posix()
        try:
            with tokenize.open(path) as source:
                ast.parse(source.read(), filename=relative)
        except (SyntaxError, UnicodeDecodeError) as exc:
            detail = getattr(exc, "msg", str(exc))
            line = getattr(exc, "lineno", None)
            invalid(f"Python syntax error: {detail}" + (f" at line {line}" if line else ""), relative)
        except TypeError as exc:
            invalid(f"Readable Python source required: {exc}", relative)
        checked.append(relative)
    return {"checked_files": sorted(checked), "graph_entries": graphs,
            "unresolved_entries": unresolved}


def main():
    parser = Parser(
        description="""Statically check generated Python syntax, langgraph.json structure,
local graph entries and explicit resource paths. External module entries are
reported as statically unresolvable; modules, graphs and models are
never imported or run.""",
        epilog="""The directory positional is the generated LangGraph application directory.
This operation is read-only. It checks Python syntax and configuration, explicit
local entries, and resource paths without importing modules or running graphs.

Except --help, output is one JSON object on stdout:
  {"ok": true, "operation": "check", "data": {"checked_files": [...],
   "graph_entries": {...}, "unresolved_entries": {...}}, "issues": []}
On failure, ok is false, data is {}, and issues lists code, path, and detail.

Exit codes: 0 success; 2 invalid argument; 5 I/O error (including a missing
directory); 6 invalid artifact.

Example:
  python check_graph.py path/to/generated-app

--help prints text and exits 0 without checking files.""",
        formatter_class=RawDescriptionHelpFormatter,
    )
    parser.add_argument("directory", help="Generated LangGraph application directory")
    args = parser.parse_args()
    return check(args.directory)


if __name__ == "__main__":
    sys.exit(run("check", main))
