
import os

from modules import db, utils


def build_tree_dict(paths):
    # Sort paths
    paths = sorted(paths)
    nodes = {}
    roots = []
    
    for path in paths:
        path = os.path.normpath(path)
        parent = os.path.dirname(path)
        
        node = {"name": os.path.basename(path) if os.path.basename(path) else path, "path": path, "children": []}
        nodes[path] = node
        
        if parent == path or not parent: # Root
             roots.append(node)
        elif parent in nodes:
             nodes[parent]["children"].append(node)
        else:
             roots.append(node)
    
    return roots

def tree_to_html(nodes, selected_path=None):
    html = '<ul style="list-style-type: none; padding-left: 20px; margin: 0;">'
    for node in nodes:
        name = node['name']
        path = node['path'].replace("\\", "\\\\").replace("'", "\\'")
        
        # Click handler
        onclick = f"selectFolder(event, '{path}')"
        
        # Style
        style = ""
        if selected_path and os.path.normpath(selected_path) == os.path.normpath(node['path']):
            style = "background-color: #2196f3; color: white;"
            
        content = f'<span onclick="{onclick}" class="tree-content" style="{style}">📁 {name}</span>'
        
        if node['children']:
            html += f'<li><details open><summary>{content}</summary>{tree_to_html(node["children"], selected_path)}</details></li>'
        else:
            html += f'<li><div class="tree-leaf">{content}</div></li>'
            
    html += '</ul>'
    return html

def get_tree_html(selected_path=None):
    raw_folders = db.get_all_folders()
    
    if not raw_folders:
        return """<div class="tree-scroll-container" style="height: 480px; display: flex; align-items: center; justify-content: center; background: #161b22; border-radius: 8px;">
            <div style="text-align: center; color: #888;">
                <p>📁 No folder cache found.</p>
                <p style="font-size: 0.9em;">Click <strong>Refresh Tree Structure</strong> to build the folder tree.</p>
            </div>
        </div>"""
    
    # Convert paths to local environment format
    # This handles Windows paths (D:\...) when running in WSL and vice versa
    folders = []
    for p in raw_folders:
        local_p = utils.convert_path_to_local(p)
        if local_p:
            # Filter out WSL artifacts on Windows (e.g. \mnt, \)
            norm = os.path.normpath(local_p)
            
            if os.name == 'nt':
                 # Enforce drive letter Start (e.g. C:\ or D:\)
                 # This filters out \mnt, \, and relative paths which appear when using WSL paths on Windows
                 if len(norm) < 2 or norm[1] != ':':
                     continue

                 # Check if normalized path starts with \mnt or is just \
                 if norm.startswith('\\mnt') or norm == '\\':
                     continue
            else:
                 # On Linux/WSL, filter paths that still look like Windows paths or are just root artifacts
                 if local_p.startswith('\\'): # Unconverted windows path
                     continue
            
            # Filter specific unwanted folders
            basename = os.path.basename(norm).lower()
            if basename in ['.tmp.drivedownload', '.tmp.driveupload', 'keywords_output', '.']:
                continue
            
            folders.append(local_p)
            
    # Remove duplicates after conversion
    folders = list(set(folders))
    
    roots = build_tree_dict(folders)
    
    # Wrap in scrollable container
    tree_content = tree_to_html(roots, selected_path)
    return f'''<div class="tree-scroll-container" style="height: 480px; overflow-y: auto; overflow-x: auto; background: #161b22; border-radius: 8px; padding: 12px;">
        {tree_content}
    </div>'''
