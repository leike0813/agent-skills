"""Build editable DOCX and CNIPA ZIP from an approved filing document."""

import argparse
import os
from pathlib import Path
import sys
from zipfile import BadZipFile

from filing_docx_reader import read_docx
from filing_ir import PATENT_TYPES, InvalidDocument, UnsupportedDocument
from filing_xml_writer import render_zip


def check_targets(targets):
    for target in targets:
        if target.exists() or target.is_symlink():
            raise FileExistsError(f"目标已存在 {target}")
        if not target.parent.is_dir():
            raise FileNotFoundError(f"目标目录不存在 {target.parent}")
    if len({target.resolve() for target in targets}) != len(targets):
        raise InvalidDocument("输出路径必须不同")


def write_outputs(outputs):
    created = []
    try:
        for path, data in outputs:
            with path.open("xb") as output:
                stat = os.fstat(output.fileno())
                created.append((path, stat))
                output.write(data)
    except (OSError, KeyboardInterrupt):
        for path, original in reversed(created):
            try:
                if os.path.samestat(path.stat(follow_symlinks=False), original):
                    path.unlink()
            except FileNotFoundError:
                pass
            except OSError as exc:
                print(f"无法清理本次写出的文件 {path} ({exc})", file=sys.stderr)
        raise


def build(source, *, docx=None, zip_path=None, docx_only_input=False, patent_type="invention"):
    targets = [path for path in (docx, zip_path) if path is not None]
    try:
        check_targets(targets)
        if docx_only_input or source.suffix.lower() == ".docx":
            filing = read_docx(source, patent_type)
        elif source.suffix.lower() == ".md":
            from filing_markdown import read_markdown

            filing = read_markdown(source, patent_type)
        else:
            raise UnsupportedDocument("输入需要结构化 Markdown (.md) 或约定版式 DOCX (.docx)")
        if patent_type == "design":
            filing.validate()
        else:
            filing.validate(patent_type)
        outputs = []
        if docx is not None:
            from filing_docx_writer import render_docx

            outputs.append((docx, render_docx(filing)))
        if zip_path is not None:
            outputs.append((zip_path, render_zip(filing)))
        write_outputs(outputs)
    except UnsupportedDocument as exc:
        print(f"{source} · {exc}", file=sys.stderr)
        return 3
    except (OSError, BadZipFile, InvalidDocument, UnicodeError) as exc:
        print(f"{source} → {', '.join(map(str, targets))} · {exc}", file=sys.stderr)
        return 1
    for target in targets:
        print(target)
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="从审定 Markdown 或 DOCX 生成申请文件 DOCX 及 CNIPA XML ZIP",
        epilog="示例: %(prog)s 审定稿.md --docx 申请文件.docx --zip 申请文件.zip",
    )
    parser.add_argument("input", type=Path, help="结构化 Markdown 或约定版式 DOCX")
    parser.add_argument("--patent-type", choices=PATENT_TYPES, default="invention", help="申请类别，默认发明")
    parser.add_argument("--docx", type=Path, help="可编辑 DOCX 输出路径")
    parser.add_argument("--zip", type=Path, help="电子申请 XML ZIP 输出路径")
    args = parser.parse_args()
    if args.docx is None and args.zip is None:
        parser.print_usage(sys.stderr)
        print("至少指定 --docx 或 --zip", file=sys.stderr)
        return 1
    return build(args.input, docx=args.docx, zip_path=args.zip, patent_type=args.patent_type)


if __name__ == "__main__":
    sys.exit(main())
