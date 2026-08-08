"""Image-student training entrypoint (E2–E8).

Requires ``requirements/requirements_student_scorer.txt``. Refuses to train if
the manifest checksum / protocol ID does not match the run config.

Before an unattended sweep, write an autonomous-run-contract.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from scripts.research.student_scorer.common import (
    COMPOSITE_KEYS,
    compute_composites_frozen,
    ensure_artifacts_dir,
    read_json,
    set_seed,
    write_json,
)
from scripts.research.student_scorer.data import validate_manifest_against_protocol
from scripts.research.student_scorer.evaluate_scores import (
    assert_selection_split_allowed,
    fidelity_report,
)
from scripts.research.student_scorer.models import StudentArchConfig, build_image_student


EXPERIMENT_CONFIGS: dict[str, dict[str, Any]] = {
    "E2": {"backbone": "convnext_tiny", "fine_tune": "last_stage"},
    "E3": {"backbone": "convnext_tiny", "fine_tune": "full"},
    "E4": {"backbone": "dinov2_vits14", "fine_tune": "frozen"},
    "E5": {"backbone": "dinov2_vits14", "fine_tune": "final_blocks"},
    "E6": {"backbone": "swin_tiny", "fine_tune": "last_stage"},
    "E7": {"backbone": "convnext_tiny", "fine_tune": "last_stage", "input": "P2"},
    "E8": {"backbone": "mobilenetv3_large", "fine_tune": "full"},
}

# E2 locked coeffs (plan): teacher + consistency; rank/human off.
DEFAULT_LOSS_COEFFS: dict[str, float] = {
    "teacher": 1.0,
    "consistency": 0.1,
    "aux_composite": 0.25,
    "uncertainty": 0.1,
    "rank": 0.0,
    "human": 0.0,
}


# Fields that must match for a --resume to be accepted; a mismatch means the
# saved state belongs to a different run and cannot be continued into this one.
RESUME_GUARD_KEYS: tuple[str, ...] = (
    "manifest_id",
    "protocol_id",
    "experiment",
    "seed",
    "epochs",
    "limit",
    "batch_size",
    "grad_accum",
    "lr",
    "patience",
    "backbone",
    "fine_tune",
)


def _resume_guard(run_config: Mapping[str, Any]) -> dict[str, Any]:
    return {k: run_config.get(k) for k in RESUME_GUARD_KEYS}


def _save_resume_state_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    """Write last.pt via tmp+replace so a kill mid-write cannot corrupt it."""
    import torch

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".pt.tmp")
    torch.save(dict(payload), tmp)
    tmp.replace(path)


def _load_resume_state(
    path: Path,
    guard: Mapping[str, Any],
    *,
    map_location: Any = "cpu",
) -> dict[str, Any] | None:
    """Load last.pt, or None if absent. Raise if it belongs to a different run."""
    import torch

    if not path.is_file():
        return None
    state = torch.load(path, map_location=map_location, weights_only=False)
    saved_guard = state.get("guard") or {}
    if saved_guard != dict(guard):
        diff = {
            k: (saved_guard.get(k), guard.get(k))
            for k in RESUME_GUARD_KEYS
            if saved_guard.get(k) != guard.get(k)
        }
        raise RuntimeError(
            f"--resume: {path} belongs to a different run config (saved, current): {diff}"
        )
    return state


def _full_target_mask_rows(masks: Sequence[Mapping[str, bool]], teachers: Sequence[str]) -> list[bool]:
    out = []
    for m in masks:
        out.append(all(bool(m.get(t)) for t in teachers))
    return out


def _dicts_from_batch_preds(
    preds: Mapping[str, Any],
    batch: Mapping[str, Any],
    teachers: Sequence[str],
    *,
    fusion: Mapping[str, Mapping[str, float]],
    anchors: Mapping[str, Mapping[str, float]],
) -> tuple[list[dict[str, float]], list[dict[str, float]], list[dict[str, bool]], list[dict[str, float]]]:
    """Build per-row pred/target/mask dicts; also derived composites from teachers."""
    n = int(batch["targets"].shape[0])
    n_t = len(teachers)
    predictions: list[dict[str, float]] = []
    targets: list[dict[str, float]] = []
    masks: list[dict[str, bool]] = []
    derived_preds: list[dict[str, float]] = []

    teacher_cpu = {t: preds[t].detach().float().cpu() for t in teachers}
    direct_cpu = {
        k: preds[k].detach().float().cpu()
        for k in COMPOSITE_KEYS
        if k in preds
    }
    tgt = batch["targets"].detach().float().cpu()
    msk = batch["masks"].detach().cpu()

    for i in range(n):
        p: dict[str, float] = {}
        t: dict[str, float] = {}
        m: dict[str, bool] = {}
        teacher_scores: dict[str, float] = {}
        for j, name in enumerate(teachers):
            p[name] = float(teacher_cpu[name][i])
            t[name] = float(tgt[i, j])
            m[name] = bool(msk[i, j])
            if m[name]:
                teacher_scores[name] = p[name]
        for j, key in enumerate(COMPOSITE_KEYS):
            if key in direct_cpu:
                p[key] = float(direct_cpu[key][i])
            t[key] = float(tgt[i, n_t + j])
            m[key] = bool(msk[i, n_t + j])
        predictions.append(p)
        targets.append(t)
        masks.append(m)
        if teacher_scores:
            d = compute_composites_frozen(teacher_scores, fusion=fusion, anchors=anchors)
        else:
            d = {k: 0.0 for k in COMPOSITE_KEYS}
        # derived report uses derived composites as predictions for composite keys
        derived = dict(p)
        derived.update(d)
        derived_preds.append(derived)
    return predictions, targets, masks, derived_preds


def _slice_fidelity(
    predictions: Sequence[Mapping[str, float]],
    targets: Sequence[Mapping[str, float]],
    masks: Sequence[Mapping[str, bool]],
    teachers: Sequence[str],
    *,
    full_target_only: bool,
    gates: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if full_target_only:
        keep = _full_target_mask_rows(masks, teachers)
        predictions = [p for p, k in zip(predictions, keep) if k]
        targets = [t for t, k in zip(targets, keep) if k]
        masks = [m for m, k in zip(masks, keep) if k]
        if not predictions:
            return {"empty": True, "full_target_only": True}
    sat = [float(t.get("general", 0.0)) for t in targets]
    return fidelity_report(
        predictions,
        targets,
        masks,
        teachers=teachers,
        gates=gates,
        saturation_values=sat,
    )


def _subgroup_by_method(
    predictions: Sequence[Mapping[str, float]],
    targets: Sequence[Mapping[str, float]],
    masks: Sequence[Mapping[str, bool]],
    methods: Sequence[str],
    teachers: Sequence[str],
    gates: Mapping[str, Any] | None,
) -> dict[str, Any]:
    by: dict[str, dict[str, Any]] = {}
    for method in sorted(set(methods)):
        idx = [i for i, m in enumerate(methods) if m == method]
        if len(idx) < 2:
            by[method] = {"n": len(idx), "skipped": "too_few"}
            continue
        report = fidelity_report(
            [predictions[i] for i in idx],
            [targets[i] for i in idx],
            [masks[i] for i in idx],
            teachers=teachers,
            gates=gates,
            saturation_values=[float(targets[i].get("general", 0.0)) for i in idx],
        )
        report["n"] = len(idx)
        by[method] = report
    return by


def _evaluate_loader(
    model,
    loader,
    *,
    teachers: Sequence[str],
    fusion,
    anchors,
    device,
    gates,
) -> dict[str, Any]:
    import torch

    model.eval()
    all_direct: list[dict[str, float]] = []
    all_derived: list[dict[str, float]] = []
    all_targets: list[dict[str, float]] = []
    all_masks: list[dict[str, bool]] = []
    all_methods: list[str] = []
    teacher_loss_sum = 0.0
    n_batches = 0

    from scripts.research.student_scorer.torch_losses import (
        coverage_normalized_teacher_loss,
    )

    with torch.no_grad():
        for batch in loader:
            images = batch["image"].to(device, non_blocking=True)
            # move tensor fields
            for k in (
                "targets",
                "masks",
                "stored_composites",
                "composite_masks",
                "uncertainty_target",
                "uncertainty_mask",
            ):
                batch[k] = batch[k].to(device, non_blocking=True)
            preds = model(images)
            teacher_l = coverage_normalized_teacher_loss(
                preds, batch["targets"], batch["masks"], teachers
            )
            teacher_loss_sum += float(teacher_l.detach().cpu())
            n_batches += 1
            direct, targets, masks, derived = _dicts_from_batch_preds(
                preds, batch, teachers, fusion=fusion, anchors=anchors
            )
            all_direct.extend(direct)
            all_derived.extend(derived)
            all_targets.extend(targets)
            all_masks.extend(masks)
            all_methods.extend(batch["resolved_method"])

    # Gate-bearing report uses derived composites for composite heads
    fidelity_derived_all = _slice_fidelity(
        all_derived, all_targets, all_masks, teachers, full_target_only=False, gates=gates
    )
    fidelity_derived_ft = _slice_fidelity(
        all_derived, all_targets, all_masks, teachers, full_target_only=True, gates=gates
    )
    fidelity_direct_all = _slice_fidelity(
        all_direct, all_targets, all_masks, teachers, full_target_only=False, gates=gates
    )
    return {
        "n": len(all_derived),
        "masked_teacher_loss": teacher_loss_sum / max(n_batches, 1),
        "derived": {"all": fidelity_derived_all, "full_target": fidelity_derived_ft},
        "direct": {"all": fidelity_direct_all},
        "resolved_method_subgroup": _subgroup_by_method(
            all_derived, all_targets, all_masks, all_methods, teachers, gates
        ),
    }


def run_train(
    *,
    manifest_dir: Path,
    experiment: str,
    seed: int = 42,
    epochs: int = 20,
    dry_build_only: bool = False,
    expected_protocol_id: str | None = None,
    cache_dir: Path | None = None,
    limit: int | None = None,
    batch_size: int = 16,
    grad_accum: int = 2,
    lr: float = 1e-4,
    patience: int = 3,
    num_workers: int = 8,
    device: str | None = None,
    resume: bool = False,
) -> dict[str, Any]:
    set_seed(seed)
    assert_selection_split_allowed("val")
    meta = read_json(manifest_dir / "manifest.meta.json")
    validate_manifest_against_protocol(
        meta,
        expected_checksum=meta.get("checksum"),
        expected_protocol_id=expected_protocol_id or meta.get("protocol_id"),
        expected_contract_hash=meta.get("contract_hash"),
    )
    teachers = tuple(meta["teachers"])
    cfg_extra = EXPERIMENT_CONFIGS[experiment]
    cfg = StudentArchConfig(
        backbone=cfg_extra["backbone"],
        fine_tune=cfg_extra["fine_tune"],
        pretrained=not dry_build_only,
        teachers=teachers,
        input_size=int((meta.get("preprocessing") or {}).get("max_resolution") or 512),
    )
    model = build_image_student(cfg)
    n_params = sum(p.numel() for p in model.parameters())
    n_trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)

    loss_coeffs = dict(DEFAULT_LOSS_COEFFS)
    run_dir = ensure_artifacts_dir(meta.get("manifest_id")) / "runs" / f"{experiment}_s{seed}"
    run_dir.mkdir(parents=True, exist_ok=True)

    run_config = {
        "experiment": experiment,
        "manifest_id": meta.get("manifest_id"),
        "protocol_id": meta.get("protocol_id"),
        "seed": seed,
        "epochs": epochs,
        "backbone": cfg.backbone,
        "fine_tune": cfg.fine_tune,
        "teachers": list(teachers),
        "loss_coeffs": loss_coeffs,
        "batch_size": batch_size,
        "grad_accum": grad_accum,
        "lr": lr,
        "patience": patience,
        "limit": limit,
        "input": "P0",
    }
    write_json(run_dir / "run_config.json", run_config)

    result: dict[str, Any] = {
        **run_config,
        "n_params": int(n_params),
        "n_trainable": int(n_trainable),
        "status": "built" if dry_build_only else "needs_gpu_loop",
    }

    if dry_build_only:
        result["note"] = "dry_build_only: architecture constructed; no GPU/renders required"
        write_json(run_dir / "run.json", result)
        return result

    import torch
    from torch.utils.data import DataLoader

    from scripts.research.student_scorer.image_dataset import (
        P0ImageDataset,
        collate_p0,
        indices_for_split,
        prepare_manifest_arrays,
    )
    from scripts.research.student_scorer.torch_losses import total_student_loss

    if device is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
    model = model.to(device)

    arrays = prepare_manifest_arrays(manifest_dir, cache_dir=cache_dir)
    if limit is not None:
        # Truncate each split proportionally by taking first N overall indices
        keep_n = int(limit)
        arrays = {
            **arrays,
            "image_ids": arrays["image_ids"][:keep_n],
            "paths": arrays["paths"][:keep_n],
            "targets": arrays["targets"][:keep_n],
            "masks": arrays["masks"][:keep_n],
            "stored_composites": arrays["stored_composites"][:keep_n],
            "composite_masks": arrays["composite_masks"][:keep_n],
            "uncertainty_targets": arrays["uncertainty_targets"][:keep_n],
            "uncertainty_masks": arrays["uncertainty_masks"][:keep_n],
            "splits": arrays["splits"][:keep_n],
            "resolved_methods": arrays["resolved_methods"][:keep_n],
        }

    train_idx = indices_for_split(arrays, "train")
    val_idx = indices_for_split(arrays, "val")
    test_idx = indices_for_split(arrays, "test")
    ood_idx = indices_for_split(arrays, "ood_test")

    def make_loader(indices: list[int], shuffle: bool) -> DataLoader:
        ds = P0ImageDataset(arrays, indices=indices)
        return DataLoader(
            ds,
            batch_size=batch_size,
            shuffle=shuffle,
            num_workers=num_workers,
            collate_fn=collate_p0,
            pin_memory=(device.startswith("cuda")),
        )

    # OOM auto-halve
    while True:
        try:
            probe = make_loader(train_idx[: max(batch_size, 1)], shuffle=False)
            batch = next(iter(probe))
            with torch.cuda.amp.autocast(enabled=device.startswith("cuda")):
                _ = model(batch["image"].to(device))
            break
        except torch.cuda.OutOfMemoryError:
            if batch_size <= 1:
                raise
            batch_size = max(1, batch_size // 2)
            run_config["batch_size"] = batch_size
            run_config["oom_halved"] = True
            write_json(run_dir / "run_config.json", run_config)
            torch.cuda.empty_cache()

    train_loader = make_loader(train_idx, shuffle=True)
    val_loader = make_loader(val_idx, shuffle=False)

    opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=lr)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=max(epochs, 1))
    scaler = torch.cuda.amp.GradScaler(enabled=device.startswith("cuda"))

    fusion = meta["fusion"]
    anchors = meta["percentile_anchors"]
    gates = meta.get("gates")

    history: list[dict[str, Any]] = []
    best_val = float("inf")
    best_epoch = -1
    bad_epochs = 0
    start_epoch = 0
    resumed_from_epoch: int | None = None

    last_path = run_dir / "last.pt"
    guard = _resume_guard(run_config)
    if resume:
        state = _load_resume_state(last_path, guard, map_location=device)
        if state is None:
            print(f"--resume: no {last_path.name} yet; starting from epoch 0")
        else:
            model.load_state_dict(state["model"])
            opt.load_state_dict(state["opt"])
            sched.load_state_dict(state["sched"])
            scaler.load_state_dict(state["scaler"])
            history = list(state["history"])
            best_val = float(state["best_val"])
            best_epoch = int(state["best_epoch"])
            bad_epochs = int(state["bad_epochs"])
            start_epoch = int(state["next_epoch"])
            resumed_from_epoch = start_epoch
            print(
                f"--resume: continuing at epoch {start_epoch} "
                f"(best {best_val:.6f} @ epoch {best_epoch})"
            )

    for epoch in range(start_epoch, int(epochs)):
        model.train()
        opt.zero_grad(set_to_none=True)
        running = 0.0
        n_steps = 0
        for step, batch in enumerate(train_loader):
            images = batch["image"].to(device, non_blocking=True)
            for k in (
                "targets",
                "masks",
                "stored_composites",
                "composite_masks",
                "uncertainty_target",
                "uncertainty_mask",
            ):
                batch[k] = batch[k].to(device, non_blocking=True)
            with torch.cuda.amp.autocast(enabled=device.startswith("cuda")):
                preds = model(images)
                loss, parts = total_student_loss(
                    preds,
                    batch,
                    teachers=teachers,
                    fusion=fusion,
                    anchors=anchors,
                    coeffs=loss_coeffs,
                )
                loss = loss / float(grad_accum)
            scaler.scale(loss).backward()
            if (step + 1) % grad_accum == 0:
                scaler.step(opt)
                scaler.update()
                opt.zero_grad(set_to_none=True)
            running += float(parts["total"])
            n_steps += 1
        # flush leftover grads
        if n_steps % grad_accum != 0:
            scaler.step(opt)
            scaler.update()
            opt.zero_grad(set_to_none=True)
        sched.step()

        val_metrics = _evaluate_loader(
            model,
            val_loader,
            teachers=teachers,
            fusion=fusion,
            anchors=anchors,
            device=device,
            gates=gates,
        )
        val_loss = float(val_metrics["masked_teacher_loss"])
        row = {
            "epoch": epoch,
            "train_loss_mean": running / max(n_steps, 1),
            "val_masked_teacher_loss": val_loss,
            "val_derived_general_spearman": (
                val_metrics["derived"]["all"]
                .get("per_head", {})
                .get("general", {})
                .get("spearman")
            ),
        }
        history.append(row)

        if val_loss < best_val - 1e-6:
            best_val = val_loss
            best_epoch = epoch
            bad_epochs = 0
            torch.save(
                {
                    "model": model.state_dict(),
                    "epoch": epoch,
                    "val_masked_teacher_loss": val_loss,
                    "teachers": list(teachers),
                    "arch": {
                        "backbone": cfg.backbone,
                        "fine_tune": cfg.fine_tune,
                        "input_size": cfg.input_size,
                    },
                },
                run_dir / "best.pt",
            )
        else:
            bad_epochs += 1

        _save_resume_state_atomic(
            last_path,
            {
                "model": model.state_dict(),
                "opt": opt.state_dict(),
                "sched": sched.state_dict(),
                "scaler": scaler.state_dict(),
                "history": history,
                "best_val": best_val,
                "best_epoch": best_epoch,
                "bad_epochs": bad_epochs,
                "next_epoch": epoch + 1,
                "guard": guard,
            },
        )

        if bad_epochs >= patience:
            break

    # Load best and report
    ckpt_path = run_dir / "best.pt"
    if ckpt_path.is_file():
        ckpt = torch.load(ckpt_path, map_location=device, weights_only=False)
        model.load_state_dict(ckpt["model"])

    val_report = _evaluate_loader(
        model,
        val_loader,
        teachers=teachers,
        fusion=fusion,
        anchors=anchors,
        device=device,
        gates=gates,
    )
    report: dict[str, Any] = {
        "experiment": experiment,
        "seed": seed,
        "best_epoch": best_epoch,
        "best_val_masked_teacher_loss": best_val,
        "history": history,
        "fidelity_val": val_report,
        "selection_split": "val",
        "gate_bearing": "derived_composites",
        "resumed_from_epoch": resumed_from_epoch,
    }

    # Report-only test + ood (never used for selection)
    for name, idx in (("test", test_idx), ("ood_test", ood_idx)):
        if not idx:
            report[f"fidelity_{name}"] = {"empty": True}
            continue
        loader = make_loader(idx, shuffle=False)
        report[f"fidelity_{name}"] = _evaluate_loader(
            model,
            loader,
            teachers=teachers,
            fusion=fusion,
            anchors=anchors,
            device=device,
            gates=gates,
        )

    # Named pass/fail from derived val all
    gates_block = val_report["derived"]["all"].get("gates", {})
    report["gates"] = gates_block
    report["all_required_passed"] = bool(
        val_report["derived"]["all"].get("all_required_passed")
    )
    report["required_failed"] = list(
        val_report["derived"]["all"].get("required_failed") or []
    )
    write_json(run_dir / "report.json", report)

    result.update(
        {
            "status": "trained",
            "best_epoch": best_epoch,
            "best_val_masked_teacher_loss": best_val,
            "all_required_passed": report["all_required_passed"],
            "required_failed": report["required_failed"],
            "n_train": len(train_idx),
            "n_val": len(val_idx),
            "n_skipped_renders": arrays.get("n_skipped"),
            "resumed_from_epoch": resumed_from_epoch,
            "device": device,
            "report_path": str(run_dir / "report.json"),
        }
    )
    write_json(run_dir / "run.json", result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Train image student (E2–E8)")
    parser.add_argument("--manifest-dir", type=Path, required=True)
    parser.add_argument("--experiment", required=True, choices=sorted(EXPERIMENT_CONFIGS))
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--dry-build-only", action="store_true")
    parser.add_argument("--cache-dir", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--grad-accum", type=int, default=2)
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--patience", type=int, default=3)
    parser.add_argument("--num-workers", type=int, default=8)
    parser.add_argument("--device", type=str, default=None)
    parser.add_argument(
        "--resume",
        action="store_true",
        help="continue from run_dir/last.pt if it matches this run config",
    )
    args = parser.parse_args(argv)
    out = run_train(
        manifest_dir=args.manifest_dir,
        experiment=args.experiment,
        seed=args.seed,
        epochs=args.epochs,
        dry_build_only=args.dry_build_only,
        cache_dir=args.cache_dir,
        limit=args.limit,
        batch_size=args.batch_size,
        grad_accum=args.grad_accum,
        lr=args.lr,
        patience=args.patience,
        num_workers=args.num_workers,
        device=args.device,
        resume=args.resume,
    )
    print(json.dumps(out, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
