"""Student scorer research package: distill the live IQA ensemble into one multi-head student.

Offline training reads immutable manifests under ``artifacts/student_scorer/``.
Production fusion is never modified by this package; shadow deployment lives in
``modules.student_scoring`` / ``modules.engines.student_model``.
"""

from __future__ import annotations

__all__ = ["DEFAULT_TEACHERS", "STUDENT_NAMESPACE"]

DEFAULT_TEACHERS: tuple[str, ...] = ("spaq", "ava", "liqe", "topiq", "arniqa")
STUDENT_NAMESPACE = "vexlum_student_v1"
