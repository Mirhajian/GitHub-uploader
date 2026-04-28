#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# setup.sh — Interactive first-time setup for the Telegram → GitHub Upload Bot
#
# What this script does:
#   1. Updates apt and installs all system dependencies
#   2. Checks Python version (3.10+)
#   3. Creates a virtual environment and installs Python dependencies
#   4. Walks you through every config value and writes .env
#   5. Optionally enables Git LFS on the target repository
#   6. Optionally sets up a systemd service so the bot starts on reboot
#
# Usage:
#   chmod +x setup.sh && ./setup.sh
#
#   — or one-liner (no clone needed) —
#   bash <(curl -sL https://raw.githubusercontent.com/mirhajian/GitHub-uploader/main/setup.sh)
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

# ── Colour palette ────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
BLUE='\033[0;34m'
BOLD='\033[1m'
DIM='\033[2m'
RESET='\033[0m'

# ── Logging helpers ───────────────────────────────────────────────────────────
info()    { echo -e "  ${CYAN}❯${RESET}  $*"; }
success() { echo -e "  ${GREEN}✔${RESET}  $*"; }
warn()    { echo -e "  ${YELLOW}⚠${RESET}  $*"; }
error()   { echo -e "  ${RED}✖${RESET}  $*" >&2; }
step()    { echo -e "\n${BOLD}${BLUE}▸ $*${RESET}"; }
section() {
    echo ""
    echo -e "${BOLD}${MAGENTA}  ┌─────────────────────────────────────────────┐${RESET}"
    printf  "${BOLD}${MAGENTA}  │  %-43s  │${RESET}\n" "$*"
    echo -e "${BOLD}${MAGENTA}  └─────────────────────────────────────────────┘${RESET}"
}
divider() { echo -e "${DIM}  ─────────────────────────────────────────────────${RESET}"; }
ask()     { echo -e "  ${BOLD}${CYAN}?${RESET}  ${BOLD}$*${RESET}"; }

# ── Prompt helpers ────────────────────────────────────────────────────────────
prompt_required() {
    local var="$1" question="$2" default="${3:-}"
    local value=""
    while [[ -z "$value" ]]; do
        if [[ -n "$default" ]]; then
            ask "$question"
            echo -ne "      ${DIM}[default: $default]${RESET} → "
        else
            ask "$question"
            echo -ne "      → "
        fi
        read -r value
        value="${value:-$default}"
        if [[ -z "$value" ]]; then
            warn "This field is required."
        fi
    done
    printf -v "$var" '%s' "$value"
}

prompt_optional() {
    local var="$1" question="$2" default="${3:-}"
    if [[ -n "$default" ]]; then
        ask "$question"
        echo -ne "      ${DIM}[default: $default]${RESET} → "
    else
        ask "$question"
        echo -ne "      ${DIM}[optional — press Enter to skip]${RESET} → "
    fi
    read -r value
    printf -v "$var" '%s' "${value:-$default}"
}

prompt_yesno() {
    local question="$1" default="${2:-n}"
    local value
    ask "$question ${DIM}[y/N]${RESET}"
    echo -ne "      → "
    read -r value
    value="${value:-$default}"
    [[ "$value" =~ ^[Yy] ]]
}

# ── Banner ────────────────────────────────────────────────────────────────────
clear
echo ""
echo -e "${BOLD}${CYAN}"
echo "     ████████╗ ██████╗     ██████╗ ██╗████████╗██╗  ██╗██╗   ██╗██████╗ "
echo "        ██╔══╝██╔════╝    ██╔════╝ ██║╚══██╔══╝██║  ██║██║   ██║██╔══██╗"
echo "        ██║   ██║  ███╗   ██║  ███╗██║   ██║   ███████║██║   ██║██████╔╝"
echo "        ██║   ██║   ██║   ██║   ██║██║   ██║   ██╔══██║██║   ██║██╔══██╗"
echo "        ██║   ╚██████╔╝   ╚██████╔╝██║   ██║   ██║  ██║╚██████╔╝██████╔╝"
echo "        ╚═╝    ╚═════╝     ╚═════╝ ╚═╝   ╚═╝   ╚═╝  ╚═╝ ╚═════╝ ╚═════╝ "
echo -e "${RESET}"
echo -e "${BOLD}         Telegram  →  GitHub  Upload  Bot  —  Setup  Wizard${RESET}"
echo -e "${DIM}         Uploads files from Telegram directly into a GitHub repository${RESET}"
echo ""
divider
echo ""

