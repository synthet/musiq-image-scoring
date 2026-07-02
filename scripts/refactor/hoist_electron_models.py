#!/usr/bin/env python3
"""Move nested BaseModel classes in electron router to module level."""

from pathlib import Path

path = Path(__file__).resolve().parents[2] / "modules" / "api" / "routers" / "electron.py"
lines = path.read_text(encoding="utf-8").splitlines(keepends=True)

factory_start = next(i for i, l in enumerate(lines) if l.startswith("def create_electron_router"))
factory_end = next(i for i, l in enumerate(lines[factory_start:], factory_start) if l.strip() == "return router")

extracted: list[str] = []
keep: list[str] = []
i = factory_start
while i < len(lines):
    line = lines[i]
    if i >= factory_start and i < factory_end and line.startswith("    class ") and "(BaseModel)" in line:
        block = []
        while i < factory_end:
            block.append(lines[i][4:] if lines[i].startswith("    ") else lines[i])
            i += 1
            if i < factory_end and lines[i].startswith("    class ") and "(BaseModel)" in lines[i]:
                break
            if i < factory_end and lines[i].startswith("    @router"):
                break
            if i < factory_end and lines[i].strip() == "# ───" and not any(c.startswith(" ") for c in block[-1:]):
                break
        extracted.extend(block)
        extracted.append("\n")
        continue
    keep.append(line)
    i += 1

insert_at = factory_start
new_lines = keep[:insert_at] + ["\n"] + extracted + ["\n"] + keep[insert_at:]
path.write_text("".join(new_lines), encoding="utf-8")
print(f"moved {len(extracted)} lines of model classes to module level")
