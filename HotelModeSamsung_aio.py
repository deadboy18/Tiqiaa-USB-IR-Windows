import time
import threading
import tkinter as tk
from tkinter import ttk, messagebox, Canvas
import usb.core
import usb.util
import struct

# ===================== CONFIGURATION =====================
VID, PID = 0x10C4, 0x8468
EP_OUT, EP_IN = 0x01, 0x81
CMD_IDLE, CMD_SEND, CMD_DATA = ord('L'), ord('S'), ord('D')
PACK_START, PACK_END = b"ST", b"EN"
TICK_US = 16
HOSPITALITY_DELAY = 0.25  # 250ms Delay

# ===================== SAMSUNG CODE GENERATOR =====================
class SamsungGen:
    """Generates raw pulses for Samsung32 Protocol on the fly."""
    @staticmethod
    def get_code(command, address=0x07):
        # Samsung32: Header(4500, 4500)
        pulses = [4500, -4500]
        
        def add_byte(val):
            for i in range(8):
                bit = (val >> i) & 1
                # Bit 1: 560, -1690 | Bit 0: 560, -560
                pulses.extend([560, -1690] if bit else [560, -560])

        add_byte(address)        # Address
        add_byte(address)        # Address (Repeated)
        add_byte(command)        # Command
        add_byte(~command & 0xFF) # Inverted Command (Checksum)
        
        # Stop bit
        pulses.extend([560, -45000]) 
        return pulses

# ===================== CODE DATABASE =====================
# 1. HARDCODED (Legacy Captured Data - Mute 1 1 9 Enter)
RAW_MUTE = [4544, -4448, 592, -1632, 592, -1632, 592, -1632, 592, -512, 592, -512, 592, -512, 592, -512, 592, -512, 592, -1648, 592, -1648, 592, -1632, 592, -512, 592, -512, 592, -512, 592, -512, 592, -512, 592, -1648, 592, -1648, 592, -1648, 592, -1648, 592, -528, 592, -512, 592, -512, 592, -528, 592, -528, 592, -512, 592, -528, 592, -512, 592, -1648, 592, -1648, 592, -1648, 592, -1648, 592, -512, 592, -512, 592, -512, 592, -512, 592, -45000]
RAW_1    = [4560, -4432, 592, -1632, 592, -1632, 592, -1632, 592, -512, 592, -512, 592, -512, 592, -512, 592, -512, 592, -1632, 592, -1632, 592, -1632, 592, -512, 592, -512, 592, -512, 592, -512, 592, -512, 592, -512, 592, -512, 592, -1632, 592, -512, 592, -512, 592, -512, 592, -512, 592, -512, 592, -1632, 592, -1632, 592, -512, 592, -1632, 592, -1632, 592, -1632, 592, -1632, 592, -1632, 592, -512, 592, -512, 592, -512, 592, -512, 592, -45000]
RAW_9    = [4528, -4464, 576, -1648, 576, -1648, 576, -1648, 576, -528, 576, -528, 576, -528, 576, -528, 576, -528, 576, -1648, 576, -1648, 576, -1648, 576, -528, 576, -528, 576, -528, 576, -528, 576, -528, 576, -528, 592, -1648, 592, -1648, 592, -1648, 592, -512, 592, -512, 592, -512, 592, -512, 592, -1648, 592, -512, 592, -512, 592, -512, 592, -1632, 592, -1632, 592, -1632, 592, -1632, 592, -512, 592, -512, 592, -512, 592, -512, 592, -45000]
RAW_ENT  = [4560, -4448, 592, -1632, 592, -1632, 592, -1632, 592, -512, 592, -512, 592, -512, 592, -512, 592, -512, 592, -1632, 592, -1632, 592, -1632, 592, -512, 592, -512, 592, -512, 592, -512, 592, -512, 592, -512, 592, -512, 592, -512, 592, -1632, 592, -512, 592, -1632, 592, -1632, 592, -512, 592, -1632, 592, -1632, 592, -1632, 592, -512, 592, -1632, 592, -512, 592, -512, 592, -1632, 592, -512, 592, -512, 592, -512, 592, -512, 592, -45000]

# 2. GENERATED (HBU8000 / Smart Remote)
# [cite_start]Hex Codes from Flipper Database [cite: 9, 10, 11]
CODE_POWER  = SamsungGen.get_code(0x02)
CODE_MUTE   = SamsungGen.get_code(0x0F) # Mute (Vol button press)
CODE_UP     = SamsungGen.get_code(0x60)
CODE_DOWN   = SamsungGen.get_code(0x61)
CODE_SELECT = SamsungGen.get_code(0x68)

SEQUENCES = {
    "OLD":  [RAW_MUTE, RAW_1, RAW_1, RAW_9, RAW_ENT],
    "NEW":  [CODE_MUTE, CODE_UP, CODE_DOWN, CODE_SELECT],
    "POWER": [CODE_POWER]
}

