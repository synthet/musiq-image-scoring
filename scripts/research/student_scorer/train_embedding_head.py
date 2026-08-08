"""E0/E1 stored-embedding multi-head baselines.

Reads a frozen manifest + embeddings NPZ. Does not query Postgres during fitting.

- E0: closed-form ridge / linear multi-output
- E1: 2-layer MLP (1024→256→H) with masked loss, early-stop on val
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from scripts.research.student_scorer.common import (
    DEFAULT_TEACHERS,
    ensure_artifacts_dir,
    read_json,
    set_seed,
    write_json,
)
from scripts.research.student_scorer.data import validate_manifest_against_protocol
from scripts.research.student_scorer.evaluate_scores import assert_selection_split_allowed, fidelity_report


def _load_splits(manifest_dir: Path) -> dict[int, str]:
    data = read_json(manifest_dir / "splits.json")
    return {int(a["image_id"]): a["split"] for a in data["assignments"]}


def _fit_ridge_multioutput(
    X_train,
    Y_train,
    M_train,
    *,
    l2: float = 1e-2,
):
    """Closed-form ridge per head with masked rows (numpy). E0 only."""
    import numpy as np

    n_heads = Y_train.shape[1]
    d = X_train.shape[1]
    W = np.zeros((d, n_heads), dtype=np.float64)
    b = np.zeros(n_heads, dtype=np.float64)
    for h in range(n_heads):
        mask = M_train[:, h].astype(bool)
        if mask.sum() < 2:
            continue
        X = X_train[mask]
        y = Y_train[mask, h]
        Xc = X - X.mean(axis=0, keepdims=True)
        yc = y - y.mean()
        xtx = Xc.T @ Xc + l2 * np.eye(d)
        w = np.linalg.solve(xtx, Xc.T @ yc)
        W[:, h] = w
        b[h] = float(y.mean() - X.mean(axis=0) @ w)
    return W, b


def _predict_linear(X, W, b):
    return X @ W + b


def _masked_mse(pred, target, mask) -> float:
    import numpy as np

    if mask.sum() == 0:
        return 0.0
    diff = (pred - target)[mask]
    return float(np.mean(diff * diff))


def _fit_mlp_numpy(
    X_train,
    Y_train,
    M_train,
    X_val,
    Y_val,
    M_val,
    *,
    hidden: tuple[int, int] = (1024, 256),
    lr: float = 1e-3,
    epochs: int = 40,
    batch_size: int = 256,
    seed: int = 42,
    patience: int = 5,
):
    """Small numpy SGD MLP with ReLU; early-stop on val masked MSE."""
    import numpy as np

    rng = np.random.default_rng(seed)
    n, d = X_train.shape
    h_out = Y_train.shape[1]
    h1, h2 = hidden

    def xavier(fan_in, fan_out):
        return rng.normal(0.0, (2.0 / (fan_in + fan_out)) ** 0.5, size=(fan_in, fan_out))

    W1 = xavier(d, h1)
    b1 = np.zeros(h1)
    W2 = xavier(h1, h2)
    b2 = np.zeros(h2)
    W3 = xavier(h2, h_out)
    b3 = np.zeros(h_out)

    # Feature normalize from train
    mu = X_train.mean(axis=0)
    sigma = X_train.std(axis=0) + 1e-6

    def forward(X):
        Z = (X - mu) / sigma
        H1 = np.maximum(0.0, Z @ W1 + b1)
        H2 = np.maximum(0.0, H1 @ W2 + b2)
        Out = H2 @ W3 + b3
        return Out, H1, H2, Z

    def predict(X):
        out, _, _, _ = forward(X)
        return out

    best_state = None
    best_val = float("inf")
    stale = 0
    history: list[dict[str, float]] = []

    idx = np.arange(n)
    for epoch in range(epochs):
        rng.shuffle(idx)
        for start in range(0, n, batch_size):
            batch = idx[start : start + batch_size]
            xb, yb, mb = X_train[batch], Y_train[batch], M_train[batch]
            out, h1a, h2a, z = forward(xb)
            # gradient of masked MSE
            err = (out - yb) * mb.astype(np.float64)
            denom = max(int(mb.sum()), 1)
            dout = (2.0 / denom) * err
            dW3 = h2a.T @ dout
            db3 = dout.sum(axis=0)
            dh2 = dout @ W3.T
            dh2 *= (h2a > 0).astype(np.float64)
            dW2 = h1a.T @ dh2
            db2 = dh2.sum(axis=0)
            dh1 = dh2 @ W2.T
            dh1 *= (h1a > 0).astype(np.float64)
            dW1 = z.T @ dh1
            db1 = dh1.sum(axis=0)
            W3 -= lr * dW3
            b3 -= lr * db3
            W2 -= lr * dW2
            b2 -= lr * db2
            W1 -= lr * dW1
            b1 -= lr * db1

        pred_v = predict(X_val)
        val_loss = _masked_mse(pred_v, Y_val, M_val)
        history.append({"epoch": float(epoch), "val_masked_mse": val_loss})
        if val_loss + 1e-9 < best_val:
            best_val = val_loss
            stale = 0
            best_state = {
                "W1": W1.copy(),
                "b1": b1.copy(),
                "W2": W2.copy(),
                "b2": b2.copy(),
                "W3": W3.copy(),
                "b3": b3.copy(),
                "mu": mu.copy(),
                "sigma": sigma.copy(),
            }
        else:
            stale += 1
            if stale >= patience:
                break

    assert best_state is not None

    def predict_best(X):
        Z = (X - best_state["mu"]) / best_state["sigma"]
        H1 = np.maximum(0.0, Z @ best_state["W1"] + best_state["b1"])
        H2 = np.maximum(0.0, H1 @ best_state["W2"] + best_state["b2"])
        return H2 @ best_state["W3"] + best_state["b3"]

    return predict_best, best_state, history


def _fit_mlp_torch(
    X_train,
    Y_train,
    M_train,
    X_val,
    Y_val,
    M_val,
    *,
    hidden: tuple[int, int] = (1024, 256),
    lr: float = 1e-3,
    epochs: int = 40,
    batch_size: int = 256,
    seed: int = 42,
    patience: int = 5,
):
    import numpy as np
    import torch
    import torch.nn as nn

    torch.manual_seed(seed)
    device = torch.device("cpu")
    d = X_train.shape[1]
    h_out = Y_train.shape[1]
    h1, h2 = hidden

    mu = X_train.mean(axis=0)
    sigma = X_train.std(axis=0) + 1e-6

    class MLP(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.net = nn.Sequential(
                nn.Linear(d, h1),
                nn.ReLU(),
                nn.Linear(h1, h2),
                nn.ReLU(),
                nn.Linear(h2, h_out),
            )

        def forward(self, x):  # noqa: ANN001
            return self.net(x)

    model = MLP().to(device)
    opt = torch.optim.Adam(model.parameters(), lr=lr)

    def to_t(a):
        return torch.from_numpy(a.astype(np.float32)).to(device)

    Xt = to_t((X_train - mu) / sigma)
    Yt = to_t(Y_train)
    Mt = to_t(M_train.astype(np.float32))
    Xv = to_t((X_val - mu) / sigma)
    Yv = to_t(Y_val)
    Mv = to_t(M_val.astype(np.float32))

    best_state = None
    best_val = float("inf")
    stale = 0
    history: list[dict[str, float]] = []
    n = Xt.shape[0]

    for epoch in range(epochs):
        model.train()
        perm = torch.randperm(n)
        for start in range(0, n, batch_size):
            idx = perm[start : start + batch_size]
            pred = model(Xt[idx])
            err = (pred - Yt[idx]) * Mt[idx]
            loss = (err * err).sum() / Mt[idx].sum().clamp_min(1.0)
            opt.zero_grad()
            loss.backward()
            opt.step()
        model.eval()
        with torch.no_grad():
            pred_v = model(Xv)
            val_loss = float(((pred_v - Yv) * Mv).pow(2).sum() / Mv.sum().clamp_min(1.0))
        history.append({"epoch": float(epoch), "val_masked_mse": val_loss})
        if val_loss + 1e-9 < best_val:
            best_val = val_loss
            stale = 0
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
        else:
            stale += 1
            if stale >= patience:
                break

    assert best_state is not None
    model.load_state_dict(best_state)
    model.eval()

    def predict_best(X):
        with torch.no_grad():
            xn = to_t((X - mu) / sigma)
            return model(xn).cpu().numpy().astype(np.float64)

    return predict_best, {"state_dict": best_state, "mu": mu, "sigma": sigma, "backend": "torch"}, history


def _fit_mlp(*args, **kwargs):
    try:
        import torch  # noqa: F401

        return _fit_mlp_torch(*args, **kwargs)
    except ImportError:
        return _fit_mlp_numpy(*args, **kwargs)


def _dicts_from_pred(pred, Y, M, indices, heads):
    predictions = []
    targets = []
    masks = []
    for i, row_i in enumerate(indices):
        predictions.append({h: float(pred[i, j]) for j, h in enumerate(heads)})
        targets.append({h: float(Y[row_i, j]) for j, h in enumerate(heads)})
        masks.append({h: bool(M[row_i, j]) for j, h in enumerate(heads)})
    return predictions, targets, masks


def _full_target_mask(M, n_teachers: int):
    import numpy as np

    return M[:, :n_teachers].all(axis=1)


def _slice_report(pred, Y, M, indices, heads, teachers, *, full_target_only: bool = False):
    import numpy as np

    if len(indices) == 0:
        return {"empty": True}
    pred_rows = pred
    if full_target_only:
        ft = _full_target_mask(M, len(teachers))
        keep_local = []
        keep_global = []
        for local_i, row_i in enumerate(indices):
            if ft[row_i]:
                keep_local.append(local_i)
                keep_global.append(row_i)
        if not keep_local:
            return {"empty": True, "full_target_only": True}
        pred_rows = pred[np.asarray(keep_local)]
        indices = np.asarray(keep_global)
    predictions, targets, masks = _dicts_from_pred(pred_rows, Y, M, indices, heads)
    sat = [float(t.get("general", 0.5)) for t in targets]
    return fidelity_report(
        predictions,
        targets,
        masks,
        teachers=teachers,
        saturation_values=sat,
    )


def run_embedding_baseline(
    *,
    manifest_dir: Path,
    embeddings_npz: Path,
    experiment: str = "E1",
    seed: int = 42,
    expected_protocol_id: str | None = None,
    epochs: int = 40,
) -> dict[str, Any]:
    import numpy as np

    set_seed(seed)
    meta = read_json(manifest_dir / "manifest.meta.json")
    validate_manifest_against_protocol(
        meta,
        expected_checksum=meta.get("checksum"),
        expected_protocol_id=expected_protocol_id or meta.get("protocol_id"),
        expected_contract_hash=meta.get("contract_hash"),
    )
    assert_selection_split_allowed("val")

    data = np.load(embeddings_npz, allow_pickle=True)
    image_ids = data["image_ids"].astype(int)
    X = data["embeddings"].astype(np.float64)
    teachers = list(meta.get("teachers") or DEFAULT_TEACHERS)
    heads = teachers + ["general", "technical", "aesthetic"]
    Y = data["targets"].astype(np.float64)
    M = data["masks"].astype(bool)

    if "splits" in data.files:
        splits = np.asarray(data["splits"]).astype(str)
    else:
        split_of = _load_splits(manifest_dir)
        splits = np.array([split_of.get(int(i), "train") for i in image_ids])

    train = splits == "train"
    val = splits == "val"
    test = splits == "test"
    ood = splits == "ood_test"

    fit_kind = "ridge" if experiment == "E0" else "mlp"
    weights_payload: dict[str, Any] = {"heads": np.array(heads), "fit_kind": fit_kind}

    if experiment == "E0":
        W, b = _fit_ridge_multioutput(X[train], Y[train], M[train])
        predict_fn = lambda xx: _predict_linear(xx, W, b)  # noqa: E731
        weights_payload["W"] = W
        weights_payload["b"] = b
        history: list[dict[str, float]] = []
    elif experiment == "E1":
        predict_fn, state, history = _fit_mlp(
            X[train],
            Y[train],
            M[train],
            X[val],
            Y[val],
            M[val],
            seed=seed,
            epochs=epochs,
        )
        weights_payload["mlp_state"] = state
    else:
        raise ValueError(f"unknown experiment {experiment}")

    def eval_split(name: str, mask: Any) -> dict[str, Any]:
        idx = np.where(mask)[0]
        if len(idx) == 0:
            return {"empty": True}
        pred = predict_fn(X[idx])
        return {
            "all": _slice_report(pred, Y, M, idx, heads, teachers, full_target_only=False),
            "full_target": _slice_report(pred, Y, M, idx, heads, teachers, full_target_only=True),
            "n": int(len(idx)),
        }

    fidelity_val = eval_split("val", val)
    # Selection uses val.all; test/OOD are report-only
    out = {
        "experiment": experiment,
        "fit_kind": fit_kind,
        "manifest_id": meta.get("manifest_id"),
        "protocol_id": meta.get("protocol_id"),
        "seed": seed,
        "in_dim": int(X.shape[1]),
        "n_train": int(train.sum()),
        "n_val": int(val.sum()),
        "n_test": int(test.sum()),
        "n_ood_test": int(ood.sum()),
        "fidelity_val": fidelity_val["all"],
        "fidelity_val_full_target": fidelity_val["full_target"],
        "fidelity_test": eval_split("test", test),
        "fidelity_ood_test": eval_split("ood_test", ood),
        "train_history": history,
        "selection_split": "val",
    }

    run_dir = ensure_artifacts_dir(meta.get("manifest_id")) / "baselines" / experiment
    run_dir.mkdir(parents=True, exist_ok=True)
    write_json(run_dir / "report.json", out)
    # weights: avoid pickling torch in npz when possible
    save_kw = {k: v for k, v in weights_payload.items() if k != "mlp_state"}
    if experiment == "E0":
        np.savez(run_dir / "weights.npz", **save_kw)
    else:
        write_json(run_dir / "mlp_meta.json", {"backend": (state or {}).get("backend", "numpy"), "epochs_ran": len(history)})
        if isinstance(state, dict) and "W1" in state:
            np.savez(run_dir / "weights.npz", **{k: state[k] for k in ("W1", "b1", "W2", "b2", "W3", "b3", "mu", "sigma")})
        elif isinstance(state, dict) and "mu" in state:
            np.savez(run_dir / "weights.npz", mu=state["mu"], sigma=state["sigma"])
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="E0/E1 embedding baselines")
    parser.add_argument("--manifest-dir", type=Path, required=True)
    parser.add_argument("--embeddings-npz", type=Path, required=True)
    parser.add_argument("--experiment", default="E1", choices=["E0", "E1"])
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--epochs", type=int, default=40)
    args = parser.parse_args(argv)
    report = run_embedding_baseline(
        manifest_dir=args.manifest_dir,
        embeddings_npz=args.embeddings_npz,
        experiment=args.experiment,
        seed=args.seed,
        epochs=args.epochs,
    )
    passed = (report.get("fidelity_val") or {}).get("all_required_passed")
    print(
        json.dumps(
            {
                "wrote": True,
                "experiment": report["experiment"],
                "fit_kind": report["fit_kind"],
                "all_required_passed": passed,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
