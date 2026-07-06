import pytest

@pytest.mark.skip(reason="stdin_filter deprecated; jailbreak handling moved to UserPromptSubmit hook (T-119)")
def test_stdin_filter_placeholder():
    pass

@pytest.mark.skip(reason="stdin_filter deprecated; jailbreak handling moved to UserPromptSubmit hook (T-119)")
def test_stdin_filter_blocks_pattern():
    pass

@pytest.mark.skip(reason="stdin_filter deprecated; jailbreak handling moved to UserPromptSubmit hook (T-119)")
def test_stdin_filter_passes_clean():
    pass
