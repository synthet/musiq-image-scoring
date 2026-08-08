"""Bird-bbox crop study (research; read-only against production).

Measures what a subject-localized crop buys each pipeline phase versus the
whole downscaled frame. See the study README for the full design.

Modules
-------
``bbox``            Parse ``images.bird_bbox`` and derive geometry features.
``labels``         Load + validate the human within-burst label set.
``bursts``         EXIF-capture-time burst grouping (unbiased ground truth).
``build_label_set``  Step 0 — sample bursts and emit a labelling CSV.
``geometry_eval``    Step 1 — zero-inference geometry study.

All DB access is read-only against production via ``common.prod_connection()``.
"""
