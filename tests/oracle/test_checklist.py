"""Tests for agentflow.oracle.checklist."""

from agentflow.oracle.checklist import (
    CHECKLIST_ITEMS,
    ChecklistState,
    evaluate_checklist,
    new_checklist_state,
)


def _history(*messages: str) -> list[dict]:
    return [{"role": "user", "content": m} for m in messages]


def test_new_checklist_state_has_all_items_known():
    state = new_checklist_state()
    for item in CHECKLIST_ITEMS:
        assert item in state.resolved


def test_new_checklist_state_not_all_resolved():
    state = new_checklist_state()
    # some items default to False
    assert not state.all_resolved


def test_evaluate_checklist_marks_tech_stack_resolved():
    state = new_checklist_state()
    history = _history("We'll build this in Python using FastAPI.")
    updated = evaluate_checklist(history, state)
    assert updated.resolved["tech_stack"] is True


def test_evaluate_checklist_marks_compliance_resolved_on_none():
    state = new_checklist_state()
    history = _history("There are no compliance requirements for this project.")
    updated = evaluate_checklist(history, state)
    assert updated.resolved["compliance_requirements"] is True


def test_evaluate_checklist_marks_deployment_target_resolved_on_docker():
    state = new_checklist_state()
    history = _history("We'll deploy using Docker containers.")
    updated = evaluate_checklist(history, state)
    assert updated.resolved["deployment_target"] is True


def test_evaluate_checklist_empty_conversation_resolves_nothing_extra():
    state = new_checklist_state()
    # only default-true items should be resolved
    updated = evaluate_checklist([], state)
    auto_true = {"no_size_violations", "no_ownership_conflicts"}
    for item, val in updated.resolved.items():
        if item not in auto_true:
            assert val is False, f"Expected {item} to be False on empty history"


def test_all_resolved_true_only_when_all_items_true():
    state = new_checklist_state()
    assert not state.all_resolved
    full_resolved = {item: True for item in CHECKLIST_ITEMS}
    state2 = ChecklistState(resolved=full_resolved, evidence={})
    assert state2.all_resolved


def test_unresolved_returns_list_of_unresolved_items():
    state = new_checklist_state()
    unresolved = state.unresolved
    assert isinstance(unresolved, list)
    assert "tech_stack" in unresolved


def test_evaluate_checklist_is_non_mutating():
    state = new_checklist_state()
    original_resolved = dict(state.resolved)
    history = _history("We'll use Python and Docker, no compliance needed.")
    evaluate_checklist(history, state)
    assert state.resolved == original_resolved


def test_interfaces_have_owners_resolved_when_module_boundaries_resolved():
    state = new_checklist_state()
    history = _history("We'll split into auth module, api module, and db module boundary.")
    updated = evaluate_checklist(history, state)
    assert updated.resolved["module_boundaries"] is True
    assert updated.resolved["interfaces_have_owners"] is True
