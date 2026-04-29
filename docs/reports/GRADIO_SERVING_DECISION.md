# Gradio Serving Decision

Product-oriented note on why Gradio remains a reasonable UI layer for this repository, when alternatives (API-only, BentoML, Triton) would matter, and how that relates to FastAPI and GPU runtimes.

---

## Summary

- Gradio is an interactive UI layer; CUDA and throughput come from TensorFlow, PyTorch, and pipeline workers—not from swapping the UI framework.
- The stack already matches an interactive tool: FastAPI hosts `/api`, Gradio is mounted on the same app, and models run in the scoring/tagging pipeline ([`webui.py`](../../webui.py), [`modules/api.py`](../../modules/api.py)).
- Consider BentoML or NVIDIA Triton only if the product shifts to API-first serving, high concurrency, or isolated model deployment—not to “make CUDA faster” in the abstract.

---

## When to reconsider the stack

Move inference behind a dedicated serving layer if external clients, strict API-first deployment, batching, or multi-model GPU scheduling become primary requirements. Until then, improving model lifecycle and workers is usually the right lever.

---

## See also

- [system-overview.md](../architecture/system-overview.md), [pipeline-architecture.md](../architecture/pipeline-architecture.md)
- [GRADIO_UI_UX_SPEC_FOR_ELECTRON_MIGRATION.md](../technical/GRADIO_UI_UX_SPEC_FOR_ELECTRON_MIGRATION.md)
