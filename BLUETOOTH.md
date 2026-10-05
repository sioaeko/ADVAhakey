# Bluetooth-only voice: experimental

`cardputer-adv-ble` / `1.5.0-ble` provides a private GATT microphone service alongside the existing BLE HID keyboard. It does not implement a Bluetooth headset profile. Windows needs the companion; Android/iPhone voice clients are not implemented.

## Transport

- Wi-Fi code is disabled in this build. Stored Wi-Fi configuration is not erased.
- Capture: 16 kHz, 16-bit mono, two 40 ms buffers.
- BLE: independent 20 ms IMA ADPCM blocks, reconstructed to PCM on the PC. ADPCM is lossy. The existing USB and Wi-Fi paths retain PCM.
- Each compressed AVP1 frame is 182 bytes, fitting one notification at MTU 185. Framed traffic falls from about 33.9 KB/s to 9.1 KB/s.
- A 64-frame firmware queue separates capture from transmission. Errors discard incomplete recordings rather than save them as successful takes.
- The receiver checks CRC and sequence, bounds queued audio, clears stale data on reconnect and leases the microphone to one companion process.
- GATT control and notification subscription require an encrypted paired connection. Pairing uses BLE Just Works; it does not provide an authenticated passkey exchange.

Service: `c0a17340-7d8e-4a15-9f4a-2b0c73a10000`; audio/control characteristics replace `7340` with `7341`/`7342` respectively. AVP1 types 1/2/3/4 are START/PCM/END/ABORT; type 5 is a 163-byte independent ADPCM block: signed little-endian predictor, initial step index and 319 low-nibble-first codes. The unused final high nibble must be zero.

Bleak is pinned to 2.1.1. `tools/ble_windows.py` supplies a known numeric Windows address because an already-connected HID may not advertise. It uses an internal backend field; upgrades require a real Windows connection check. Service-filtered discovery avoids a GATT cache error observed after firmware upgrades.

## Verification status

Version 1.5.0 adds an optional, capability-negotiated `AVD1` dashboard on the
existing encrypted control characteristic. Packets include the current owner's
32-bit token and a bounded 6–34 byte state payload; wrong-owner writes are ignored.
`AVS1` flag bit 1 advertises this feature and the high byte reports microphone errors.
The display expires after ten seconds without an accepted update. Legacy 1.4.x
firmware continues to work with the companion without dashboard writes.
The PC app is documented in [COMPANION.md](COMPANION.md).

During development, firmware boot, Wi-Fi disabled state, MTU 185, encrypted voice subscription, heartbeats and clean receiver shutdown were checked on an ADV. Unit tests exercise the real native C++ encoder against Python 3.12's independent `audioop` reference and verify the receiver's error handling.

Versions 1.4.0/1.4.1 failed physical recording attempts through capture starvation and a full transmit queue. Version 1.4.2 introduced ADPCM as the mitigation. **A successful physical recording on 1.4.2, unplugged battery operation, simultaneous typing, range and battery life have not been verified.** Keep this feature experimental until those checks are completed.

The Codex bridge can discard buffered invalid audio but cannot retract sound already delivered to a live dictation session. Its shortcut-based UI control also remains experimental.

## Start

1. Build/install for the actual target partition layout as described in the README.
2. Pair `AhaKey ADV` in Windows Bluetooth settings.
3. Run `start-voice-bluetooth.cmd`; wait for `Bluetooth audio ready`.
4. Focus a text field. Tap G0 to start and again to stop.

Only one voice receiver should run at a time. The ordinary keyboard does not require the speech model; the microphone receiver does.