# ── Step 1: System dependencies ───────────────────────────────────────────────
section "Step 1 / 6  —  System Dependencies"

if [[ "$(uname -s)" == "Linux" ]] && command -v apt-get &>/dev/null; then
    step "Updating package lists"
    sudo apt-get update -qq
    success "Package lists updated."

    step "Installing required packages"
    PACKAGES=(
        build-essential
        python3
        python3-dev
        python3-venv
        python3-pip
        git
        git-lfs
        curl
    )
    echo ""
    for pkg in "${PACKAGES[@]}"; do
        if dpkg -s "$pkg" &>/dev/null 2>&1; then
            echo -e "  ${GREEN}✔${RESET}  ${DIM}$pkg${RESET}  ${DIM}(already installed)${RESET}"
        else
            echo -ne "  ${CYAN}↓${RESET}  Installing ${BOLD}$pkg${RESET} …"
            sudo apt-get install -y -qq "$pkg" &>/dev/null
            echo -e "\r  ${GREEN}✔${RESET}  ${BOLD}$pkg${RESET} installed.          "
        fi
    done
    echo ""
    success "All system packages are ready."
else
    warn "Not on a Debian/Ubuntu system — skipping apt install."
    warn "Make sure these are installed: python3.10+, git, git-lfs, curl"
fi

# ── Step 2: Python version check ──────────────────────────────────────────────
section "Step 2 / 6  —  Python"

PYTHON=""
for cmd in python3.12 python3.11 python3.10 python3; do
    if command -v "$cmd" &>/dev/null; then
        if "$cmd" -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' 2>/dev/null; then
            PYTHON="$cmd"
            success "Found $($PYTHON --version)"
            break
        fi
    fi
done

if [[ -z "$PYTHON" ]]; then
    error "Python 3.10+ not found."
    error "On Ubuntu/Debian: sudo apt install python3.11 python3.11-venv"
    exit 1
fi

# ── Step 3: Virtual environment ───────────────────────────────────────────────
section "Step 3 / 6  —  Virtual Environment & Dependencies"

# If running as a one-liner (no repo cloned yet), clone it first
if [[ ! -f "requirements.txt" ]]; then
    step "Cloning the repository"
    if [[ -z "${REPO_URL:-}" ]]; then
        REPO_URL="https://github.com/mirhajian/GitHub-uploader.git"
    fi
    git clone "$REPO_URL" tg-github-uploader
    cd tg-github-uploader
    success "Repository cloned into $(pwd)"
fi

if [[ ! -d ".venv" ]]; then
    step "Creating virtual environment"
    "$PYTHON" -m venv .venv
    success "Virtual environment created."
else
    info "Virtual environment already exists — skipping."
fi

# shellcheck source=/dev/null
source .venv/bin/activate

step "Installing Python dependencies"
pip install --quiet --upgrade pip
echo ""
# Show packages as they install for a satisfying progress feel
pip install -r requirements.txt 2>&1 | while IFS= read -r line; do
    if [[ "$line" == *"Successfully installed"* ]]; then
        packages=$(echo "$line" | sed 's/Successfully installed //')
        for pkg in $packages; do
            echo -e "  ${GREEN}✔${RESET}  $pkg"
        done
    elif [[ "$line" == *"already satisfied"* ]]; then
        pkg=$(echo "$line" | awk '{print $3}')
        echo -e "  ${DIM}✔  $pkg (already satisfied)${RESET}"
    fi
done
echo ""
success "All Python dependencies installed."

# ── Step 4: .env configuration ────────────────────────────────────────────────
section "Step 4 / 6  —  Configuration  (.env)"

