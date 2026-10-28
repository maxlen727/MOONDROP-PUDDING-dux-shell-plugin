#!/usr/bin/env bash
# Installer for the MOONDROP Pudding Dux Shell (DMS) plugin.
#
#   ./install.sh              install plugin + CLI, enable it, add to the bar
#   ./install.sh --no-bar     install but do not touch the bar layout
#   ./install.sh --uninstall  remove everything this script added
#
set -euo pipefail

PLUGIN_ID="puddingControl"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/dms"
PLUGIN_DIR="$CONFIG_DIR/plugins/$PLUGIN_ID"
SETTINGS="$CONFIG_DIR/settings.json"
PLUGIN_SETTINGS="$CONFIG_DIR/plugin_settings.json"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

ADD_TO_BAR=1
UNINSTALL=0
for arg in "$@"; do
    case "$arg" in
        --no-bar) ADD_TO_BAR=0 ;;
        --uninstall) UNINSTALL=1 ;;
        -h|--help) sed -n '2,8p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "unknown option: $arg" >&2; exit 1 ;;
    esac
done

say() { printf '\033[1m%s\033[0m\n' "$*"; }
warn() { printf '\033[33m%s\033[0m\n' "$*" >&2; }

if [ "$UNINSTALL" = 1 ]; then
    say "Removing $PLUGIN_ID"
    if [ -f "$SETTINGS" ]; then
        cp "$SETTINGS" "$SETTINGS.bak-pudding-uninstall"
        python3 - "$SETTINGS" "$PLUGIN_ID" <<'PY'
import json, sys
path, pid = sys.argv[1], sys.argv[2]
d = json.load(open(path))
for bar in d.get("barConfigs", []):
    for side in ("leftWidgets", "centerWidgets", "rightWidgets"):
        ws = bar.get(side) or []
        bar[side] = [w for w in ws
                     if (w.get("id") if isinstance(w, dict) else w) != pid]
json.dump(d, open(path, "w"), ensure_ascii=False, indent=2)
print("  removed from bar layout")
PY
    fi
    if [ -f "$PLUGIN_SETTINGS" ]; then
        python3 - "$PLUGIN_SETTINGS" "$PLUGIN_ID" <<'PY'
import json, sys
path, pid = sys.argv[1], sys.argv[2]
d = json.load(open(path))
d.pop(pid, None)
json.dump(d, open(path, "w"), ensure_ascii=False, indent=2)
print("  removed plugin settings")
PY
    fi
    rm -rf "$PLUGIN_DIR"
    command -v dms >/dev/null && dms restart >/dev/null 2>&1 || true
    say "Done. Restart DMS if the widget is still visible."
    exit 0
fi

# ---------------------------------------------------------------- checks
command -v dms >/dev/null 2>&1 || {
    warn "The 'dms' command was not found. Install Dux Shell first:"
    warn "  https://github.com/duxlabs-dev/dux-shell"
    exit 1
}
command -v python3 >/dev/null 2>&1 || { warn "python3 is required"; exit 1; }
[ -d "$CONFIG_DIR" ] || { warn "$CONFIG_DIR not found — has DMS run at least once?"; exit 1; }

# ---------------------------------------------------------------- files
say "Installing plugin to $PLUGIN_DIR"
mkdir -p "$PLUGIN_DIR"
cp "$SRC_DIR"/dms-plugin/plugin.json \
   "$SRC_DIR"/dms-plugin/PuddingWidget.qml \
   "$SRC_DIR"/dms-plugin/PuddingSettings.qml \
   "$SRC_DIR"/dms-plugin/visible.sh \
   "$PLUGIN_DIR/"
# The widget shells out to this CLI, so it must live next to the QML.
cp "$SRC_DIR/pudding.py" "$PLUGIN_DIR/pudding.py"
chmod +x "$PLUGIN_DIR/pudding.py" "$PLUGIN_DIR/visible.sh"

# ---------------------------------------------------------------- enable
say "Enabling plugin"
[ -f "$PLUGIN_SETTINGS" ] && cp "$PLUGIN_SETTINGS" "$PLUGIN_SETTINGS.bak-pudding"
python3 - "$PLUGIN_SETTINGS" "$PLUGIN_ID" <<'PY'
import json, os, sys
path, pid = sys.argv[1], sys.argv[2]
data = {}
if os.path.exists(path):
    try:
        data = json.load(open(path))
    except Exception:
        data = {}
data.setdefault(pid, {})["enabled"] = True
json.dump(data, open(path, "w"), ensure_ascii=False, indent=2)
print("  enabled")
PY

# ---------------------------------------------------------------- bar
if [ "$ADD_TO_BAR" = 1 ] && [ -f "$SETTINGS" ]; then
    say "Adding to the bar"
    cp "$SETTINGS" "$SETTINGS.bak-pudding"
    python3 - "$SETTINGS" "$PLUGIN_ID" <<'PY'
import json, sys
path, pid = sys.argv[1], sys.argv[2]
d = json.load(open(path))
bars = d.get("barConfigs") or []
if not bars:
    print("  no bar config found, skipped")
    raise SystemExit
bar = bars[0]
right = bar.setdefault("rightWidgets", [])
if any((w.get("id") if isinstance(w, dict) else w) == pid for w in right):
    print("  already on the bar")
else:
    right.insert(0, {"id": pid, "enabled": True})
    json.dump(d, open(path, "w"), ensure_ascii=False, indent=2)
    print("  added to rightWidgets")
PY
fi

# ---------------------------------------------------------------- reload
say "Reloading DMS"
dms restart >/dev/null 2>&1 || true
sleep 3
dms ipc call plugins reload "$PLUGIN_ID" >/dev/null 2>&1 || true

cat <<'EOF'

Installed.

  The widget only appears while the earbuds are connected.
  Left click  -> control panel
  Right click -> cycle noise control (ANC -> transparency -> off)

  If it is not on the bar yet: Settings -> Bar -> add "MOONDROP Pudding".
  To remove everything: ./install.sh --uninstall
EOF
