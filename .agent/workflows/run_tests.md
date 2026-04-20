---
description: Run the image scoring test suite (Pytest)
---

// turbo
1. **Run All Tests**:
   Execute the full test suite using Pytest:
   ```bash
   python -m pytest
   ```

2. **Run Specific Tests**:
   - **Culling Tests**: `python -m pytest tests/test_culling.py`
   - **Stacking Tests**: `python -m pytest tests/test_stacks.py`
   - **Database Tests**: `python -m pytest tests/test_db.py`

3. **Debug Mode**:
   Run tests with stdout enabled:
   ```bash
   python -m pytest -s
   ```

4. **Cleanup**:
   The tests automatically create a temporary PostgreSQL test database. This is isolated from production.
