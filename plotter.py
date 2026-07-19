#!/usr/bin/env python3
"""
============================================================
ECG Live Plotter - for the ESP32-S3 + AD8232 (SEN0213) firmware
============================================================
Reads raw 10-bit ADC values (0-1023) streamed one-per-line over
Serial at a fixed 200 Hz from the matching Arduino sketch, applies
a bandpass + notch filter tuned for that sample rate, and plots
both the raw and filtered ECG live, plus a running BPM estimate.

Fs = 200 Hz is a hard assumption baked into the filter design
below. If you change SAMPLE_INTERVAL_US on the firmware side,
update FS here to match, or the filters will be tuned wrong.

Usage:
    python ecg_plotter.py --port COM5
    python ecg_plotter.py --port /dev/ttyUSB0 --window 1000
    python ecg_plotter.py --port /dev/ttyUSB0 --window 2000 --mains 50

Options:
    --port      Serial port (required)
    --baud      Baud rate (default 115200, matches firmware)
    --window    Number of data points visible in the plot at once
                (default 1000, i.e. 5 seconds at 200 Hz)
    --mains     Mains hum frequency to notch out: 50 or 60 (default 50)
    --raw-only  Skip filtering, plot raw ADC values only

NOTE: Hobbyist/research tool, NOT a certified medical device.
Do not use for diagnosis or clinical decisions.
============================================================
"""

import argparse
import sys
from collections import deque

import numpy as np
import serial
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from scipy.signal import butter, sosfilt, sosfilt_zi, iirnotch, find_peaks

FS = 200.0  # Hz - must match SAMPLE_INTERVAL_US in the firmware


def build_filters(mains_hz: float):
    """Bandpass (0.5-40 Hz) isolates the ECG band and removes baseline
    wander + high-freq noise. Notch removes mains hum (50/60 Hz)."""
    nyq = FS / 2.0

    bp_sos = butter(4, [0.5 / nyq, 40.0 / nyq], btype="band", output="sos")
    bp_zi = sosfilt_zi(bp_sos)

    notch_b, notch_a = iirnotch(mains_hz, Q=30, fs=FS)

    return bp_sos, bp_zi, notch_b, notch_a


