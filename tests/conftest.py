import pytest

from tam import vpn


class FakeSystem:
    """Records VPN / rpi-connect commands instead of running them."""

    def __init__(self):
        self.calls: list[str] = []
        self.rpi_connect_result = (True, "restarted")

    def stop_vpn(self):
        self.calls.append("vpn disconnect")
        return True

    def restart_rpi_connect(self):
        self.calls.append("rpi-connect restart")
        return self.rpi_connect_result


@pytest.fixture(autouse=True)
def system(monkeypatch):
    """Never let a test disconnect the real VPN or restart rpi-connect."""
    fake = FakeSystem()
    monkeypatch.setattr(vpn, "stop_vpn", fake.stop_vpn)
    monkeypatch.setattr(vpn, "restart_rpi_connect", fake.restart_rpi_connect)
    return fake
