# Readable wiring

This page covers the prototype built from modules (PowerBoost, MAX98357A
breakout). For the production build, the custom IO board replaces the power,
audio and page-light wiring: see `IO_BOARD.md`.

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
- `/boot/firmware/config.txt`: add `dtoverlay=max98357a,no-sdmode` and set `dtparam=audio=off`.
  (`no-sdmode` because the amplifier's SD pin is not wired to a GPIO; without it the
  driver toggles GPIO4.)
- Leave GAIN unconnected (9 dB). Tie it to GND for 12 dB if the voice is too quiet.
- Speaker: 40 mm, 8 Ω 2 W (Same Sky CMS-4049-28S). It has spring contacts instead of
  solder tags: tin the contacts and solder thin wires to them quickly, or press them
  against two pads. Into 8 Ω the amplifier gives about 1.8 W, so it cannot overdrive it.

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
- The Akyga cell comes with a 2.54 mm plug, not the PowerBoost's JST-PH. Cut it off and
  solder a JST-PH 2-pin lead on, one wire at a time so they never touch. **Check polarity
  against the + and − marks next to the PowerBoost's battery socket before plugging in**:
  lead colours are not a standard.
- On/off: slide switch between PowerBoost EN and GND (EN low = off; charging still works).
- Charging: Adafruit 4090 USB-C breakout in the enclosure wall, VBUS and GND wired to the
  PowerBoost USB 5 V / GND pads (the PowerBoost's own micro-USB stays inside).
- **USB-C needs two 5.1 kΩ resistors**: one from CC1 to GND and one from CC2 to GND
  on the breakout. Without them a USB-C to USB-C charger supplies no power (a USB-A
  to USB-C cable still works). Measure CC1 to GND first: if it already reads about
  5.1 kΩ, the board has them and you can skip this.
- Use thicker wire (0.5 mm² / 20 AWG) for battery, 5 V and GND between the PowerBoost
  and the header. The 28 AWG ribbon is for buttons, LEDs and I2S only.
- **Check for brown-outs.** The PowerBoost 1000C is rated 1 A continuous; the
  CM5 can briefly draw more during Wi-Fi bursts and camera capture. After a few
  scans run `vcgencmd get_throttled`. Anything other than `throttled=0x0` means
  under-voltage: move to a 5 V boost-charger rated 2.5 A or more.

## Camera

Camera Module 3 on the CM5-NANO-B CSI connector (22-pin FPC). Follow the
Waveshare CM5-NANO-B wiki for the `dtoverlay` line for that port, then check
with `rpicam-hello --list-cameras`.
