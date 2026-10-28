# MOONDROP Pudding (MD-TWS-056) control protocol

Everything here was verified against real hardware — a MOONDROP Pudding on
firmware **3.5.6**, over classic Bluetooth RFCOMM from Linux (BlueZ 5.87).

If you are writing your own client, read [§2](#2-jieli-rcsp-authentication-first)
first. It is the part every other write-up gets wrong, and the reason naive GAIA
frames are silently ignored.

---

## 1. Transport

| | |
|---|---|
| Profile | Serial Port (SPP), UUID `00001101-0000-1000-8000-00805f9b34fb` |
| RFCOMM channel | **1** |
| Socket | `AF_BLUETOOTH` / `SOCK_STREAM` / `BTPROTO_RFCOMM` |

The earbuds also accept connections on RFCOMM channels 10–13, but those never
answer anything. Channel 1 is the only one that talks.

The earbuds expose a separate BLE interface (advertised as `TWS-056-BLE`,
manufacturer ID `0x05D6`). It is **not needed** and was never made to work here —
it stops advertising while a classic audio link is up. Control goes over RFCOMM.

---

## 2. Jieli RCSP authentication (first!)

The channel carries **two stacked protocols**. Before anything else, a Jieli
RCSP handshake must succeed. Until it does, GAIA frames get no reply at all —
not an error frame, just silence. This is what makes the protocol look broken.

### 2.1 Frame shape

Plain bytes, no header:

```
host → buds    00 + <16 random bytes>        (challenge)
buds → host    01 + <16 bytes>               (respond(challenge))
host → buds    02 'p' 'a' 's' 's'
buds → host    00 + <16 random bytes>        (the buds' own challenge)
host → buds    01 + <16 bytes>               (respond(buds' challenge))
buds → host    02 'p' 'a' 's' 's'            (confirmed)
```

`respond()` is Jieli's published cipher, from `jl_auth_2.0.0.js` in
[Jieli-Tech/WeChat-Mini-Program-OTA](https://github.com/Jieli-Tech/WeChat-Mini-Program-OTA).
`pudding.py` contains a Python port (`jl_respond`). The values it produces match
what the earbuds return, byte for byte.

### 2.2 Practical notes

- **The final `02 'p' 'a' 's' 's'` is not always sent.** Do not block on it.
  Send the two rounds, then probe with a cheap GAIA query (firmware version) and
  treat a valid reply as proof the link is up. This is what `pudding.py` does.
- The earbuds sometimes push a GAIA frame during the handshake. Skip anything
  starting with `FF 04` (see [§3](#3-gaia-frames)) while parsing the auth stream.
- A fresh socket needs a few hundred milliseconds before it accepts writes.

---

## 3. GAIA frames

Once authenticated, the same channel speaks Qualcomm GAIA:

```
FF 04 [Len:2 BE] [Seq] [Vendor=0x1D] [Feature] [Cmd] [Payload...]
```

- `Len` counts the **payload only** — not vendor, feature or cmd.
- `Seq` increments per frame.
- The response's Feature is the request's Feature with bit 0 set
  (`Feature | 0x01`).

There is no checksum and no trailing byte. Some write-ups mention a stray byte
after the payload (`0x9A`, `0x29`, `0x40`, `0x86`); it appears in phone-side
captures but is **not required** and the earbuds ignore it.

### 3.1 Feature numbers are doubled

This is the second trap. Pudding uses **twice** the standard GAIA feature id:

| Function | Standard GAIA | Pudding |
|---|---|---|
| Battery | `0x0D` (13) | **`0x1A`** |
| DAC gain | `0x0F` (15) | **`0x1E`** |
| Codec / LDAC | `0x10` (16) | **`0x20`** |
| One-two (multipoint) | `0x14` (20) | **`0x28`** |
| ANC V2 | `0x20` (32) | **`0x40`** |

Sending the standard id produces no response at all. `pudding.py` was stuck on
multipoint for a long time purely because it was probing `0x14`.

The device confirms this itself: `Feature 0x00 / Cmd 0x01` (supported features)
returns a list of `(feature, version)` pairs whose ids are the **standard** ones —
`00 00 02 01 01 05 01 0D 01 0E 01 0F 01 10 01 13 01 14 01 16 01 20 01`.
Read them as `0x00, 0x01, 0x05, 0x0D, 0x0E, 0x0F, 0x10, 0x13, 0x14, 0x16, 0x20`
and multiply by two to get the ids you actually talk to.

---

## 4. Commands

### 4.1 Device info

| Feature | Cmd | Payload | Response |
|---|---|---|---|
| `0x00` | `0x01` | — | supported feature list (see above) |
| `0x00` | `0x05` | — | firmware version, ASCII (`3.5.6`) |
| `0x00` | `0x0C` | param id | config value, 4 bytes |
| `0x28` | `0x05` | — | `00` + 6-byte MAC + ASCII name of the connected host |
| `0x28` | `0x06` | — | `00` + 6-byte MAC of the *second* device slot (`FF`×6 = empty) |

### 4.2 Battery

Query `0x1A` / `0x01`, payload `01 02`.

Response payload is `(id, level)` pairs:

```
01 58 02 62 03 64
│  │  │  │  │  └── case  100%
│  │  │  │  └───── id 3 = charging case
│  │  │  └──────── right   98%
│  └──┴─────────── id 2 = right earbud
```

`id 1` = left, `id 2` = right, `id 3` = case. `0xFF` means "not readable"
(e.g. an earbud sitting in the case). The earbuds also push this unsolicited as
`0x1A` / `0x81` when the level changes.

### 4.3 Noise control (ANC V2)

| Feature | Cmd | Payload |
|---|---|---|
| `0x40` | `0x03` | — (query, returns 1 byte) |
| `0x40` | `0x04` | 1 byte mode (set) |
| `0x40` | `0x29` | — (available modes) |

| Value | Mode |
|---|---|
| `0x00` | off |
| `0x01` | adaptive |
| `0x02` | transparency |
| `0x03` | wind noise reduction |
| `0x04` | noise cancelling (base) |

`0x29` returns `01 01 01 01 00` — four of the five modes available, in the order
off / adaptive / transparency / wind / noise.

**Setting has no ACK you can trust.** The earbuds reply to the set frame, but a
read immediately afterwards often still returns the old mode. Wait ~1.5 s and
read back. The earbuds also play a voice prompt while switching.

### 4.4 DAC gain

| Feature | Cmd | Payload |
|---|---|---|
| `0x1E` | `0x01` | — (query) |
| `0x1E` | `0x02` | 1 byte: `00` high / `01` mid / `02` low |

Note the order is inverted relative to intuition — `00` is the loudest.

### 4.5 Codec / LDAC

| Feature | Cmd | Payload |
|---|---|---|
| `0x20` | `0x05` | — (query LDAC, `01` on / `00` off) |
| `0x20` | `0x06` | 1 byte: `01` on / `00` off |

**Writing this drops the Bluetooth link.** The earbuds restart their audio
stack, the RFCOMM socket dies, and audio reconnects a few seconds later. That is
expected, not a bug — catch the exception and reconnect.

> Caveat: toggling this bit on the earbuds is **not sufficient** to actually use
> LDAC on Linux. See [§6](#6-known-limitations).

### 4.6 Multipoint ("one-two")

| Feature | Cmd | Payload |
|---|---|---|
| `0x28` | `0x01` | — (query, `01` on / `00` off) |
| `0x28` | `0x02` | 1 byte: `01` on / `00` off |

`0x28` / `0x05` and `0x28` / `0x06` read the two connection slots (see §4.1).

---

## 5. Quirks worth knowing

- **Connection churn.** Opening and closing RFCOMM sockets rapidly makes the
  earbuds refuse new connections for a few hundred milliseconds. Retry with
  backoff (the CLI uses 4 attempts at 0.8 / 1.5 / 2.2 s).
- **Do not tear down the classic link to try BLE.** The earbuds can land in an
  unconnectable state (`br-connection-page-timeout`) and need a power cycle.
- **Audio link and control link are independent.** Reading state while music
  plays is fine.
- **One controller at a time.** If the phone app holds the control channel, the
  earbuds ignore everyone else. Turning off "dual device connection" on the
  phone side helps.

---

## 6. Known limitations

**LDAC cannot actually be negotiated from Linux with this earbud.**

The earbud's A2DP endpoint capabilities do not contain Sony's LDAC vendor id
`0x0000012D` — it never advertises LDAC over SDP to this host. PipeWire therefore
only offers SBC / SBC-XQ / AAC, and the connection runs on AAC.

The GAIA `0x20` / `0x06` switch is a *permission bit inside the earbuds*, not a
codec announcement. Flipping it does not make Linux select LDAC. `libldac` and
`libspa-codec-bluez5-ldac.so` being installed does not help either — A2DP codec
selection is a two-sided negotiation.

Whether the earbud advertises LDAC when paired to the phone app is untested here.
If you need LDAC on a desktop, a transmitter that advertises it itself is the
practical route.

---

## 7. Sources

Standing on the shoulders of:

- [luoning77/moondrop-gaia-protocol](https://github.com/Luoning77/moondrop-gaia-protocol) —
  Pudding-specific reverse engineering from MOONDROP Link btsnoop captures
  (firmware 3.5.2). Source of the GAIA command table.
- [lingbai-rong/PuddingPods](https://github.com/lingbai-rong/PuddingPods) —
  LSPosed module for the same model. Confirmed the ANC V2 feature family and the
  gain / LED commands.
- [Desmond123-arch/spacebuds-ctl](https://github.com/Desmond123-arch/spacebuds-ctl) —
  Python port of the Jieli RCSP auth cipher.
- [Karthik-Unni/libboat](https://github.com/Karthik-Unni/libboat) —
  Jieli RCSP framing and `GetSysInfo` / `SetSysInfo` structure.
- [FEAKEuser/moondrop-control](https://github.com/FEAKEuser/moondrop-control) —
  KDE Plasma widget. Its feature enum is what exposed the doubling.
- [silverpoetry/HyperEars](https://github.com/silverpoetry/HyperEars) —
  Pudding protocol notes, ANC state semantics.

None of them document the RCSP-authentication-then-GAIA stacking, which is why
they all report the model as either "untested" or "GAIA over SPP works" without
explaining why plain frames do nothing.
