# 在 Linux 上控制水月雨 Pudding

不用手机 App，直接在 Linux 上控制 **MOONDROP Pudding**（`MD-TWS-056`）真无线耳机。

两个部分，可以分开用：

- **`pudding.py`** —— 零依赖的 Python 命令行工具，通过蓝牙 RFCOMM 直接和耳机通信。
  降噪、输出增益、双设备连接、LDAC、电量都能读写。
- **Dux Shell（DMS）状态栏插件** —— 点击开控制面板，**耳机没连接时自动隐藏**。

[English](README.md) | 简体中文

```
$ ./pudding.py status
电量    左 76%  右 84%
固件    3.5.6
降噪    noise
增益    high
多点    关
LDAC    关
```

## 能做什么

| | |
|---|---|
| 降噪 | 关闭 / 自适应 / 通透 / 抗风噪 / 基础降噪 |
| 输出增益 | 高 / 中 / 低 |
| 双设备连接 | 开 / 关（一带二） |
| LDAC | 开 / 关（注意[已知限制](#已知限制)） |
| 电量 | 左耳 / 右耳 / 充电盒 |
| 信息 | 固件版本 |

**固件 3.5.6 真机实测**，环境 Arch Linux + BlueZ 5.87。

## 安装

### DMS 插件

```bash
git clone https://github.com/maxlen727/MOONDROP-PUDDING-dux-shell-plugin.git
cd MOONDROP-PUDDING-dux-shell-plugin
./install.sh
```

脚本会把插件复制到 `~/.config/dms/plugins/puddingControl/`、启用它、加到状态栏，然后重启 DMS。
不想动状态栏布局就加 `--no-bar`；想彻底删干净用 `./install.sh --uninstall`。

需要 [Dux Shell](https://github.com/duxlabs-dev/dux-shell) 2.x。插件自带 CLI，装完就能用。

**左键**开控制面板，**右键**快速轮换降噪（降噪 → 通透 → 关闭）。

### 只用命令行

```bash
./pudding.py status            # 电量 + 固件 + 降噪 + 增益 + 多点 + LDAC
./pudding.py battery
./pudding.py anc               # 读当前模式
./pudding.py anc transparency  # off / adaptive / transparency / wind / noise
./pudding.py gain high         # high / mid / low
./pudding.py multipoint on     # on / off / toggle
./pudding.py codec ldac        # ldac / sbc / toggle
./pudding.py -j status         # 输出 JSON，给脚本用
```

除 Python 标准库外没有依赖 —— 直接用 `socket` 的 `AF_BLUETOOTH`。

耳机要已配对、开机，并且**没被手机 App 占着控制通道**（读不到状态的话，先去手机端关掉"双设备连接"）。

## 环境要求

- Linux + BlueZ
- Python 3.8+
- 用插件的话：Dux Shell 2.x

## 原理

耳机在一个 RFCOMM 通道上**叠了两套协议**，顺序不能错：

1. **杰理 RCSP 认证** —— 用杰理公开的密码算法做挑战/应答。**不过这一步，后面发什么都是石沉大海**，
   连个错误包都不回。
2. **高通 GAIA 帧** —— `FF 04 <长度> <序号> 1D <功能> <命令> <数据>`。

还有第三个坑：Pudding 的 GAIA **功能号是标准编号的两倍**。多点连接是 `0x28` 不是 `0x14`，
电量是 `0x1A` 不是 `0x0D`。

完整协议、每条命令、认证的逐字节流程：**[docs/PROTOCOL.md](docs/PROTOCOL.md)**

## 已知限制

**这副耳机在 Linux 上用不了 LDAC。**

耳机的 A2DP 端点能力里没有索尼 LDAC 的厂商号（`0x0000012D`），也就是它根本没向 Linux 广播
自己支持 LDAC。所以 PipeWire 只会给出 SBC / SBC-XQ / AAC，实际跑在 AAC 上。
GAIA 里那个 LDAC 开关是**耳机内部的许可位**，不是编码声明 —— 打开它并不能让 Linux 协商出 LDAC。

其他：

- 切 LDAC 会**断开蓝牙链路**几秒（耳机要重启音频栈），属正常现象
- 连续快速开关连接会让耳机在几百毫秒内拒绝新连接，CLI 里做了退避重试
- **别为了试 BLE 断开经典连接** —— 耳机可能进入不可连接状态，得重新开机
- 降噪切换要 ~1.5 秒生效，写完立刻回读可能还是旧值

## 致谢

这个协议此前没有任何一处完整文档，站在这些项目肩上：

- [luoning77/moondrop-gaia-protocol](https://github.com/Luoning77/moondrop-gaia-protocol) —— Pudding 的 GAIA 命令表
- [lingbai-rong/PuddingPods](https://github.com/lingbai-rong/PuddingPods) —— 同型号的 LSPosed 模块
- [Desmond123-arch/spacebuds-ctl](https://github.com/Desmond123-arch/spacebuds-ctl) —— 杰理 RCSP 认证算法（本项目移植成 Python）
- [Karthik-Unni/libboat](https://github.com/Karthik-Unni/libboat) —— 杰理 RCSP 帧结构
- [FEAKEuser/moondrop-control](https://github.com/FEAKEuser/moondrop-control) —— 它的 feature 枚举暴露了「编号翻倍」这件事
- [silverpoetry/HyperEars](https://github.com/silverpoetry/HyperEars) —— Pudding 协议笔记

## 许可

MIT。与水月雨官方无关。这些是未公开的命令，厂商随时可能改，自担风险。
