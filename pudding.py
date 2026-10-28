#!/usr/bin/env python3
"""
pudding.py — 在 Linux 上控制 MOONDROP PUDDING (MD-TWS-056) 真无线耳机

原理
----
耳机在 RFCOMM 通道 1 上跑两套协议，顺序不能错：

1. 先做**杰理 RCSP 认证**（`00` + 16 字节挑战 → 回 `01` + 16 字节应答，
   两轮 + `02 pass`）。不过认证，后面发什么都不会有回应。
2. 认证通过后，同一个通道上就能收发**高通 GAIA 帧**：

       FF 04 [Len:2 BE] [Seq] [Vendor=0x1D] [Feature] [Cmd] [Payload]

   Len 只算 payload（不含 vendor/feature/cmd）。

用法
----
    ./pudding.py status             # 电量 + 固件 + ANC + 增益
    ./pudding.py battery            # 只读电量
    ./pudding.py anc                # 读当前降噪模式
    ./pudding.py anc off            # 关闭
    ./pudding.py anc adaptive       # 自适应降噪
    ./pudding.py anc transparency   # 通透
    ./pudding.py anc wind           # 抗风噪
    ./pudding.py anc noise          # 基础降噪
    ./pudding.py gain high|mid|low  # 输出增益

不加 -a 时自动找已配对、已连接的水月雨耳机。
"""

import argparse
import json
import os
import socket
import sys
import time

VENDOR = 0x1D
RFCOMM_CHANNEL = 1

# ---- 杰理 RCSP 认证（jl_auth_2.0.0.js 的 Python 移植） --------------------

