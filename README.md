# MOONDROP Pudding on Linux

Control a **MOONDROP Pudding** (`MD-TWS-056`) true-wireless earbud from Linux —
no phone app required.

Two pieces, usable independently:

- **`pudding.py`** — a dependency-free Python CLI that talks to the earbuds over
  Bluetooth RFCOMM. Reads and writes noise control, DAC gain, multipoint, LDAC,
  and battery.
- **Dux Shell (DMS) plugin** — a bar widget with a control panel. It hides itself
  when the earbuds are not connected.

English | [简体中文](README.zh-CN.md)

```
$ ./pudding.py status
电量    左 76%  右 84%
固件    3.5.6
降噪    noise
增益    high
多点    关
LDAC    关
```

## Features

| | |
|---|---|
| Noise control | off / adaptive / transparency / wind reduction / noise cancelling |
| DAC gain | high / mid / low |
| Multipoint | on / off (two-device connection) |
| LDAC | on / off (see [limitations](#limitations)) |
| Battery | left / right / charging case |
| Info | firmware version |

Verified on **firmware 3.5.6** against real hardware, on Arch Linux with BlueZ 5.87.

## Install

### The DMS plugin

```bash
git clone https://github.com/maxlen727/MOONDROP-PUDDING-dux-shell-plugin.git
cd MOONDROP-PUDDING-dux-shell-plugin
./install.sh
```

That copies the plugin to `~/.config/dms/plugins/puddingControl/`, enables it,
adds it to the bar, and restarts DMS. Use `./install.sh --no-bar` to leave the
bar layout alone, or `./install.sh --uninstall` to remove everything.

Requires [Dux Shell](https://github.com/duxlabs-dev/dux-shell) 2.x. The CLI it
ships is self-contained, so the plugin works out of the box.

**Left click** opens the control panel. **Right click** cycles noise control
(ANC → transparency → off).

### The CLI on its own

```bash
./pudding.py status            # battery + firmware + ANC + gain + multipoint + LDAC
./pudding.py battery
./pudding.py anc               # read current mode
./pudding.py anc transparency  # off / adaptive / transparency / wind / noise
./pudding.py gain high         # high / mid / low
./pudding.py multipoint on     # on / off / toggle
./pudding.py codec ldac        # ldac / sbc / toggle
./pudding.py -j status         # JSON, for scripts
```

No dependencies beyond the Python standard library — it uses `socket`'s
`AF_BLUETOOTH` directly.

The earbuds must be paired, powered on, and **not currently held by the phone
app** (turn off "dual device connection" on the phone if state reads fail).

## Requirements

- Linux with BlueZ
- Python 3.8+
- For the widget: Dux Shell 2.x

## How it works

The earbuds stack **two protocols** on one RFCOMM channel, in this order:

1. **Jieli RCSP authentication** — a challenge/response handshake using Jieli's
   published cipher. Until it succeeds, the earbuds ignore everything else
   silently.
2. **Qualcomm GAIA frames** — `FF 04 <len> <seq> 1D <feature> <cmd> <payload>`.

A third trap: Pudding uses **twice** the standard GAIA feature ids. Multipoint is
`0x28`, not `0x14`; battery is `0x1A`, not `0x0D`.

Full protocol notes, including every command and the byte-level auth sequence:
**[docs/PROTOCOL.md](docs/PROTOCOL.md)**.

## Limitations

**LDAC does not actually work on Linux with this earbud.**

The earbud never advertises Sony's LDAC vendor id (`0x0000012D`) in its A2DP
endpoint capabilities, so PipeWire only offers SBC / SBC-XQ / AAC and the link
runs on AAC. The GAIA LDAC switch is a permission bit inside the earbuds, not a
codec announcement — flipping it does not make Linux negotiate LDAC.

Other notes:

- Switching LDAC **drops the Bluetooth link** for a few seconds while the earbuds
  restart their audio stack. Expected.
- Rapidly opening/closing connections makes the earbuds refuse new ones for a
  few hundred milliseconds. The CLI retries with backoff.
- Do **not** disconnect the classic link to experiment with BLE — the earbuds can
  land in an unconnectable state and need a power cycle.
- Noise-control changes take ~1.5 s to apply; a read immediately after a write
  may return the old value.

## Troubleshooting

| Symptom | Cause |
|---|---|
| `the earbuds are not connected` | Powered off or in the case. Take them out and connect them in your Bluetooth settings. |
| `the Bluetooth channel is busy` | A previous connection has not been released yet. Wait a few seconds; if it persists, disconnect and reconnect the earbuds. |
| `authentication was rejected` | The phone app holds the control channel. Turn off "dual device connection" on the phone, or quit the app. |
| Widget does not appear | The earbuds are not connected (that is by design). Also check Settings → Plugins that the plugin is enabled. |
| Mode change seems ignored | Noise control takes ~1.5 s to apply. Read back after waiting. |

## Credits

The protocol was not documented anywhere in one piece. This builds on:

- [luoning77/moondrop-gaia-protocol](https://github.com/Luoning77/moondrop-gaia-protocol) — Pudding GAIA command table
- [lingbai-rong/PuddingPods](https://github.com/lingbai-rong/PuddingPods) — LSPosed module for the same model
- [Desmond123-arch/spacebuds-ctl](https://github.com/Desmond123-arch/spacebuds-ctl) — Jieli RCSP auth cipher, ported to Python
- [Karthik-Unni/libboat](https://github.com/Karthik-Unni/libboat) — Jieli RCSP framing
- [FEAKEuser/moondrop-control](https://github.com/FEAKEuser/moondrop-control) — the feature enum that revealed the id doubling
- [silverpoetry/HyperEars](https://github.com/silverpoetry/HyperEars) — Pudding protocol notes

## License

MIT. Not affiliated with MOONDROP. Use at your own risk — these are undocumented
commands and the vendor can change them at any time.
