"""Parse Cursor agent transcripts and extract lesson candidates."""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import yaml

from scripts.agent_memory.consolidate import normalize_text
from scripts.agent_memory.secrets import find_secret_hits

UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.I,
)
USER_QUERY_RE = re.compile(r"<user_query>\s*(.*?)\s*</user_query>", re.S | re.I)
PROJECT_PATH_RE = re.compile(
    r"(?:D:|/mnt/[a-z])/Projects/([A-Za-z0-9_.\-]+)(?:/|\\)",
    re.I,
)
WSL_PROJECT_PATH_RE = re.compile(
    r"/mnt/[a-z]/Projects/([A-Za-z0-9_.\-]+)(?:/|$)",
    re.I,
)
OFF_TOPIC_MARKERS = (
    "factorio",
    "appdata\\roaming\\factorio",
    "lightroom catalog",
    "nwn player",
)

THEME_KEYWORDS: dict[str, tuple[str, ...]] = {
    "wsl_env": ("~/.venvs/tf", "wsl", "ld_library_path", "image-scoring-tests"),
    "pytest": ("pytest", "test_probe", "not gpu and not db", "postgres api e2e"),
    "mcp": ("is-be-mcp", "dispatch(", "search(", "mcp_server"),
    "e2e_naming": ("postgres api e2e", "docker inference e2e", "inference_e2e"),
    "gallery_ipc": ("electron/", "ipc", "preload", "webui.lock", "apiService"),
    "raw_export": ("nef", "raw preview", "exif orientation", "exportImageBake"),
    "wiki_okf": ("wiki-ingest", "okf_lint", "docs/log.md"),
    "db_postgres": ("db_postgres", "pgvector", "alembic", "postgres"),
    "pipeline": ("phase_code", "culling", "scoring", "clustering"),
    "input_size": ("input-size", "max_size", "thumbnail long edge"),
    "release": ("changelog", "release-notes", "gh pr create"),
    "nwscript": ("nwscript", "nwn-modules", "docker-ops"),
    "telegram": ("telegram", "telebot", "birdweather"),
    "design_tokens": ("image-scoring-ui", "tokens.json", "embeddingSpace"),
}

AUTHORITY_FILES = (
    "CLAUDE.md",
    "AGENTS.md",
    ".agent-memory/memory.md",
    "docs/CANONICAL_SOURCES.md",
)


@dataclass
class ParsedTurn:
    role: str
    text: str
    tool_names: list[str] = field(default_factory=list)
    paths: list[str] = field(default_factory=list)
    commands: list[str] = field(default_factory=list)


@dataclass
class TranscriptRecord:
    uuid: str
    workspace: str
    path: Path
    mtime: float
    user_queries: list[str] = field(default_factory=list)
    assistant_texts: list[str] = field(default_factory=list)
    file_paths: list[str] = field(default_factory=list)
    commands: list[str] = field(default_factory=list)
    tool_names: list[str] = field(default_factory=list)
    repo_scores: dict[str, int] = field(default_factory=dict)
    themes: list[str] = field(default_factory=list)
    relevance: float = 0.0
    primary_repo: str | None = None
    outcome: str | None = None
    turn_count: int = 0

    @property
    def task_summary(self) -> str:
        if self.user_queries:
            first = self.user_queries[0].strip()
            return first[:240] + ("…" if len(first) > 240 else "")
        return f"Transcript {self.uuid[:8]}"

    @property
    def corpus(self) -> str:
        parts = self.user_queries + self.assistant_texts
        return "\n".join(parts)