_SEED = [17, 34, 51, 51, 34, 17]
_KEY = [6, 119, 95, 135, 145, 141, 212, 35, 0, 93, 241, 216, 207, 12, 20, 43]
_A = [
    [119, 241, 86, 36, 126, 71, 27, 134, 189, 112, 142, 30, 59, 115, 22, 3],
    [100, 172, 40, 90, 201, 179, 55, 197, 10, 16, 183, 163, 186, 177, 151, 70],
    [61, 5, 220, 102, 110, 246, 154, 248, 13, 88, 149, 103, 198, 170, 171, 236],
    [160, 104, 155, 150, 212, 235, 191, 67, 73, 54, 233, 106, 137, 216, 195, 138],
    [148, 99, 153, 188, 123, 190, 193, 34, 187, 92, 113, 213, 31, 146, 87, 93],
    [143, 68, 65, 29, 81, 230, 64, 23, 251, 253, 25, 50, 52, 184, 97, 42],
    [202, 35, 111, 218, 57, 247, 162, 1, 127, 214, 49, 231, 222, 128, 4, 221],
    [44, 89, 130, 175, 168, 224, 15, 205, 161, 18, 62, 48, 209, 28, 208, 58],
    [51, 114, 46, 79, 144, 2, 19, 6, 117, 206, 135, 194, 239, 178, 173, 125],
    [56, 21, 225, 82, 159, 122, 108, 47, 39, 196, 226, 129, 169, 207, 141, 192],
    [215, 223, 255, 96, 118, 20, 140, 94, 85, 9, 228, 8, 199, 66, 32, 252],
    [210, 80, 145, 217, 76, 98, 158, 232, 185, 166, 249, 26, 0, 33, 11, 250],
    [53, 156, 78, 75, 105, 72, 203, 14, 200, 164, 91, 234, 132, 7, 180, 24],
    [244, 174, 107, 219, 167, 204, 63, 139, 74, 12, 60, 37, 229, 84, 77, 69],
    [131, 237, 17, 240, 176, 83, 147, 242, 116, 38, 181, 157, 109, 124, 243, 45],
    [241, 86, 36, 126, 71, 27, 134, 189, 112, 142, 30, 59, 115, 22, 3, 182],
    [172, 40, 90, 201, 179, 55, 197, 10, 16, 183, 163, 186, 177, 151, 70, 136],
]
_S = [
    1, 45, 226, 147, 190, 69, 21, 174, 120, 3, 135, 164, 184, 56, 207, 63,
    8, 103, 9, 148, 235, 38, 168, 107, 189, 24, 52, 27, 187, 191, 114, 247,
    64, 53, 72, 156, 81, 47, 59, 85, 227, 192, 159, 216, 211, 243, 141, 177,
    255, 167, 62, 220, 134, 119, 215, 166, 17, 251, 244, 186, 146, 145, 100, 131,
    241, 51, 239, 218, 44, 181, 178, 43, 136, 209, 153, 203, 140, 132, 29, 20,
    129, 151, 113, 202, 95, 163, 139, 87, 60, 130, 196, 82, 92, 28, 232, 160,
    4, 180, 133, 74, 246, 19, 84, 182, 223, 12, 26, 142, 222, 224, 57, 252,
    32, 155, 36, 78, 169, 152, 158, 171, 242, 96, 208, 108, 234, 250, 199, 217,
    0, 212, 31, 110, 67, 188, 236, 83, 137, 254, 122, 93, 73, 201, 50, 194,
    249, 154, 248, 109, 22, 219, 89, 150, 68, 233, 205, 230, 70, 66, 143, 10,
    193, 204, 185, 101, 176, 210, 198, 172, 30, 65, 98, 41, 46, 14, 116, 80,
    2, 90, 195, 37, 123, 138, 42, 91, 240, 6, 13, 71, 111, 112, 157, 126,
    16, 206, 18, 39, 213, 76, 79, 214, 121, 48, 104, 54, 117, 125, 228, 237,
    128, 106, 144, 55, 162, 94, 118, 170, 197, 127, 61, 175, 165, 229, 25, 97,
    253, 77, 124, 183, 11, 238, 173, 75, 34, 245, 231, 115, 35, 33, 200, 5,
    225, 102, 221, 179, 88, 105, 99, 86, 15, 161, 49, 149, 23, 7, 58, 40,
]
_I = [
    128, 0, 176, 9, 96, 239, 185, 253, 16, 18, 159, 228, 105, 186, 173, 248,
    192, 56, 194, 101, 79, 6, 148, 252, 25, 222, 106, 27, 93, 78, 168, 130,
    112, 237, 232, 236, 114, 179, 21, 195, 255, 171, 182, 71, 68, 1, 172, 37,
    201, 250, 142, 65, 26, 33, 203, 211, 13, 110, 254, 38, 88, 218, 50, 15,
    32, 169, 157, 132, 152, 5, 156, 187, 34, 140, 99, 231, 197, 225, 115, 198,
    175, 36, 91, 135, 102, 39, 247, 87, 244, 150, 177, 183, 92, 139, 213, 84,
    121, 223, 170, 246, 62, 163, 241, 17, 202, 245, 209, 23, 123, 147, 131, 188,
    189, 82, 30, 235, 174, 204, 214, 53, 8, 200, 138, 180, 226, 205, 191, 217,
    208, 80, 89, 63, 77, 98, 52, 10, 72, 136, 181, 86, 76, 46, 107, 158,
    210, 61, 60, 3, 19, 251, 151, 81, 117, 74, 145, 113, 35, 190, 118, 42,
    95, 249, 212, 85, 11, 220, 55, 49, 22, 116, 215, 119, 167, 230, 7, 219,
    164, 47, 70, 243, 97, 69, 103, 227, 12, 162, 59, 28, 133, 24, 4, 29,
    41, 160, 143, 178, 90, 216, 166, 126, 238, 141, 83, 75, 161, 154, 193, 14,
    122, 73, 165, 44, 129, 196, 199, 54, 43, 127, 67, 149, 51, 242, 108, 104,
    109, 240, 2, 40, 206, 221, 155, 234, 94, 153, 124, 20, 134, 207, 229, 66,
    184, 64, 120, 45, 58, 233, 100, 31, 146, 144, 125, 57, 111, 224, 137, 48,
]
_XOR_ADD = (0, 3, 4, 7, 8, 11, 12, 15)
_PERM = (8, 11, 12, 15, 2, 1, 6, 5, 10, 9, 14, 13, 0, 7, 4, 3)


