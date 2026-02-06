# Tiqiaa USB IR Blaster Driver & Samsung Hotel Unlocker (Windows)

This project provides a stable Python driver and GUI for the **Tiqiaa (Tview)** USB IR Transceiver. It bypasses the need for the official "CaptureIR" software and allows for custom scripting, specifically designed for IT Managers to unlock **Samsung Hospitality TVs**.

## 🔌 Hardware Compatibility

**IMPORTANT:** Not all USB IR dongles are the same. This project **ONLY** works with the Tiqiaa chipset.

**How to verify your device:**
1.  Plug the dongle into an Android phone (USB-C).
2.  Install the official **ZaZa Remote** app.
3.  If the app automatically detects the dongle, **this project will work**.
4.  *Note:* Dongles from brands like **Ocrustar** or generic audio-jack IR blasters will **NOT** work with this driver.

When plugged into a PC, the device should identify in Device Manager as **"Tview"**.
Hardware ID is : `USB\VID_10C4&PID_8468` | `USB\VID_10C4&PID_8468&REV_0000`

<img width="408" height="465" alt="image" src="https://github.com/user-attachments/assets/41b6afbd-7f5f-47d3-a0e7-ff7d2dd7726a" />
<img width="401" height="462" alt="image" src="https://github.com/user-attachments/assets/dc0ffe21-a557-42b0-9b58-35921acec9d7" />
<img width="234" height="24" alt="image" src="https://github.com/user-attachments/assets/165b5bc2-8124-480e-9cf9-5660ebc57b08" />

---

## ⚙️ Installation & Setup

This script requires a specific USB driver setup on Windows to communicate with the hardware via Python.

### Step 1: Install Python
Ensure you have Python installed. You will need the following libraries:
```bash
pip install pyusb libusb

```

### Step 2: Driver Replacement (Zadig)

By default, Windows installs a HID driver (`hidusb`) which prevents Python from sending raw data. You must replace it with `WinUSB`.

1. Download **Zadig** (https://zadig.akeo.ie/).
2. Plug in the Tiqiaa IR Dongle.
3. Open Zadig and select **Options -> List All Devices**.
4. Select **"Tview"** (or the device with VID `10C4` and PID `8468`).
5. Change the driver on the right side to **WinUSB (v6.x.x)**.
6. Click **Replace Driver**.

<img width="595" height="286" alt="image" src="https://github.com/user-attachments/assets/b123c974-c8aa-47cf-b940-09bcaf1af1f5" />

### Step 3: Install DLLs

For the `libusb` library to function on Windows, you must manually place the driver DLL files.

1. Download the DLLs included in this repository (see the `dlls` folder) or source them from [libusb.info](https://libusb.info/).
2. Copy `libusb0.dll` and `libusbk.dll`.
3. Paste them into your **`C:\Windows\System32`** folder.

---

## 🛠️ Usage: Samsung Hospitality Unlocker

Included in this repo is `HotelModeSamsung_aio.py`. This is a standalone GUI tool designed for Hotel IT staff.

### Features

* **Zero-Config:** No external text files required. All IR codes are hardcoded into the script.
* **Universal Support:** Supports both Legacy Samsung TVs (Number Pad) and newer HBU8000 series (Smart Remote).
* **Stability:** Uses a custom "Idle-Sandwich" packet logic to prevent the dongle from freezing.

### How it Works

The Tiqiaa hardware is sensitive to packet timing. If you send data too fast, it crashes. This script implements a robust driver port that:

1. Sends the IR Data packet.
2. Forces the device into `IDLE` mode immediately after.
3. Waits `250ms` (the sweet spot for Samsung TVs) before sending the next command.

**The Macros:**

* **POWER:** Toggles TV Power.
* **UNLOCK (Old):** Sends `Mute` -> `1` -> `1` -> `9` -> `Enter`.
* **UNLOCK (New):** Sends `Mute` -> `Up` -> `Down` -> `Select`.

### Running the Tool

Simply run the script via Python:

```bash
python HotelModeSamsung_aio.py

```

**The Screenshot of the Tool:**

<img width="345" height="403" alt="image" src="https://github.com/user-attachments/assets/dbcc2b80-3246-48b4-ab16-a6d6caf2da63" />

*For compiled executable versions (.exe) that do not require Python installation, please check the **Releases** tab of this repository.*

---

## ⚠️ Known Issues & Troubleshooting

**Interference with Phone Cameras (Samsung S23 Ultra / Laser AF)**
If you are trying to record a video of this tool working, you may notice the TV does not respond.

* **The Cause:** Modern phones (like the S23 Ultra) use **Laser Autofocus** sensors that emit infrared light. This can interfere with or "jam" the IR receiver on the TV.
* **The Fix:** If you experience signal drops while recording, try moving your phone further away from the IR blaster/TV receiver.

---

## 👏 Credits & Acknowledgements

This project was built upon the hard work of the open-source community who reverse-engineered the original protocol.

* **Normanr:** [gitlab.com/normanr/tiqiaa-usb-ir-py](https://gitlab.com/normanr/tiqiaa-usb-ir-py)
* **XenRE:** Based on the post at [Habr.com](https://habr.com/ru/post/494800/) and code at [gitlab.com/XenRE/tiqiaa-usb-ir](https://gitlab.com/XenRE/tiqiaa-usb-ir).

```
