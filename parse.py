import json

with open("project_items.json", encoding="utf-16") as f:
    data = json.load(f)

for item in data.get("items", []):
    if item.get("Stage") == "Ready":
        content = item.get("content", {})
        print(f"#{content.get('number')} {content.get('title')} ({item.get('priority')}) - {content.get('repository')}")