def _mix(t):
    for k in range(0, 16, 2):
        e = ((t[k] << 1) + t[k + 1]) & 255
        t[k + 1] = (t[k] + t[k + 1]) & 255
        t[k] = e


def _perm(t):
    e = t[:16]
    for k in range(16):
        t[k] = e[_PERM[k]]


def _rot3(t):
    for k in range(17):
        t[k] = ((t[k] << 3) & 255) + (t[k] >> 5) & 255


def _schedule(key):
    m = [[0] * 16 for _ in range(17)]
    i = list(key) + [0]
    for k in range(16):
        i[16] ^= i[k]
    r = i[:]
    m[0] = i[:16]
    for h in range(16):
        _rot3(r)
        s = h + 1
        for c in range(16):
            m[h + 1][c] = (r[s] + _A[h + 1][15 - c]) & 255
            s += 1
            if s > 16:
                s = 0
    return m


def _round(n, c, m):
    for u in range(16):
        c[u] = c[u] ^ m[2 * n][u] if u in _XOR_ADD else (c[u] + m[2 * n][u]) & 255
    for u in range(16):
        c[u] = c[u] ^ m[2 * n + 1][u]
    for _ in range(3):
        _mix(c)
        _perm(c)
    _mix(c)


def _encrypt(t, m, feed_forward):
    s = t[:16]
    for r in range(8):
        if r == 2 and feed_forward:
            for h in range(16):
                t[h] = s[h] ^ t[h] if h in _XOR_ADD else (s[h] + t[h]) & 255
        _round(r, t, m)
    for h in range(16):
        t[h] = t[h] ^ m[16][h] if h in _XOR_ADD else (t[h] + m[16][h]) & 255


def jl_respond(challenge):
    """对 16 字节挑战算出 17 字节应答（0x01 + 16 字节）。"""
    rnd = list(challenge)
    key = _KEY
    rep = [_SEED[k % len(_SEED)] for k in range(16)]
    out = rnd[:]
    _encrypt(out, _schedule(key), False)
    for k in range(16):
        out[k] = ((out[k] ^ rnd[k]) + rep[k]) & 255
    h = [0] * 16
    for k in range(16):
        add = k % 2 == 0 if k < 8 else k % 2 == 1
        const = (233, 229, 223, 193, 179, 167, 149, 131)[k % 8]
        h[k] = (key[k] + const) & 255 if add else const ^ key[k]
    _encrypt(out, _schedule(h), True)
    return bytes([1] + out)


# ---- 设备发现 -------------------------------------------------------------

def find_device(explicit=None):
    if explicit:
        return explicit.upper()
    import subprocess
    try:
        out = subprocess.run(["bluetoothctl", "devices"], capture_output=True,
                             text=True, timeout=5).stdout
    except Exception:
        out = ""
    cands = []
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[1].count(":") == 5:
            name = " ".join(parts[2:])
            if "pudding" in name.lower() or "水月雨" in name:
                cands.append(parts[1])
    if len(cands) == 1:
        return cands[0]
    if not cands:
        sys.exit("没找到已配对的水月雨 Pudding 耳机。先配对，或用 -a <MAC> 指定地址。")
    sys.exit("找到多台候选：" + ", ".join(cands) + "，请用 -a 指定。")


def bt_connected(mac):
    """耳机在系统蓝牙里是否处于已连接状态。用来把底层 errno 翻译成人话。"""
    import subprocess
    try:
        out = subprocess.run(["bluetoothctl", "info", mac], capture_output=True,
                             text=True, timeout=4).stdout
    except Exception:
        return None
    return "Connected: yes" in out