# ===================== DRIVER =====================
class TiqiaaDriver:
    def __init__(self, log_func, led_func):
        self.dev, self.log, self.set_led = None, log_func, led_func
        self._lock = threading.Lock()
        self.packet_idx, self.cmd_id = 0, 0

    def connect(self):
        self.log("Connecting...")
        self.set_led("gray")
        self.dev = usb.core.find(idVendor=VID, idProduct=PID)
        if not self.dev:
            self.log("Device Not Found")
            return False
        
        try:
            if self.dev.is_kernel_driver_active(0): self.dev.detach_kernel_driver(0)
        except: pass 

        try:
            self.dev.set_configuration()
            self._rec_response(100)
            if self._send_cmd(CMD_IDLE) and self._send_cmd(CMD_SEND):
                self.log("Ready.")
                self.set_led("#00ff00")
                return True
        except: self.set_led("red"); return False

    def _rec_response(self, timeout=500):
        try:
            buf = self.dev.read(EP_IN, 64, timeout=timeout)
            if len(buf) < 5: return False
            _, _, _, total, cur = struct.unpack("<BBBBB", buf[:5])
            while cur < total:
                buf = self.dev.read(EP_IN, 64, timeout=timeout)
                cur = buf[4]
            return True
        except: return False

    def _send_cmd(self, cmd_type, payload=b""):
        self.cmd_id = (self.cmd_id % 0x7F) + 1
        inner = bytes([self.cmd_id, cmd_type]) + payload
        data = PACK_START + inner + PACK_END
        total = len(data)
        frag_cnt = (total + 55) // 56
        self.packet_idx = (self.packet_idx % 15) + 1
        
        for i in range(frag_cnt):
            frag = data[i*56 : (i+1)*56]
            hdr = struct.pack("<BBBBB", 0x02, len(frag)+3, self.packet_idx, frag_cnt, i+1)
            try: self.dev.write(EP_OUT, hdr + frag, timeout=1000)
            except: return False
        return self._rec_response()

    def send_pulses(self, pulses):
        if not self.dev: return
        out = []
        for v in pulses:
            is_pulse = v > 0
            ticks = abs(int(round(v / TICK_US)))
            if ticks == 0: ticks = 1
            while ticks > 0:
                chunk = min(0x7F, ticks)
                ticks -= chunk
                out.append((0x80 if is_pulse else 0x00) | chunk)
        
        with self._lock:
            self.set_led("orange")
            if not self._send_cmd(CMD_DATA, b'\x00' + bytes(out)): self.connect()
            time.sleep(0.05)
            self._send_cmd(CMD_IDLE)
            self.set_led("#00ff00")

# ===================== GUI =====================
class HotelUnlockerGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Samsung Hotel Tv Unlocker (Universal)")
        self.geometry("320x350") 
        self.resizable(False, False)
        
        self.ir = TiqiaaDriver(self.log, self.set_led)
        self.setup_ui()
        self.after(500, lambda: threading.Thread(target=self.ir.connect, daemon=True).start())

    def log(self, msg): self.status_var.set(msg)
    def set_led(self, color): self.led.itemconfig(self.led_id, fill=color)

    def setup_ui(self):
        # Header
        frame_top = tk.Frame(self, pady=10)
        frame_top.pack(fill="x")
        self.led = Canvas(frame_top, width=20, height=20, highlightthickness=0)
        self.led_id = self.led.create_oval(2,2,18,18, fill="gray")
        self.led.pack(side="left", padx=15)
        self.status_var = tk.StringVar(value="Initializing...")
        tk.Label(frame_top, textvariable=self.status_var, fg="gray", font=("Arial", 9)).pack(side="left")

        # --- POWER ---
        tk.Button(self, text="POWER (Toggle)", bg="#ffcdd2", font=("Arial", 10, "bold"), 
                  command=lambda: self.run("POWER"), height=2).pack(fill="x", padx=20, pady=5)

        ttk.Separator(self, orient='horizontal').pack(fill='x', padx=20, pady=10)

        # --- OLD TV ---
        tk.Label(self, text="Standard Models (Number Pad)", fg="#666").pack()
        tk.Button(self, text="UNLOCK (Mute-1-1-9-Enter)", bg="#fff9c4", font=("Arial", 11), 
                  command=lambda: self.run("OLD"), height=2).pack(fill="x", padx=20, pady=2)

        # --- NEW TV ---
        tk.Label(self, text="HBU8000 / Smart Remote", fg="#666").pack(pady=(10,0))
        tk.Button(self, text="UNLOCK (Mute-Up-Dn-Sel)", bg="#b3e5fc", font=("Arial", 11), 
                  command=lambda: self.run("NEW"), height=2).pack(fill="x", padx=20, pady=2)

    def run(self, key):
        def _seq():
            self.log(f"Sending {key}...")
            seq = SEQUENCES[key]
            for pulses in seq:
                self.ir.send_pulses(pulses)
                time.sleep(HOSPITALITY_DELAY)
            self.log("Done."); time.sleep(1); self.log("Ready.")
        threading.Thread(target=_seq, daemon=True).start()

if __name__ == "__main__":
    HotelUnlockerGUI().mainloop()