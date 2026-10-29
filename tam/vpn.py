import subprocess
import time
from collections.abc import Callable


def start_vpn():
    try:
        subprocess.run(["nordvpn", "connect"], check=False)
    except FileNotFoundError:
        pass


def stop_vpn() -> bool:
    """Run `nordvpn disconnect`. Returns False if nordvpn is missing or the command fails."""
    try:
        result = subprocess.run(["nordvpn", "disconnect"], capture_output=True, check=False)
    except FileNotFoundError:
        return False
    return result.returncode == 0


def is_vpn_connected() -> bool:
    try:
        status = subprocess.run(["nordvpn", "status"], capture_output=True, text=True, check=False)
    except FileNotFoundError:
        return False
    return "Status: Connected" in (status.stdout or "")


def ensure_vpn(attempts: int = 3, sleep: Callable[[float], None] = time.sleep) -> bool:
    """Connect the VPN if needed. Returns True once it reports connected."""
    for attempt in range(attempts):
        if is_vpn_connected():
            return True
        start_vpn()
        if attempt < attempts - 1:
            sleep(2)
    return is_vpn_connected()


def restart_rpi_connect() -> tuple[bool, str]:
    """Run `rpi-connect restart`. Returns (succeeded, output or error)."""
    try:
        result = subprocess.run(
            ["rpi-connect", "restart"], capture_output=True, text=True, check=False
        )
    except FileNotFoundError:
        return False, "rpi-connect is not installed"
    output = (result.stdout or result.stderr or "").strip()
    return result.returncode == 0, output
