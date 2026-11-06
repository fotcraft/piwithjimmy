"""Check whether a photo contains a Wi-Fi QR code the device can read.

    python3 tools/wifi_qr_check.py photo.jpg

Prints the network name and security type. Never prints the password and
never connects; use it to test QR codes from routers and phones.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2  # noqa: E402

from app.wifi_qr import find_wifi_qr  # noqa: E402


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    image = cv2.imread(sys.argv[1])
    if image is None:
        print(f"Cannot open {sys.argv[1]}")
        return 1
    creds = find_wifi_qr(image)
    if creds is None:
        print("No Wi-Fi QR code found.")
        return 1
    print(f"Network:  {creds.ssid}")
    print(f"Security: {creds.security}{' (supported)' if creds.supported else ' (NOT supported)'}")
    print(f"Hidden:   {'yes' if creds.hidden else 'no'}")
    print(f"Password: {'present' if creds.password else 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
