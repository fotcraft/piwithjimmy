# Readable wiring

All GPIO numbers are BCM. Pins are configurable in `config.yaml` (`hardware`).

## Pin map

| Function | GPIO | Header pin | Wiring |
| --- | --- | --- | --- |
| Scan (large front button) | 17 | 11 | Switch between pin and GND |
| Repeat (hold = help) | 27 | 13 | Switch between pin and GND |
| Volume + | 22 | 15 | Switch between pin and GND |
| Volume − | 23 | 16 | Switch between pin and GND |
| Language | 24 | 18 | Switch between pin and GND |
| Status LED (front) | 25 | 22 | GPIO → 330 Ω → LED anode, cathode → GND |
| Illumination LED (back, next to camera) | 16 | 36 | Through an NPN transistor, see below |
| Low battery (PowerBoost LBO) | 26 | 37 | Through a Schottky diode, see below |
| I2S BCLK → MAX98357A BCLK | 18 | 12 | Direct |
| I2S LRCLK → MAX98357A LRC | 19 | 35 | Direct |
| I2S DOUT → MAX98357A DIN | 21 | 40 | Direct |
| 5 V in (from PowerBoost) | | 2, 4 | PowerBoost 5V out |
| GND | | 6, 9, 14, 20, 25, 30, 34, 39 | Common ground |

The buttons use the Pi's internal pull-ups, so no resistors are needed.

## Audio: MAX98357A I2S amplifier

- Vin → 5 V, GND → GND, BCLK/LRC/DIN as above, speaker on the + / − terminals.
- `/boot/firmware/config.txt`: add `dtoverlay=max98357a` and set `dtparam=audio=off`.
- Leave GAIN unconnected (9 dB). Tie it to GND for 12 dB if the voice is too quiet.

## Illumination LED

A white LED needs ~20 mA, more than a GPIO pin should source.

- GPIO16 → 1 kΩ → base of an NPN transistor (2N2222 / BC547).
- Emitter → GND.
- 5 V → 100 Ω → LED anode, LED cathode → collector.

## Low-battery signal (PowerBoost 1000C LBO)

LBO is pulled up to the battery voltage (up to 4.2 V), which is too high for a
3.3 V GPIO. Put a Schottky diode (BAT85 / 1N5817) between them:

- Diode anode → GPIO26, cathode (band) → LBO.
- The internal pull-up holds GPIO26 high. When the battery drops below ~3.2 V,
  LBO pulls low, the diode conducts and the device says "Battery low".

## Power

- LiPo → PowerBoost 1000C BAT. PowerBoost 5V/GND → header pins 2/4 and GND.
- On/off: slide switch between PowerBoost EN and GND (EN low = off; charging still works).
- Charging: USB-C panel breakout in the enclosure wall, wired to the PowerBoost
  USB 5 V / GND pads (the PowerBoost's own micro-USB stays inside).
- **Check for brown-outs.** The PowerBoost 1000C is rated 1 A continuous; the
  CM5 can briefly draw more during Wi-Fi bursts and camera capture. After a few
  scans run `vcgencmd get_throttled`. Anything other than `throttled=0x0` means
  under-voltage: move to a 5 V boost-charger rated 2.5 A or more.

## Camera

Camera Module 3 on the CM5-NANO-B CSI connector (22-pin FPC). Follow the
Waveshare CM5-NANO-B wiki for the `dtoverlay` line for that port, then check
with `rpicam-hello --list-cameras`.