def load_json_config(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def resolve_repo_path(projects_root: Path, repo_name: str) -> Path:
    return projects_root / repo_name


def load_workspace_config(config_dir: Path) -> tuple[dict[str, Any], dict[str, Any], Path, Path]:
    workspace_map = load_json_config(config_dir / "workspace_map.json")
    repo_profiles = load_json_config(config_dir / "repo_profiles.json")
    projects_root = Path(workspace_map.get("projects_root", "D:/Projects"))
    cursor_root = Path(workspace_map.get("cursor_projects_root", ""))
    return workspace_map, repo_profiles, projects_root, cursor_root


def discover_parent_transcripts(cursor_projects: Path) -> list[tuple[str, Path, float]]:
    """Return (workspace_name, jsonl_path, mtime) for parent chats only."""
    found: list[tuple[str, Path, float]] = []
    if not cursor_projects.is_dir():
        return found
    for workspace_dir in cursor_projects.iterdir():
        if not workspace_dir.is_dir() or not workspace_dir.name.startswith("d-Projects-"):
            continue
        transcripts_dir = workspace_dir / "agent-transcripts"
        if not transcripts_dir.is_dir():
            continue
        for chat_dir in transcripts_dir.iterdir():
            if not chat_dir.is_dir() or chat_dir.name == "subagents":
                continue
            if not UUID_RE.match(chat_dir.name):
                continue
            jsonl = chat_dir / f"{chat_dir.name}.jsonl"
            if jsonl.is_file():
                found.append((workspace_dir.name, jsonl, jsonl.stat().st_mtime))
    return found


def dedupe_transcripts(
    entries: Iterable[tuple[str, Path, float]],
) -> dict[str, tuple[str, Path, float]]:
    """Keep newest mtime per transcript UUID."""
    by_uuid: dict[str, tuple[str, Path, float]] = {}
    for workspace, path, mtime in entries:
        uuid = path.parent.name
        prev = by_uuid.get(uuid)
        if prev is None or mtime > prev[2]:
            by_uuid[uuid] = (workspace, path, mtime)
    return by_uuid


def _extract_text_from_message(message: dict[str, Any]) -> str:
    content = message.get("content") or []
    chunks: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "text":
            chunks.append(str(item.get("text") or ""))
    return "\n".join(chunks)


def _extract_paths_from_obj(obj: Any, paths: set[str]) -> None:
    if isinstance(obj, str):
        if "Projects" in obj or "projects" in obj:
            paths.add(obj)
        return
    if isinstance(obj, dict):
        for key, val in obj.items():
            if key in ("path", "target_directory", "working_directory", "glob_pattern"):
                if isinstance(val, str):
                    paths.add(val)
            _extract_paths_from_obj(val, paths)
    elif isinstance(obj, list):
        for item in obj:
            _extract_paths_from_obj(item, paths)


def _extract_commands_from_obj(obj: Any, commands: list[str]) -> None:
    if isinstance(obj, dict):
        if "command" in obj and isinstance(obj["command"], str):
            cmd = obj["command"].strip()
            if len(cmd) >= 5:
                commands.append(cmd[:500])
        for val in obj.values():
            _extract_commands_from_obj(val, commands)
    elif isinstance(obj, list):
        for item in obj:
            _extract_commands_from_obj(item, commands)


def parse_jsonl(path: Path) -> list[ParsedTurn]:
    turns: list[ParsedTurn] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            role = str(row.get("role") or "")
            if role not in ("user", "assistant"):
                continue
            message = row.get("message") or {}
            text = _extract_text_from_message(message)
            tool_names: list[str] = []
            paths: set[str] = set()
            commands: list[str] = []
            for item in message.get("content") or []:
                if not isinstance(item, dict):
                    continue
                if item.get("type") == "tool_use":
                    name = item.get("name")
                    if name:
                        tool_names.append(str(name))
                    tool_input = item.get("input")
                    _extract_paths_from_obj(tool_input, paths)
                    _extract_commands_from_obj(tool_input, commands)
            turns.append(
                ParsedTurn(
                    role=role,
                    text=text,
                    tool_names=tool_names,
                    paths=sorted(paths),
                    commands=commands,
                )
            )
    return turns


def extract_user_queries(text: str) -> list[str]:
    return [m.strip() for m in USER_QUERY_RE.findall(text) if m.strip()]


def score_repos_in_text(text: str, known_repos: set[str]) -> Counter[str]:
    scores: Counter[str] = Counter()
    lower = text.lower()
    for marker in OFF_TOPIC_MARKERS:
        if marker in lower:
            scores["_off_topic"] += 3
    for match in PROJECT_PATH_RE.finditer(text):
        repo = match.group(1)
        if repo in known_repos:
            scores[repo] += 2
    for match in WSL_PROJECT_PATH_RE.finditer(text):
        repo = match.group(1)
        if repo in known_repos:
            scores[repo] += 2
    for repo in known_repos:
        token = repo.replace("-", " ")
        if repo.replace("_", "-") in lower or repo in lower:
            scores[repo] += 1
    return scores


def detect_themes(text: str) -> list[str]:
    lower = text.lower()
    hits: list[str] = []
    for theme, keywords in THEME_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            hits.append(theme)
    return hits


def compute_relevance(record: TranscriptRecord, workspace_repos: list[str]) -> float:
    if record.repo_scores.get("_off_topic", 0) >= 3 and sum(
        v for k, v in record.repo_scores.items() if k != "_off_topic"
    ) == 0:
        return 0.05
    score = 0.0
    project_hits = sum(v for k, v in record.repo_scores.items() if k != "_off_topic")
    if project_hits:
        score += min(0.5, project_hits * 0.05)
    if record.themes:
        score += min(0.35, len(record.themes) * 0.07)
    if record.user_queries:
        score += 0.1
    if record.file_paths:
        score += min(0.15, len(record.file_paths) * 0.01)
    if workspace_repos and any(r in record.repo_scores for r in workspace_repos):
        score += 0.1
    return min(1.0, score)


def build_record(
    uuid: str,
    workspace: str,
    path: Path,
    mtime: float,
    known_repos: set[str],
    workspace_repos: list[str],
) -> TranscriptRecord:
    turns = parse_jsonl(path)
    record = TranscriptRecord(
        uuid=uuid,
        workspace=workspace,
        path=path,
        mtime=mtime,
        turn_count=len(turns),
    )
    all_text_parts: list[str] = []
    for turn in turns:
        all_text_parts.append(turn.text)
        if turn.role == "user":
            record.user_queries.extend(extract_user_queries(turn.text))
            if not record.user_queries and turn.text.strip():
                stripped = turn.text.strip()
                if len(stripped) < 500:
                    record.user_queries.append(stripped)
        elif turn.role == "assistant":
            if turn.text.strip() and "[REDACTED]" not in turn.text[:40]:
                record.assistant_texts.append(turn.text.strip())
        record.file_paths.extend(turn.paths)
        record.tool_names.extend(turn.tool_names)
        record.commands.extend(turn.commands)

    corpus = "\n".join(all_text_parts)
    repo_counter: Counter[str] = Counter()
    repo_counter.update(score_repos_in_text(corpus, known_repos))
    record.repo_scores = dict(repo_counter)
    record.themes = detect_themes(corpus)
    if record.repo_scores:
        filtered = {k: v for k, v in record.repo_scores.items() if k != "_off_topic"}
        if filtered:
            record.primary_repo = max(filtered, key=filtered.get)  # type: ignore[arg-type]
    record.relevance = compute_relevance(record, workspace_repos)
    record.outcome = _infer_outcome(turns)
    record.file_paths = sorted(set(record.file_paths))[:80]
    record.commands = list(dict.fromkeys(record.commands))[:30]
    record.tool_names = list(dict.fromkeys(record.tool_names))[:30]
    return record


def _infer_outcome(turns: list[ParsedTurn]) -> str | None:
    for turn in reversed(turns):
        if turn.role != "assistant":
            continue
        text = turn.text.strip()
        if not text or len(text) < 40:
            continue
        if text.startswith("Done") or "## Results" in text or "## Summary" in text:
            return text[:1200]
    for turn in reversed(turns):
        if turn.role == "assistant" and turn.text.strip():
            return turn.text.strip()[:800]
    return None


def load_authority_corpus(repo_root: Path) -> str:
    parts: list[str] = []
    for rel in AUTHORITY_FILES:
        path = repo_root / rel
        if path.is_file():
            try:
                parts.append(path.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                continue
    skills_dir = repo_root / ".cursor" / "skills"
    if skills_dir.is_dir():
        for skill in skills_dir.glob("**/SKILL.md"):
            try:
                parts.append(skill.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                continue
    return "\n".join(parts)


def is_duplicate_lesson(text: str, authority_corpus: str) -> bool:
    key = normalize_text(text)
    if len(key) < 20:
        return True
    auth_norm = normalize_text(authority_corpus)
    if key in auth_norm:
        return True
    words = key.split()
    if len(words) >= 4:
        snippet = " ".join(words[: min(8, len(words))])
        if len(snippet) > 25 and snippet in auth_norm:
            return True
    return False


def extract_heuristic_candidates(record: TranscriptRecord) -> list[dict[str, str]]:
    """Rule-based memory_candidates from transcript structure."""
    candidates: list[dict[str, str]] = []
    corpus_lower = record.corpus.lower()

    rules: list[tuple[tuple[str, ...], str, str, str]] = [
        (
            ("~/.venvs/tf", "wsl -e bash"),
            "Python app/scripts importing modules should run in WSL with ~/.venvs/tf unless documented otherwise.",
            "working_rule",
            "high",
        ),
        (
            ("image-scoring-tests", "pytest -m wsl"),
            "Official WSL pytest suite uses ~/.venvs/image-scoring-tests, not ~/.venvs/tf.",
            "working_rule",
            "high",
        ),
        (
            ("test_probe.py", "--ignore=tests/test_probe.py"),
            "Fast pytest runs must ignore tests/test_probe.py (import-time DB calls).",
            "recurring_issue",
            "high",
        ),
        (
            ("postgres api e2e", "docker inference e2e", "inference_e2e"),
            "Disambiguate Postgres API E2E (tests/integration) vs Docker inference E2E (tests/e2e_docker).",
            "recurring_issue",
            "medium",
        ),
        (
            ("search(", "dispatch(", "is-be-mcp"),
            "Use MCP search then dispatch on is-be-mcp / is-ui-mcp before ad-hoc debugging.",
            "successful_pattern",
            "medium",
        ),
        (
            ("webui.lock", "config.api"),
            "Gallery resolves backend URL via webui.lock with config.api override.",
            "stable_fact",
            "high",
        ),
        (
            ("exportimagebake", "exif orientation", "usemwg"),
            "JPEG export EXIF orientation is a separate pass from raster bake; see gallery feature doc.",
            "working_rule",
            "high",
        ),
        (
            ("okf_lint", "wiki-ingest", "docs/log.md"),
            "Doc changes should go through OKF wiki ingest and append docs/log.md.",
            "successful_pattern",
            "medium",
        ),
        (
            ("never modify `.git/config`", "extensions.worktreeconfig"),
            "Never modify .git/config (worktreeConfig breaks embedded git libraries).",
            "working_rule",
            "high",
        ),
        (
            ("tokens.json", "image-scoring-ui", "prepublishonly"),
            "Design token changes start in image-scoring-ui src/tokens.json; bump consumers after npm build.",
            "working_rule",
            "medium",
        ),
    ]

    for keywords, text, category, confidence in rules:
        if any(kw in corpus_lower for kw in keywords):
            candidates.append(
                {
                    "text": text,
                    "category": category,
                    "confidence": confidence,
                    "source_hint": record.uuid[:8],
                }
            )

    if record.outcome and record.relevance >= 0.35:
        first_line = record.outcome.splitlines()[0].strip()
        if 30 < len(first_line) < 200 and "factorio" not in first_line.lower():
            candidates.append(
                {
                    "text": f"Session outcome pattern: {first_line}",
                    "category": "successful_pattern",
                    "confidence": "low",
                    "source_hint": record.uuid[:8],
                }
            )

    seen: set[str] = set()
    unique: list[dict[str, str]] = []
    for cand in candidates:
        key = normalize_text(cand["text"])
        if key not in seen:
            seen.add(key)
            unique.append(cand)
    return unique


def filter_candidates_for_repo(
    candidates: list[dict[str, str]],
    authority_corpus: str,
) -> list[dict[str, str]]:
    safe: list[dict[str, str]] = []
    for cand in candidates:
        text = cand.get("text") or ""
        if find_secret_hits(text):
            continue
        if is_duplicate_lesson(text, authority_corpus):
            continue
        safe.append(cand)
    return safe


def record_to_session_yaml(record: TranscriptRecord, candidates: list[dict[str, str]]) -> dict[str, Any]:
    ts = datetime.fromtimestamp(record.mtime, tz=timezone.utc).isoformat()
    return {
        "timestamp": ts,
        "task_summary": record.task_summary,
        "final_outcome": (record.outcome or "")[:2000],
        "files_touched": [p for p in record.file_paths if "Projects" in p][:40],
        "commands_run": record.commands[:20],
        "tests_run": [],
        "test_results": "",
        "key_decisions": record.themes,
        "errors_or_blockers": [],
        "memory_candidates": candidates,
        "source_transcript_uuid": record.uuid,
        "source_workspace": record.workspace,
    }


def group_records_by_repo(
    records: list[TranscriptRecord],
    workspace_map: dict[str, Any],
) -> dict[str, list[TranscriptRecord]]:
    workspaces = workspace_map.get("workspaces") or {}
    grouped: dict[str, list[TranscriptRecord]] = defaultdict(list)
    for record in records:
        ws_cfg = workspaces.get(record.workspace) or {}
        default_repos = ws_cfg.get("repos") or []
        repo = record.primary_repo
        if repo is None and default_repos:
            repo = default_repos[0]
        if repo is None:
            repo = "_unassigned"
        grouped[repo].append(record)
    for repo in grouped:
        grouped[repo].sort(key=lambda r: r.relevance, reverse=True)
    return dict(grouped)


def render_review_markdown(
    repo_name: str,
    records: list[TranscriptRecord],
    candidates_by_uuid: dict[str, list[dict[str, str]]],
    profile: dict[str, Any],
) -> str:
    tier = profile.get("tier", "?")
    lines = [
        f"# Transcript mining review — {repo_name}",
        "",
        f"**Tier:** {tier} · **Chats routed:** {len(records)}",
        "",
        "## Top sessions (by relevance)",
        "",
        "| UUID | Relevance | Themes | Summary |",
        "|------|-----------|--------|---------|",
    ]
    for rec in records[:40]:
        themes = ", ".join(rec.themes[:4]) or "—"
        summary = rec.task_summary.replace("|", "\\|")[:80]
        lines.append(
            f"| `{rec.uuid[:8]}` | {rec.relevance:.2f} | {themes} | {summary} |"
        )
    lines.extend(["", "## Proposed memory candidates", ""])
    seen_texts: set[str] = set()
    for rec in records:
        cands = candidates_by_uuid.get(rec.uuid) or []
        if not cands:
            continue
        lines.append(f"### `{rec.uuid[:8]}` — {rec.task_summary[:60]}")
        lines.append("")
        for cand in cands:
            text = cand["text"]
            key = normalize_text(text)
            if key in seen_texts:
                continue
            seen_texts.add(key)
            lines.append(
                f"- **{cand['category']}** ({cand['confidence']}): {text} "
                f"_(chat {cand.get('source_hint', rec.uuid[:8])})_"
            )
        lines.append("")
    if not seen_texts:
        lines.append("_No new candidates after dedupe/secret filter._")
    return "\n".join(lines) + "\n"


def render_summary_report(
    all_records: list[TranscriptRecord],
    grouped: dict[str, list[TranscriptRecord]],
    repo_profiles: dict[str, Any],
) -> str:
    lines = [
        "# Transcript mining summary",
        "",
        f"**Total parent chats (deduped):** {len(all_records)}",
        "",
        "## By repo",
        "",
        "| Repo | Tier | Chats | Avg relevance | Top themes |",
        "|------|------|-------|---------------|------------|",
    ]
    for repo, records in sorted(grouped.items(), key=lambda x: -len(x[1])):
        if repo == "_unassigned":
            profile = {"tier": "?"}
        else:
            profile = repo_profiles.get(repo, {})
        tier = profile.get("tier", "?")
        avg = sum(r.relevance for r in records) / len(records) if records else 0
        theme_counter: Counter[str] = Counter()
        for r in records:
            theme_counter.update(r.themes)
        top_themes = ", ".join(t for t, _ in theme_counter.most_common(4)) or "—"
        lines.append(
            f"| {repo} | {tier} | {len(records)} | {avg:.2f} | {top_themes} |"
        )
    lines.extend(["", "## Workspaces scanned", ""])
    ws_counter = Counter(r.workspace for r in all_records)
    for ws, count in ws_counter.most_common():
        lines.append(f"- `{ws}`: {count} chats")
    return "\n".join(lines) + "\n"


def consolidate_repo_candidates(
    repo_records: list[TranscriptRecord],
    candidates_by_uuid: dict[str, list[dict[str, str]]],
    *,
    max_items: int = 20,
    min_confidence: str = "medium",
) -> list[dict[str, str]]:
    """Merge unique high-confidence candidates across chats for one session log."""
    rank = {"high": 3, "medium": 2, "low": 1}
    min_rank = rank.get(min_confidence, 2)
    seen: set[str] = set()
    merged: list[tuple[int, dict[str, str]]] = []
    for rec in sorted(repo_records, key=lambda r: r.relevance, reverse=True):
        for cand in candidates_by_uuid.get(rec.uuid) or []:
            if rank.get(cand.get("confidence", "low"), 1) < min_rank:
                continue
            key = normalize_text(cand.get("text") or "")
            if not key or key in seen:
                continue
            seen.add(key)
            merged.append((rank.get(cand.get("confidence", "low"), 1), cand))
    merged.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in merged[:max_items]]


def write_session_files(
    repo_root: Path,
    sessions: list[dict[str, Any]],
    *,
    dry_run: bool = False,
) -> list[Path]:
    raw_dir = repo_root / ".agent-memory" / "raw-sessions"
    written: list[Path] = []
    for session in sessions:
        uuid = str(session.get("source_transcript_uuid", "unknown"))[:24]
        if uuid.startswith("transcript-mining"):
            filename = "2026-06-16-transcript-mining-batch1.yaml"
        else:
            ts_slug = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
            filename = f"transcript-{ts_slug}-{uuid[:8]}.yaml"
        path = raw_dir / filename
        body = yaml.safe_dump(session, sort_keys=False, allow_unicode=True)
        if find_secret_hits(body):
            continue
        if not dry_run:
            raw_dir.mkdir(parents=True, exist_ok=True)
            path.write_text(body, encoding="utf-8")
        written.append(path)
    return written
