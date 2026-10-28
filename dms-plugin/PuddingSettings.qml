import QtQuick
import qs.Common
import qs.Widgets
import qs.Modules.Plugins

PluginSettings {
    id: root
    pluginId: "puddingControl"

    StyledText {
        width: parent.width
        text: "MOONDROP Pudding"
        font.pixelSize: Theme.fontSizeLarge
        font.weight: Font.Bold
        color: Theme.surfaceText
    }

    StyledText {
        width: parent.width
        text: "从状态栏控制水月雨 Pudding 耳机。左键点开面板，右键快速轮换降噪（降噪 → 通透 → 关闭）。"
        font.pixelSize: Theme.fontSizeSmall
        color: Theme.surfaceVariantText
        wrapMode: Text.WordWrap
    }

    StringSetting {
        settingKey: "scriptPath"
        label: "pudding.py 路径"
        description: "留空则用插件目录里自带的 pudding.py。只有当你想用另一个副本时才需要填绝对路径。"
        placeholder: "/path/to/pudding.py"
        defaultValue: ""
    }

    StyledText {
        width: parent.width
        text: "耳机要在开机状态、蓝牙已配对连接，并且没被手机占着控制通道。"
        font.pixelSize: Theme.fontSizeExtraSmall
        color: Theme.surfaceVariantText
        wrapMode: Text.WordWrap
    }
}