_write_env=false

if [[ -f ".env" ]]; then
    echo ""
    warn ".env already exists."
    if prompt_yesno "  Overwrite it with a fresh configuration?"; then
        _write_env=true
    else
        info "Keeping existing .env — skipping configuration."
    fi
else
    _write_env=true
fi

if [[ "$_write_env" == "true" ]]; then
    echo ""
    echo -e "  ${DIM}You will need the following before continuing:${RESET}"
    echo -e "  ${DIM}  • A Telegram bot token from @BotFather${RESET}"
    echo -e "  ${DIM}  • API ID + Hash from https://my.telegram.org${RESET}"
    echo -e "  ${DIM}  • A GitHub Personal Access Token (repo scope)${RESET}"
    echo ""
    divider

    # ── Telegram ──────────────────────────────────────────────────────────────
    step "Telegram credentials"
    echo ""
    prompt_required BOT_TOKEN  "Bot token  (from @BotFather)"
    prompt_required API_ID     "API ID     (from my.telegram.org — number only)"
    prompt_required API_HASH   "API Hash   (from my.telegram.org — long string)"

    # ── GitHub ────────────────────────────────────────────────────────────────
    step "GitHub credentials & repository"
    echo ""
    prompt_required GH_TOKEN   "Personal Access Token  (repo scope)"
    prompt_required GH_OWNER   "GitHub username or organisation"
    prompt_required GH_REPO    "Repository name"
    prompt_optional GH_BRANCH  "Target branch" "main"

    # ── Upload behaviour ──────────────────────────────────────────────────────
    step "Upload behaviour"
    echo ""
    prompt_optional UPLOAD_PATH "Base folder inside the repo" "uploads"
    prompt_optional CONFLICT    "File conflict strategy  (overwrite / version)" "version"
    prompt_optional LFS_MB      "Git LFS threshold in MB  (files at or above → LFS)" "50"

    # ── Cleanup ───────────────────────────────────────────────────────────────
    step "Auto-cleanup  (recommended for small VPS disks)"
    echo ""
    info  "When the repo exceeds the size limit, the oldest files are removed."
    echo ""
    if prompt_yesno "  Enable auto-cleanup?"; then
        CLEANUP_ENABLED="true"
        prompt_optional CLEANUP_MAX  "Start cleanup when repo exceeds (MB)" "800"
        prompt_optional CLEANUP_KEEP "Always keep this many newest files" "10"
    else
        CLEANUP_ENABLED="false"
        CLEANUP_MAX="800"
        CLEANUP_KEEP="10"
    fi

    # ── Access control ────────────────────────────────────────────────────────
    step "Access control"
    echo ""
    info  "Find your Telegram user ID by sending /start to @userinfobot."
    echo ""
    prompt_optional ALLOWED_IDS "Allowed user IDs  (comma-separated, empty = allow all)"
    prompt_optional ADMIN_ID    "Admin user ID  (receives error notifications)"

    # ── Write .env ────────────────────────────────────────────────────────────
    cat > .env << EOF
# Generated by setup.sh on $(date '+%Y-%m-%d %H:%M')
# ─── Telegram ────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN=${BOT_TOKEN}
TELEGRAM_API_ID=${API_ID}
TELEGRAM_API_HASH=${API_HASH}

# ─── GitHub ──────────────────────────────────────────────────────────────────
GITHUB_TOKEN=${GH_TOKEN}
GITHUB_OWNER=${GH_OWNER}
GITHUB_REPO=${GH_REPO}
GITHUB_BRANCH=${GH_BRANCH:-main}

# ─── Upload behaviour ────────────────────────────────────────────────────────
UPLOAD_BASE_PATH=${UPLOAD_PATH:-uploads}
FILE_CONFLICT_STRATEGY=${CONFLICT:-version}
LFS_THRESHOLD_MB=${LFS_MB:-50}

# ─── VPS disk cleanup ────────────────────────────────────────────────────────
CLEANUP_ENABLED=${CLEANUP_ENABLED}
CLEANUP_MAX_REPO_MB=${CLEANUP_MAX:-800}
CLEANUP_KEEP_LATEST=${CLEANUP_KEEP:-10}

