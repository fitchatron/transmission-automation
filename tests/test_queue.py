import pytest

from tam.queue import QueueLocked, queue_lock, read_queue, rewrite_queue


def test_read_skips_blank_and_comment_lines(tmp_path):
    path = tmp_path / "tv.txt"
    path.write_text("# my shows\n\nmagnet:?a\n  magnet:?b  \n# error: old (2026-01-01 00:00)\n")

    entries = read_queue(path, "tv-show")

    assert [e.magnet for e in entries] == ["magnet:?a", "magnet:?b"]
    assert {e.type for e in entries} == {"tv-show"}
    assert {e.path for e in entries} == {path}


def test_read_missing_file_is_empty(tmp_path):
    assert read_queue(tmp_path / "movies.txt", "movie") == []


def test_rewrite_drops_processed_and_keeps_failures(tmp_path):
    path = tmp_path / "tv.txt"
    path.write_text("# keep me\nmagnet:?ok\nmagnet:?bad\n# error: stale (2026-01-01 00:00)\n")

    rewrite_queue(path, processed={"magnet:?ok", "magnet:?bad"}, failures={"magnet:?bad": "boom"})

    lines = path.read_text().splitlines()
    assert lines[0] == "# keep me"
    assert lines[1] == "magnet:?bad"
    assert lines[2].startswith("# error: boom (")
    assert len(lines) == 3  # the stale error comment is gone


def test_rewrite_keeps_lines_added_during_run(tmp_path):
    path = tmp_path / "movies.txt"
    path.write_text("magnet:?ok\n")
    # ...start runs, meanwhile the user appends another magnet...
    path.write_text("magnet:?ok\nmagnet:?new\n")

    rewrite_queue(path, processed={"magnet:?ok"}, failures={})

    assert path.read_text() == "magnet:?new\n"


def test_rewrite_everything_processed_leaves_empty_file(tmp_path):
    path = tmp_path / "movies.txt"
    path.write_text("magnet:?ok\n")

    rewrite_queue(path, processed={"magnet:?ok"}, failures={})

    assert path.read_text() == ""
    assert [p.name for p in tmp_path.iterdir()] == ["movies.txt"]  # no temp files left


def test_lock_blocks_second_holder(tmp_path):
    with queue_lock(tmp_path / "queue"):
        with pytest.raises(QueueLocked):
            with queue_lock(tmp_path / "queue"):
                pass
    with queue_lock(tmp_path / "queue"):  # released again
        pass
