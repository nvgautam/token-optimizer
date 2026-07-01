from pathlib import Path

CONTEXT_LIMIT     = 200_000          # Claude's context window
COMPACT_THRESHOLD = 0.70             # Shadow compacts at 70% of context window
CTX_WARN_THRESHOLD = 0.40            # Stop hook warns to handoff at this context %
COMPACT_RETENTION = 0.35             # Compaction keeps ~35% of context

# Sonnet 4.6 pricing per token
INPUT_PRICE       = 3.00  / 1_000_000
CACHE_WRITE_PRICE = 3.75  / 1_000_000
CACHE_READ_PRICE  = 0.30  / 1_000_000
OUTPUT_PRICE      = 15.00 / 1_000_000

CLAUDE_PROJECTS_DIR = Path.home() / ".claude" / "projects"
