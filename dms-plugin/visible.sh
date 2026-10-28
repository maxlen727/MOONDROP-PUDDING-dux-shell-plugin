#!/bin/sh
# 耳机连着 → exit 0（DMS 显示这个部件）；没连 → exit 1（自动隐藏）
# 只查蓝牙连接状态，不碰 RFCOMM，所以不会跟 pudding.py 抢控制通道。
for mac in $(bluetoothctl devices 2>/dev/null | awk '/[Pp]udding/ {print $2}'); do
    if bluetoothctl info "$mac" 2>/dev/null | grep -q 'Connected: yes'; then
        exit 0
    fi
done
exit 1