# ---- 连接 + 认证 ----------------------------------------------------------

class Pudding:
    def __init__(self, mac, channel=RFCOMM_CHANNEL, timeout=8, retries=4):
        self.mac = mac
        self.seq = 0
        self.sock = None
        last_err = None
        # 耳机对接连开关很敏感：刚断开的会话要几百毫秒才释放，
        # 连不上或认证不过就退避重试。
        for attempt in range(retries):
            try:
                self.sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM,
                                          socket.BTPROTO_RFCOMM)
                self.sock.settimeout(timeout)
                self.sock.connect((mac, channel))
                self._auth()
                return
            except (OSError, RuntimeError) as e:
                last_err = e
                self.close()
                if attempt < retries - 1:
                    time.sleep(0.8 + attempt * 0.7)
        raise RuntimeError(f"连接/认证失败（试了 {retries} 次）：{last_err}")

    def _drain(self, seconds):
        self.sock.settimeout(seconds)
        buf = b""
        end = time.time() + seconds
        while time.time() < end:
            try:
                d = self.sock.recv(4096)
                if not d:
                    break
                buf += d
            except socket.timeout:
                break
            except ConnectionResetError:
                break
        return buf

    def _auth(self):
        time.sleep(0.35)
        self._drain(0.4)
        self.sock.sendall(b"\x00" + os.urandom(16))
        buf = b""
        end = time.time() + 6
        seen_device_challenge = False
        while time.time() < end:
            buf += self._drain(0.8)
            while buf:
                # 认证期间耳机可能先推一条 GAIA 帧（FF 04 ...），跳过它
                if buf[0] == 0xFF and len(buf) >= 8 and buf[1] == 0x04:
                    ln = (buf[2] << 8) | buf[3]
                    total = 8 + ln
                    if len(buf) < total:
                        break
                    buf = buf[total:]
                    continue
                need = {0: 17, 1: 17, 2: 5}.get(buf[0])
                if need is None:
                    raise RuntimeError("认证握手收到意外字节 0x%02x" % buf[0])
                if len(buf) < need:
                    break
                msg, buf = buf[:need], buf[need:]
                if msg[0] == 0:
                    # 耳机的挑战，回我们的应答
                    self.sock.sendall(jl_respond(msg[1:]))
                    seen_device_challenge = True
                elif msg[0] == 1:
                    self.sock.sendall(b"\x02pass")
                elif msg == b"\x02pass":
                    return True
            # 双方向都走完了；设备不一定再补一个 pass，直接进入验证
            if seen_device_challenge and not buf:
                break
        # 用一次固件查询确认链路真的通了；收不到就说明认证没过
        if self._probe():
            return True
        raise RuntimeError("认证后耳机无响应——可能被手机占着控制通道")

    def _collect(self, timeout):
        """读到至少一个完整 GAIA 帧就返回；否则最多等 timeout 秒。"""
        buf = b""
        end = time.time() + timeout
        self.sock.settimeout(0.25)
        while time.time() < end:
            # 已有完整帧就走
            if buf:
                i = 0
                while i + 8 <= len(buf):
                    if buf[i] == 0xFF and buf[i + 1] == 0x04:
                        ln = (buf[i + 2] << 8) | buf[i + 3]
                        if i + 8 + ln <= len(buf):
                            return buf
                        break
                    i += 1
            try:
                d = self.sock.recv(4096)
                if not d:
                    break
                buf += d
            except socket.timeout:
                continue
            except (ConnectionResetError, ConnectionAbortedError):
                break
        return buf

    def _probe(self):
        """认证后发一次固件查询，收到 GAIA 帧就算链路可用。"""
        try:
            return bool(self.gaia(0x00, 0x05, wait=1.8))
        except Exception:
            return False

    # ---- GAIA ----
    def gaia(self, feature, cmd, payload=b"", wait=2.0):
        """发一帧并收集响应。收到至少一个完整帧就立刻返回，不空等到超时。"""
        self.seq = (self.seq + 1) & 0xFF
        pkt = (bytes([0xFF, 0x04]) + len(payload).to_bytes(2, "big")
               + bytes([self.seq, VENDOR, feature, cmd]) + payload)
        self.sock.sendall(pkt)
        raw = self._collect(wait)
        frames = []
        i = 0
        while i + 8 <= len(raw):
            if raw[i] != 0xFF or raw[i + 1] != 0x04:
                i += 1
                continue
            ln = (raw[i + 2] << 8) | raw[i + 3]
            total = 8 + ln
            if i + total > len(raw):
                break
            frames.append(raw[i:i + total])
            i += total
        return frames

    def close(self):
        try:
            self.sock.close()
        except Exception:
            pass


