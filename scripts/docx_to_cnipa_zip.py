"""Convert supported CNIPA template DOCX documents into electronic filing ZIPs."""

import argparse
from pathlib import Path
import sys

from build_filing import build
from filing_ir import PATENT_TYPES


def main():
    parser = argparse.ArgumentParser(description="从审定 DOCX 生成 CNIPA 电子申请 XML ZIP")
    parser.add_argument("docx", type=Path)
    parser.add_argument("zip", type=Path)
    parser.add_argument("--patent-type", choices=PATENT_TYPES, default="invention", help="申请类别，默认发明")
    args = parser.parse_args()
    return build(args.docx, zip_path=args.zip, docx_only_input=True, patent_type=args.patent_type)


if __name__ == "__main__":
    sys.exit(main())
