#!/usr/bin/env python3
"""Tests for plan preflight: optimist vs realist, checklist, records."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.helpers import Isolate, speech

import debate


def case(seat: str) -> str:
    return speech(seat, "case")


def preflight_payload(**overrides) -> dict:
    checklist = {
        item_id: {
            "applies": item_id in {"usage-budget", "permanent-fix"},
            "addressed": (
                "This test plan stays inside the usage budget."
                if item_id == "usage-budget"
                else "This is a lasting research step, not a band-aid."
                if item_id == "permanent-fix"
                else "Does not apply to this test plan."
            ),
        }
        for item_id in debate.checklist_ids()
    }
    data = {
        "title": "Test plan",
        "plan": "Research a small, reversible next step and report back before doing more.",
        "optimist": case("optimist"),
        "realist": case("realist"),
        "rebuttals": {
            "optimist": speech("optimist", "rebuttal"),
            "realist": speech("realist", "rebuttal"),
        },
        "checklist": checklist,
        "verdict": {
            "landed": "go-with-changes",
            "reason": "Do the research, but keep it bounded.",
            "top_risk": "The work quietly grows past research into action.",
            "changes": ["Keep this pass as research only; do not spend or publish."],
            "questions": ["Any constraint I should bake in before starting?"],
            "would_change_my_mind": "A hard no from the owner, or a rule conflict I missed.",
            "sharpened_plan": (
                "Research the next step only, then bring a short report. "
                "No spending, sending, or publishing without approval."
            ),
        },
    }
    data.update(overrides)
    return data


class PreflightTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.iso = Isolate(Path(self.tmp.name))
        self.iso.__enter__()

    def tearDown(self) -> None:
        self.iso.__exit__(None, None, None)
        self.tmp.cleanup()

    def test_checklist_covers_standing_rules(self):
        text = debate.format_checklist()
        self.assertIn("Realist checklist", text)
        for item_id in (
            "owner-ok",
            "no-private-to-consultants",
            "public-release",
            "drive-room-cap",
            "usage-budget",
            "permanent-fix",
            "fail-safe",
            "messy-then-clean",
        ):
            self.assertIn(item_id, text)
        for phrase in (
            "the owner's OK",
            "third-party consultants",
            "unpublished security-test results",
            "weaknesses",
            "defense configs",
            "storage cap",
            "Usage budget",
            "permanent fix over a band-aid",
            "fail safe",
            "messy first pass",
            "clean it up after",
        ):
            self.assertIn(phrase, text)

    def test_cli_checklist_prints_and_writes_nothing(self):
        self.assertEqual(debate.main(["preflight", "--checklist"]), 0)
        self.assertEqual(debate.list_preflight_records(), [])

    def test_preflight_writes_json_and_short_markdown_summary(self):
        record = debate.run_preflight(preflight_payload())
        self.assertEqual(record["mode"], "preflight")
        self.assertEqual(record["status"], "complete")
        self.assertTrue(record["id"].startswith("pf-"))
        self.assertEqual(record["verdict"]["landed"], "go-with-changes")
        self.assertIsNone(record["consultant_second_opinion"])
        self.assertEqual(record["optimist"]["speaker"], "Optimist")
        self.assertEqual(record["realist"]["speaker"], "Realist")
        self.assertEqual(len(record["checklist"]), 8)
        json_path, md_path = debate._preflight_paths(record["id"])
        self.assertTrue(json_path.is_file())
        self.assertTrue(md_path.is_file())
        summary = md_path.read_text(encoding="utf-8")
        self.assertEqual(summary, debate.render_preflight_summary(record))
        lines = [line for line in summary.strip().splitlines() if line.strip()]
        self.assertGreaterEqual(len(lines), 3)
        self.assertLessEqual(len(lines), 6)
        self.assertTrue(lines[0].startswith("Verdict: go-with-changes"))
        self.assertTrue(any(line.startswith("Top risk:") for line in lines))
        self.assertTrue(any(line.startswith("Changes:") for line in lines))
        self.assertTrue(any(line.startswith("Questions for the owner:") for line in lines))
        # Preflight records stay out of the Moot debate list root.
        self.assertNotIn(record["id"], [row["id"] for row in debate.list_records()])
        self.assertIn(record["id"], debate.format_log())

    def test_plan_file_overrides_payload_plan(self):
        payload = preflight_payload()
        plan_path = Path(self.tmp.name) / "plan.md"
        plan_path.write_text("Use the plan file text as the plan under review.", encoding="utf-8")
        record = debate.run_preflight(
            payload,
            plan_text=debate.read_plan_file(plan_path),
            plan_source=str(plan_path),
        )
        self.assertEqual(record["plan"], "Use the plan file text as the plan under review.")
        self.assertEqual(record["plan_source"], str(plan_path))

    def test_word_limits_are_enforced(self):
        too_long = " ".join(["word"] * (debate.WORD_LIMIT + 1))
        payload = preflight_payload(optimist=too_long)
        with self.assertRaises(debate.DebateError) as ctx:
            debate.run_preflight(payload)
        self.assertIn(str(debate.WORD_LIMIT), str(ctx.exception))

        payload = preflight_payload()
        payload["verdict"]["reason"] = " ".join(["word"] * (debate.LINE_WORD_LIMIT + 1))
        with self.assertRaises(debate.DebateError):
            debate.run_preflight(payload)

        payload = preflight_payload(plan=" ".join(["word"] * (debate.PLAN_WORD_LIMIT + 1)))
        with self.assertRaises(debate.DebateError) as ctx:
            debate.run_preflight(payload)
        self.assertIn(str(debate.PLAN_WORD_LIMIT), str(ctx.exception))

    def test_verdict_landings_and_aliases(self):
        for raw, expected in (
            ("go", "go"),
            ("go with changes", "go-with-changes"),
            ("go_with_changes", "go-with-changes"),
            ("hold", "hold"),
            ("scrap", "scrap"),
        ):
            payload = preflight_payload()
            payload["verdict"]["landed"] = raw
            if expected != "go-with-changes":
                payload["verdict"]["changes"] = []
            record = debate.run_preflight(payload)
            self.assertEqual(record["verdict"]["landed"], expected)

        payload = preflight_payload()
        payload["verdict"]["landed"] = "maybe"
        with self.assertRaises(debate.DebateError):
            debate.run_preflight(payload)


    def test_verdict_accepts_questions_for_owner_fallback(self):
        payload = preflight_payload()
        questions = payload["verdict"].pop("questions")
        payload["verdict"]["questions_for_owner"] = questions
        record = debate.run_preflight(payload)
        self.assertEqual(record["verdict"]["questions"], questions)

    def test_go_with_changes_requires_a_change(self):
        payload = preflight_payload()
        payload["verdict"]["changes"] = []
        with self.assertRaises(debate.DebateError) as ctx:
            debate.run_preflight(payload)
        self.assertIn("change", str(ctx.exception).lower())

    def test_applicable_checklist_items_must_be_addressed(self):
        payload = preflight_payload()
        payload["checklist"]["owner-ok"] = {"applies": True, "addressed": ""}
        with self.assertRaises(debate.DebateError) as ctx:
            debate.run_preflight(payload)
        self.assertIn("owner-ok", str(ctx.exception))

        payload = preflight_payload()
        del payload["checklist"]["fail-safe"]
        with self.assertRaises(debate.DebateError) as ctx:
            debate.run_preflight(payload)
        self.assertIn("fail-safe", str(ctx.exception))

        payload = preflight_payload()
        payload["checklist"]["not-a-rule"] = {"applies": False, "addressed": "n/a"}
        with self.assertRaises(debate.DebateError) as ctx:
            debate.run_preflight(payload)
        self.assertIn("Unknown checklist", str(ctx.exception))

    def test_incomplete_payload_and_secrets_are_refused(self):
        payload = preflight_payload()
        del payload["rebuttals"]
        with self.assertRaises(debate.DebateError) as ctx:
            debate.run_preflight(payload)
        self.assertIn("incomplete", str(ctx.exception).lower())

        payload = preflight_payload(realist="Do not store password=hunter2 in a preflight.")
        with self.assertRaises(debate.DebateError) as ctx:
            debate.run_preflight(payload)
        self.assertIn("shareable", str(ctx.exception).lower())

        with self.assertRaises(debate.DebateError):
            debate.run_preflight({"optimist": case("optimist")})

    def test_consultant_is_off_by_default_and_sends_nothing(self):
        record = debate.run_preflight(preflight_payload())
        self.assertIsNone(record["consultant_second_opinion"])

        with mock.patch("debate.os.environ.get", wraps=debate.os.environ.get) as env_get:
            with self.assertRaises(debate.DebateError) as ctx:
                debate.run_preflight(preflight_payload(), consultant=True)
            message = str(ctx.exception).lower()
            self.assertIn("nothing was sent", message)
            self.assertIn("offline", message)
            # The hook may read the adapter env var, but it must not start a client.
            called = [args[0] for args, _ in env_get.call_args_list]
            self.assertTrue(
                all("GEMINI" not in str(name).upper() and "GOOGLE" not in str(name).upper()
                    for name in called)
            )

        secret_payload = preflight_payload()
        secret_payload["optimist"] = "Here is api_key=abcd1234 hidden in the upside."
        with self.assertRaises(debate.DebateError) as ctx:
            debate.maybe_consultant_second_opinion(
                {"optimist": secret_payload["optimist"]},
                enabled=True,
            )
        self.assertIn("shareable", str(ctx.exception).lower())

    def test_cli_preflight_from_plan_and_payload(self):
        root = Path(self.tmp.name)
        plan_path = root / "plan.md"
        payload_path = root / "payload.json"
        plan_path.write_text(
            "Research a bounded next step and stop before acting on it.",
            encoding="utf-8",
        )
        payload_path.write_text(json.dumps(preflight_payload()), encoding="utf-8")
        self.assertEqual(
            debate.main(
                [
                    "preflight",
                    "--plan",
                    str(plan_path),
                    "--from",
                    str(payload_path),
                ]
            ),
            0,
        )
        records = debate.list_preflight_records()
        self.assertEqual(len(records), 1)
        self.assertEqual(
            records[0]["plan"],
            "Research a bounded next step and stop before acting on it.",
        )
        self.assertEqual(debate.main(["show", records[0]["id"]]), 0)
        self.assertEqual(debate.main(["log"]), 0)
        self.assertEqual(debate.main(["preflight"]), 2)


if __name__ == "__main__":
    unittest.main()
