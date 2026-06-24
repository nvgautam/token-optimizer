"""Checklist evaluator — tracks whether oracle has enough info to generate artifacts."""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field

CHECKLIST_ITEMS = [
    "project_name",
    "project_purpose",
    "tech_stack",
    "module_boundaries",
    "shared_interfaces",
    "scale_requirements",
    "performance_constraints",
    "security_model",
    "compliance_requirements",
    "test_strategy",
    "deployment_target",
    "no_size_violations",
    "no_ownership_conflicts",
    "interfaces_have_owners",
]

_KEYWORDS: dict[str, list[str]] = {
    "project_name": [r"\bcalled\b", r"\bnamed\b", r"\bthe project\b", r"\bproject name\b"],
    "project_purpose": [r"\bbuilds?\b", r"\bmanages?\b", r"\bprovides?\b", r"\bserves?\b",
                        r"\bpurpose\b", r"\bgoal\b", r"\bdoes\b"],
    "tech_stack": [r"\bpython\b", r"\bgo\b", r"\btypescript\b", r"\bjava\b", r"\brust\b",
                   r"\bnode\b", r"\bdjango\b", r"\bfastapi\b", r"\bflask\b", r"\bspring\b",
                   r"\breact\b", r"\bvue\b", r"\bpostgres\b", r"\bmysql\b", r"\bmongo\b"],
    "module_boundaries": [r"\bmodule\b", r"\bservice\b", r"\bcomponent\b", r"\bboundary\b",
                           r"\blayer\b", r"\bpackage\b"],
    "shared_interfaces": [r"\bapi\b", r"\binterface\b", r"\bcontract\b", r"\bschema\b",
                          r"\bprotocol\b", r"\bendpoint\b"],
    "scale_requirements": [r"\bscale\b", r"\busers\b", r"\brequests\b", r"\btraffic\b",
                            r"\bvolume\b", r"\bgrowth\b", r"\bconcurrent\b"],
    "performance_constraints": [r"\blatency\b", r"\bslo\b", r"\bthroughput\b",
                                 r"\bmillisecond\b", r"\bms\b", r"\bperformance\b", r"\bfast\b"],
    "security_model": [r"\bauth\b", r"\bjwt\b", r"\boauth\b", r"\bapi.?key\b",
                       r"\bauthentication\b", r"\bauthorization\b", r"\brbac\b"],
    "compliance_requirements": [r"\bgdpr\b", r"\bhipaa\b", r"\bsoc.?2\b", r"\bpci\b",
                                 r"\bno compliance\b", r"\bnot regulated\b", r"\bnone\b"],
    "test_strategy": [r"\bcoverage\b", r"\btdd\b", r"\btesting\b", r"\bunit test\b",
                      r"\bintegration test\b", r"\btest\b"],
    "deployment_target": [r"\baws\b", r"\bgcp\b", r"\bazure\b", r"\bdocker\b",
                           r"\bkubernetes\b", r"\bk8s\b", r"\bserverless\b",
                           r"\bcloud\b", r"\bon.?prem\b", r"\bheroku\b"],
}

# These items are set True by default — enforced structurally at generation time
_DEFAULT_TRUE = {"no_size_violations", "no_ownership_conflicts"}


def new_checklist_state() -> "ChecklistState":
    resolved = {item: item in _DEFAULT_TRUE for item in CHECKLIST_ITEMS}
    return ChecklistState(resolved=resolved, evidence={})


def evaluate_checklist(
    conversation_history: list[dict], state: "ChecklistState"
) -> "ChecklistState":
    """Return updated ChecklistState without mutating the input."""
    new_resolved = copy.copy(state.resolved)
    new_evidence = copy.copy(state.evidence)

    text_pool = " ".join(
        turn.get("content", "") for turn in conversation_history
    ).lower()

    for item, patterns in _KEYWORDS.items():
        if new_resolved.get(item):
            continue
        for pattern in patterns:
            match = re.search(pattern, text_pool, re.IGNORECASE)
            if match:
                new_resolved[item] = True
                start = max(0, match.start() - 40)
                new_evidence[item] = text_pool[start: match.end() + 40].strip()
                break

    # interfaces_have_owners resolves when module_boundaries resolves
    if new_resolved.get("module_boundaries"):
        new_resolved["interfaces_have_owners"] = True

    return ChecklistState(resolved=new_resolved, evidence=new_evidence)


@dataclass
class ChecklistState:
    resolved: dict[str, bool] = field(default_factory=dict)
    evidence: dict[str, str] = field(default_factory=dict)

    @property
    def all_resolved(self) -> bool:
        return all(self.resolved.values())

    @property
    def unresolved(self) -> list[str]:
        return [k for k, v in self.resolved.items() if not v]
