"""Inspect and snapshot an Agent Skill package without interpreting its workflow."""
from argparse import RawDescriptionHelpFormatter
import os
from pathlib import Path
import shutil
import stat
import sys

from _cli import Failure, Parser, run


def inspect(source):
    try:
        import yaml
    except ImportError:
        raise Failure(2, "invalid-argument", "PyYAML is required; provide it in the calling environment")
    root = Path(source).resolve()
    skill = root / "SKILL.md"
    if not root.is_dir() or not skill.is_file():
        raise Failure(3, "invalid-source", "Expected a directory containing SKILL.md", skill)
    lines = skill.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0] != "---" or "---" not in lines[1:]:
        raise Failure(3, "invalid-source", "Missing YAML frontmatter delimiters", skill)
    # YAML timestamps are text metadata, not Python date objects in the JSON report.
    class Loader(yaml.SafeLoader):
        pass
    Loader.yaml_implicit_resolvers = {
        key: [(tag, regex) for tag, regex in values
              if tag != "tag:yaml.org,2002:timestamp"]
        for key, values in Loader.yaml_implicit_resolvers.items()
    }
    try:
        metadata = yaml.load("\n".join(lines[1:lines.index("---", 1)]), Loader=Loader)
    except yaml.YAMLError as exc:
        raise Failure(3, "invalid-source", str(exc), skill)
    if not isinstance(metadata, dict) or not all(isinstance(k, str) for k in metadata):
        raise Failure(3, "invalid-source", "Frontmatter must be a string-keyed mapping", skill)

    def require(valid, detail):
        if not valid:
            raise Failure(3, "invalid-source", detail, skill)

    name = metadata.get("name")
    require(isinstance(name, str) and 1 <= len(name) <= 64, "name must contain 1–64 characters")
    require(name == name.lower() and all(c.isalnum() or c == "-" for c in name)
            and not name.startswith("-") and not name.endswith("-") and "--" not in name,
            "name must use lowercase letters, numbers and single hyphens")
    require(name == root.name, "name must match the package directory name")
    description = metadata.get("description")
    require(isinstance(description, str) and bool(description.strip()) and len(description) <= 1024,
            "description must contain 1–1024 characters")
    for key in ("license", "compatibility"):
        if key in metadata:
            require(isinstance(metadata[key], str), f"{key} must be a string")
    if "compatibility" in metadata:
        require(len(metadata["compatibility"]) <= 500, "compatibility exceeds 500 characters")
    if "metadata" in metadata:
        require(isinstance(metadata["metadata"], dict) and
                all(isinstance(k, str) and isinstance(v, str) for k, v in metadata["metadata"].items()),
                "metadata must map strings to strings")
    if "allowed-tools" in metadata:
        value = metadata["allowed-tools"]
        require(isinstance(value, str) or (isinstance(value, list) and
                all(isinstance(item, str) for item in value)),
                "allowed-tools must be text or a platform tool list")
    # Extra platform fields stay available, but arbitrary YAML objects cannot form JSON metadata.
    def json_value(value):
        return (value is None or isinstance(value, (str, int, float, bool)) or
                isinstance(value, list) and all(json_value(v) for v in value) or
                isinstance(value, dict) and all(isinstance(k, str) and json_value(v)
                                                for k, v in value.items()))
    try:
        compatible = json_value(metadata)
    except RecursionError:
        compatible = False
    require(compatible, "Frontmatter values must be JSON-compatible and acyclic")
    files = []

    def inventory(directory, ancestors):
        real = directory.resolve()
        if real in ancestors:
            raise Failure(5, "io-error", "Directory symlink cycle cannot be copied", directory)
        for entry in sorted(directory.iterdir()):
            mode = entry.stat().st_mode
            if not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
                raise Failure(5, "io-error", "Only regular files and directories can be snapshotted", entry)
            kind = "symlink" if entry.is_symlink() else "directory" if entry.is_dir() else "file"
            files.append({"path": entry.relative_to(root).as_posix(), "type": kind})
            if entry.is_dir():
                inventory(entry, ancestors | {real})
    inventory(root, set())
    return {"source_root": str(root), "metadata": metadata,
            "files": sorted(files, key=lambda item: item["path"])}


