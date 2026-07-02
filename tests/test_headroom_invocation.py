"""Static assertion tests for T-079: headroom invocation shape in cmd_shell.

Guards against future flags (e.g. --intercept-tool-results, --mode) being
added to the `headroom wrap` invocation without a corresponding
design_status.md decision. headroom/config.py's DEFAULT_EXCLUDE_TOOLS
already excludes Read/Glob/Grep/Write/Edit from ContentRouter compression,
but headroom/transforms/read_lifecycle.py's ReadLifecycleConfig
(compress_stale=True by default) runs independent of tool exclusion and
rewrites a prior Read into a stale marker once the file is later
Written/Edited. Extra flags on the `headroom wrap` invocation are the
mechanism by which that protection could be widened or bypassed, so the
invocation shape is pinned here rather than asserted only at runtime.
"""

import ast
import inspect

from agentflow.cli import cmd_shell


def _cmd_shell_source() -> str:
    return inspect.getsource(cmd_shell)


def _find_cmd_args_assignments(tree: ast.AST):
    """Return all ast.Assign nodes that target a bare name `cmd_args`."""
    assigns = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "cmd_args":
                    assigns.append(node)
    return assigns


def _headroom_cmd_args_assignments(tree: ast.AST):
    return [
        a
        for a in _find_cmd_args_assignments(tree)
        if isinstance(a.value, ast.List)
        and any(
            isinstance(elt, ast.Constant) and elt.value == "headroom"
            for elt in a.value.elts
        )
    ]


def test_cmd_shell_source_contains_headroom_wrap_assignment():
    """cmd_shell must construct a cmd_args = [...] list containing 'headroom'."""
    tree = ast.parse(_cmd_shell_source())
    assert _headroom_cmd_args_assignments(tree), (
        "expected a cmd_args = [...] assignment containing 'headroom' in cmd_shell"
    )


def test_headroom_cmd_args_no_extra_flags():
    """
    The headroom cmd_args list must be exactly ["headroom", "wrap", cmd] —
    no extra flags. Adding flags like --intercept-tool-results or a
    non-default --mode would defeat headroom's DEFAULT_EXCLUDE_TOOLS
    protection for Read/Grep/Glob/Write/Edit, since ReadLifecycle's
    compress_stale=True runs independent of tool exclusion.
    """
    tree = ast.parse(_cmd_shell_source())
    headroom_assigns = _headroom_cmd_args_assignments(tree)
    assert len(headroom_assigns) == 1, "expected exactly one headroom cmd_args assignment"

    elts = headroom_assigns[0].value.elts
    assert len(elts) == 3, (
        f"cmd_args for headroom wrap must have exactly 3 elements "
        f"(['headroom', 'wrap', cmd]), found {len(elts)} — "
        f"extra flags would defeat DEFAULT_EXCLUDE_TOOLS protection"
    )

    first, second, third = elts
    assert isinstance(first, ast.Constant) and first.value == "headroom"
    assert isinstance(second, ast.Constant) and second.value == "wrap"
    # Third element must be the `cmd` variable itself, not a literal flag string.
    assert isinstance(third, ast.Name) and third.id == "cmd"


def test_no_intercept_tool_results_flag_in_source():
    """Belt-and-suspenders substring guard against this specific flag regressing in."""
    assert "--intercept-tool-results" not in _cmd_shell_source()


def test_no_mode_flag_in_source():
    """Belt-and-suspenders substring guard against a --mode flag regressing in."""
    assert "--mode" not in _cmd_shell_source()
