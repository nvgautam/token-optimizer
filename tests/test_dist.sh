#!/usr/bin/env bash
# Smoke tests for T-302 customer distribution
# Usage: bash tests/test_dist.sh
# All filesystem writes use TMPDIR — no writes to ~/.claude or real paths

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PASS=0
FAIL=0

pass() { echo "PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "FAIL: $1"; FAIL=$((FAIL+1)); }

# ---------------------------------------------------------------------------
# T1: build_dist.sh fails fast when AGENTFLOW_MASTER_KEY is unset
# ---------------------------------------------------------------------------
test_build_fails_without_key() {
  local out
  out=$(AGENTFLOW_MASTER_KEY="" AGENTFLOW_KEY="" \
        bash "$PROJECT_ROOT/scripts/build_dist.sh" 2>&1) && {
    fail "T1: build_dist.sh should exit non-zero without key"
    return
  }
  if echo "$out" | grep -qi "error"; then
    pass "T1: build_dist.sh fails with error message when no key"
  else
    fail "T1: build_dist.sh exited non-zero but no 'Error' in output: $out"
  fi
}

# ---------------------------------------------------------------------------
# T2: scripts/stubs/ has stub .md for every expected skill
# ---------------------------------------------------------------------------
test_stubs_exist() {
  local stubs_dir="$PROJECT_ROOT/scripts/stubs"
  for name in oracle orchestrate handoff debug drift; do
    if [ -f "$stubs_dir/$name.md" ]; then
      pass "T2: stub $name.md exists"
    else
      fail "T2: stub $name.md missing from $stubs_dir"
    fi
  done
}

# ---------------------------------------------------------------------------
# T3: each stub contains the load-skill invocation and nothing else
# ---------------------------------------------------------------------------
test_stub_content() {
  local stubs_dir="$PROJECT_ROOT/scripts/stubs"
  for name in oracle orchestrate handoff debug drift; do
    local f="$stubs_dir/$name.md"
    [ -f "$f" ] || { fail "T3: $name.md missing"; continue; }

    if grep -q "agentflow ip load-skill $name" "$f"; then
      pass "T3: $name.md contains correct invocation"
    else
      fail "T3: $name.md missing 'agentflow ip load-skill $name'"
    fi

    # Stub must be short — no skill logic
    local lines
    lines=$(wc -l < "$f" | tr -d '[:space:]')
    if [ "$lines" -le 5 ]; then
      pass "T3: $name.md is minimal ($lines lines)"
    else
      fail "T3: $name.md too long ($lines lines) — likely contains skill logic"
    fi
  done
}

# ---------------------------------------------------------------------------
# T4: make dist produces archive with zero .py/.pyc files
# ---------------------------------------------------------------------------
test_dist_archive_no_py() {
  local tmpdir
  tmpdir=$(mktemp -d)

  # Fake binary so we can test without Nuitka
  mkdir -p "$tmpdir/dist"
  printf '#!/usr/bin/env sh\necho "agentflow 2.0.0"\n' > "$tmpdir/dist/agentflow"
  chmod +x "$tmpdir/dist/agentflow"

  # Plant a .py file to verify stripping is applied
  echo "should be removed" > "$tmpdir/dist/leftover.py"

  local out
  out=$(AGENTFLOW_MASTER_KEY="smoke-test-key-do-not-use" \
        AGENTFLOW_DIST_DIR="$tmpdir/dist" \
        AGENTFLOW_SKIP_COMPILE="1" \
        bash "$PROJECT_ROOT/scripts/build_dist.sh" 2>&1) || {
    fail "T4: build_dist.sh exited non-zero: $out"
    rm -rf "$tmpdir"
    return
  }

  local archive
  archive=$(find "$tmpdir" -name "agentflow-v*.tar.gz" 2>/dev/null | head -1)
  if [ -z "$archive" ]; then
    fail "T4: no archive produced (output: $out)"
    rm -rf "$tmpdir"
    return
  fi
  pass "T4: archive produced: $(basename "$archive")"

  local py_count
  py_count=$(tar -tzf "$archive" | { grep -E '\.(py|pyc)$' || true; } | wc -l | tr -d '[:space:]')
  if [ "$py_count" -eq 0 ]; then
    pass "T4: archive contains zero .py/.pyc files"
  else
    fail "T4: archive contains $py_count .py/.pyc file(s):"
    tar -tzf "$archive" | grep -E '\.(py|pyc)$' || true
  fi

  # Verify install.sh is in the archive
  if tar -tzf "$archive" | grep -q "install.sh"; then
    pass "T4: install.sh present in archive"
  else
    fail "T4: install.sh missing from archive"
  fi

  # Verify stubs are in the archive
  local stub_count
  stub_count=$(tar -tzf "$archive" | { grep "stubs/.*\.md" || true; } | wc -l | tr -d '[:space:]')
  if [ "$stub_count" -ge 5 ]; then
    pass "T4: $stub_count stub(s) in archive"
  else
    fail "T4: only $stub_count stub(s) in archive (expected >=5)"
  fi

  rm -rf "$tmpdir"
}

# ---------------------------------------------------------------------------
# T5: install.sh is idempotent — running twice produces no duplicates
# ---------------------------------------------------------------------------
test_install_idempotent() {
  local tmpdir
  tmpdir=$(mktemp -d)

  # Build a minimal archive layout (as if extracted from .tar.gz)
  local archive_dir="$tmpdir/agentflow-v2.0.0"
  mkdir -p "$archive_dir/dist" "$archive_dir/stubs" "$archive_dir/skills"

  # Fake binary
  printf '#!/usr/bin/env sh\necho "agentflow 2.0.0"\n' > "$archive_dir/dist/agentflow"
  chmod +x "$archive_dir/dist/agentflow"

  # Fake bundle
  echo "fake-encrypted-bundle" > "$archive_dir/skills/bundle-v1.enc"

  # Stubs from scripts/stubs/
  cp "$PROJECT_ROOT/scripts/stubs/"*.md "$archive_dir/stubs/"

  # Copy install.sh into archive
  cp "$PROJECT_ROOT/scripts/install.sh" "$archive_dir/install.sh"
  chmod +x "$archive_dir/install.sh"

  local bin_dir="$tmpdir/bin"
  local commands_dir="$tmpdir/commands"
  local bundle_dir="$tmpdir/.agentflow/skills"
  mkdir -p "$bin_dir" "$commands_dir" "$bundle_dir"

  # Run install twice
  local rc=0
  for i in 1 2; do
    AGENTFLOW_INSTALL_DIR="$bin_dir" \
    CLAUDE_COMMANDS_DIR="$commands_dir" \
    AGENTFLOW_SKIP_HOOKS="1" \
    AGENTFLOW_BUNDLE_DEST="$bundle_dir/bundle-v1.enc" \
    AGENTFLOW_ARCHIVE_DIR="$archive_dir" \
      bash "$archive_dir/install.sh" > /dev/null 2>&1 || rc=$?
  done

  if [ $rc -ne 0 ]; then
    fail "T5: install.sh exited non-zero on second run"
  else
    pass "T5: install.sh succeeded on both runs"
  fi

  # Binary installed
  if [ -x "$bin_dir/agentflow" ]; then
    pass "T5: binary installed at $bin_dir/agentflow"
  else
    fail "T5: binary not installed"
  fi

  # All stubs installed
  local stub_ok=0
  for name in oracle orchestrate handoff debug drift; do
    if [ -f "$commands_dir/$name.md" ]; then
      stub_ok=$((stub_ok+1))
    fi
  done
  if [ "$stub_ok" -eq 5 ]; then
    pass "T5: all 5 stubs installed"
  else
    fail "T5: only $stub_ok/5 stubs installed"
  fi

  # Bundle copied
  if [ -f "$bundle_dir/bundle-v1.enc" ]; then
    pass "T5: bundle installed"
  else
    fail "T5: bundle not installed"
  fi

  # No duplicate stubs — each file should appear exactly once
  local dup_count
  dup_count=$(find "$commands_dir" -name "*.md" | sort | uniq -d | wc -l | tr -d '[:space:]')
  if [ "$dup_count" -eq 0 ]; then
    pass "T5: no duplicate stubs"
  else
    fail "T5: $dup_count duplicate stub(s) found"
  fi

  rm -rf "$tmpdir"
}

# ---------------------------------------------------------------------------
# Run all tests
# ---------------------------------------------------------------------------
test_build_fails_without_key
test_stubs_exist
test_stub_content
test_dist_archive_no_py
test_install_idempotent

echo ""
echo "Results: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
