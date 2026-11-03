#!/usr/bin/env python3
"""Copy backend/handler.py into the inline Lambda code of backend/template.yaml.

CloudFormation can only take inline Lambda code inside the template, so the
template carries a copy of handler.py. Edit handler.py, then run:

    python backend/sync_template.py          # update template.yaml
    python backend/sync_template.py --check  # exit 1 if they differ (used by tests/CI)
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
HANDLER = HERE / "handler.py"
TEMPLATE = HERE / "template.yaml"
BEGIN = "# --- BEGIN handler.py"
END = "# --- END handler.py ---"
INLINE_LIMIT = 4096  # CloudFormation limit for inline ZipFile code (characters)


def build(template_text: str, handler_text: str) -> str:
    lines = template_text.splitlines(keepends=True)
    start = next(i for i, line in enumerate(lines) if line.lstrip().startswith(BEGIN))
    end = next(i for i, line in enumerate(lines) if line.lstrip().startswith(END))
    indent = lines[start][: len(lines[start]) - len(lines[start].lstrip())]
    body = [(indent + line if line.strip() else "\n") for line in handler_text.splitlines(keepends=True)]
    if body and not body[-1].endswith("\n"):
        body[-1] += "\n"
    return "".join(lines[: start + 1] + body + lines[end:])


def inline_code(template_text: str) -> str:
    """The code CloudFormation will deploy (markers included), de-indented."""
    lines = template_text.splitlines(keepends=True)
    start = next(i for i, line in enumerate(lines) if line.lstrip().startswith(BEGIN))
    end = next(i for i, line in enumerate(lines) if line.lstrip().startswith(END))
    indent = len(lines[start]) - len(lines[start].lstrip())
    return "".join(line[indent:] if line.strip() else "\n" for line in lines[start : end + 1])


def main() -> int:
    handler_text = HANDLER.read_text(encoding="utf-8")
    current = TEMPLATE.read_text(encoding="utf-8")
    updated = build(current, handler_text)
    size = len(inline_code(updated))
    if size > INLINE_LIMIT:
        print(f"ERROR: inline code is {size} chars; CloudFormation allows {INLINE_LIMIT}. Shorten handler.py.")
        return 1
    if "--check" in sys.argv:
        if updated != current:
            print("template.yaml is out of date - run: python backend/sync_template.py")
            return 1
        print(f"template.yaml is in sync with handler.py ({size}/{INLINE_LIMIT} chars inline)")
        return 0
    if updated != current:
        TEMPLATE.write_text(updated, encoding="utf-8")
        print(f"Updated template.yaml ({size}/{INLINE_LIMIT} chars inline)")
    else:
        print(f"template.yaml already up to date ({size}/{INLINE_LIMIT} chars inline)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
