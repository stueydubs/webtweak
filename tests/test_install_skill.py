"""Tests for `webtweak --install-skill`.

This path is what a global/npx user relies on to reach the reconcile skill at
all, and it is the only place webtweak calls fs.cpSync - an API old enough to
matter for the `engines: >=18` claim. Running it under CI's Node matrix is what
turns that claim into something verified rather than assumed.

HOME is redirected to a temp dir so a test run never touches the real
~/.claude/skills.
"""

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ENTRY = ROOT / "webtweak.js"


def run_install(home: Path):
    env = dict(os.environ, HOME=str(home), USERPROFILE=str(home))
    return subprocess.run(["node", str(ENTRY), "--install-skill"],
                          capture_output=True, text=True, env=env)


@pytest.fixture
def home(tmp_path):
    h = tmp_path / "home"
    h.mkdir()
    return h


def test_installs_the_skill_and_its_helper(home):
    r = run_install(home)
    assert r.returncode == 0, r.stderr
    dest = home / ".claude" / "skills" / "webtweak-reconcile"
    assert (dest / "SKILL.md").is_file()
    assert (dest / "scripts" / "wtreconcile.py").is_file()
    assert str(dest) in r.stdout


def test_installed_skill_carries_the_create_op(home):
    """The create-op section is what tells Claude a shape patch is not an edit
    patch. An install that silently drops it is worse than no install."""
    assert run_install(home).returncode == 0
    skill = (home / ".claude" / "skills" / "webtweak-reconcile" / "SKILL.md").read_text()
    assert 'op: "create"' in skill
    assert "not drag jitter" in skill      # the nudge guard must survive the copy


def test_installed_helper_is_executable(home):
    """SKILL.md invokes scripts/wtreconcile.py directly, so the +x bit is load
    bearing - npm does not preserve it on every install path."""
    assert run_install(home).returncode == 0
    helper = home / ".claude" / "skills" / "webtweak-reconcile" / "scripts" / "wtreconcile.py"
    assert os.access(helper, os.X_OK)
    r = subprocess.run([str(helper), "--help"], capture_output=True, text=True)
    assert r.returncode == 0


def test_install_is_idempotent(home):
    """Re-running after an upgrade must overwrite cleanly, not fail on an
    existing directory."""
    assert run_install(home).returncode == 0
    second = run_install(home)
    assert second.returncode == 0, second.stderr
    dest = home / ".claude" / "skills" / "webtweak-reconcile"
    assert (dest / "SKILL.md").is_file()


def test_reports_failure_instead_of_claiming_success(home):
    """An unwritable destination must exit non-zero and say so - never print the
    success line while having installed nothing.

    `.claude` is a regular file, so creating `.claude/skills` fails with ENOTDIR
    for any user. Permission bits would not do: root ignores them."""
    (home / ".claude").write_text("not a directory")
    r = run_install(home)
    assert r.returncode != 0
    assert "could not install skill" in r.stderr
    assert "installed to" not in r.stdout