def copy(source, output=None):
    report = inspect(source)
    root = Path(report["source_root"])
    destination = Path(output or f"{report['metadata']['name']}-graph").absolute()
    resolved = destination.resolve()
    if os.path.lexists(destination) or os.path.lexists(resolved) or resolved == root or root in resolved.parents or resolved in root.parents:
        raise Failure(4, "output-conflict", "Output must be new and must not overlap the source", destination)
    destination = resolved
    try:
        destination.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        raise Failure(4, "output-conflict", "Output already exists", destination)
    snapshot = destination / "source" / root.name
    # Materialize links so a copied package does not depend on the original link targets.
    try:
        shutil.copytree(root, snapshot, symlinks=False, copy_function=shutil.copy2)
    except shutil.Error as exc:
        raise Failure(5, "io-error", str(exc), snapshot)
    return {"output_dir": str(destination), "source_dir": str(snapshot)}


def main():
    parser = Parser(
        description="""Inspect a Skill package read-only, or copy its complete snapshot into a new
application directory. Existing output directories are never overwritten.""",
        epilog="""The source positional is a Skill package directory containing SKILL.md.
inspect is read-only. copy requires a new output directory that does not overlap
the source; --output defaults to ./<skill-name>-graph.

Except --help, output is one JSON object on stdout:
  {"ok": true, "operation": "inspect", "data": {...}, "issues": []}
Success data contains source_root, metadata, and files for inspect, or output_dir
and source_dir for copy. On failure, ok is false, data is {}, and issues lists
code, path, and detail.

Exit codes: 0 success; 2 invalid argument (including missing PyYAML); 3 invalid
source; 4 output conflict; 5 I/O error. copy may leave a partial new directory
after an I/O failure.

Examples:
  python skill_package.py inspect path/to/skill
  python skill_package.py copy path/to/skill --output path/to/new-app

--help prints text and exits 0 without an operation.""",
        formatter_class=RawDescriptionHelpFormatter,
    )
    commands = parser.add_subparsers(dest="operation", required=True, parser_class=Parser)
    for command in ("inspect", "copy"):
        sub = commands.add_parser(
            command,
            help="Read metadata and inventory" if command == "inspect" else "Create a fresh application with source snapshot",
            description=(
                "Validate one Skill package and inventory it without writing."
                if command == "inspect"
                else """Validate a Skill package and copy its complete snapshot into a new
application directory. The destination is never overwritten."""
            ),
            epilog=(
                """The source positional is the Skill package directory containing SKILL.md.
This operation is read-only.

Output is one JSON object on stdout:
  {"ok": true, "operation": "inspect", "data": {"source_root": "...",
   "metadata": {...}, "files": [{"path": "...", "type": "file"}]},
   "issues": []}
On failure, ok is false, data is {}, and issues lists code, path, and detail.

Exit codes: 0 success; 2 invalid argument (including missing PyYAML); 3 invalid
source; 5 I/O error.

Example:
  python skill_package.py inspect path/to/skill

--help prints text and exits 0 without inspecting files."""
                if command == "inspect"
                else """The source positional is the Skill package directory containing SKILL.md.
--output names a new application directory and defaults to
./<skill-name>-graph. It must not exist or overlap the source. The snapshot is
placed under <output>/source/<skill-name>/ and links are materialized.

Output is one JSON object on stdout:
  {"ok": true, "operation": "copy", "data": {"output_dir": "...",
   "source_dir": "..."}, "issues": []}
On failure, ok is false, data is {}, and issues lists code, path, and detail.

Exit codes: 0 success; 2 invalid argument (including missing PyYAML); 3 invalid
source; 4 output conflict; 5 I/O error. An I/O failure can leave a partial new
directory.

Example:
  python skill_package.py copy path/to/skill --output path/to/new-app

--help prints text and exits 0 without creating files."""
            ),
            formatter_class=RawDescriptionHelpFormatter,
        )
        sub.add_argument("source", help="Skill package directory containing SKILL.md")
        if command == "copy":
            sub.add_argument("--output", help="New application directory; default: CWD/<skill-name>-graph")
    args = parser.parse_args()
    return inspect(args.source) if args.operation == "inspect" else copy(args.source, args.output)


if __name__ == "__main__":
    operation = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] in {"inspect", "copy"} else None
    sys.exit(run(operation, main))
