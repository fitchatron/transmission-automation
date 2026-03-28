import subprocess


def start_vpn():
    subprocess.run(["nordvpn", "connect"], check=False)


def stop_vpn():
    subprocess.run(["nordvpn", "disconnect"], check=False)


def is_vpn_connected():
    status = subprocess.run(
        ["nordvpn", "status"], capture_output=True, text=True, check=False
    )
    connected = "Status: Connected" in (status.stdout or "")

    return connected

