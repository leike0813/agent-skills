"""Shared JSON reporting for the two standalone helper commands."""
import argparse
import json


class Failure(Exception):
    def __init__(self, status, code, detail, path=None):
        super().__init__(detail)
        self.status = status
        self.issue = {"code": code, "path": str(path) if path is not None else None,
                      "detail": str(detail)}


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise Failure(2, "invalid-argument", message)


def run(operation, action):
    """action returns a data object; expected errors become one JSON report."""
    status, data, issues = 0, {}, []
    try:
        data = action()
    except Failure as exc:
        status, issues = exc.status, [exc.issue]
    except (OSError, UnicodeError) as exc:
        status = 5
        issues = [{"code": "io-error", "path": getattr(exc, "filename", None),
                   "detail": str(exc)}]
    print(json.dumps({"ok": status == 0, "operation": operation, "data": data,
                      "issues": issues}, ensure_ascii=False))
    return status
