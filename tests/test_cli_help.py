"""The CLI's own text must agree with the README flag table.

HELP, USAGE and the README table are three hand-written copies of the same
list of flags, and they had already drifted (USAGE hid --root and
--install-skill). These tests read the README table, so adding a flag there
without teaching `--help` about it fails here.
"""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENTRY = ROOT / "webtweak.js"


def run_cli(*args):
    return subprocess.run(["node", str(ENTRY), *args], capture_output=True, text=True)


def names(flag, text):
    """True if `flag` appears as a whole token - a bare substring test would
    find `-h` inside `--help` and pass whatever the help said about `-h`."""
    return re.search(r"(?<![\w-])" + re.escape(flag) + r"(?![\w-])", text) is not None


def readme_flags():
    """Every flag named in the first column of the README flag table."""
    flags = []
    in_table = False
    for line in (ROOT / "README.md").read_text(encoding="utf-8").splitlines():
        if re.match(r"\|\s*Flag\s*\|", line):
            in_table = True
            continue
        if not in_table:
            continue
        if not line.startswith("|"):
            break
        first_cell = line.split("|")[1]
        flags += re.findall(r"`(--?[A-Za-z][\w-]*)", first_cell)
    return flags


def test_readme_flag_table_was_parsed():
    """Guard against the parser going vacuous if the table moves or changes shape."""
    flags = readme_flags()
    assert len(flags) >= 6, flags
    for expected in ("--root", "--port", "--no-browser", "--install-skill",
                     "--version", "--help"):
        assert expected in flags, flags


def test_help_lists_every_readme_flag():
    r = run_cli("--help")
    assert r.returncode == 0, r.stderr
    missing = [f for f in readme_flags() if not names(f, r.stdout)]
    assert not missing, f"--help does not mention: {missing}"


def test_usage_line_lists_every_long_flag():
    """The usage line is all an error prints, so it must name every long flag."""
    r = run_cli()
    usage = r.stderr
    missing = [f for f in readme_flags() if f.startswith("--") and not names(f, usage)]
    assert not missing, f"usage line does not mention: {missing}\n{usage}"


def test_no_args_exits_1_and_points_at_root_and_help():
    r = run_cli()
    assert r.returncode == 1
    assert "--root" in r.stderr
    assert "--help" in r.stderr
    # USAGE itself names --help, so check the hint line the issue asked for too.
    assert "Run webtweak --help for options." in r.stderr


def test_directory_error_shows_usage_with_root(tmp_path):
    r = run_cli(str(tmp_path))
    assert r.returncode == 1
    assert "--root" in r.stderr


def test_help_hint_is_only_on_the_no_page_error():
    r = run_cli("--bogus")
    assert r.returncode == 1
    assert "--root" in r.stderr
    assert "Run webtweak --help" not in r.stderr
