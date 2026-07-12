"""
Test that report_builder_helpers module was extracted correctly and imports still work.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[2]))

import pytest


def test_build_report_still_importable_from_report_builder():
    """Verify that build_report can be imported from the original location."""
    from agentflow.reporting.report_builder import build_report
    assert callable(build_report)


def test_helper_functions_still_importable_from_report_builder():
    """Verify that helper functions can be imported from the original location."""
    from agentflow.reporting.report_builder import (
        _reporting_window,
        _filter_by_window,
        _format_baseline_annotation,
        _load_proxy_savings,
        _compression_delta_from_history,
        _handoff_component,
        _lifetime_recycling_callout,
        _load_proxy_log,
        _load_calibration_html,
    )
    assert callable(_reporting_window)
    assert callable(_filter_by_window)
    assert callable(_format_baseline_annotation)
    assert callable(_load_proxy_savings)
    assert callable(_compression_delta_from_history)
    assert callable(_handoff_component)
    assert callable(_lifetime_recycling_callout)
    assert callable(_load_proxy_log)
    assert callable(_load_calibration_html)


def test_report_builder_helpers_module_exists():
    """Verify that the new report_builder_helpers module exists and is importable."""
    from agentflow.reporting import report_builder_helpers
    assert report_builder_helpers is not None


def test_helpers_are_in_report_builder_helpers():
    """Verify that helpers are defined in the new helpers module."""
    from agentflow.reporting import report_builder_helpers
    assert hasattr(report_builder_helpers, '_reporting_window')
    assert hasattr(report_builder_helpers, '_filter_by_window')
    assert hasattr(report_builder_helpers, '_format_baseline_annotation')
    assert hasattr(report_builder_helpers, '_load_proxy_savings')
    assert hasattr(report_builder_helpers, '_compression_delta_from_history')
    assert hasattr(report_builder_helpers, '_handoff_component')
    assert hasattr(report_builder_helpers, '_lifetime_recycling_callout')
    assert hasattr(report_builder_helpers, '_load_proxy_log')
    assert hasattr(report_builder_helpers, '_load_calibration_html')
