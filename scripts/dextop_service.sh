#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="dextop-node"
SERVICE_FILE="${SERVICE_NAME}.service"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "${SCRIPT_DIR}")"
SOURCE_UNIT="${PROJECT_DIR}/${SERVICE_FILE}"
SYSTEMD_DIR="/etc/systemd/system"
DEST_UNIT="${SYSTEMD_DIR}/${SERVICE_FILE}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info()  { echo -e "${CYAN}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
err()   { echo -e "${RED}[ERROR]${NC} $*" >&2; }

need_sudo() {
    if [[ "$(id -u)" -ne 0 ]]; then
        if ! command -v sudo >/dev/null 2>&1; then
            err "This command requires root privileges and sudo is not available."
            exit 1
        fi
        SUDO="sudo"
    else
        SUDO=""
    fi
}

cmd_install() {
    if [[ ! -f "$SOURCE_UNIT" ]]; then
        err "Unit file not found: ${SOURCE_UNIT}"
        exit 1
    fi
    need_sudo
    info "Copying ${SERVICE_FILE} to ${SYSTEMD_DIR}/"
    $SUDO cp "$SOURCE_UNIT" "$DEST_UNIT"
    $SUDO systemctl daemon-reload
    ok "Service installed. Run: dextop_service.sh --start"
}

cmd_uninstall() {
    need_sudo
    info "Stopping and disabling ${SERVICE_NAME}..."
    $SUDO systemctl stop "$SERVICE_NAME" 2>/dev/null || true
    $SUDO systemctl disable "$SERVICE_NAME" 2>/dev/null || true
    if [[ -f "$DEST_UNIT" ]]; then
        $SUDO rm -f "$DEST_UNIT"
        $SUDO systemctl daemon-reload
        ok "Service uninstalled."
    else
        warn "Unit file not found at ${DEST_UNIT}, nothing to remove."
    fi
}

cmd_start() {
    if [[ ! -f "$DEST_UNIT" ]]; then
        err "Service not installed. Run: dextop_service.sh --install"
        exit 1
    fi
    need_sudo
    $SUDO systemctl enable "$SERVICE_NAME"
    $SUDO systemctl start "$SERVICE_NAME"
    ok "Service started and enabled for boot."
    systemctl --no-pager status "$SERVICE_NAME" || true
}

cmd_stop() {
    need_sudo
    $SUDO systemctl stop "$SERVICE_NAME"
    ok "Service stopped."
}

cmd_status() {
    systemctl --no-pager status "$SERVICE_NAME" || true
    echo ""
    info "Recent logs:"
    journalctl -u "$SERVICE_NAME" -n 20 --no-pager 2>/dev/null || true
}

cmd_logs() {
    journalctl -u "$SERVICE_NAME" -f
}

usage() {
    cat <<EOF
Usage: dextop_service.sh <command>

Commands:
  --install     Install the systemd service (copies unit file, reloads daemon)
  --uninstall   Stop, disable, and remove the systemd service
  --start       Enable and start the service (persists across reboots)
  --stop        Stop the service (stays enabled for next boot)
  --check       Show service status and recent logs
  --status      Same as --check
  --logs        Follow the service journal logs (Ctrl+C to stop)
  --help        Show this help message
EOF
}

case "${1:-}" in
    --install)   cmd_install ;;
    --uninstall) cmd_uninstall ;;
    --start)     cmd_start ;;
    --stop)      cmd_stop ;;
    --check|--status) cmd_status ;;
    --logs)      cmd_logs ;;
    --help|-h)   usage ;;
    *)
        if [[ -n "${1:-}" ]]; then
            err "Unknown command: $1"
        fi
        usage
        exit 1
        ;;
esac
