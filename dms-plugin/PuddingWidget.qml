import QtQuick
import QtQuick.Layouts
import Quickshell.Io
import qs.Common
import qs.Services
import qs.Widgets
import qs.Modules.Plugins

PluginComponent {
    id: root

    // 插件目录从自身 URL 推出来，这样插件整体搬走也不会断。
    // （PluginComponent 的绑定上下文里 Quickshell.env("HOME") 和 pluginData
    //  都可能为空，所以不要拿它们拼路径。）
    readonly property string pluginDir: Qt.resolvedUrl(".").toString().replace("file://", "")
    readonly property string script: (pluginData && pluginData.scriptPath)
                                     ? pluginData.scriptPath
                                     : pluginDir + "/pudding.py"

    // 耳机没连上时整个部件自动隐藏（DMS 原生机制：命令 exit 0 = 显示）。
    // 每 5 秒查一次蓝牙连接状态，脚本只读 bluetoothctl，不碰 RFCOMM。
    visibilityCommand: pluginDir + "/visible.sh"
    visibilityInterval: 5

    // ---------------- state ----------------
    property bool hasState: false
    property bool busy: false
    property string lastError: ""

    property int batteryL: -1
    property int batteryR: -1
    property int batteryCase: -1
    property string firmware: ""
    property string anc: ""        // off / adaptive / transparency / wind / noise
    property string gain: ""       // high / mid / low
    property bool multipoint: false
    property bool ldac: false

    readonly property var ancModes: [
        { key: "noise",        label: "降噪",   icon: "noise_aware" },
        { key: "adaptive",     label: "自适应", icon: "auto_awesome" },
        { key: "transparency", label: "通透",   icon: "hearing" },
        { key: "wind",         label: "抗风噪", icon: "air" },
        { key: "off",          label: "关闭",   icon: "noise_control_off" }
    ]

    readonly property var gainLevels: [
        { key: "high", label: "高" },
        { key: "mid",  label: "中" },
        { key: "low",  label: "低" }
    ]

    readonly property string ancLabel: {
        for (let i = 0; i < ancModes.length; i++)
            if (ancModes[i].key === anc)
                return ancModes[i].label;
        return "";
    }

    readonly property string ancIcon: {
        if (anc === "off") return "noise_control_off";
        if (anc === "transparency") return "hearing";
        if (anc === "wind") return "air";
        if (anc === "adaptive") return "auto_awesome";
        return "noise_aware";
    }

    // 电量：优先显示两只耳里较低的那个，更接近真实可用时间
    readonly property int shownBattery: {
        if (batteryL < 0 && batteryR < 0)
            return -1;
        if (batteryL < 0) return batteryR;
        if (batteryR < 0) return batteryL;
        return Math.min(batteryL, batteryR);
    }

    // ---------------- lifecycle ----------------
    readonly property bool pluginPopoutVisible: pluginPopout ? pluginPopout.shouldBeVisible : false

    onPluginPopoutVisibleChanged: {
        if (pluginPopoutVisible)
            refresh();
    }

    Component.onCompleted: refresh()

    property int refreshGen: 0

    function refresh() {
        if (procState.running)
            return;
        refreshGen++;
        procState.kick();
    }

    function applyStatus(txt) {
        let d;
        try {
            d = JSON.parse(txt);
        } catch (e) {
            lastError = txt.toString().trim().slice(0, 120);
            return;
        }
        if (!d.ok) {
            hasState = false;
            lastError = d.error || "连不上耳机";
            return;
        }
        hasState = true;
        lastError = "";
        const b = d.battery || {};
        batteryL = b["1"] !== undefined ? b["1"] : -1;
        batteryR = b["2"] !== undefined ? b["2"] : -1;
        batteryCase = b["3"] !== undefined ? b["3"] : -1;
        firmware = d.firmware || "";
        anc = d.anc || "";
        gain = d.gain || "";
        multipoint = !!d.multipoint;
        ldac = !!d.ldac;
    }

    function runAction(args) {
        if (busy)
            return;
        busy = true;
        lastError = "";
        procAction.command = ["python3", script, "-j"].concat(args);
        procAction.running = false;
        procAction.running = true;
    }

    function setAnc(key) {
        anc = key;  // 先乐观更新，真实状态由刷新纠正
        runAction(["anc", key]);
    }

    function cycleAnc() {
        // 右击轮换：降噪 → 通透 → 关闭 → 降噪
        const order = ["noise", "transparency", "off"];
        const i = order.indexOf(anc);
        setAnc(order[(i + 1) % order.length]);
    }

    function setGain(key) {
        gain = key;
        runAction(["gain", key]);
    }

    function toggleMultipoint() {
        multipoint = !multipoint;
        runAction(["multipoint", multipoint ? "on" : "off"]);
    }

    function toggleLdac() {
        ldac = !ldac;
        runAction(["codec", ldac ? "ldac" : "sbc"]);
    }

    // ---------------- processes ----------------
    Timer {
        // 面板开着时勤刷；关着只低频兜底。切 LDAC 会断链，刷新要慢一点。
        interval: pluginPopoutVisible ? 5000 : 30000
        repeat: true
        running: true
        onTriggered: root.refresh()
    }

    Process {
        id: procState
        command: ["python3", root.script, "-j", "status"]
        running: false
        environment: { "PYTHONIOENCODING": "utf-8" }

        function kick() {
            if (running)
                running = false;
            running = true;
        }

        stdout: StdioCollector {
            id: stateOut
            waitForEnd: true
            onStreamFinished: root.applyStatus(stateOut.text)
        }
        onExited: function (code) { }
    }

    Process {
        id: procAction
        running: false
        environment: { "PYTHONIOENCODING": "utf-8" }

        stdout: StdioCollector {
            id: actionOut
            waitForEnd: true
            onStreamFinished: {
                const txt = actionOut.text;
                if (!txt || txt.trim() === "")
                    return;
                try {
                    const d = JSON.parse(txt);
                    if (d.ok === false)
                        root.lastError = d.error || "操作失败";
                } catch (e) { }
            }
        }
        onExited: function (code) {
            root.busy = false;
            // 动作完成后再拉一次真实状态（切 LDAC 会断链，多等一会儿）
            actionTimer.restart();
        }
    }

    Timer {
        id: actionTimer
        interval: 900
        repeat: false
        onTriggered: root.refresh()
    }

    // ================= bar pill =================
    pillRightClickAction: function () { root.cycleAnc() }

    horizontalBarPill: Component {
        Row {
            spacing: Theme.spacingXS

            DankIcon {
                anchors.verticalCenter: parent.verticalCenter
                name: root.hasState ? root.ancIcon : "headphones"
                filled: root.hasState
                size: Theme.iconSizeSmall
                color: !root.hasState ? Theme.surfaceVariantText : Theme.primary
                opacity: root.busy ? 0.45 : 1
            }

            StyledText {
                anchors.verticalCenter: parent.verticalCenter
                visible: root.hasState && root.shownBattery >= 0
                text: root.shownBattery + "%"
                font.pixelSize: Theme.fontSizeSmall
                color: Theme.surfaceText
            }
        }
    }

    verticalBarPill: Component {
        Column {
            spacing: Theme.spacingXXS

            DankIcon {
                anchors.horizontalCenter: parent.horizontalCenter
                name: root.hasState ? root.ancIcon : "headphones"
                filled: root.hasState
                size: Theme.iconSizeSmall
                color: !root.hasState ? Theme.surfaceVariantText : Theme.primary
                opacity: root.busy ? 0.45 : 1
            }

            StyledText {
                anchors.horizontalCenter: parent.horizontalCenter
                visible: root.hasState && root.shownBattery >= 0
                text: root.shownBattery
                font.pixelSize: Theme.fontSizeExtraSmall
                color: Theme.surfaceText
            }
        }
    }

    // ================= popout =================
    popoutWidth: 340

    popoutContent: Component {
        PopoutComponent {
            id: popout
            headerText: "水月雨 Pudding"
            detailsText: !root.hasState
                         ? (root.lastError || "未连接")
                         : "固件 " + root.firmware
            showCloseButton: true
            closePopout: function () { root.closePopout() }

            Column {
                width: parent.width
                spacing: Theme.spacingM
                opacity: root.hasState ? 1 : 0.4

                // ---------- 电量 ----------
                Row {
                    width: parent.width
                    spacing: Theme.spacingM

                    Repeater {
                        model: [
                            { label: "左", value: root.batteryL },
                            { label: "右", value: root.batteryR },
                            { label: "盒", value: root.batteryCase }
                        ]

                        delegate: Row {
                            required property var modelData
                            spacing: Theme.spacingXXS

                            StyledText {
                                anchors.verticalCenter: parent.verticalCenter
                                text: modelData.label
                                font.pixelSize: Theme.fontSizeExtraSmall
                                color: Theme.surfaceVariantText
                            }

                            StyledText {
                                anchors.verticalCenter: parent.verticalCenter
                                text: modelData.value >= 0 ? modelData.value + "%" : "—"
                                font.pixelSize: Theme.fontSizeSmall
                                color: Theme.surfaceText
                            }
                        }
                    }
                }

                // ---------- 降噪 ----------
                Column {
                    width: parent.width
                    spacing: Theme.spacingXS

                    StyledText {
                        text: "降噪"
                        font.pixelSize: Theme.fontSizeSmall
                        color: Theme.surfaceVariantText
                    }

                    Flow {
                        width: parent.width
                        spacing: Theme.spacingXS

                        Repeater {
                            model: root.ancModes

                            delegate: Rectangle {
                                required property var modelData

                                readonly property bool selected: root.anc === modelData.key

                                width: (parent.width - Theme.spacingXS * (root.ancModes.length - 1)) / root.ancModes.length
                                height: 30
                                radius: Theme.cornerRadius / 2
                                color: selected
                                       ? Qt.rgba(Theme.primary.r, Theme.primary.g, Theme.primary.b, 0.16)
                                       : "transparent"
                                border.width: 1
                                border.color: selected
                                              ? Theme.primary
                                              : Qt.rgba(Theme.surfaceText.r, Theme.surfaceText.g, Theme.surfaceText.b, 0.08)

                                StyledText {
                                    anchors.centerIn: parent
                                    text: modelData.label
                                    font.pixelSize: Theme.fontSizeExtraSmall
                                    color: selected ? Theme.primary : Theme.surfaceVariantText
                                }

                                MouseArea {
                                    anchors.fill: parent
                                    enabled: root.hasState && !root.busy
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: root.setAnc(modelData.key)
                                }
                            }
                        }
                    }
                }

                // ---------- 增益 ----------
                Column {
                    width: parent.width
                    spacing: Theme.spacingXS

                    StyledText {
                        text: "输出增益"
                        font.pixelSize: Theme.fontSizeSmall
                        color: Theme.surfaceVariantText
                    }

                    Row {
                        width: parent.width
                        spacing: Theme.spacingXS

                        Repeater {
                            model: root.gainLevels

                            delegate: Rectangle {
                                required property var modelData

                                readonly property bool selected: root.gain === modelData.key

                                width: (parent.width - Theme.spacingXS * 2) / 3
                                height: 30
                                radius: Theme.cornerRadius / 2
                                color: selected
                                       ? Qt.rgba(Theme.primary.r, Theme.primary.g, Theme.primary.b, 0.16)
                                       : "transparent"
                                border.width: 1
                                border.color: selected
                                              ? Theme.primary
                                              : Qt.rgba(Theme.surfaceText.r, Theme.surfaceText.g, Theme.surfaceText.b, 0.08)

                                StyledText {
                                    anchors.centerIn: parent
                                    text: modelData.label
                                    font.pixelSize: Theme.fontSizeExtraSmall
                                    color: selected ? Theme.primary : Theme.surfaceVariantText
                                }

                                MouseArea {
                                    anchors.fill: parent
                                    enabled: root.hasState && !root.busy
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: root.setGain(modelData.key)
                                }
                            }
                        }
                    }
                }

                // ---------- 开关 ----------
                Column {
                    width: parent.width
                    spacing: Theme.spacingS

                    Repeater {
                        model: [
                            { key: "mp", label: "双设备连接", sub: "一带二，两台设备轮流用", on: root.multipoint },
                            { key: "ldac", label: "LDAC", sub: "切换会断开音频几秒", on: root.ldac }
                        ]

                        delegate: Row {
                            required property var modelData
                            width: parent.width
                            spacing: Theme.spacingS

                            Column {
                                width: parent.width - toggle.width - Theme.spacingS
                                anchors.verticalCenter: parent.verticalCenter
                                spacing: 1

                                StyledText {
                                    text: modelData.label
                                    font.pixelSize: Theme.fontSizeSmall
                                    color: Theme.surfaceText
                                }

                                StyledText {
                                    text: modelData.sub
                                    font.pixelSize: Theme.fontSizeExtraSmall
                                    color: Theme.surfaceVariantText
                                }
                            }

                            Rectangle {
                                id: toggle
                                width: 40
                                height: 22
                                radius: 11
                                color: modelData.on
                                       ? Theme.primary
                                       : Qt.rgba(Theme.surfaceText.r, Theme.surfaceText.g, Theme.surfaceText.b, 0.18)

                                Rectangle {
                                    width: 16
                                    height: 16
                                    radius: 8
                                    y: 3
                                    x: modelData.on ? parent.width - width - 3 : 3
                                    color: modelData.on ? Theme.surfaceText : Theme.surfaceVariantText

                                    Behavior on x {
                                        NumberAnimation { duration: 120 }
                                    }
                                }

                                MouseArea {
                                    anchors.fill: parent
                                    enabled: root.hasState && !root.busy
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: {
                                        if (modelData.key === "mp")
                                            root.toggleMultipoint();
                                        else
                                            root.toggleLdac();
                                    }
                                }
                            }
                        }
                    }
                }

                // ---------- 错误提示 ----------
                StyledText {
                    width: parent.width
                    visible: root.lastError.length > 0
                    text: root.lastError
                    font.pixelSize: Theme.fontSizeExtraSmall
                    color: Theme.error
                    wrapMode: Text.WordWrap
                }
            }
        }
    }
}