class ECGPlotter:
    def __init__(self, port, baud, window, mains_hz, raw_only):
        self.window = window
        self.raw_only = raw_only

        self.ser = serial.Serial(port, baud, timeout=1)

        self.raw_buf = deque([0] * window, maxlen=window)
        self.filt_buf = deque([0.0] * window, maxlen=window)
        self.x = np.arange(window)

        if not raw_only:
            self.bp_sos, self.bp_zi, self.notch_b, self.notch_a = build_filters(mains_hz)
            # rolling filter state, so each new sample is filtered in
            # real time without recomputing over the whole buffer
            self.notch_zi = np.zeros(max(len(self.notch_a), len(self.notch_b)) - 1)

        self.fig, self.axes = plt.subplots(
            2 if not raw_only else 1, 1, figsize=(11, 7), sharex=True
        )
        if raw_only:
            self.axes = [self.axes]

        self.fig.suptitle("ECG Live Monitor (ESP32-S3 / AD8232)")

        self.line_raw, = self.axes[0].plot(self.x, list(self.raw_buf), lw=0.8, color="tab:gray")
        self.axes[0].set_ylabel("Raw ADC (0-1023)")
        self.axes[0].set_ylim(0, 1023)
        self.axes[0].grid(True, alpha=0.3)

        if not raw_only:
            self.line_filt, = self.axes[1].plot(self.x, list(self.filt_buf), lw=1.0, color="tab:red")
            self.axes[1].set_ylabel("Filtered ECG")
            self.axes[1].grid(True, alpha=0.3)
            self.axes[1].set_xlabel(f"Samples (window = {window} pts, {window / FS:.1f} s @ {FS:.0f} Hz)")
            self.bpm_text = self.axes[1].text(
                0.02, 0.92, "BPM: --", transform=self.axes[1].transAxes,
                fontsize=12, color="tab:blue", fontweight="bold"
            )
        else:
            self.axes[0].set_xlabel(f"Samples (window = {window} pts, {window / FS:.1f} s @ {FS:.0f} Hz)")

        self.fig.tight_layout()

    def read_available_samples(self):
        """Drain whatever whole lines are currently waiting in the
        serial buffer, so the plot doesn't fall behind real time."""
        samples = []
        while self.ser.in_waiting:
            line = self.ser.readline().decode(errors="ignore").strip()
            if not line:
                continue
            try:
                samples.append(int(line))
            except ValueError:
                continue  # skip corrupted/partial lines
        return samples

    def filter_sample(self, value):
        # bandpass (stateful, streaming) then notch (stateful, streaming)
        filtered, self.bp_zi = sosfilt(self.bp_sos, [value], zi=self.bp_zi)
        notched, self.notch_zi = sosfilt_helper_notch(
            self.notch_b, self.notch_a, filtered, self.notch_zi
        )
        return notched[0]

    def estimate_bpm(self):
        data = np.array(self.filt_buf)
        if len(data) < FS:  # need at least ~1s of data
            return None

        # peaks (R-waves) should stand out well above the noise floor
        threshold = np.std(data) * 1.2
        min_distance = int(FS * 0.3)  # refractory: max ~200 BPM
        peaks, _ = find_peaks(data, height=threshold, distance=min_distance)

        if len(peaks) < 2:
            return None

        intervals = np.diff(peaks) / FS  # seconds between beats
        avg_interval = np.mean(intervals)
        if avg_interval <= 0:
            return None
        return 60.0 / avg_interval

    def update(self, _frame):
        samples = self.read_available_samples()
        for value in samples:
            self.raw_buf.append(value)
            if not self.raw_only:
                self.filt_buf.append(self.filter_sample(value))

        self.line_raw.set_ydata(self.raw_buf)

        if not self.raw_only:
            self.line_filt.set_ydata(self.filt_buf)
            filt_arr = np.array(self.filt_buf)
            if filt_arr.size:
                margin = max(np.ptp(filt_arr) * 0.15, 1)
                self.axes[1].set_ylim(filt_arr.min() - margin, filt_arr.max() + margin)

            bpm = self.estimate_bpm()
            self.bpm_text.set_text(f"BPM: {bpm:.0f}" if bpm else "BPM: --")
            return self.line_raw, self.line_filt, self.bpm_text

        return (self.line_raw,)

    def run(self):
        ani = animation.FuncAnimation(
            self.fig, self.update, interval=30, blit=False, cache_frame_data=False
        )
        plt.show()
        self.ser.close()


def sosfilt_helper_notch(b, a, x, zi):
    """Small wrapper so the notch (a plain IIR filter, not SOS) uses
    the same streaming/stateful pattern as the SOS bandpass above."""
    from scipy.signal import lfilter
    y, zf = lfilter(b, a, x, zi=zi)
    return y, zf


def main():
    parser = argparse.ArgumentParser(description="Live ECG plotter for ESP32-S3 + AD8232")
    parser.add_argument("--port", required=True, help="Serial port, e.g. COM5 or /dev/ttyUSB0")
    parser.add_argument("--baud", type=int, default=115200, help="Baud rate (default 115200)")
    parser.add_argument("--window", type=int, default=1000,
                         help="Number of data points shown in the plot window (default 1000 = 5s @ 200Hz)")
    parser.add_argument("--mains", type=float, default=50.0, choices=[50.0, 60.0],
                         help="Mains hum frequency to notch out (default 50)")
    parser.add_argument("--raw-only", action="store_true", help="Skip filtering, plot raw values only")
    args = parser.parse_args()

    if args.window < int(FS):
        print(f"Warning: --window {args.window} is under 1 second of data ({int(FS)} pts). "
              f"BPM detection needs at least ~1s to work.", file=sys.stderr)

    try:
        plotter = ECGPlotter(args.port, args.baud, args.window, args.mains, args.raw_only)
    except serial.SerialException as e:
        print(f"Could not open serial port '{args.port}': {e}", file=sys.stderr)
        sys.exit(1)

    plotter.run()


if __name__ == "__main__":
    main()