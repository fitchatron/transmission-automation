import logging
import subprocess

from utils.transmission import list_torrents


def test_list_torrents_parses_name_with_multiple_spaces(monkeypatch):
    stdout = "\n".join(
        [
            "    ID   Done       Have  ETA           Up    Down  Ratio  Status       Name",
            "    10   100%    4.53 GB  Done        41.0     0.0    0.0  Seeding      www.UIndex.org    -    The.Boys.S05E01.1080p.WEB.h264-ETHEL",
            "    11   100%   640.0 MB  Done         0.0     0.0    0.0  Idle         The.Boys.S05E02.1080p.HEVC.x265-MeGusta[EZTVx.to].mkv",
            "    12   100%    3.60 GB  Done         0.0     0.0    0.0  Seeding      Saturday.Night.Live.S51E17.Colman.Domingo.1080p.WEB.h264-EDITH[EZTVx.to].mkv",
            "Sum:             8.77 GB              41.0     0.0",
        ]
    )

    def mock_run(*_args, **_kwargs):
        return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")

    monkeypatch.setattr(subprocess, "run", mock_run)

    torrents = list_torrents(logging.getLogger(__name__))

    assert len(torrents) == 3
    assert torrents[0]["id"] == "10"
    assert torrents[0]["status"] == "Seeding"
    assert torrents[0]["name"] == "www.UIndex.org    -    The.Boys.S05E01.1080p.WEB.h264-ETHEL"


def test_list_torrents_parses_status_with_spaces(monkeypatch):
    stdout = "\n".join(
        [
            "    ID   Done       Have  ETA           Up    Down  Ratio  Status       Name",
            "    10     0%   16.46 MB  10 hrs       0.0   162.0    0.0  Downloading  www.UIndex.org    -    The.Boys.S05E01.1080p.WEB.h264-ETHEL",
            "    11     2%   15.80 MB  5 min        4.0  2066.0    0.0  Up & Down    The.Boys.S05E02.1080p.HEVC.x265-MeGusta[EZTVx.to].mkv",
            "    12     0%       None  Unknown      0.0     0.0   None  Idle         Saturday.Night.Live.S51E17.Colman.Domingo.1080p.WEB.h264-EDITH[EZTVx.to].mkv",
            "Sum:            32.26 MB               4.0  2228.0",
        ]
    )

    def mock_run(*_args, **_kwargs):
        return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")

    monkeypatch.setattr(subprocess, "run", mock_run)

    torrents = list_torrents(logging.getLogger(__name__))

    assert len(torrents) == 3
    assert torrents[1]["id"] == "11"
    assert torrents[1]["status"] == "Up & Down"
    assert torrents[1]["name"] == "The.Boys.S05E02.1080p.HEVC.x265-MeGusta[EZTVx.to].mkv"
