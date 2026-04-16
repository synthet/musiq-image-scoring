import json
import sys

file_path = r'c:\Users\dmnsy\.claude\projects\d--Projects-image-scoring-backend\3d8d3903-c0d3-45d9-8a54-73dece21c79c.jsonl'

with open(file_path, 'r', encoding='utf-8') as f:
    for line in f:
        try:
            data = json.loads(line)
            t = data.get('type')
            if t == 'user':
                content = data.get('message', {}).get('content', [])
                print("--- USER ---")
                for item in content:
                    if item.get('type') == 'text':
                        print(item.get('text'))
                    elif item.get('type') == 'image':
                        print("[IMAGE ATTACHED]")
            elif t == 'assistant':
                print("--- AI ---")
                message = data.get('message', {})
                content = message.get('content', [])
                if isinstance(content, list):
                    for item in content:
                        if item.get('type') == 'text':
                            print(item.get('text'))
                        elif item.get('type') == 'tool_use':
                            print(f"[TOOL USE: {item.get('name')}]")
                            # print(json.dumps(item.get('input'), indent=2))
                elif isinstance(content, str):
                    print(content)
            elif t == 'tool-use': # adjust if needed
                print(f"--- TOOL USE: {data.get('name')} ---")
            elif t == 'tool-result':
                print(f"--- TOOL RESULT ---")
            elif t == 'ai-title':
                print(f"=== {data.get('aiTitle')} ===")
        except Exception as e:
            pass
