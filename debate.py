#!/usr/bin/env python3
"""Debate Loops v0.2 — one topic, both sides, then the room weighs in.

Commands: topics, pick, start, fill, practice, preflight, log, show.

Practice at honest pushback. No pulling rank. The owner's rules outrank any
result. A verdict is an opinion, not policy, unless the owner signs off.
Changing your mind gets credit, not a penalty. Records stay shareable:
never put secrets, passwords, private facts, or vault data in them.

Preflight mode: before a non-trivial plan reaches the owner, an Optimist seat
and a Realist seat argue it. The output is a short sharpened plan.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Sequence
from zoneinfo import ZoneInfo

VERSION = "v0.2"
TZ = ZoneInfo("America/Chicago")
RECENT_WINDOW = 6
WORD_LIMIT = 120
LINE_WORD_LIMIT = 60
SIDES = ("for", "against")
LANDINGS = ("for", "against", "split", "changed my mind")
LANDING_ALIASES = {
    "for": "for",
    "against": "against",
    "split": "split",
    "changed my mind": "changed my mind",
    "changed_my_mind": "changed my mind",
    "changed-my-mind": "changed my mind",
    "changed": "changed my mind",
}
CATEGORIES = ("fun", "craft", "ethics", "family")
MODES = ("moot", "practice")
SECTIONS = ("openings", "rebuttals", "steelmans")
SEATS = ("optimist", "realist")
PREFLIGHT_LANDINGS = ("go", "go-with-changes", "hold", "scrap")
PREFLIGHT_LANDING_ALIASES = {
    "go": "go",
    "go-with-changes": "go-with-changes",
    "go_with_changes": "go-with-changes",
    "go with changes": "go-with-changes",
    "hold": "hold",
    "scrap": "scrap",
}
PLAN_WORD_LIMIT = 400
SHARPENED_WORD_LIMIT = 120
PREFLIGHT_SUMMARY_MIN_LINES = 3
PREFLIGHT_SUMMARY_MAX_LINES = 6
CHECKLIST_ITEMS = (
    {
        "id": "owner-ok",
        "title": "Sends, spends, anything public, and private things need the owner's OK",
        "detail": (
            "Do not send messages, spend money, publish anything, or touch "
            "the owner's private things without approval."
        ),
    },
    {
        "id": "no-private-to-consultants",
        "title": "Nothing private goes to third-party consultants",
        "detail": (
            "Private family facts, records, and vault data stay off "
            "consultant channels."
        ),
    },
    {
        "id": "public-release",
        "title": "Public release rule",
        "detail": (
            "Nothing public may include unpublished security-test results, "
            "weaknesses, or defense configs."
        ),
    },
    {
        "id": "drive-room-cap",
        "title": "Respect the household storage cap",
        "detail": "Do not grow shared storage past the household cap.",
    },
    {
        "id": "usage-budget",
        "title": "Usage budget",
        "detail": (
            "Respect the usage budget; do not burn runs on work that can wait."
        ),
    },
    {
        "id": "permanent-fix",
        "title": "Prefer a permanent fix over a band-aid",
        "detail": (
            "If a lasting fix is in reach, do not ship a temporary patch "
            "and walk away."
        ),
    },
    {
        "id": "fail-safe",
        "title": "Failsafes must fail safe",
        "detail": (
            "If a safeguard breaks, it should stop or stay safe, not fail open."
        ),
    },
    {
        "id": "messy-then-clean",
        "title": "A messy first pass is fine, but clean it up after",
        "detail": (
            "It is okay to start messy; the follow-up cleanup is part of the job."
        ),
    },
)
SECRET_PATTERNS = (
    re.compile(r"password\s*[:=]\s*\S+", re.I),
    re.compile(r"passwd\s*[:=]\s*\S+", re.I),
    re.compile(r"api[_-]?key\s*[:=]\s*\S+", re.I),
    re.compile(r"secret\s*[:=]\s*\S+", re.I),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"vault\s*(id|key|token)\s*[:=]\s*\S+", re.I),
)


class DebateError(Exception):
    """User-facing error for bad topics, text, or verdicts."""


# ---- paths ------------------------------------------------------------------
def home() -> Path:
    raw = os.environ.get("DEBATE_HOME", "").strip()
    return Path(raw).resolve() if raw else Path(__file__).resolve().parent


def package_dir() -> Path:
    return Path(__file__).resolve().parent


def topics_path() -> Path:
    raw = os.environ.get("DEBATE_TOPICS", "").strip()
    if raw:
        return Path(raw).resolve()
    override = home() / "topics.json"
    if override.is_file():
        return override
    return package_dir() / "topics.json"


def records_dir() -> Path:
    path = home() / "records"
    path.mkdir(parents=True, exist_ok=True)
    return path


def now() -> datetime:
    return datetime.now(TZ)


# ---- helpers ----------------------------------------------------------------
def word_count(text: str) -> int:
    return len(text.split())


def normalize_space(text: str) -> str:
    return " ".join(text.split())


def canonical_landing(value: str) -> str:
    key = (value or "").strip().lower()
    if key not in LANDING_ALIASES:
        raise DebateError(
            "Landing must be one of: for, against, split, changed my mind."
        )
    return LANDING_ALIASES[key]


def assert_shareable(text: str, label: str) -> None:
    for pattern in SECRET_PATTERNS:
        if pattern.search(text):
            raise DebateError(
                f"{label} looks like a secret or credential. "
                "Records stay shareable: no passwords, vault data, or private facts."
            )


def assert_speech(text: str, label: str, limit: int = WORD_LIMIT) -> str:
    cleaned = text.strip()
    if not cleaned:
        raise DebateError(f"{label} cannot be empty.")
    if "\n\n\n" in cleaned:
        raise DebateError(f"{label} should stay short and tight.")
    assert_shareable(cleaned, label)
    n = word_count(cleaned)
    if n > limit:
        raise DebateError(
            f"{label} is {n} words; keep it to {limit} or fewer."
        )
    return cleaned


def assert_one_line(text: str, label: str) -> str:
    cleaned = normalize_space(text)
    if not cleaned:
        raise DebateError(f"{label} cannot be empty.")
    if "\n" in text.strip():
        raise DebateError(f"{label} should be one line.")
    assert_shareable(cleaned, label)
    n = word_count(cleaned)
    if n > LINE_WORD_LIMIT:
        raise DebateError(
            f"{label} is {n} words; keep it to one line ({LINE_WORD_LIMIT} or fewer)."
        )
    return cleaned


def _load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except (OSError, ValueError) as exc:
        raise DebateError(f"Could not read {path}: {exc}") from exc


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


# ---- topics -----------------------------------------------------------------
def load_topics(path: Path | None = None) -> list[dict[str, str]]:
    data = _load_json(path or topics_path(), None)
    if not isinstance(data, dict) or not isinstance(data.get("topics"), list):
        raise DebateError("Topic bank is missing or malformed.")
    topics = []
    seen = set()
    for item in data["topics"]:
        if not isinstance(item, dict):
            raise DebateError("Each topic must be an object with id, title, and category.")
        tid = str(item.get("id", "")).strip()
        title = str(item.get("title", "")).strip()
        category = str(item.get("category", "")).strip()
        if not tid or not title:
            raise DebateError("Each topic needs an id and a title.")
        if category not in CATEGORIES:
            raise DebateError(
                f"Topic {tid} has category {category!r}; "
                f"use one of: {', '.join(CATEGORIES)}."
            )
        if tid in seen:
            raise DebateError(f"Duplicate topic id: {tid}")
        seen.add(tid)
        topics.append({"id": tid, "title": title, "category": category})
    if not topics:
        raise DebateError("Topic bank is empty.")
    return topics


def get_topic(topic_id: str, topics: list[dict[str, str]] | None = None) -> dict[str, str]:
    bank = topics if topics is not None else load_topics()
    for topic in bank:
        if topic["id"] == topic_id:
            return topic
    raise DebateError(f"Unknown topic id: {topic_id}")


def format_topics(topics: Iterable[dict[str, str]] | None = None) -> str:
    bank = list(topics) if topics is not None else load_topics()
    lines = [
        f"Debate Loops {VERSION} — {len(bank)} topics",
        "id  category  title",
        "--  --------  -----",
    ]
    for topic in bank:
        lines.append(f"{topic['id']}  {topic['category']}  {topic['title']}")
    return "\n".join(lines)


# ---- records ----------------------------------------------------------------
def _record_paths(debate_id: str) -> tuple[Path, Path]:
    base = records_dir() / debate_id
    return base.with_suffix(".json"), base.with_suffix(".md")


def list_records() -> list[dict[str, Any]]:
    items = []
    folder = records_dir()
    if not folder.is_dir():
        return items
    for path in sorted(folder.glob("*.json")):
        data = _load_json(path, None)
        if isinstance(data, dict) and data.get("id"):
            items.append(data)
    items.sort(key=lambda row: (row.get("created") or "", row.get("id") or ""))
    return items


def load_debate(debate_id: str) -> dict[str, Any]:
    json_path, _ = _record_paths(debate_id)
    data = _load_json(json_path, None)
    if not isinstance(data, dict) or data.get("id") != debate_id:
        raise DebateError(f"No debate record named {debate_id}.")
    return data


def recent_topic_ids(
    records: list[dict[str, Any]] | None = None,
    window: int = RECENT_WINDOW,
) -> list[str]:
    rows = records if records is not None else list_records()
    newest_first = sorted(
        rows, key=lambda row: (row.get("created") or "", row.get("id") or ""), reverse=True
    )
    ids = []
    for row in newest_first:
        tid = str(row.get("topic_id") or "").strip()
        if tid:
            ids.append(tid)
        if len(ids) >= window:
            break
    return ids


def pick_topic(
    topics: list[dict[str, str]] | None = None,
    records: list[dict[str, Any]] | None = None,
    window: int = RECENT_WINDOW,
    rng: random.Random | None = None,
) -> dict[str, str]:
    bank = topics if topics is not None else load_topics()
    blocked = set(recent_topic_ids(records, window=window))
    eligible = [topic for topic in bank if topic["id"] not in blocked]
    if not eligible:
        raise DebateError(
            f"No eligible topic left: all {len(bank)} are in the last {window} debates. "
            "Pass a topic id to start or practice if you want a repeat."
        )
    chooser = rng if rng is not None else random.Random()
    return chooser.choice(eligible)


def _empty_sides() -> dict[str, Any]:
    return {"for": None, "against": None}


def _next_id(when: datetime | None = None) -> str:
    stamp = (when or now()).strftime("%Y-%m-%d")
    existing = [row["id"] for row in list_records() if row.get("id", "").startswith(stamp)]
    number = 1
    while f"{stamp}-{number:02d}" in existing:
        number += 1
    return f"{stamp}-{number:02d}"


def new_record(
    topic: dict[str, str],
    *,
    mode: str = "moot",
    participant: str = "Assistant",
    when: datetime | None = None,
    debate_id: str | None = None,
) -> dict[str, Any]:
    if mode not in MODES:
        raise DebateError("Mode must be moot or practice.")
    created = when or now()
    name = (participant or "").strip() or "Assistant"
    return {
        "id": debate_id or _next_id(created),
        "version": VERSION,
        "created": created.isoformat(timespec="seconds"),
        "timezone": "America/Chicago",
        "mode": mode,
        "status": "open",
        "topic_id": topic["id"],
        "topic": topic["title"],
        "category": topic["category"],
        "participants": [name],
        "openings": _empty_sides(),
        "rebuttals": _empty_sides(),
        "steelmans": _empty_sides(),
        "verdicts": [],
        "notes": (
            "Changing your mind gets credit, not a penalty. "
            "Results are opinions, not policy, unless the owner signs off."
        ),
    }


def set_speech(
    record: dict[str, Any],
    section: str,
    side: str,
    text: str,
    speaker: str | None = None,
) -> dict[str, Any]:
    if section not in SECTIONS:
        raise DebateError("Section must be openings, rebuttals, or steelmans.")
    if side not in SIDES:
        raise DebateError("Side must be for or against.")
    cleaned = assert_speech(text, f"{side} {section[:-1]}")
    who = (speaker or _default_speaker(record)).strip()
    if not who:
        raise DebateError("Speaker cannot be empty.")
    record[section][side] = {
        "speaker": who,
        "text": cleaned,
        "words": word_count(cleaned),
    }
    _touch_participants(record, who)
    return record


def _default_speaker(record: dict[str, Any]) -> str:
    people = record.get("participants") or ["Assistant"]
    return str(people[0])


def _touch_participants(record: dict[str, Any], name: str) -> None:
    people = record.setdefault("participants", [])
    if name not in people:
        people.append(name)


def validate_verdict(
    landed: str,
    reason: str,
    would_change: str,
    participant: str,
) -> dict[str, str]:
    who = (participant or "").strip()
    if not who:
        raise DebateError("Verdict needs a participant name.")
    return {
        "participant": who,
        "landed": canonical_landing(landed),
        "reason": assert_one_line(reason, "Verdict reason"),
        "would_change_my_mind": assert_one_line(
            would_change, "What would change my mind"
        ),
    }


def add_verdict(
    record: dict[str, Any],
    *,
    participant: str,
    landed: str,
    reason: str,
    would_change: str,
) -> dict[str, Any]:
    entry = validate_verdict(landed, reason, would_change, participant)
    verdicts = record.setdefault("verdicts", [])
    verdicts[:] = [row for row in verdicts if row.get("participant") != entry["participant"]]
    verdicts.append(entry)
    _touch_participants(record, entry["participant"])
    return record


def missing_sections(record: dict[str, Any]) -> list[str]:
    missing = []
    for section in SECTIONS:
        for side in SIDES:
            if not record.get(section, {}).get(side):
                missing.append(f"{side} {section[:-1]}")
    if not record.get("verdicts"):
        missing.append("verdict")
    return missing


def is_complete(record: dict[str, Any]) -> bool:
    return not missing_sections(record)


def complete(record: dict[str, Any]) -> dict[str, Any]:
    missing = missing_sections(record)
    if missing:
        raise DebateError("Debate is incomplete. Still need: " + ", ".join(missing) + ".")
    record["status"] = "complete"
    return record


def render_transcript(record: dict[str, Any]) -> str:
    mode = record.get("mode") or "moot"
    mode_note = "practice (one assistant, both sides)" if mode == "practice" else "moot"
    created = record.get("created") or ""
    try:
        when = datetime.fromisoformat(created)
        date_line = when.strftime("%Y-%m-%d %-I:%M %p") + " America/Chicago"
    except ValueError:
        date_line = created or "unknown date"
    lines = [
        f"# Debate {record.get('id')} — {record.get('topic')}",
        "",
        f"- Mode: {mode_note}",
        f"- Date: {date_line}",
        f"- Topic id: {record.get('topic_id')}",
        f"- Category: {record.get('category')}",
        f"- Status: {record.get('status')}",
        f"- Participants: {', '.join(record.get('participants') or [])}",
        "",
    ]
    for section, heading in (
        ("openings", "Opening"),
        ("rebuttals", "Rebuttal"),
        ("steelmans", "Steelman"),
    ):
        for side in SIDES:
            entry = (record.get(section) or {}).get(side)
            title = f"## {heading} — {side}"
            if section == "steelmans":
                other = "against" if side == "for" else "for"
                title = f"## Steelman — {side} states the best {other} point"
            lines.append(title)
            if entry:
                speaker = entry.get("speaker") or "unknown"
                words = entry.get("words")
                suffix = f" ({words} words)" if words else ""
                lines.append(f"*{speaker}{suffix}*")
                lines.append("")
                lines.append(entry.get("text") or "")
            else:
                lines.append("_not yet written_")
            lines.append("")
    lines.append("## Verdict")
    lines.append("")
    verdicts = record.get("verdicts") or []
    if not verdicts:
        lines.append("_no verdicts yet_")
        lines.append("")
    for row in verdicts:
        lines.append(f"### {row.get('participant')}")
        lines.append(f"- Landed: {row.get('landed')}")
        lines.append(f"- Reason: {row.get('reason')}")
        lines.append(f"- What would change my mind: {row.get('would_change_my_mind')}")
        lines.append("")
    lines.append("Changing your mind gets credit, not a penalty.")
    lines.append(
        "This result is an opinion, not policy, unless the owner signs off. "
        "The owner's rules outrank anything the Moot decides."
    )
    lines.append("")
    return "\n".join(lines)


def save_debate(record: dict[str, Any]) -> tuple[Path, Path]:
    if not record.get("id"):
        raise DebateError("Record is missing an id.")
    blob = json.dumps(record, indent=2, ensure_ascii=False)
    assert_shareable(blob, "Debate record")
    json_path, md_path = _record_paths(record["id"])
    _write_json(json_path, record)
    md_path.write_text(render_transcript(record), encoding="utf-8")
    return json_path, md_path


def start_debate(
    topic_id: str,
    *,
    mode: str = "moot",
    participant: str = "Assistant",
) -> dict[str, Any]:
    record = new_record(get_topic(topic_id), mode=mode, participant=participant)
    save_debate(record)
    return record


def apply_payload(record: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    speaker = (payload.get("speaker") or _default_speaker(record)).strip()
    for section in SECTIONS:
        block = payload.get(section) or {}
        if not isinstance(block, dict):
            raise DebateError(f"{section} must be an object with for and against text.")
        for side in SIDES:
            if side in block and block[side]:
                set_speech(record, section, side, str(block[side]), speaker=speaker)
    verdict = payload.get("verdict")
    verdicts = payload.get("verdicts")
    rows: list[dict[str, Any]] = []
    if isinstance(verdict, dict):
        rows.append(verdict)
    if isinstance(verdicts, list):
        rows.extend(row for row in verdicts if isinstance(row, dict))
    for row in rows:
        add_verdict(
            record,
            participant=str(row.get("participant") or speaker),
            landed=str(row.get("landed") or ""),
            reason=str(row.get("reason") or ""),
            would_change=str(
                row.get("would_change_my_mind")
                or row.get("would_change")
                or ""
            ),
        )
    return record


def load_payload(path: Path) -> dict[str, Any]:
    data = _load_json(path, None)
    if not isinstance(data, dict):
        raise DebateError("Practice payload must be a JSON object.")
    return data


def run_practice(
    topic_id: str | None,
    payload: dict[str, Any],
    *,
    participant: str = "Assistant",
) -> dict[str, Any]:
    tid = topic_id or payload.get("topic_id")
    if not tid:
        tid = pick_topic()["id"]
    record = new_record(
        get_topic(str(tid)),
        mode="practice",
        participant=payload.get("participant") or participant,
    )
    apply_payload(record, payload)
    complete(record)
    save_debate(record)
    return record



# ---- preflight ------------------------------------------------------------------
def preflight_records_dir() -> Path:
    path = records_dir() / "preflight"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _preflight_paths(preflight_id: str) -> tuple[Path, Path]:
    base = preflight_records_dir() / preflight_id
    return base.with_suffix(".json"), base.with_suffix(".md")


def list_preflight_records() -> list[dict[str, Any]]:
    items = []
    folder = preflight_records_dir()
    if not folder.is_dir():
        return items
    for path in sorted(folder.glob("*.json")):
        data = _load_json(path, None)
        if isinstance(data, dict) and data.get("id"):
            items.append(data)
    items.sort(key=lambda row: (row.get("created") or "", row.get("id") or ""))
    return items


def load_preflight(preflight_id: str) -> dict[str, Any]:
    json_path, _ = _preflight_paths(preflight_id)
    data = _load_json(json_path, None)
    if not isinstance(data, dict) or data.get("id") != preflight_id:
        raise DebateError(f"No preflight record named {preflight_id}.")
    return data


def _next_preflight_id(when: datetime | None = None) -> str:
    stamp = (when or now()).strftime("%Y-%m-%d")
    prefix = f"pf-{stamp}-"
    existing = [
        row["id"]
        for row in list_preflight_records()
        if str(row.get("id") or "").startswith(prefix)
    ]
    number = 1
    while f"{prefix}{number:02d}" in existing:
        number += 1
    return f"{prefix}{number:02d}"


def format_checklist() -> str:
    lines = [
        "Realist checklist — address every item that applies before a plan reaches the owner.",
        "A preflight verdict is an opinion, not policy, unless the owner signs off.",
        "",
    ]
    for i, item in enumerate(CHECKLIST_ITEMS, start=1):
        lines.append(f"{i}. {item['id']} — {item['title']}")
        lines.append(f"   {item['detail']}")
    lines.append("")
    lines.append(
        "Mark each item in the payload checklist. If it applies, say how it was addressed."
    )
    return "\n".join(lines)


def checklist_ids() -> tuple[str, ...]:
    return tuple(item["id"] for item in CHECKLIST_ITEMS)


def canonical_preflight_landing(value: str) -> str:
    key = (value or "").strip().lower()
    if key not in PREFLIGHT_LANDING_ALIASES:
        raise DebateError(
            "Preflight verdict must be one of: go, go-with-changes, hold, scrap."
        )
    return PREFLIGHT_LANDING_ALIASES[key]


def _as_line_list(value: Any, label: str) -> list[str]:
    if value is None:
        items: list[Any] = []
    elif isinstance(value, str):
        items = [value]
    elif isinstance(value, list):
        items = value
    else:
        raise DebateError(f"{label} must be a list of short lines.")
    cleaned = []
    for item in items:
        text = assert_one_line(str(item), label)
        cleaned.append(text)
    return cleaned


def validate_checklist(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, dict):
        raise DebateError(
            "Preflight payload needs a checklist object keyed by item id. "
            "Run: debate.py preflight --checklist"
        )
    known = {item["id"]: item for item in CHECKLIST_ITEMS}
    unknown = sorted(set(raw) - set(known))
    if unknown:
        raise DebateError("Unknown checklist id(s): " + ", ".join(unknown) + ".")
    missing = [item_id for item_id in checklist_ids() if item_id not in raw]
    if missing:
        raise DebateError(
            "Checklist is missing: "
            + ", ".join(missing)
            + ". Every standing rule must be marked. "
            "Run: debate.py preflight --checklist"
        )
    rows = []
    unaddressed = []
    for item in CHECKLIST_ITEMS:
        entry = raw[item["id"]]
        if isinstance(entry, str):
            entry = {"applies": True, "addressed": entry}
        if not isinstance(entry, dict):
            raise DebateError(
                f"Checklist item {item['id']} must be an object "
                "with applies and addressed fields."
            )
        if "applies" not in entry:
            applies = True
        else:
            applies = bool(entry.get("applies"))
        addressed_raw = str(entry.get("addressed") or "").strip()
        if applies and not addressed_raw:
            unaddressed.append(item["id"])
            continue
        addressed = (
            assert_one_line(addressed_raw, f"{item['id']} addressed")
            if addressed_raw
            else ""
        )
        rows.append(
            {
                "id": item["id"],
                "title": item["title"],
                "applies": applies,
                "addressed": addressed,
            }
        )
    if unaddressed:
        raise DebateError(
            "Applicable checklist item(s) were not addressed: "
            + ", ".join(unaddressed)
            + "."
        )
    return rows


def _short_title(plan: str) -> str:
    words = plan.split()
    title = " ".join(words[:12])
    if len(words) > 12:
        title = title.rstrip(".,;:") + "…"
    return title


def validate_preflight_verdict(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise DebateError("Preflight payload needs a verdict object.")
    landed = canonical_preflight_landing(str(raw.get("landed") or ""))
    reason = assert_one_line(str(raw.get("reason") or ""), "Verdict reason")
    top_risk = assert_one_line(str(raw.get("top_risk") or ""), "Top risk")
    would_change = assert_one_line(
        str(raw.get("would_change_my_mind") or raw.get("would_change") or ""),
        "What would change my mind",
    )
    changes = _as_line_list(raw.get("changes"), "Changes")
    questions = _as_line_list(
        raw.get("questions") or raw.get("questions_for_owner"),
        "Questions for the owner",
    )
    if landed == "go-with-changes" and not changes:
        raise DebateError("go-with-changes needs at least one concrete change.")
    sharpened_raw = str(raw.get("sharpened_plan") or "").strip()
    return {
        "landed": landed,
        "reason": reason,
        "top_risk": top_risk,
        "changes": changes,
        "questions": questions,
        "would_change_my_mind": would_change,
        "sharpened_plan": sharpened_raw,
    }


def compose_sharpened_plan(plan: str, verdict: dict[str, Any]) -> str:
    existing = str(verdict.get("sharpened_plan") or "").strip()
    if existing:
        return assert_speech(existing, "Sharpened plan", limit=SHARPENED_WORD_LIMIT)
    landed = verdict["landed"]
    changes = verdict.get("changes") or []
    if landed == "scrap":
        draft = "Do not proceed. " + (verdict.get("reason") or "")
    elif landed == "hold":
        draft = "Hold this plan. " + (verdict.get("reason") or "")
        if changes:
            draft += " Before moving: " + "; ".join(changes) + "."
    elif changes:
        draft = plan.rstrip() + " Changes: " + "; ".join(changes) + "."
    else:
        draft = plan
    return assert_speech(draft, "Sharpened plan", limit=SHARPENED_WORD_LIMIT)


def read_plan_file(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise DebateError(f"Could not read plan file {path}: {exc}") from exc
    return assert_speech(text, "Plan", limit=PLAN_WORD_LIMIT)


def set_seat_speech(
    text: str,
    seat: str,
    kind: str,
    speaker: str | None = None,
) -> dict[str, Any]:
    if seat not in SEATS:
        raise DebateError("Seat must be optimist or realist.")
    label = f"{seat} {kind}"
    cleaned = assert_speech(text, label)
    who = (speaker or seat.capitalize()).strip()
    if not who:
        raise DebateError("Speaker cannot be empty.")
    return {"speaker": who, "text": cleaned, "words": word_count(cleaned)}


def maybe_consultant_second_opinion(
    record: dict[str, Any],
    *,
    enabled: bool = False,
) -> dict[str, Any] | None:
    """Optional consultant realist second opinion. Off by default. Stays offline.

    Never sends private content. A local adapter must be configured before
    anything would be considered, and even then the record is scanned first.
    This build does not ship an adapter, so enabling the flag raises unless
    PREFLIGHT_CONSULTANT_ADAPTER is set; no network call is made here.
    """
    if not enabled:
        return None
    blob = json.dumps(record, ensure_ascii=False)
    assert_shareable(blob, "Preflight record for a consultant")
    adapter = os.environ.get("PREFLIGHT_CONSULTANT_ADAPTER", "").strip()
    if not adapter:
        raise DebateError(
            "Consultant second opinion is off by default and stays offline. "
            "No consultant call was made and nothing was sent. To use it, set "
            "PREFLIGHT_CONSULTANT_ADAPTER to a local adapter and never "
            "include private content."
        )
    raise DebateError(
        "Consultant second opinion adapter is not loaded in this offline build. "
        "Nothing was sent."
    )


def new_preflight_record(
    plan: str,
    *,
    title: str | None = None,
    plan_source: str | None = None,
    when: datetime | None = None,
    preflight_id: str | None = None,
) -> dict[str, Any]:
    cleaned_plan = assert_speech(plan, "Plan", limit=PLAN_WORD_LIMIT)
    created = when or now()
    heading = (title or "").strip() or _short_title(cleaned_plan)
    return {
        "id": preflight_id or _next_preflight_id(created),
        "kind": "preflight",
        "version": VERSION,
        "created": created.isoformat(timespec="seconds"),
        "timezone": "America/Chicago",
        "mode": "preflight",
        "status": "open",
        "title": heading,
        "plan": cleaned_plan,
        "plan_words": word_count(cleaned_plan),
        "plan_source": plan_source,
        "participants": ["Optimist", "Realist"],
        "optimist": None,
        "realist": None,
        "rebuttals": {"optimist": None, "realist": None},
        "checklist": [],
        "verdict": None,
        "consultant_second_opinion": None,
        "notes": (
            "A preflight verdict is an opinion, not policy, unless the owner signs off. "
            "The owner's rules outrank anything the seats decide."
        ),
    }


def _format_when(created: str) -> str:
    try:
        when = datetime.fromisoformat(created)
        return when.strftime("%Y-%m-%d %-I:%M %p") + " America/Chicago"
    except ValueError:
        return created or "unknown date"


def _speech_block(heading: str, entry: Any, seat: str) -> list[str]:
    lines = [f"## {heading}"]
    if entry:
        suffix = f" ({entry.get('words')} words)" if entry.get("words") else ""
        lines.append(f"*{entry.get('speaker') or seat}{suffix}*")
        lines.append("")
        lines.append(entry.get("text") or "")
    else:
        lines.append("_not yet written_")
    lines.append("")
    return lines


def apply_preflight_payload(record: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    record["optimist"] = set_seat_speech(
        str(payload.get("optimist") or ""),
        "optimist",
        "case",
        speaker="Optimist",
    )
    record["realist"] = set_seat_speech(
        str(payload.get("realist") or ""),
        "realist",
        "case",
        speaker="Realist",
    )
    rebuttals = payload.get("rebuttals") or {}
    if not isinstance(rebuttals, dict):
        raise DebateError("rebuttals must be an object with optimist and realist text.")
    missing = [seat for seat in SEATS if not rebuttals.get(seat)]
    if missing:
        raise DebateError(
            "Preflight is incomplete. Still need: "
            + ", ".join(f"{seat} rebuttal" for seat in missing)
            + "."
        )
    record["rebuttals"] = {
        "optimist": set_seat_speech(
            str(rebuttals.get("optimist") or ""),
            "optimist",
            "rebuttal",
            speaker="Optimist",
        ),
        "realist": set_seat_speech(
            str(rebuttals.get("realist") or ""),
            "realist",
            "rebuttal",
            speaker="Realist",
        ),
    }
    record["checklist"] = validate_checklist(payload.get("checklist"))
    verdict = validate_preflight_verdict(payload.get("verdict"))
    verdict["sharpened_plan"] = compose_sharpened_plan(record["plan"], verdict)
    record["verdict"] = verdict
    return record


def render_preflight_summary(record: dict[str, Any]) -> str:
    verdict = record.get("verdict") or {}
    landed = verdict.get("landed") or "unfinished"
    reason = (verdict.get("reason") or "").strip()
    top_risk = (verdict.get("top_risk") or "").strip() or "not yet written"
    changes = verdict.get("changes") or []
    questions = verdict.get("questions") or []
    change_text = "; ".join(changes) if changes else "none"
    question_text = "; ".join(questions) if questions else "none"
    lines = [
        f"Verdict: {landed}" + (f" — {reason}" if reason else ""),
        f"Top risk: {top_risk}",
        f"Changes: {change_text}",
        f"Questions for the owner: {question_text}",
    ]
    changer = (verdict.get("would_change_my_mind") or "").strip()
    if changer:
        lines.append(f"What would change my mind: {changer}")
    sharpened = (verdict.get("sharpened_plan") or "").strip()
    if sharpened and len(lines) < PREFLIGHT_SUMMARY_MAX_LINES:
        lines.append(f"Sharpened plan: {sharpened}")
    if not (
        PREFLIGHT_SUMMARY_MIN_LINES
        <= len(lines)
        <= PREFLIGHT_SUMMARY_MAX_LINES
    ):
        raise DebateError(
            "Preflight summary must be "
            f"{PREFLIGHT_SUMMARY_MIN_LINES}-{PREFLIGHT_SUMMARY_MAX_LINES} lines."
        )
    return "\n".join(lines) + "\n"


def _checklist_lines(checklist: list[dict[str, Any]]) -> list[str]:
    lines = ["## Checklist", ""]
    if not checklist:
        lines.append("_not yet filled_")
        lines.append("")
        return lines
    for row in checklist:
        flag = "applies" if row.get("applies") else "does not apply"
        addressed = row.get("addressed") or "—"
        lines.append(f"- {row.get('id')} ({flag}): {addressed}")
    lines.append("")
    return lines


def render_preflight_show(record: dict[str, Any]) -> str:
    lines = [
        f"# Preflight {record.get('id')} — {record.get('title')}",
        "",
        f"- Date: {_format_when(str(record.get('created') or ''))}",
        f"- Status: {record.get('status')}",
        f"- Participants: {', '.join(record.get('participants') or [])}",
        "",
        "## Plan",
        "",
        record.get("plan") or "_not yet written_",
        "",
    ]
    for seat in SEATS:
        lines.extend(_speech_block(f"{seat.capitalize()} case", record.get(seat), seat))
    for seat in SEATS:
        entry = (record.get("rebuttals") or {}).get(seat)
        lines.extend(_speech_block(f"{seat.capitalize()} rebuttal", entry, seat))
    lines.extend(_checklist_lines(list(record.get("checklist") or [])))
    lines.append("## Pasteable summary")
    lines.append("")
    if record.get("verdict"):
        lines.append(render_preflight_summary(record).rstrip())
    else:
        lines.append("_no verdict yet_")
    lines.append("")
    lines.append(
        "This result is an opinion, not policy, unless the owner signs off. "
        "The owner's rules outrank anything the seats decide."
    )
    lines.append("")
    return "\n".join(lines)


def save_preflight(record: dict[str, Any]) -> tuple[Path, Path]:
    if not record.get("id"):
        raise DebateError("Record is missing an id.")
    blob = json.dumps(record, indent=2, ensure_ascii=False)
    assert_shareable(blob, "Preflight record")
    json_path, md_path = _preflight_paths(record["id"])
    _write_json(json_path, record)
    md_path.write_text(render_preflight_summary(record), encoding="utf-8")
    return json_path, md_path


def resolve_preflight_plan(
    payload: dict[str, Any],
    plan_text: str | None,
    plan_source: str | None,
) -> tuple[str, str | None]:
    plan = (plan_text or "").strip() or str(payload.get("plan") or "").strip()
    if not plan:
        raise DebateError("Preflight needs a plan (--plan or a plan field in the payload).")
    source = plan_source
    if source is None and not plan_text and payload.get("plan"):
        source = "payload"
    return plan, source


def run_preflight(
    payload: dict[str, Any],
    *,
    plan_text: str | None = None,
    plan_source: str | None = None,
    consultant: bool = False,
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise DebateError("Preflight payload must be a JSON object.")
    plan, source = resolve_preflight_plan(payload, plan_text, plan_source)
    record = new_preflight_record(
        plan,
        title=str(payload.get("title") or "").strip() or None,
        plan_source=source,
    )
    apply_preflight_payload(record, payload)
    record["consultant_second_opinion"] = maybe_consultant_second_opinion(
        record, enabled=consultant
    )
    record["status"] = "complete"
    save_preflight(record)
    return record


def format_preflight_log(records: list[dict[str, Any]] | None = None) -> str:
    rows = records if records is not None else list_preflight_records()
    if not rows:
        return "No preflight records yet."
    lines = [
        "id  date  verdict  title",
        "--  ----  -------  -----",
    ]
    for row in rows:
        verdict = (row.get("verdict") or {}).get("landed") or "—"
        created = row.get("created") or ""
        date = created[:10] if created else "—"
        lines.append(
            f"{row.get('id')}  {date}  {verdict}  {row.get('title')}"
        )
    return "\n".join(lines)


# ---- formatting / CLI -------------------------------------------------------
def format_log(records: list[dict[str, Any]] | None = None) -> str:
    provided = records is not None
    rows = records if provided else list_records()
    preflights = [] if provided else list_preflight_records()
    if not rows and not preflights:
        return "No debates recorded yet."
    if rows:
        lines = ["id  date  mode  status  topic  landed", "--  ----  ----  ------  -----  ------"]
        for row in rows:
            landed = ", ".join(
                f"{v.get('participant')}: {v.get('landed')}" for v in row.get("verdicts") or []
            ) or "—"
            created = row.get("created") or ""
            date = created[:10] if created else "—"
            lines.append(
                f"{row.get('id')}  {date}  {row.get('mode')}  "
                f"{row.get('status')}  {row.get('topic')}  {landed}"
            )
    else:
        lines = ["No debates recorded yet."]
    if preflights:
        lines.append("")
        lines.append("Preflight plans")
        lines.extend(format_preflight_log(preflights).splitlines())
    return "\n".join(lines)


def format_pick(topic: dict[str, str]) -> str:
    return (
        f"Picked: {topic['id']}\n"
        f"Title: {topic['title']}\n"
        f"Category: {topic['category']}\n"
        "Start it with: debate.py start " + topic["id"]
    )


def _print(text: str) -> int:
    sys.stdout.write(text.rstrip() + "\n")
    return 0


def _fail(exc: Exception) -> int:
    sys.stderr.write(f"error: {exc}\n")
    return 2


def cmd_topics(category: str | None) -> int:
    bank = load_topics()
    if category:
        if category not in CATEGORIES:
            raise DebateError(f"Category must be one of: {', '.join(CATEGORIES)}.")
        bank = [topic for topic in bank if topic["category"] == category]
        if not bank:
            raise DebateError(f"No topics in category {category}.")
    return _print(format_topics(bank))


def cmd_pick(seed: int | None) -> int:
    rng = random.Random(seed) if seed is not None else random.Random()
    return _print(format_pick(pick_topic(rng=rng)))


def cmd_start(topic_id: str, mode: str) -> int:
    record = start_debate(topic_id, mode=mode)
    json_path, md_path = _record_paths(record["id"])
    return _print(
        f"Started {record['id']} ({mode}) on {record['topic']}.\n"
        f"JSON: {json_path}\n"
        f"Transcript: {md_path}"
    )


def cmd_log() -> int:
    return _print(format_log())


def cmd_show(debate_id: str) -> int:
    try:
        return _print(render_transcript(load_debate(debate_id)))
    except DebateError:
        pass
    try:
        return _print(render_preflight_show(load_preflight(debate_id)))
    except DebateError:
        raise DebateError(f"No debate or preflight record named {debate_id}.")


def cmd_fill(debate_id: str, payload_path: Path) -> int:
    record = load_debate(debate_id)
    apply_payload(record, load_payload(payload_path))
    if is_complete(record):
        complete(record)
    save_debate(record)
    status = record["status"]
    return _print(f"Updated {record['id']} ({status}).")


def cmd_preflight(
    plan_path: Path | None,
    payload_path: Path | None,
    checklist_only: bool,
    consultant: bool,
) -> int:
    if checklist_only:
        return _print(format_checklist())
    if payload_path is None:
        raise DebateError(
            "preflight needs --from payload.json (or pass --checklist)."
        )
    plan_text = read_plan_file(plan_path) if plan_path is not None else None
    plan_source = str(plan_path) if plan_path is not None else None
    record = run_preflight(
        load_payload(payload_path),
        plan_text=plan_text,
        plan_source=plan_source,
        consultant=consultant,
    )
    json_path, md_path = _preflight_paths(record["id"])
    landed = (record.get("verdict") or {}).get("landed") or "—"
    return _print(
        f"Preflight {record['id']} is complete ({landed}).\n"
        f"JSON: {json_path}\n"
        f"Summary: {md_path}\n\n"
        + render_preflight_summary(record).rstrip()
    )


def cmd_practice(topic_id: str | None, payload_path: Path) -> int:
    record = run_practice(topic_id, load_payload(payload_path))
    json_path, md_path = _record_paths(record["id"])
    landed = ", ".join(
        f"{v['participant']}: {v['landed']}" for v in record.get("verdicts") or []
    )
    return _print(
        f"Practice debate {record['id']} on {record['topic']} is complete.\n"
        f"Landed: {landed}\n"
        f"JSON: {json_path}\n"
        f"Transcript: {md_path}\n\n"
        + render_transcript(record)
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Debate Loops: topic debates, plus plan preflight."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    topics = sub.add_parser("topics", help="List the topic bank.")
    topics.add_argument("--category", choices=CATEGORIES, help="Filter by category.")

    pick = sub.add_parser("pick", help="Choose a topic not used in the last 6 debates.")
    pick.add_argument("--seed", type=int, help="Optional RNG seed, for tests or a rematch.")

    start = sub.add_parser("start", help="Create an open debate record.")
    start.add_argument("topic_id", help="Topic id from the bank.")
    start.add_argument("--mode", choices=MODES, default="moot")

    fill = sub.add_parser("fill", help="Add openings, rebuttals, steelmans, or a verdict from a JSON file.")
    fill.add_argument("debate_id")
    fill.add_argument("--from", dest="payload", required=True, help="Path to a debate payload JSON file.")

    practice = sub.add_parser(
        "practice",
        help="Run a solo practice debate (one assistant argues both sides) from a JSON file.",
    )
    practice.add_argument("topic_id", nargs="?", help="Topic id; picked for you if omitted.")
    practice.add_argument(
        "--from",
        dest="payload",
        required=True,
        help="JSON file with openings, rebuttals, steelmans, and a verdict.",
    )

    preflight = sub.add_parser(
        "preflight",
        help=(
            "Argue a plan in Optimist vs Realist seats before it reaches the owner, "
            "or print the realist checklist."
        ),
    )
    preflight.add_argument(
        "--plan",
        dest="plan_path",
        help="Path to the plan (markdown or text). Optional if the payload has a plan field.",
    )
    preflight.add_argument(
        "--from",
        dest="payload",
        help="JSON file with optimist and realist cases, rebuttals, checklist, and a verdict.",
    )
    preflight.add_argument(
        "--checklist",
        action="store_true",
        dest="checklist",
        help="Print the realist checklist and exit.",
    )
    preflight.add_argument(
        "--consultant",
        action="store_true",
        dest="consultant",
        help=(
            "Optional consultant realist second opinion. Off by default, stays offline, "
            "and never sends private content."
        ),
    )

    sub.add_parser("log", help="List past debates.")
    show = sub.add_parser("show", help="Print a debate or preflight record.")
    show.add_argument("debate_id")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        if args.command == "topics":
            return cmd_topics(args.category)
        if args.command == "pick":
            return cmd_pick(args.seed)
        if args.command == "start":
            return cmd_start(args.topic_id, args.mode)
        if args.command == "fill":
            return cmd_fill(args.debate_id, Path(args.payload))
        if args.command == "practice":
            return cmd_practice(args.topic_id, Path(args.payload))
        if args.command == "preflight":
            plan_path = Path(args.plan_path) if args.plan_path else None
            payload_path = Path(args.payload) if args.payload else None
            return cmd_preflight(plan_path, payload_path, args.checklist, args.consultant)
        if args.command == "log":
            return cmd_log()
        if args.command == "show":
            return cmd_show(args.debate_id)
    except DebateError as exc:
        return _fail(exc)
    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    sys.exit(main())
