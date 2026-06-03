#!/usr/bin/env python3
"""Phase 0: log native preprocess / max_dimension for culling towers and IQA scorers.

    python -m scripts.research.clip_culling.input_size_native
"""

from __future__ import annotations

import logging

from scripts.research.clip_culling import common
from scripts.research.clip_culling.embed_persist import TOWERS

logger = logging.getLogger("clip_culling.input_size_native")


def _open_clip_input_size(model_name: str, pretrained: str) -> dict:
    import open_clip

    model, _, preprocess = open_clip.create_model_and_transforms(model_name, pretrained=pretrained)
    del model
    out = {"model_name": model_name, "pretrained": pretrained}
    transforms = getattr(preprocess, "transforms", preprocess)
    if isinstance(transforms, (list, tuple)):
        for t in transforms:
            name = type(t).__name__
            if name == "Resize" and hasattr(t, "size"):
                out["resize"] = t.size
            if name == "CenterCrop" and hasattr(t, "size"):
                out["center_crop"] = t.size
    return out


def _timm_input_size(timm_name: str) -> dict:
    import timm

    model = timm.create_model(timm_name, pretrained=False, num_classes=0)
    cfg = timm.data.resolve_model_data_config(model)
    del model
    return {
        "timm_name": timm_name,
        "input_size": cfg.get("input_size"),
        "crop_pct": cfg.get("crop_pct"),
        "interpolation": str(cfg.get("interpolation", "")),
    }


def _hf_input_size(hf_model_id: str, kind: str) -> dict:
    from transformers import AutoImageProcessor, AutoConfig

    out = {"hf_model_id": hf_model_id, "kind": kind}
    try:
        proc = AutoImageProcessor.from_pretrained(hf_model_id)
        size = getattr(proc, "size", None) or getattr(proc, "crop_size", None)
        out["processor_size"] = size
    except Exception as e:  # noqa: BLE001
        out["processor_error"] = str(e)
    try:
        cfg = AutoConfig.from_pretrained(hf_model_id)
        if hasattr(cfg, "vision_config"):
            vc = cfg.vision_config
            out["vision_image_size"] = getattr(vc, "image_size", None)
    except Exception:  # noqa: BLE001
        pass
    return out


def collect_native_sizes() -> dict:
    """Probe each tower/scorer without running the full corpus."""
    out: dict = {
        "thumbnail_max_size": [512, 512],
        "mobilenet_clustering_resize": [224, 224],
        "embedding_towers": {},
        "iqa_scorers": {},
    }

    for label, fn in (
        ("clip_b32", lambda: _open_clip_input_size("ViT-B-32", "openai")),
    ):
        try:
            out["embedding_towers"][label] = fn()
        except Exception as e:  # noqa: BLE001
            out["embedding_towers"][label] = {"error": str(e)}

    for key, (_space, kind, args) in TOWERS.items():
        try:
            if kind == "open_clip":
                out["embedding_towers"][key] = _open_clip_input_size(
                    args["model_name"], args["pretrained"]
                )
            elif kind == "timm":
                out["embedding_towers"][key] = _timm_input_size(args["timm_name"])
            elif kind == "hf":
                out["embedding_towers"][key] = _hf_input_size(
                    args["hf_model_id"], args["kind"]
                )
        except Exception as e:  # noqa: BLE001
            out["embedding_towers"][key] = {"error": str(e)}

    try:
        from modules.liqe import LiqeScorer

        s = LiqeScorer(device="cpu")
        out["iqa_scorers"]["liqe"] = {"max_dimension": s.max_dimension, "default": 518}
    except Exception as e:  # noqa: BLE001
        out["iqa_scorers"]["liqe"] = {"error": str(e)}

    try:
        from modules.topiq import TopiqScorer

        s = TopiqScorer(device="cpu")
        out["iqa_scorers"]["topiq"] = {"max_dimension": s.max_dimension}
    except Exception as e:  # noqa: BLE001
        out["iqa_scorers"]["topiq"] = {"error": str(e)}

    try:
        from modules.arniqa import ArniqaScorer

        s = ArniqaScorer(device="cpu")
        out["iqa_scorers"]["arniqa"] = {"max_dimension": s.max_dimension}
    except Exception as e:  # noqa: BLE001
        out["iqa_scorers"]["arniqa"] = {"error": str(e)}

    try:
        from modules.config import get_config_value

        out["iqa_scorers"]["musiq_raw_conversion"] = {
            "max_resolution": get_config_value("raw_conversion.max_resolution", default=512),
        }
    except Exception as e:  # noqa: BLE001
        out["iqa_scorers"]["musiq_raw_conversion"] = {"error": str(e)}

    out["tagging_models"] = {}
    for label, hf_id, kind in (
        ("blip_caption", "Salesforce/blip-image-captioning-base", "blip"),
        ("siglip2", "google/siglip2-base-patch16-224", "siglip2"),
    ):
        try:
            out["tagging_models"][label] = _hf_input_size(hf_id, kind)
        except Exception as e:  # noqa: BLE001
            out["tagging_models"][label] = {"error": str(e)}

    try:
        import open_clip

        model, _, preprocess = open_clip.create_model_and_transforms(
            "hf-hub:imageomics/bioclip-2"
        )
        del model
        transforms = getattr(preprocess, "transforms", preprocess)
        out["tagging_models"]["bioclip2"] = {"model_id": "hf-hub:imageomics/bioclip-2"}
        if isinstance(transforms, (list, tuple)):
            for t in transforms:
                name = type(t).__name__
                if name == "Resize" and hasattr(t, "size"):
                    out["tagging_models"]["bioclip2"]["resize"] = t.size
                if name == "CenterCrop" and hasattr(t, "size"):
                    out["tagging_models"]["bioclip2"]["center_crop"] = t.size
    except Exception as e:  # noqa: BLE001
        out["tagging_models"]["bioclip2"] = {"error": str(e), "expected_native": 224}

    return out


def main() -> None:
    payload = collect_native_sizes()
    common.write_input_size_json("native_input_sizes.json", payload)
    logger.info("Recorded native input sizes for %d towers", len(payload.get("embedding_towers", {})))


if __name__ == "__main__":
    main()
