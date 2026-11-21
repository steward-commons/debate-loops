#!/usr/bin/env python3
"""Tests for Debate Loops: picking, records, verdicts, and practice."""

from __future__ import annotations

import json
import random
import tempfile
import unittest
from pathlib import Path

from tests.helpers import Isolate, DEBATE, payload, sample_topics, seeded_record, speech

import debate


class DebateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.iso = Isolate(Path(self.tmp.name))
        self.iso.__enter__()

    def tearDown(self) -> None:
        self.iso.__exit__(None, None, None)
        self.tmp.cleanup()

    # --- topic picking -------------------------------------------------------
    def test_pick_avoids_topics_used_in_the_last_six_debates(self):
        topics = sample_topics(8)
        # Rebuild the isolate bank to match this list exactly.
        self.iso.close()
        self.tmp.cleanup()
        self.tmp = tempfile.TemporaryDirectory()
        self.iso = Isolate(Path(self.tmp.name), topics=topics)
        self.iso.__enter__()
        used = [f"topic-{i:02d}" for i in range(1, 7)]
        for i, tid in enumerate(used, start=1):
            seeded_record(tid, f"2026-11-{i:02d}T10:00:00-06:00", f"2026-11-{i:02d}-01")
        recent = debate.recent_topic_ids()
        self.assertEqual(recent, list(reversed(used)))
        picked = {debate.pick_topic(rng=random.Random(n))["id"] for n in range(40)}
        self.assertTrue(picked <= {"topic-07", "topic-08"})
        self.assertFalse(picked & set(used))

    def test_pick_errors_when_every_topic_is_still_in_the_window(self):
        topics = sample_topics(3)
        self.iso.close()
        self.tmp.cleanup()
        self.tmp = tempfile.TemporaryDirectory()
        self.iso = Isolate(Path(self.tmp.name), topics=topics)
        self.iso.__enter__()
        for i, topic in enumerate(topics, start=1):
            seeded_record(topic["id"], f"2026-11-{i:02d}T09:00:00-06:00", f"2026-11-{i:02d}-01")
        with self.assertRaises(debate.DebateError) as ctx:
            debate.pick_topic()
        self.assertIn("No eligible topic", str(ctx.exception))

    def test_a_topic_falls_off_after_six_newer_debates(self):
        topics = sample_topics(7)
        self.iso.close()
        self.tmp.cleanup()
        self.tmp = tempfile.TemporaryDirectory()
        self.iso = Isolate(Path(self.tmp.name), topics=topics)
        self.iso.__enter__()
        # topic-01 is oldest; six newer debates follow, so only topic-01 is eligible.
        order = [f"topic-{i:02d}" for i in range(1, 8)]
        for i, tid in enumerate(order, start=1):
            seeded_record(tid, f"2026-10-{i:02d}T12:00:00-05:00", f"2026-10-{i:02d}-01")
        self.assertNotIn("topic-01", debate.recent_topic_ids())
        self.assertEqual(debate.recent_topic_ids(), [f"topic-{i:02d}" for i in range(7, 1, -1)])
        self.assertEqual(debate.pick_topic(rng=random.Random(0))["id"], "topic-01")

    # --- record save / load --------------------------------------------------
    def test_start_saves_and_load_round_trips(self):
        record = debate.start_debate("topic-03", mode="moot")
        loaded = debate.load_debate(record["id"])
        self.assertEqual(loaded["topic_id"], "topic-03")
        self.assertEqual(loaded["status"], "open")
        self.assertEqual(loaded["mode"], "moot")
        json_path, md_path = debate._record_paths(record["id"])
        self.assertTrue(json_path.is_file())
        self.assertTrue(md_path.is_file())
        self.assertIn("Sample topic 3", md_path.read_text(encoding="utf-8"))
        self.assertIn(record["id"], debate.format_log())

    def test_unknown_topic_is_rejected(self):
        with self.assertRaises(debate.DebateError):
            debate.start_debate("not-a-real-topic")

    def test_secrets_are_refused_in_records(self):
        record = debate.new_record(debate.get_topic("topic-01"))
        with self.assertRaises(debate.DebateError) as ctx:
            debate.set_speech(record, "openings", "for", "Do not store password=hunter2 in a debate.")
        self.assertIn("shareable", str(ctx.exception).lower())

    # --- verdict validation --------------------------------------------------
    def test_verdict_accepts_the_four_landings_and_aliases(self):
        for raw, expected in (
            ("for", "for"),
            ("against", "against"),
            ("split", "split"),
            ("changed my mind", "changed my mind"),
            ("changed_my_mind", "changed my mind"),
        ):
            row = debate.validate_verdict(
                raw,
                "A one-line reason.",
                "A one-line changer.",
                "Assistant",
            )
            self.assertEqual(row["landed"], expected)

    def test_verdict_rejects_bad_landing_and_blank_reason(self):
        with self.assertRaises(debate.DebateError):
            debate.validate_verdict("undecided", "reason", "changer", "Assistant")
        with self.assertRaises(debate.DebateError):
            debate.validate_verdict("for", "   ", "changer", "Assistant")
        with self.assertRaises(debate.DebateError):
            debate.validate_verdict("for", "reason", "", "Assistant")
        with self.assertRaises(debate.DebateError):
            debate.validate_verdict("for", "reason", "changer", "  ")

    def test_speech_over_the_word_limit_is_rejected(self):
        record = debate.new_record(debate.get_topic("topic-02"))
        too_long = " ".join(["word"] * (debate.WORD_LIMIT + 1))
        with self.assertRaises(debate.DebateError) as ctx:
            debate.set_speech(record, "openings", "for", too_long)
        self.assertIn(str(debate.WORD_LIMIT), str(ctx.exception))

    # --- practice mode -------------------------------------------------------
    def test_practice_produces_all_sections_and_a_transcript(self):
        record = debate.run_practice("topic-04", payload())
        self.assertEqual(record["mode"], "practice")
        self.assertEqual(record["status"], "complete")
        self.assertEqual(record["topic_id"], "topic-04")
        self.assertFalse(debate.missing_sections(record))
        for section in debate.SECTIONS:
            for side in debate.SIDES:
                entry = record[section][side]
                self.assertTrue(entry["text"])
                self.assertEqual(entry["speaker"], "Assistant")
                self.assertGreater(entry["words"], 0)
        self.assertEqual(len(record["verdicts"]), 1)
        self.assertEqual(record["verdicts"][0]["landed"], "split")
        text = debate.render_transcript(record)
        for heading in (
            "## Opening — for",
            "## Opening — against",
            "## Rebuttal — for",
            "## Rebuttal — against",
            "## Steelman — for states the best against point",
            "## Steelman — against states the best for point",
            "## Verdict",
            "Landed: split",
            "Changing your mind gets credit, not a penalty.",
        ):
            self.assertIn(heading, text)
        json_path, md_path = debate._record_paths(record["id"])
        self.assertTrue(json_path.is_file())
        self.assertEqual(md_path.read_text(encoding="utf-8"), text)

    def test_practice_refuses_to_save_an_incomplete_payload(self):
        incomplete = payload()
        del incomplete["rebuttals"]
        with self.assertRaises(debate.DebateError) as ctx:
            debate.run_practice("topic-05", incomplete)
        self.assertIn("incomplete", str(ctx.exception).lower())

    # --- who opens (2026-11-21) ---------------------------------------------
    def test_opening_side_is_random_but_seedable(self):
        seen = {debate.choose_opener(random.Random(n)) for n in range(40)}
        self.assertEqual(seen, set(debate.SIDES))
        a = debate.choose_opener(random.Random(7))
        self.assertEqual(a, debate.choose_opener(random.Random(7)))

    def test_record_stores_opener_and_transcript_puts_it_first(self):
        rec = debate.start_debate("topic-03", opens="against")
        self.assertEqual(debate.load_debate(rec["id"])["opens"], "against")
        text = debate.render_transcript(rec)
        self.assertIn("- Opens: against", text)
        self.assertLess(text.index("## Opening — against"), text.index("## Opening — for"))
        self.assertLess(text.index("## Rebuttal — against"), text.index("## Rebuttal — for"))

    def test_seeded_start_matches_choose_opener(self):
        expected = debate.choose_opener(random.Random(3))
        rec = debate.start_debate("topic-02", rng=random.Random(3))
        self.assertEqual(rec["opens"], expected)

    def test_bad_opener_is_rejected(self):
        with self.assertRaises(debate.DebateError):
            debate.start_debate("topic-02", opens="sideways")

    def test_old_record_without_opener_stays_for_first(self):
        self.assertEqual(debate.side_order({}), ("for", "against"))
        self.assertEqual(debate.side_order({"opens": "nonsense"}), ("for", "against"))

    def test_practice_payload_can_name_opener(self):
        data = payload(); data["opens"] = "against"
        rec = debate.run_practice("topic-04", data)
        self.assertEqual(rec["opens"], "against")

    def test_cli_start_seed_and_opens(self):
        self.assertEqual(debate.main(["start", "topic-02", "--opens", "against"]), 0)
        self.assertEqual(debate.main(["start", "topic-03", "--seed", "5"]), 0)
        opens = sorted(r.get("opens") for r in debate.list_records())
        self.assertEqual(len(opens), 2)
        self.assertIn("against", opens)
        self.assertTrue(set(opens) <= set(debate.SIDES))

    # --- CLI -----------------------------------------------------------------
    def test_cli_topics_pick_start_log_and_practice(self):
        self.assertEqual(debate.main(["topics"]), 0)
        self.assertEqual(debate.main(["pick", "--seed", "1"]), 0)
        self.assertEqual(debate.main(["start", "topic-02"]), 0)
        started = debate.list_records()
        self.assertEqual(len(started), 1)
        self.assertEqual(debate.main(["log"]), 0)

        path = Path(self.tmp.name) / "payload.json"
        path.write_text(json.dumps(payload()), encoding="utf-8")
        self.assertEqual(debate.main(["practice", "topic-08", "--from", str(path)]), 0)
        records = debate.list_records()
        self.assertEqual(len(records), 2)
        practice = [row for row in records if row["mode"] == "practice"][0]
        self.assertEqual(practice["status"], "complete")
        self.assertFalse(debate.missing_sections(practice))
        self.assertEqual(debate.main(["show", practice["id"]]), 0)

    def test_real_topic_bank_is_valid_and_has_the_practice_topic(self):
        # Point only the records home at the temp dir; use the shipped bank.
        import os

        os.environ["DEBATE_TOPICS"] = str(DEBATE / "topics.json")
        bank = debate.load_topics()
        self.assertGreaterEqual(len(bank), 20)
        ids = {topic["id"] for topic in bank}
        self.assertIn("initiative-beats-orders", ids)
        for topic in bank:
            self.assertIn(topic["category"], debate.CATEGORIES)


if __name__ == "__main__":
    unittest.main()