def _filter(frames, feature, cmd):
    """只挑出 feature 匹配、cmd 匹配的响应帧，返回 payload。"""
    want_f = feature | 0x01
    for f in frames:
        if f[5] == VENDOR and f[6] == want_f and f[7] == cmd:
            return f[8:]
    return None


# ---- 动作 -----------------------------------------------------------------

ANC_MODES = {
    "off": 0x00,
    "adaptive": 0x01,
    "transparency": 0x02,
    "wind": 0x03,
    "noise": 0x04,
}
ANC_NAMES = {v: k for k, v in ANC_MODES.items()}

GAIN_LEVELS = {"high": 0x00, "mid": 0x01, "low": 0x02}
GAIN_NAMES = {v: k for k, v in GAIN_LEVELS.items()}

# 注：Pudding 的 GAIA feature 号是标准 GAIA 编号的**两倍**
#   标准 20(OneBringTwo 一带二) → Pudding 0x28
#   标准 13(Battery)            → Pudding 0x1A
#   标准 15(DacGain)            → Pudding 0x1E
#   标准 16(CodecType)          → Pudding 0x20
#   标准 32(AncV2)              → Pudding 0x40
FEATURE_MULTIPOINT = 0x28   # 一带二 / 双设备连接（cmd 1 读 / cmd 2 写）
FEATURE_CODEC = 0x20        # 编解码（cmd 5 读 LDAC / cmd 6 写 LDAC）


def read_battery(p):
    # 多次读：耳机偶尔只报一侧，多读几次取最新的完整值
    best = {}
    for _ in range(2):
        frames = p.gaia(0x1A, 0x01, b"\x01\x02", wait=1.2)
        payload = _filter(frames, 0x1A, 0x01)
        if payload:
            for k in range(0, len(payload) - 1, 2):
                did, lvl = payload[k], payload[k + 1]
                if lvl != 0xFF:
                    best[did] = lvl
        if len([k for k in best if k in (1, 2)]) == 2:
            break
        time.sleep(0.3)
    return best


def read_firmware(p):
    payload = _filter(p.gaia(0x00, 0x05, wait=1.2), 0x00, 0x05)
    return payload.decode("ascii", "replace") if payload else None


def read_anc(p):
    payload = _filter(p.gaia(0x40, 0x03, wait=1.2), 0x40, 0x03)
    return payload[0] if payload else None


def set_anc(p, mode):
    value = ANC_MODES[mode]
    p.gaia(0x40, 0x04, bytes([value]), wait=1.2)
    time.sleep(1.6)  # 耳机切换要时间，立刻读会拿到旧值
    return read_anc(p)


def read_gain(p):
    payload = _filter(p.gaia(0x1E, 0x01, wait=1.2), 0x1E, 0x01)
    return payload[0] if payload else None


def set_gain(p, level):
    value = GAIN_LEVELS[level]
    p.gaia(0x1E, 0x02, bytes([value]), wait=1.2)
    time.sleep(0.8)
    return read_gain(p)


