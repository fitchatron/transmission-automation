import subprocess
import time
from collections.abc import Callable


def start_vpn():
    try:
        subprocess.run(["nordvpn", "connect"], check=False)
    except FileNotFoundError:
        pass


def stop_vpn():
    try:
        subprocess.run(["nordvpn", "disconnect"], check=False)
    except FileNotFoundError:
        pass


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
