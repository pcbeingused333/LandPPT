"""Run actual workspace controller regressions instead of retired JS strings."""

import shutil
import subprocess
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("controller", ["outline", "generator", "template-wizard"])
def test_workspace_controller_lifecycle_and_recovery(controller):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js 22.12+ is required for frontend controller tests")
    version = subprocess.run(
        [node, "--version"], capture_output=True, text=True, check=True
    )
    numbers = tuple(map(int, re.findall(r"\d+", version.stdout)[:2]))
    if numbers < (22, 12):
        pytest.skip("Node.js 22.12+ is required for frontend controller tests")
    result = subprocess.run(
        [
            node,
            "--experimental-strip-types",
            "--test",
            f"frontend/tests/{controller}-controller.test.mjs",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
