"""Join Wi-Fi by scanning a Wi-Fi QR code.

Readable has no screen, so typing a Wi-Fi password is not an option. Most
routers print a Wi-Fi QR code on their sticker, and Android phones and iPhones
can show one ("Share Wi-Fi"). The user points the device at it and presses
Scan; the device reads the network name aloud, asks for a second press to
confirm, and joins the network with NetworkManager (nmcli).

QR format (the de-facto standard used by phones and routers):
    WIFI:T:WPA;S:<ssid>;P:<password>;H:true;;
Special characters in values are escaped with a backslash: \\ \\; \\, \\: \\"

The password is passed to nmcli only. It is never logged or spoken.
"""
import logging
import subprocess
from dataclasses import dataclass
from typing import Callable, List, Optional, Sequence

logger = logging.getLogger(__name__)

PREFIX = "WIFI:"
SUPPORTED_SECURITY = {"WPA", "WPA2", "WPA3", "SAE", "NOPASS", ""}


@dataclass
class WifiCredentials:
    ssid: str
    password: str = ""
    security: str = "WPA"   # WPA (any WPA/WPA2/WPA3 personal), WEP, nopass
    hidden: bool = False

    @property
    def supported(self) -> bool:
        return self.security.upper() in SUPPORTED_SECURITY

    def __repr__(self) -> str:  # keep the password out of logs
        return f"WifiCredentials(ssid={self.ssid!r}, security={self.security!r}, hidden={self.hidden})"


def _split_fields(body: str) -> List[str]:
    """Split on unescaped ';' and unescape each field."""
    fields, cur, i = [], [], 0
    while i < len(body):
        ch = body[i]
        if ch == "\\" and i + 1 < len(body):
            cur.append(body[i + 1])
            i += 2
            continue
        if ch == ";":
            fields.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
        i += 1
    if cur:
        fields.append("".join(cur))
    return fields


def parse_wifi_qr(text: str) -> Optional[WifiCredentials]:
    """Parse a WIFI: QR payload. Returns None if it is not a Wi-Fi code."""
    if not text:
        return None
    text = text.strip()
    if text[: len(PREFIX)].upper() != PREFIX:
        return None
    values = {}
    for field in _split_fields(text[len(PREFIX):]):
        if ":" not in field:
            continue
        key, value = field.split(":", 1)
        values.setdefault(key.strip().upper(), value)
    ssid = values.get("S", "")
    if not ssid:
        return None
    security = values.get("T", "WPA" if values.get("P") else "nopass").strip()
    if security.upper() == "NOPASS":
        security = "nopass"
    return WifiCredentials(
        ssid=ssid,
        password=values.get("P", ""),
        security=security,
        hidden=values.get("H", "").strip().lower() == "true",
    )


def find_wifi_qr(image) -> Optional[WifiCredentials]:
    """Look for a Wi-Fi QR code in a BGR/RGB image. Returns None if there is none."""
    try:
        import cv2
    except ImportError:
        return None
    if image is None:
        return None
    detector = cv2.QRCodeDetector()
    candidates = [image]
    h, w = image.shape[:2]
    if max(h, w) > 1400:  # the full-resolution photo can be slow or miss large codes
        scale = 1200.0 / max(h, w)
        candidates.append(cv2.resize(image, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA))
    for img in candidates:
        try:
            ok, texts, _, _ = detector.detectAndDecodeMulti(img)
        except cv2.error:
            ok, texts = False, []
        if not ok:
            try:
                single, _, _ = detector.detectAndDecode(img)
            except cv2.error:
                single = ""
            texts = [single] if single else []
        for text in texts:
            creds = parse_wifi_qr(text)
            if creds:
                return creds
    return None


Runner = Callable[[Sequence[str], float], subprocess.CompletedProcess]


def _run(cmd: Sequence[str], timeout: float) -> subprocess.CompletedProcess:
    return subprocess.run(list(cmd), capture_output=True, text=True, timeout=timeout)


def nmcli_command(creds: WifiCredentials) -> List[str]:
    cmd = ["nmcli", "--wait", "40", "device", "wifi", "connect", creds.ssid]
    if creds.security != "nopass" and creds.password:
        cmd += ["password", creds.password]
    if creds.hidden:
        cmd += ["hidden", "yes"]
    return cmd


def join(creds: WifiCredentials, timeout: float = 45.0, runner: Runner = _run) -> bool:
    """Connect with NetworkManager. NetworkManager saves the network, so the
    device reconnects automatically after a reboot."""
    if not creds.supported:
        logger.warning("Wi-Fi QR: unsupported security %r", creds.security)
        return False
    if creds.hidden:
        # Make sure NetworkManager has scanned before connecting to a hidden network.
        try:
            runner(["nmcli", "device", "wifi", "rescan"], 10.0)
        except Exception:
            pass
    try:
        result = runner(nmcli_command(creds), timeout)
    except FileNotFoundError:
        logger.error("Wi-Fi QR: nmcli not found (NetworkManager is required)")
        return False
    except subprocess.TimeoutExpired:
        logger.error("Wi-Fi QR: connecting to %r timed out", creds.ssid)
        return False
    if result.returncode != 0:
        # nmcli's error text does not contain the password.
        logger.error("Wi-Fi QR: nmcli failed (%d): %s", result.returncode, (result.stderr or "").strip()[:200])
        return False
    logger.info("Wi-Fi QR: connected to %r", creds.ssid)
    return True
