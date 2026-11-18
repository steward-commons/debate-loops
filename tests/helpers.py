"""Isolate debate records so tests never touch the live Moot folder."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

DEBATE = Path(__file__).resolve().parents[1]
if str(DEBATE) not in sys.path:
    sys.path.insert(0, str(DEBATE))

import debate  # noqa: E402


def sample_topics(count: int = 8) -> list[dict[str, str]]:
    categories = ("fun", "craft", "ethics", "family")
    return [
        {
            "id": f"topic-{i:02d}",
            "title": f"Sample topic {i}",
            "category": categories[i % 4],
        }
        for i in range(1, count + 1)
    ]


def write_topics(path: Path, topics: list[dict[str, str]]) -> Path:
    path.write_text(
        json.dumps({"version": "v0.1", "topics": topics}, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def speech(side: str, kind: str = "opening") -> str:
    return f"This is a {side} {kind} written for a unit test, long enough to count as a real argument and short enough to stay under the word cap."


def payload() -> dict:
    return {
        "openings": {"for": speech("for", "opening"), "against": speech("against", "opening")},
        "rebuttals": {"for": speech("for", "rebuttal"), "against": speech("against", "rebuttal")},
        "steelmans": {"for": speech("for", "steelman"), "against": speech("against", "steelman")},
        "verdict": {
            "participant": "Assistant",
            "landed": "split",
            "reason": "Both sides earned a point.",
            "would_change_my_mind": "A clearer hard rule from the owner one way or the other.",
        },
    }


class Isolate:
    """Point debate home and the topic bank at a temp folder."""

    def __init__(self, tmp: Path, topics: list[dict[str, str]] | None = None) -> None:
        self.home = tmp / "debate"
        self.home.mkdir()
        (self.home / "records").mkdir()
        write_topics(self.home / "topics.json", topics if topics is not None else sample_topics())
        self._old_home = os.environ.get("DEBATE_HOME")
        self._old_topics = os.environ.get("DEBATE_TOPICS")
        os.environ["DEBATE_HOME"] = str(self.home)
        os.environ.pop("DEBATE_TOPICS", None)

    def close(self) -> None:
        if self._old_home is None:
            os.environ.pop("DEBATE_HOME", None)
        else:
            os.environ["DEBATE_HOME"] = self._old_home
        if self._old_topics is None:
            os.environ.pop("DEBATE_TOPICS", None)
        else:
            os.environ["DEBATE_TOPICS"] = self._old_topics

    def __enter__(self) -> "Isolate":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def seeded_record(topic_id: str, created: str, debate_id: str | None = None) -> dict:
    topic = debate.get_topic(topic_id)
    record = debate.new_record(
        topic,
        mode="practice",
        debate_id=debate_id or created[:10] + "-01",
    )
    record["created"] = created
    debate.save_debate(record)
    return record
