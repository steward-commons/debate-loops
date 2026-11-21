# Debate Loops v0.2

At each family-bot meetup (a "Moot"), one topic is argued from both sides, then the room weighs in. The point is practice at honest pushback and changing your mind on the merits, without anyone pulling rank.

Before a non-trivial plan reaches the owner, preflight mode runs the same tool as an Optimist seat versus a Realist seat and returns a short sharpened plan.

The owner's rules outrank anything a debate decides. A verdict is an opinion, not policy, unless the owner signs off. Changing your mind gets credit, not a penalty.

## Commands

Run from this folder, or pass the script path:

```
python3 debate.py topics
python3 debate.py topics --category craft
python3 debate.py pick
python3 debate.py start <topic-id>
python3 debate.py fill <debate-id> --from payload.json
python3 debate.py practice [topic-id] --from payload.json
python3 debate.py preflight --plan plan.md --from payload.json
python3 debate.py preflight --checklist
python3 debate.py log
python3 debate.py show <debate-id-or-preflight-id>
```

`pick` avoids a topic used in the last 6 debates. `start` still accepts a requested id if you want a rematch. `practice` is the solo form: one assistant argues both sides and records a verdict.

`preflight` is the plan form: Optimist argues the upside, Realist argues risks, costs, usage budget, breakage, missing info, and rule conflicts, then one rebuttal each. The verdict is *go*, *go-with-changes*, *hold*, or *scrap*, plus concrete changes, open questions for the owner, and a "what would change my mind" line. `--plan` can be omitted if the payload already has a `plan` field. The tool stays offline: no network, and no consultant call is required. `--consultant` is an optional realist second opinion, off by default; it never sends private content and will not call a consultant unless a local adapter is configured.

## Format

Kept short on purpose.

Topic debates:

1. Opening for (max 120 words)
2. Opening against (max 120 words)
3. One rebuttal each (max 120 words)
4. Steelman: each side states the other's best point fairly (max 120 words)
5. Verdict: each participant lands *for*, *against*, *split*, or *changed my mind*, with a one-line reason and a "what would change my mind" line

Plan preflight:

1. Optimist case (max 120 words)
2. Realist case (max 120 words)
3. One rebuttal each (max 120 words)
4. Realist checklist: every standing rule that applies must be addressed
5. Verdict: *go*, *go-with-changes*, *hold*, or *scrap*, with a reason, top risk, concrete changes, open questions for the owner, a "what would change my mind" line, and a sharpened plan (max 120 words). The plan itself stays at or under 400 words.

## Realist checklist

Print it with `python3 debate.py preflight --checklist`. Every item must be marked in the payload. If it applies, say how it was addressed:

- Sends, spends, anything public, and private things need the owner's OK
- Nothing private goes to third-party consultants
- Public release rule: no unpublished security-test results, weaknesses, or defense configs
- Respect the household storage cap
- Usage budget
- Prefer a permanent fix over a band-aid
- Failsafes must fail safe
- A messy first pass is fine, but clean it up after

## Files

- `topics.json` — seed bank of family-friendly, spoiler-free, non-political topics (fun, craft, ethics, family).
- `records/` — created on first use: one JSON record and one markdown transcript per topic debate. Not shipped in this repo.
- `records/preflight/` — one JSON record and one short pasteable markdown summary (3-6 lines: verdict, top risk, changes, questions) per preflight.
- `tests/` — unit tests. Run: `python3 -m unittest discover -s tests` from this folder.

Records stay shareable. Never put secrets, passwords, private facts, or vault data in them.

A payload file for `practice` or `fill` looks like:

```json
{
  "openings": {"for": "...", "against": "..."},
  "rebuttals": {"for": "...", "against": "..."},
  "steelmans": {"for": "...", "against": "..."},
  "verdict": {
    "participant": "Assistant",
    "landed": "split",
    "reason": "...",
    "would_change_my_mind": "..."
  }
}
```

A payload file for `preflight` looks like:

```json
{
  "title": "Optional short title",
  "plan": "Optional if you pass --plan",
  "optimist": "Upside and why it works.",
  "realist": "Risks, costs, usage budget, what could break, missing info, rule conflicts.",
  "rebuttals": {"optimist": "...", "realist": "..."},
  "checklist": {
    "owner-ok": {"applies": true, "addressed": "..."},
    "no-private-to-consultants": {"applies": true, "addressed": "..."},
    "public-release": {"applies": false, "addressed": "Not publishing."},
    "drive-room-cap": {"applies": false, "addressed": "No Drive change."},
    "usage-budget": {"applies": true, "addressed": "..."},
    "permanent-fix": {"applies": true, "addressed": "..."},
    "fail-safe": {"applies": true, "addressed": "..."},
    "messy-then-clean": {"applies": true, "addressed": "..."}
  },
  "verdict": {
    "landed": "go-with-changes",
    "reason": "...",
    "top_risk": "...",
    "changes": ["..."],
    "questions": ["..."],
    "would_change_my_mind": "...",
    "sharpened_plan": "..."
  }
}
```

## Environment

- `DEBATE_HOME` — where `records/` lives (default: this folder).
- `DEBATE_TOPICS` — an alternate topics bank.
- `PREFLIGHT_CONSULTANT_ADAPTER` — optional local adapter for a consultant second opinion. Unset means stay offline; nothing is sent.

## License

MIT. See `LICENSE`.

## Who opens (2026-11-21)

Each new debate picks its opening side at random, so `for` doesn't always get the first word.
The record stores it as `"opens": "for" | "against"`, and the transcript shows `- Opens: ...`
and lists the opener first in every section. Older records with no `opens` keep for-first.
`start --opens against` picks the opener yourself; `start --seed N` makes the draw repeatable
(tests or a rematch). In code, pass `rng=random.Random(N)` to `start_debate`, `new_record`, or
`run_practice`; a practice payload may also set `"opens"`.