def read_multipoint(p):
    payload = _filter(p.gaia(FEATURE_MULTIPOINT, 0x01, wait=1.2), FEATURE_MULTIPOINT, 0x01)
    return payload[0] if payload else None


def set_multipoint(p, enabled):
    p.gaia(FEATURE_MULTIPOINT, 0x02, bytes([1 if enabled else 0]), wait=1.4)
    time.sleep(1.2)
    return read_multipoint(p)


def read_ldac(p):
    payload = _filter(p.gaia(FEATURE_CODEC, 0x05, wait=1.2), FEATURE_CODEC, 0x05)
    return payload[0] if payload else None


def set_ldac(p, enabled):
    """切 LDAC 会让耳机重启蓝牙链路，这条连接必然断，属正常现象。"""
    try:
        p.gaia(FEATURE_CODEC, 0x06, bytes([1 if enabled else 0]), wait=1.4)
    except (ConnectionAbortedError, BrokenPipeError, OSError):
        pass  # 预期：切编码断链
    p.close()


def fmt_battery(d):
    parts = []
    for did, label in ((1, "左"), (2, "右"), (3, "盒")):
        if did in d:
            parts.append(f"{label} {d[did]}%")
    return "  ".join(parts) if parts else "读不到"


def main():
    ap = argparse.ArgumentParser(description="控制 MOONDROP Pudding 耳机")
    ap.add_argument("-a", "--address", help="耳机 MAC 地址（默认自动找）")
    ap.add_argument("-c", "--channel", type=int, default=RFCOMM_CHANNEL,
                    help="RFCOMM 通道（默认 1）")
    ap.add_argument("-j", "--json", action="store_true",
                    help="输出 JSON（给脚本/插件用）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="电量 + 固件 + ANC + 增益")
    sub.add_parser("battery", help="只读电量")
    sub.add_parser("firmware", help="固件版本")

    pa = sub.add_parser("anc", help="读/设降噪模式")
    pa.add_argument("mode", nargs="?", choices=list(ANC_MODES) + [None],
                    help="off / adaptive / transparency / wind / noise")

    pg = sub.add_parser("gain", help="读/设输出增益")
    pg.add_argument("level", nargs="?", choices=list(GAIN_LEVELS) + [None],
                    help="high / mid / low")

    pm = sub.add_parser("multipoint", aliases=["mp"],
                        help="读/设双设备连接（一带二）")
    pm.add_argument("state", nargs="?", choices=["on", "off", "toggle", None],
                    help="on / off / toggle")

    pc = sub.add_parser("codec", help="读/设解码方式（目前只有 LDAC 开关）")
    pc.add_argument("state", nargs="?", choices=["ldac", "sbc", "toggle", None],
                    help="ldac 开 LDAC / sbc 关 LDAC / toggle 取反")

    args = ap.parse_args()
    mac = find_device(args.address)

    try:
        p = Pudding(mac, args.channel)
    except (OSError, RuntimeError) as e:
        # 把底层 errno 翻成人话：没连上 / 被占用 / 认证被拒，三种原因处理方式不同
        if bt_connected(mac) is False:
            msg = "耳机没有连接。请开机或从充电盒取出，再在系统蓝牙里连上它。"
        elif "busy" in str(e).lower():
            msg = "蓝牙通道被占用。等几秒重试；如果一直这样，断开再重连耳机。"
        elif "认证" in str(e):
            msg = ("认证没通过。可能是手机 App 正占着控制通道 —— "
                   "在手机端关掉「双设备连接」，或退出 App 后再试。")
        else:
            msg = str(e)
        if args.json:
            print(json.dumps({"ok": False, "connected": False, "error": msg},
                             ensure_ascii=False))
            sys.exit(2)
        sys.exit(f"连不上 {mac}：{msg}")

    try:
        if args.cmd == "status":
            bat = read_battery(p)
            fw = read_firmware(p)
            a = read_anc(p)
            g = read_gain(p)
            mp = read_multipoint(p)
            ld = read_ldac(p)
            if args.json:
                print(json.dumps({
                    "ok": True,
                    "connected": True,
                    "address": mac,
                    "battery": {str(k): v for k, v in bat.items()},
                    "firmware": fw,
                    "anc": ANC_NAMES.get(a, None) if a is not None else None,
                    "anc_raw": a,
                    "gain": GAIN_NAMES.get(g, None) if g is not None else None,
                    "gain_raw": g,
                    "multipoint": bool(mp) if mp is not None else None,
                    "ldac": bool(ld) if ld is not None else None,
                }, ensure_ascii=False))
            else:
                print(f"电量    {fmt_battery(bat)}")
                print(f"固件    {fw or '读不到'}")
                print(f"降噪    {ANC_NAMES.get(a, f'未知({a})') if a is not None else '读不到'}")
                print(f"增益    {GAIN_NAMES.get(g, f'未知({g})') if g is not None else '读不到'}")
                print(f"多点    {'开' if mp else '关' if mp == 0 else '读不到'}")
                print(f"LDAC    {'开' if ld else '关' if ld == 0 else '读不到'}")

        elif args.cmd == "battery":
            bat = read_battery(p)
            if args.json:
                print(json.dumps({"ok": True, "battery": {str(k): v for k, v in bat.items()}},
                                 ensure_ascii=False))
            else:
                print(fmt_battery(bat))

        elif args.cmd == "firmware":
            print(read_firmware(p) or "读不到")

        elif args.cmd == "anc":
            if args.mode is None:
                a = read_anc(p)
                print(ANC_NAMES.get(a, f"未知({a})") if a is not None else "读不到")
            else:
                a = set_anc(p, args.mode)
                if args.json:
                    print(json.dumps({"ok": True, "anc": ANC_NAMES.get(a, None) if a is not None else None,
                                      "anc_raw": a}, ensure_ascii=False))
                else:
                    print(f"已设为 {args.mode}"
                          + (f"（回读：{ANC_NAMES.get(a, a)}）" if a is not None else ""))

        elif args.cmd in ("multipoint", "mp"):
            if args.state is None:
                mp = read_multipoint(p)
                print("开" if mp else "关" if mp == 0 else "读不到")
            else:
                if args.state == "toggle":
                    cur = read_multipoint(p)
                    target = not bool(cur)
                else:
                    target = (args.state == "on")
                mp = set_multipoint(p, target)
                if args.json:
                    print(json.dumps({"ok": True, "multipoint": bool(mp) if mp is not None else None},
                                     ensure_ascii=False))
                else:
                    print(f"已设为{'开' if target else '关'}"
                          + (f"（回读：{'开' if mp else '关'}）" if mp is not None else ""))

        elif args.cmd == "codec":
            if args.state is None:
                ld = read_ldac(p)
                print(f"LDAC {'开' if ld else '关' if ld == 0 else '读不到'}")
            elif args.state == "toggle":
                cur = read_ldac(p)
                target = not bool(cur)
                set_ldac(p, target)
                print(f"已{'开启' if target else '关闭'} LDAC。"
                      "耳机重连后生效，蓝牙音频会短暂中断。")
            else:
                target = (args.state == "ldac")
                set_ldac(p, target)
                print(f"已{'开启' if target else '关闭'} LDAC（关掉后走系统默认编码）。"
                      "耳机重连后生效，蓝牙音频会短暂中断。")

        elif args.cmd == "gain":
            if args.level is None:
                g = read_gain(p)
                print(GAIN_NAMES.get(g, f"未知({g})") if g is not None else "读不到")
            else:
                g = set_gain(p, args.level)
                print(f"已设为 {args.level}"
                      + (f"（回读：{GAIN_NAMES.get(g, g)}）" if g is not None else ""))
    finally:
        p.close()


if __name__ == "__main__":
    main()
