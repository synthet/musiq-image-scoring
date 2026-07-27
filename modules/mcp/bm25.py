"""BM25 lexical search over MCP tool cards (BM25F-style weighted fields)."""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any

_TOKEN_RE = re.compile(r"[a-z0-9_]+")


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall((text or "").lower())


def _field_text(entry: dict[str, Any], field: str) -> str:
    if field in ("name", "action_id"):
        return str(entry.get("action_id") or entry.get("name") or "")
    if field == "title":
        return str(entry.get("title") or "")
    if field == "tags":
        tags = entry.get("tags") or []
        return " ".join(str(t) for t in tags)
    if field == "aliases":
        aliases = entry.get("aliases") or []
        return " ".join(str(a) for a in aliases)
    if field == "examples":
        examples = entry.get("examples") or entry.get("intent_examples") or []
        return " ".join(str(e) for e in examples)
    if field == "intent_examples":
        examples = entry.get("intent_examples") or []
        return " ".join(str(e) for e in examples)
    if field == "argument_names":
        return str(entry.get("argument_names") or "")
    return str(entry.get(field) or "")


class Bm25Index:
    """Lightweight BM25 index over tool catalog entries."""

    def __init__(
        self,
        entries: list[dict[str, Any]],
        field_weights: dict[str, float] | None = None,
        *,
        k1: float = 1.2,
        b: float = 0.75,
    ) -> None:
        self._entries = entries
        self._field_weights = field_weights or {
            "name": 3.0,
            "tags": 2.0,
            "description": 1.0,
            "examples": 2.0,
            "args_summary": 1.5,
        }
        self._k1 = k1
        self._b = b
        self._doc_fields: list[dict[str, list[str]]] = []
        self._doc_lengths: list[float] = []
        self._avgdl = 0.0
        self._df: Counter[str] = Counter()
        self._N = len(entries)
        self._build()

    def _build(self) -> None:
        for entry in self._entries:
            fields: dict[str, list[str]] = {}
            total_len = 0.0
            for field, weight in self._field_weights.items():
                if weight <= 0:
                    continue
                tokens = tokenize(_field_text(entry, field))
                fields[field] = tokens
                total_len += len(tokens) * weight
                for tok in set(tokens):
                    self._df[tok] += 1
            self._doc_fields.append(fields)
            self._doc_lengths.append(total_len)
        if self._N:
            self._avgdl = sum(self._doc_lengths) / self._N

    def _idf(self, term: str) -> float:
        df = self._df.get(term, 0)
        return math.log(1.0 + (self._N - df + 0.5) / (df + 0.5))

    def _score_doc(self, q_terms: list[str], doc_idx: int) -> float:
        fields = self._doc_fields[doc_idx]
        dl = self._doc_lengths[doc_idx]
        score = 0.0
        for field, weight in self._field_weights.items():
            if weight <= 0:
                continue
            doc_tokens = fields.get(field) or []
            if not doc_tokens:
                continue
            tf_map = Counter(doc_tokens)
            field_len = len(doc_tokens) * weight
            norm = 1.0 - self._b + self._b * (field_len / (self._avgdl or 1.0))
            for term in q_terms:
                tf = tf_map.get(term, 0)
                if tf <= 0:
                    continue
                num = tf * (self._k1 + 1.0)
                den = tf + self._k1 * norm
                score += weight * self._idf(term) * (num / den)
        return score

    def search(
        self,
        query: str,
        *,
        limit: int = 10,
        domain: str | None = None,
        repo: str | None = None,
        risk: str | None = None,
    ) -> list[tuple[dict[str, Any], float]]:
        q_terms = tokenize(query)
        if not q_terms:
            return []

        scored: list[tuple[int, float]] = []
        for idx, entry in enumerate(self._entries):
            if domain and entry.get("domain") != domain:
                continue
            if repo and entry.get("repo") != repo:
                continue
            if risk and entry.get("risk") != risk:
                continue
            s = self._score_doc(q_terms, idx)
            if s > 0:
                scored.append((idx, s))

        scored.sort(key=lambda x: x[1], reverse=True)
        out: list[tuple[dict[str, Any], float]] = []
        for idx, s in scored[: max(1, limit)]:
            out.append((self._entries[idx], s))
        return out


def format_when_to_use(entry: dict[str, Any]) -> str:
    examples = entry.get("examples") or []
    if examples:
        return f"Example intents: {'; '.join(str(e) for e in examples[:3])}"
    tags = entry.get("tags") or []
    if tags:
        return f"Tags: {', '.join(str(t) for t in tags[:6])}"
    return str(entry.get("description") or "")
