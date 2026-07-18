# tests/prompts/test_oracle_skill.py
"""Tests for commands/oracle.md and commands/gemini/skills/oracle/SKILL.md — the oracle skills."""
import re
from pathlib import Path

ORACLE_FILES = [
    Path("commands/claude/oracle.md"),
    Path("commands/gemini/skills/oracle/SKILL.md"),
]


# Test 1: architecture.md UNRESOLVED check on startup
def test_oracle_skill_checks_architecture_unresolved_on_startup():
    for f in ORACLE_FILES:
        content = f.read_text(encoding="utf-8")
        # Must mention reading architecture.md and checking for UNRESOLVED items
        assert "architecture.md" in content, f"{f.name} must reference architecture.md"
        assert "UNRESOLVED" in content, f"{f.name} must check for UNRESOLVED items"
        # The check must appear in the startup section, not only in later phases
        startup_section = content.split("## Phase")[0]
        assert "architecture.md" in startup_section, \
            f"architecture.md check must appear before Phase 1 in {f.name}"
        assert "UNRESOLVED" in startup_section, \
            f"UNRESOLVED keyword must appear in startup section in {f.name}"


# Test 2: multi-persona declaration (PE + PM + Designer)
def test_oracle_skill_declares_three_personas():
    for f in ORACLE_FILES:
        content = f.read_text(encoding="utf-8")
        # All three personas must appear
        for persona in ["Principal Engineer", "Principal PM", "Principal Designer"]:
            assert persona in content or persona.replace("Principal ", "PE").replace("Principal ", "PM") in content, \
                f"{f.name} must declare persona: {persona}"
        # Specifically check that all three are present (PE, PM, Designer)
        assert re.search(r"Engineer", content), f"PE persona missing in {f.name}"
        assert re.search(r"PM|Product Manager", content), f"PM persona missing in {f.name}"
        assert re.search(r"Designer", content), f"Designer persona missing in {f.name}"
        # Must be declared together (same line or block)
        lines = content.splitlines()
        persona_lines = [line for line in lines if "Engineer" in line and ("PM" in line or "Product" in line) and "Designer" in line]
        assert persona_lines, \
            f"{f.name} must declare all three personas (Engineer, PM, Designer) on the same line or block"


# Test 3: no hardcoded project-specific content
def test_oracle_skill_contains_no_specific_project_names():
    for f in ORACLE_FILES:
        content = f.read_text(encoding="utf-8")
        # Should not reference specific project names from the AgentFlow project
        forbidden = ["AgentFlow", "token-optimizer", "PTY shell", "tiktoken", "agentflow/shell"]
        for term in forbidden:
            assert term not in content, \
                f"{f.name} must be generic — found project-specific term: '{term}'"


# Test 4: ~2% budget announcement
def test_oracle_skill_contains_budget_announcement():
    for f in ORACLE_FILES:
        content = f.read_text(encoding="utf-8")
        # Must announce ~2% of 5-hour window usage
        assert "2%" in content, f"{f.name} must announce ~2% of window usage"
        assert "5-hour" in content or "5 hour" in content, \
            f"{f.name} must reference the 5-hour window"
        # The announcement must come early (startup section)
        idx_2pct = content.find("2%")
        idx_first_phase = content.find("## Phase")
        assert idx_2pct < idx_first_phase, \
            f"Budget announcement must appear before Phase 1 in {f.name}"


# Test 5: ≤3-sentence verbosity rule near the opening
def test_oracle_skill_contains_three_sentence_verbosity_rule():
    for f in ORACLE_FILES:
        content = f.read_text(encoding="utf-8")
        # Must specify ≤3 sentences per exchange
        assert re.search(r"≤\s*3\s*sentence|3\s*sentence|three\s*sentence", content, re.IGNORECASE), \
            f"{f.name} must specify ≤3 sentences per exchange verbosity rule"
        # Must appear near the opening (before Phase 1)
        idx_first_phase = content.find("## Phase 1")
        idx_verbosity = content.find("Verbosity")
        assert idx_verbosity != -1 and idx_verbosity < idx_first_phase, \
            f"Verbosity rule must appear near the opening of the file, before Phase 1 in {f.name}"


# Test 6: lazy sub-file loading (per phase, not at startup)
def test_oracle_skill_uses_lazy_subfile_loading():
    for f in ORACLE_FILES:
        content = f.read_text(encoding="utf-8")
        # market.md, checklist.md, and generation.md must NOT all be loaded at startup
        startup_section = content.split("## Phase")[0]
        for sub_file in ["market.md", "checklist.md", "generation.md"]:
            assert sub_file not in startup_section, \
                f"{sub_file} must NOT be loaded at startup in {f.name} — lazy load only in its phase"

        # Each sub-file must appear in its respective phase section
        assert "market.md" in content, f"market.md must be referenced in {f.name}"
        assert "checklist.md" in content, f"checklist.md must be referenced in {f.name}"
        assert "generation.md" in content, f"generation.md must be referenced in {f.name}"

        # Lazy load instruction must indicate per-phase loading
        assert re.search(r"[Ll]azy\s+load|only when entering|not at startup", content), \
            f"{f.name} must contain lazy loading instruction"


# Test 7: oracle reads rate_calibration_<provider>.json after oracle-complete check
def test_oracle_reads_rate_calibration_after_oracle_complete_check():
    for f in ORACLE_FILES:
        content = f.read_text(encoding="utf-8")
        cal_file = "rate_calibration_claude.json" if "claude" in str(f) else "rate_calibration_gemini.json"
        assert cal_file in content, f"{f.name} must reference {cal_file}"
        # Must appear in startup section (before Phase 1)
        startup_section = content.split("## Phase")[0]
        assert cal_file in startup_section, \
            f"{cal_file} must be read in the startup section (before Phase 1) in {f.name}"
        # Must appear after Step 2 (oracle-complete check)
        step2_idx = content.find("### Step 2")
        cal_idx = content.find(cal_file)
        assert cal_idx > step2_idx, \
            f"{cal_file} read must appear after Step 2 (oracle-complete check) in {f.name}"


