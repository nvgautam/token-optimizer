# Verbosity rules

- Target ≤3 sentences (~150 tokens) per orchestrator status message.
- Status: one line only
- Round reports: table only — no prose between spawns
- Don't narrate grouping logic, overlap scores, or round-sizing
- Never narrate internal mechanics — comply silently with hooks, idx reads, flock, sys.path bootstrap, cache paths, skill file names. These are implementation details; the user doesn't need narration about them.
- Never narrate strategy: round-sizing rationale, calibration values, EWMA/cv, task-cost estimates, disjoint owns analysis.
