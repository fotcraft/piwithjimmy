# Connecting Readable to Wi-Fi with a QR code

Readable has no screen, so it joins Wi-Fi by reading a Wi-Fi QR code with its camera.

## For the user

1. Get the network's Wi-Fi QR code:
   - **Router sticker:** many routers (Cosmote, Vodafone, Nova and others) print one next to the password.
   - **Android phone:** Settings → Wi-Fi → tap the connected network → Share (shows a QR code).
   - **iPhone (iOS 18 and later):** Passwords app → Wi-Fi → the network → Show Network QR Code.
2. Hold Readable about 10 cm above the code and press the big button.
3. Readable says "Wi-Fi code found. Network:" and the network name.
4. Press the big button again to connect, or any other button to cancel.
   After 20 seconds without a press it cancels by itself.
5. Readable says "Connected to Wi-Fi" or "Could not connect".

The network is saved, so the device reconnects by itself after a restart.
The password is never spoken, logged or stored by Readable (NetworkManager stores it,
as for any saved network).

What doesn't work:
- **WEP networks** (old routers): Readable says the code is not supported.
- **Enterprise Wi-Fi** (username and password, as at universities): no QR code exists for these.
- **Very small codes from far away:** move closer. Codes under about 2 cm need to be held within ~10 cm.

## Device setup (once, when installing)

Readable connects through NetworkManager (`nmcli`), which Raspberry Pi OS Bookworm
and later use by default. The service runs as a systemd user service without a
desktop login, so it needs permission to add networks:

```bash
sudo cp deploy/50-readable-wifi.rules /etc/polkit-1/rules.d/
groups | grep -q netdev || sudo usermod -aG netdev $USER
sudo systemctl restart polkit
```

Test without the camera: `nmcli device wifi list` should work as your user without `sudo`.

Test a QR code from a photo (prints the network name, never the password, and does not connect):

```bash
python3 tools/wifi_qr_check.py router-sticker.jpg
```

Settings in `config.yaml` → `wifi_qr` (`enabled`, `confirm_timeout_seconds`,
`connect_timeout_seconds`).

## Notes

- Every scan checks for a Wi-Fi code before reading text. This adds about 0.1 s on
  a laptop; measure on the device and set `wifi_qr.enabled: false` if it is noticeable
  and the device is already set up.
- While connecting, the password is passed to `nmcli` on its command line, so another
  local user could briefly see it with `ps`. Readable is a single-user device, so this
  is acceptable here.
