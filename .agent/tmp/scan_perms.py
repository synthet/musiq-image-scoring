import json, glob, os, collections, shlex, re

base = "/mnt/c/Users/dmnsy/.claude/projects"
files = sorted(glob.glob(os.path.join(base, "*", "*.jsonl")), key=os.path.getmtime, reverse=True)[:50]
bash = collections.Counter()
mcp = collections.Counter()


def lead(cmd):
    cmd = cmd.strip()
    seg = re.split(r'\|\||&&|\||;', cmd)[0].strip()
    try:
        toks = shlex.split(seg)
    except Exception:
        toks = seg.split()
    i = 0
    while i < len(toks):
        t = toks[i]
        if "=" in t and not t.startswith("-") and "/" not in t.split("=")[0]:
            i += 1; continue
        if t in ("sudo", "command", "nohup", "setsid"):
            i += 1; continue
        if t == "timeout":
            i += 1
            while i < len(toks) and (toks[i].startswith("-") or toks[i].replace(".", "").isdigit() or toks[i][-1:] in "smhd"):
                i += 1
            continue
        break
    toks = toks[i:]
    if not toks:
        return None
    c0 = os.path.basename(toks[0])
    c1 = toks[1] if len(toks) > 1 and not toks[1].startswith("-") else ""
    return c0, c1


for f in files:
    try:
        fh = open(f, encoding="utf-8")
    except Exception:
        continue
    for line in fh:
        try:
            obj = json.loads(line)
        except Exception:
            continue
        msg = obj.get("message") or {}
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for item in content:
            if not isinstance(item, dict) or item.get("type") != "tool_use":
                continue
            name = item.get("name", "")
            if name == "Bash":
                cmd = (item.get("input") or {}).get("command", "")
                r = lead(cmd)
                if r:
                    c0, c1 = r
                    bash[f"{c0} {c1}".strip()] += 1
            elif name.startswith("mcp__"):
                mcp[name] += 1

print("=== BASH (top 70) ===")
for k, v in bash.most_common(70):
    print(f"{v:5d}  {k}")
print("\n=== MCP (top 40) ===")
for k, v in mcp.most_common(40):
    print(f"{v:5d}  {k}")
