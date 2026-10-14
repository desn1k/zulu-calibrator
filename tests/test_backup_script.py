"""docker/backup.sh, run with --once against temporary directories."""

import os
import shutil
import sqlite3
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "docker" / "backup.sh"

SH = shutil.which("sh")
SQLITE3 = shutil.which("sqlite3")

if not (SH and SQLITE3):
    if os.environ.get("CI"):
        pytest.fail("sh and sqlite3 are required in CI", pytrace=False)
    pytest.skip("needs sh and the sqlite3 CLI", allow_module_level=True)


def run_backup(db: Path, backups: Path, keep: int = 14) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "DB_PATH": str(db),
        "BACKUP_DIR": str(backups),
        "BACKUP_KEEP": str(keep),
    }
    return subprocess.run(  # noqa: S603
        [SH, str(SCRIPT), "--once"], env=env, capture_output=True, text=True, check=False
    )


def make_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE t (x INTEGER)")
        conn.execute("INSERT INTO t VALUES (42)")
    conn.close()


def test_backup_copies_the_database(tmp_path: Path) -> None:
    db, backups = tmp_path / "app.db", tmp_path / "backups"
    backups.mkdir()
    make_db(db)

    result = run_backup(db, backups)

    assert result.returncode == 0, result.stdout + result.stderr
    [copy] = list(backups.glob("app-*.db"))
    with sqlite3.connect(copy) as conn:
        assert conn.execute("SELECT x FROM t").fetchall() == [(42,)]
    conn.close()


def test_failed_backup_is_not_published(tmp_path: Path) -> None:
    db, backups = tmp_path / "app.db", tmp_path / "backups"
    backups.mkdir()
    db.write_bytes(b"this is not an sqlite database" * 100)

    result = run_backup(db, backups)

    assert result.returncode != 0
    assert list(backups.iterdir()) == [], "no backup and no temp file may be left behind"


def test_failed_backup_is_not_published_in_daily_loop(tmp_path: Path) -> None:
    # In the loop set -e is off, so a failed .backup must be caught explicitly.
    db, backups = tmp_path / "app.db", tmp_path / "backups"
    backups.mkdir()
    db.write_bytes(b"this is not an sqlite database" * 100)
    env = {**os.environ, "DB_PATH": str(db), "BACKUP_DIR": str(backups), "BACKUP_KEEP": "14"}
    env["BACKUP_INTERVAL_SECONDS"] = "3600"

    proc = subprocess.Popen(  # noqa: S603
        [SH, str(SCRIPT)], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )
    try:
        assert proc.stdout is not None
        # The first attempt reports before sleeping; sqlite3's own error may come first.
        report = ""
        for _ in range(5):
            line = proc.stdout.readline()
            if line.startswith("backup:"):
                report = line
                break
    finally:
        proc.kill()
        proc.wait()

    assert "failed" in report
    assert list(backups.iterdir()) == []


def test_only_newest_copies_are_kept(tmp_path: Path) -> None:
    db, backups = tmp_path / "app.db", tmp_path / "backups"
    backups.mkdir()
    make_db(db)
    for day in ("20260101", "20260102", "20260103"):
        (backups / f"app-{day}T000000Z.db").write_bytes(b"old")

    result = run_backup(db, backups, keep=2)

    assert result.returncode == 0, result.stdout + result.stderr
    names = sorted(p.name for p in backups.glob("app-*.db"))
    assert len(names) == 2
    assert names[0] == "app-20260103T000000Z.db"
