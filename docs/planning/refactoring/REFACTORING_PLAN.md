# Refactoring Plan for webui.py

## Overview

The `webui.py` file has grown to over 5,200 lines, mixing business logic, data access, and UI definition. This plan outlines a systematic approach to split it into a modular component-based structure.

## Current State

- **File Size**: 5,212 lines
- **Tabs**: 7 tabs (Scoring, Keywords, Gallery, Folder Tree, Stacks, Culling, Configurations)
- **Already Extracted**: 
  - `modules/ui/common.py` - Shared helpers (keyword highlighting, wrappers)
  - `modules/ui/tabs/stacks.py` - Complete Stacks tab extraction

## Target Structure

```
modules/ui/
├── __init__.py              # Package exports
├── common.py                # Shared constants, helpers, wrappers (EXISTS)
├── app.py                   # Main entry point (replaces most of webui.py)
├── assets.py                # CSS and JavaScript (extracted from webui.py)
├── navigation.py            # Cross-tab navigation functions
├── state.py                 # (NEW) Type definitions for shared state
└── tabs/
    ├── __init__.py
    ├── scoring.py           # Scoring tab logic and UI
    ├── tagging.py           # Keywords/Tagging tab logic and UI
    ├── gallery.py           # Gallery tab logic and UI
    ├── folder_tree.py       # Folder Tree tab logic and UI
    ├── stacks.py            # Stacks tab (EXISTS - complete)
    ├── culling.py           # Culling tab logic and UI
    └── settings.py          # Configurations/Settings tab logic and UI
```

## Refactoring Strategy

### Phase 1: Extract Shared Assets (Foundation)
**Goal**: Move CSS and JavaScript to separate file for reuse

1. **Create `modules/ui/assets.py`**
   - Extract CSS block (lines ~2423-3445)
   - Extract JavaScript for folder tree (tree_js variable)
   - Provide functions: `get_css()`, `get_tree_js()`

2. **Update `webui.py`**
   - Import from `modules.ui.assets`
   - Replace inline CSS/JS with function calls

**Benefits**: Requires minimal logic changes but reduces file size by ~1,000 lines immediately.

---

### Phase 2: Define Shared State Architecture
**Goal**: Manage dependencies between tabs without circular imports.

1. **Identify Shared State**:
   - `current_paths` (List[str]): Paths of images currently in view (Gallery/Scoring).
   - `current_page` (int): Current page number in Gallery.
   - `image_details` (dict): Data for the currently selected image.
   - `main_tabs` (gr.Tabs): The top-level tab controller.

2. **Strategy**:
   - `app.py` instantiates these states first.
   - Tabs requiring these states accept them as arguments in their `create_tab` function.
   - Tabs returning components for other tabs (e.g. Navigation) return a Dictionary.

---

### Phase 3: Extract Cross-Tab Navigation
**Goal**: Centralize navigation functions used by multiple tabs

1. **Create `modules/ui/navigation.py`**
   - Implement `open_folder_in_gallery`, `open_folder_in_stacks`, etc.
   - These functions will accept the target Tab's components as arguments.

2. **Update `webui.py`**
   - Move the complex navigation logic out of the main block.

---

### Phase 4: Extract Individual Tabs (Incremental)

#### 4.1: Settings Tab (Low Dependencies)
**File**: `modules/ui/tabs/settings.py`
- **Inputs**: `app_config`
- **Extract**: `save_all_config`, `reset_config_defaults`, UI definition.

#### 4.2: Scoring & Tagging Tabs (Medium Dependencies)
**Files**: `modules/ui/tabs/scoring.py`, `modules/ui/tabs/tagging.py`
- **Inputs**: `runner` instances, `app_config`.
- **Extract**: Run wrappers, Status HTML, Log outputs.

#### 4.3: Folder Tree Tab (Medium Dependencies)
**File**: `modules/ui/tabs/folder_tree.py`
- **Inputs**: None (Self-contained).
- **Returns**: Navigation buttons (`open_gallery_btn`, etc.) to be wired in `app.py`.

#### 4.4: Gallery Tab (High Dependencies)
**File**: `modules/ui/tabs/gallery.py`
- **Inputs**: `shared_state` (current_paths, image_details), `app_config`.
- **Extract**: Pagination logic, Filter logic, Details panel.
- **Returns**: `gallery` component, Filter inputs (needed by Navigation).

#### 4.5: Culling Tab (High Dependencies)
**File**: `modules/ui/tabs/culling.py`
- **Inputs**: `app_config`.
- **Extract**: Culling session management.

---

### Phase 5: Create Main App Entry Point
**Goal**: Replace `webui.py` with a clean orchestrator

**File**: `modules/ui/app.py`

**Structure**:
```python
def create_ui():
    # 1. Init Data & Config
    app_config = config.load_config()
    
    # 2. Init Shared State
    current_paths = gr.State([])
    image_details = gr.State({})
    
    with gr.Blocks(css=assets.get_css()) as demo:
        # 3. Create Tabs (Injecting dependencies)
        scoring_tab = scoring.create_tab(runner, ...)
        gallery_tab = gallery.create_tab(current_paths, ...)
        
        # 4. Wire Navigation
        navigation.setup_navigation(
            source=folder_tree_tab, 
            target=gallery_tab
        )
        
    return demo
```

---

## Detailed Component Return Pattern

Each tab's `create_tab()` function returns a dictionary. To ensure type safety and clarity, we can document the expected keys.

**Example: Gallery Tab Returns**
```python
{
    'tab_item': gr.TabItem,       # For switching to this tab
    'gallery': gr.Gallery,        # For updating content
    'sort_by': gr.Dropdown,       # For Navigation filters
    'selected_path': gr.Textbox,  # For other tabs to know selection
    ...
}
```

## Next Steps

1.  **Refine Phase 1**: Extract CSS/JS immediately.
2.  **Verify Shared State**: Confirm list of shared states by checking `webui.py` one last time.
3.  **Execute Phase 4.1 (Settings)**: Easiest tab to move.
