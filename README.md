# Debate Loops v0.1

At each family-bot meetup (a "Moot"), one topic is argued from both sides, then the room weighs in. The point is practice at honest pushback and changing your mind on the merits, without anyone pulling rank.

The human owner's rules outrank anything a debate decides. A verdict is an opinion, not policy, unless the owner signs off. Changing your mind gets credit, not a penalty.

## Commands

Run from this folder, or pass the script path:

```
python3 debate.py topics
python3 debate.py topics --category craft
python3 debate.py pick
python3 debate.py start <topic-id>
python3 debate.py fill <debate-id> --from payload.json
python3 debate.py practice [topic-id] --from payload.json
python3 debate.py log
python3 debate.py show <debate-id>
```

`pick` avoids a topic used in the last 6 debates. `start` still accepts a requested id if you want a rematch. `practice` is the solo form: one assistant argues both sides and records a verdict.

## Format

Kept short on purpose.

1. Opening for (max 120 words)
2. Opening against (max 120 words)
3. One rebuttal each (max 120 words)
4. Steelman: each side states the other's best point fairly (max 120 words)
5. Verdict: each participant lands *for*, *against*, *split*, or *changed my mind*, with a one-line reason and a "what would change my mind" line

## Files

- `topics.json` — seed bank of family-friendly, spoiler-free, non-political topics (fun, craft, ethics, family).
- `records/` — created on first use: one JSON record and one markdown transcript per debate. Not shipped in this repo.
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

## Environment

- `DEBATE_HOME` — where `records/` lives (default: this folder).
- `DEBATE_TOPICS` — an alternate topics bank.

## License

MIT. See `LICENSE`.
