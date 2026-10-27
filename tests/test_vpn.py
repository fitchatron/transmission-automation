from tam import vpn


def test_ensure_vpn_connects_when_down(monkeypatch):
    state = {"connected": False, "connects": 0}

    def start():
        state["connects"] += 1
        state["connected"] = True

    monkeypatch.setattr(vpn, "is_vpn_connected", lambda: state["connected"])
    monkeypatch.setattr(vpn, "start_vpn", start)

    assert vpn.ensure_vpn(sleep=lambda s: None) is True
    assert state["connects"] == 1


def test_ensure_vpn_gives_up(monkeypatch):
    monkeypatch.setattr(vpn, "is_vpn_connected", lambda: False)
    monkeypatch.setattr(vpn, "start_vpn", lambda: None)

    assert vpn.ensure_vpn(attempts=3, sleep=lambda s: None) is False


def test_missing_nordvpn_reads_as_disconnected(monkeypatch):
    monkeypatch.setenv("PATH", "")

    assert vpn.is_vpn_connected() is False
