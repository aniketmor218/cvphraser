import json

import pytest

from skillsift.cli import EXIT_BELOW_THRESHOLD, EXIT_ERROR, EXIT_OK, main


@pytest.fixture
def paths(tmp_path, cv_text, jd_text):
    cv = tmp_path / "cv.md"
    jd = tmp_path / "junior-ml-engineer.md"
    cv.write_text(cv_text)
    jd.write_text(jd_text)
    return tmp_path, cv, jd


def run(db, *args):
    return main(["--db", str(db), "--no-color", *args])


def test_match_prints_a_score(paths, capsys):
    tmp, cv, jd = paths
    code = run(tmp / "db.sqlite", "match", str(cv), str(jd))
    out = capsys.readouterr().out
    assert code in (EXIT_OK, EXIT_BELOW_THRESHOLD)
    assert "%" in out
    assert "Junior Ml Engineer" in out  # title inferred from the filename


def test_match_json_is_parseable(paths, capsys):
    tmp, cv, jd = paths
    run(tmp / "db.sqlite", "match", str(cv), str(jd), "--json")
    payload = json.loads(capsys.readouterr().out)
    assert 0 <= payload["percentage"] <= 100
    assert "matched" in payload


def test_exit_code_reflects_the_threshold(paths, monkeypatch, capsys):
    tmp, cv, jd = paths
    monkeypatch.setenv("SKILLSIFT_PASS_THRESHOLD", "0.99")
    assert run(tmp / "db.sqlite", "match", str(cv), str(jd)) == EXIT_BELOW_THRESHOLD
    monkeypatch.setenv("SKILLSIFT_PASS_THRESHOLD", "0.0")
    assert run(tmp / "db.sqlite", "match", str(cv), str(jd)) == EXIT_OK


def test_save_then_list_then_status(paths, capsys):
    tmp, cv, jd = paths
    db = tmp / "db.sqlite"
    run(db, "match", str(cv), str(jd), "--save", "--title", "MLE", "--company", "Acme")
    capsys.readouterr()

    run(db, "list")
    assert "MLE" in capsys.readouterr().out

    assert run(db, "status", "1", "applied") == EXIT_OK
    run(db, "list", "--status", "applied")
    assert "MLE" in capsys.readouterr().out


def test_status_on_unknown_posting_errors(tmp_path, capsys):
    assert run(tmp_path / "db.sqlite", "status", "42", "applied") == EXIT_ERROR
    assert "No application found" in capsys.readouterr().err


def test_bad_status_is_reported(tmp_path, capsys):
    assert run(tmp_path / "db.sqlite", "status", "1", "ghosted") == EXIT_ERROR
    assert "unknown status" in capsys.readouterr().err


def test_missing_file_is_reported(tmp_path, capsys):
    code = run(tmp_path / "db.sqlite", "match", str(tmp_path / "nope.md"), str(tmp_path / "x.md"))
    assert code == EXIT_ERROR
    assert "no such file" in capsys.readouterr().err


def test_gaps_report(paths, capsys):
    tmp, cv, jd = paths
    db = tmp / "db.sqlite"
    run(db, "match", str(cv), str(jd), "--save")
    capsys.readouterr()
    run(db, "gaps")
    # Only *required* gaps are tracked — the study list should be must-haves.
    assert "TensorFlow" in capsys.readouterr().out


def test_skills_listing_can_be_filtered(tmp_path, capsys):
    run(tmp_path / "db.sqlite", "skills", "--category", "ml")
    out = capsys.readouterr().out
    assert "PyTorch" in out
    assert "Flask" not in out


def test_global_flags_work_after_the_subcommand(paths, capsys):
    """Regression: '--no-color' was rejected unless it preceded the subcommand."""
    tmp, cv, jd = paths
    code = main(["match", str(cv), str(jd), "--db", str(tmp / "db.sqlite"), "--no-color"])
    assert code in (EXIT_OK, EXIT_BELOW_THRESHOLD)
    assert "\033[" not in capsys.readouterr().out