# ─── Access control ──────────────────────────────────────────────────────────
ALLOWED_USER_IDS=${ALLOWED_IDS:-}
ADMIN_USER_ID=${ADMIN_ID:-}

# ─── Logging ─────────────────────────────────────────────────────────────────
LOG_LEVEL=INFO
LOG_FILE=logs/bot.log
EOF
    echo ""
    success ".env written successfully."
fi

# ── Step 5: Git LFS ───────────────────────────────────────────────────────────
section "Step 5 / 6  —  Git LFS"

LFS_MB_VAL=$(grep -E '^LFS_THRESHOLD_MB=' .env 2>/dev/null | cut -d= -f2 || echo "50")
echo ""
info  "Your LFS threshold: ${BOLD}${LFS_MB_VAL} MB${RESET}"
info  "Files at or above this size will be stored via Git LFS instead of the Contents API."
echo ""

if command -v git-lfs &>/dev/null; then
    if prompt_yesno "  Configure Git LFS in this repository now?"; then
        git lfs install --skip-repo 2>/dev/null || git lfs install
        git lfs track "uploads/**" 2>/dev/null || true
        if [[ ! -f .gitattributes ]]; then
            echo "uploads/** filter=lfs diff=lfs merge=lfs -text" > .gitattributes
        fi
        git add .gitattributes 2>/dev/null || true
        echo ""
        success "Git LFS configured."
        warn  "Remember to commit and push .gitattributes:"
        echo  ""
        echo -e "    ${CYAN}git commit -m 'chore: enable Git LFS for uploads'${RESET}"
        echo -e "    ${CYAN}git push${RESET}"
    fi
else
    warn "git-lfs not found (it should have been installed in Step 1)."
    warn "If you skipped apt install, run: sudo apt install git-lfs"
fi

# ── Step 6: systemd service ───────────────────────────────────────────────────
section "Step 6 / 6  —  Auto-start on Boot  (systemd)"

if [[ "$(uname -s)" == "Linux" ]] && command -v systemctl &>/dev/null; then
    echo ""
    info  "A systemd service keeps the bot running after reboots and auto-restarts it on crashes."
    echo ""
    if prompt_yesno "  Install systemd service for the bot?"; then
        BOT_DIR="$(pwd)"
        CURRENT_USER="$(whoami)"
        SERVICE_FILE="/etc/systemd/system/tg-github-uploader.service"

        sudo tee "$SERVICE_FILE" > /dev/null << EOF
[Unit]
Description=Telegram → GitHub Upload Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${CURRENT_USER}
WorkingDirectory=${BOT_DIR}
ExecStart=${BOT_DIR}/.venv/bin/python -m bot
Restart=on-failure
RestartSec=10
EnvironmentFile=${BOT_DIR}/.env

[Install]
WantedBy=multi-user.target
EOF
        sudo systemctl daemon-reload
        sudo systemctl enable tg-github-uploader
        echo ""
        success "systemd service installed and enabled."
        info  "Start the bot now:  ${CYAN}sudo systemctl start tg-github-uploader${RESET}"
        info  "Live log stream:    ${CYAN}sudo journalctl -u tg-github-uploader -f${RESET}"
    fi
else
    info "Not on Linux / systemctl not available — skipping."
fi

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
divider
echo ""
echo -e "${BOLD}${GREEN}  ✔  Setup complete!${RESET}"
echo ""
echo -e "  To start the bot now:"
echo ""
echo -e "    ${CYAN}source .venv/bin/activate${RESET}"
echo -e "    ${CYAN}python -m bot${RESET}"
echo ""
echo -e "  Or in the background with screen:"
echo ""
echo -e "    ${CYAN}screen -S tg2github${RESET}"
echo -e "    ${CYAN}source .venv/bin/activate && python -m bot${RESET}"
echo -e "    ${DIM}Detach: Ctrl+A then D${RESET}"
echo ""
divider
echo ""