# Test 8: skips CV adjustment when sample_count < 7
def test_oracle_skips_cv_adjustment_when_sample_count_below_threshold():
    for f in ORACLE_FILES:
        content = f.read_text(encoding="utf-8")
        # Must mention sample_count threshold of 7
        assert re.search(r"sample_count\s*[<>=!]+\s*7|sample_count.*7", content), \
            f"{f.name} must reference sample_count threshold of 7 for CV adjustment"
        # Must explicitly skip or not apply when sample_count < 7
        assert re.search(r"sample_count\s*<\s*7|sample_count.*fewer than 7|below\s*7", content), \
            f"{f.name} must skip CV adjustment when sample_count < 7"


# Test 9: CV notification is NOT present (IP protection — internal logic must be silent)
def test_oracle_informs_user_of_cv_driven_adjustment():
    for f in ORACLE_FILES:
        content = f.read_text(encoding="utf-8")
        # Must NOT contain the user-facing CV notification line
        assert not re.search(r"CV=.*high.*sizing tasks more conservatively", content), \
            f"{f.name} must NOT show CV notification to user (IP protection)"
        # Must still reference cv_threshold or 0.3 (logic present but silent)
        assert re.search(r"cv_threshold|0\.3", content), \
            f"{f.name} must reference cv_threshold (default 0.3)"


# Test 10: caps estimated_lines more tightly when high CV detected
def test_oracle_caps_estimated_lines_when_high_cv():
    for f in ORACLE_FILES:
        content = f.read_text(encoding="utf-8")
        # Must mention estimated_lines capping or reduction in Phase 3
        phase3_match = re.search(r"## Phase 3.*", content, re.DOTALL)
        assert phase3_match, f"{f.name} must have Phase 3 section"
        phase3_content = phase3_match.group(0)
        # Must reference tighter sizing (20% reduction or 180-line split threshold)
        assert re.search(r"180|20%|tightly|conservativ", phase3_content, re.IGNORECASE), \
            f"Phase 3 of {f.name} must reference 180-line split threshold or 20% reduction for high CV"
        # ewma_cv must be referenced in Phase 3
        assert "ewma_cv" in phase3_content, \
            f"Phase 3 of {f.name} must reference ewma_cv for CV-driven task sizing"


# Test 11: CV adjustment logic present in Phase 3 without user notification
def test_oracle_cv_adjustment_logic_present_without_notification():
    for f in ORACLE_FILES:
        content = f.read_text(encoding="utf-8")
        phase3_match = re.search(r"## Phase 3.*", content, re.DOTALL)
        assert phase3_match, f"{f.name} must have Phase 3 section"
        phase3_content = phase3_match.group(0)
        # ewma_cv threshold check (>= 0.3) must be present
        assert re.search(r"ewma_cv\s*>=\s*0\.3|ewma_cv.*0\.3|0\.3.*ewma_cv", phase3_content), \
            f"Phase 3 of {f.name} must contain ewma_cv >= 0.3 threshold check"
        # 180-line split threshold must be present
        assert "180" in phase3_content, \
            f"Phase 3 of {f.name} must contain 180-line split threshold"
        # 20% reduction must be present
        assert re.search(r"20%|80%", phase3_content), \
            f"Phase 3 of {f.name} must reference 20% reduction (or 80% cap) for high-CV task sizing"
        # The user-facing notification line must NOT be present
        assert not re.search(r"CV=.*high.*sizing tasks more conservatively", phase3_content), \
            f"Phase 3 of {f.name} must NOT emit user-facing CV notification (IP protection)"
# T-108: Orchestrate skill fixes tests (round complete emission + Step 4b startup)
def test_orchestrate_skill_no_vestigial_round_complete():
    orchestrate_files = [
        Path("commands/claude/orchestrate.md"),
        Path("commands/gemini/skills/orchestrate/SKILL.md"),
    ]
    for f in orchestrate_files:
        content = f.read_text(encoding="utf-8")
        assert "AGENTFLOW_ROUND_COMPLETE" not in content, f"{f.name} must not print vestigial AGENTFLOW_ROUND_COMPLETE"
        
        # Check that it instructs to do human gate passed/yes response
        human_gate_section = content.split("## Human gate")[1].split("## Merge")[0]
        assert "yes" in human_gate_section, \
            f"{f.name} must mention 'yes' in the Human gate section"


def test_orchestrate_skill_has_step_4b_startup():
    orchestrate_files = [
        Path("commands/claude/orchestrate.md"),
        Path("commands/gemini/skills/orchestrate/SKILL.md"),
    ]
    for f in orchestrate_files:
        content = f.read_text(encoding="utf-8")
        assert "Step 4b" in content, f"{f.name} must contain Step 4b"
        
        # Check that Step 4b instructs to read round table, identify PENDING tasks, and announce "Picking up Round"
        startup_section = content.split("## Decomposition")[0]
        assert "Step 4b" in startup_section, f"Step 4b must appear in the Startup section in {f.name}"
        assert "round table" in startup_section.lower(), f"Step 4b must mention 'round table' in {f.name}"
        assert "pending" in startup_section.lower(), f"Step 4b must mention 'PENDING' in {f.name}"
        assert "picking up round" in startup_section.lower(), f"Step 4b must announce 'Picking up Round X: T-xxx' in {f.name}"
