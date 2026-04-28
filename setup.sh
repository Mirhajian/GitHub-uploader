#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# setup.sh — Interactive first-time setup for the Telegram → GitHub Upload Bot
#
# What this script does:
#   1. Updates apt and installs all system dependencies
#   2. Checks Python version (3.10+)
#   3. Creates a virtual environment and installs Python dependencies
#   4. Walks you through every config value and writes .env
#   5. Enables Git LFS on the target repository (fully automated via API)
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
    git clone -b supporting-github-lfs-for-large-files --single-branch "$REPO_URL" tg-github-uploader
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
section "Step 5 / 6  —  Git LFS  (fully automated)"

# Read the values we need from .env (works whether we just wrote it or it existed)
_lfs_threshold=$(grep -E '^LFS_THRESHOLD_MB=' .env 2>/dev/null | cut -d= -f2 || echo "50")
_gh_token=$(grep -E '^GITHUB_TOKEN='  .env 2>/dev/null | cut -d= -f2 || echo "")
_gh_owner=$(grep -E '^GITHUB_OWNER='  .env 2>/dev/null | cut -d= -f2 || echo "")
_gh_repo=$( grep -E '^GITHUB_REPO='   .env 2>/dev/null | cut -d= -f2 || echo "")
_gh_branch=$(grep -E '^GITHUB_BRANCH=' .env 2>/dev/null | cut -d= -f2 || echo "main")

echo ""
info "Your LFS threshold: ${BOLD}${_lfs_threshold} MB${RESET}"
info "Files at or above this size will be stored via Git LFS."
echo ""

# ── 5a. Install git-lfs hooks in the local clone ─────────────────────────────
if command -v git-lfs &>/dev/null; then
    git lfs install --skip-repo 2>/dev/null || git lfs install
    success "git-lfs hooks installed locally."
else
    warn "git-lfs not found — skipping local install (was it installed in Step 1?)."
fi

# ── 5b. Push .gitattributes to the remote repo via GitHub API ────────────────
#
# This is the part that used to require manual work on a local machine.
# We do it entirely through the GitHub Contents API, so no local clone of the
# *target* repo is needed.
#
if [[ -n "$_gh_token" && -n "$_gh_owner" && -n "$_gh_repo" ]]; then
    echo ""
    step "Configuring Git LFS on the remote repository (${_gh_owner}/${_gh_repo})"
    echo ""

    _GITATTRIBUTES_CONTENT="* filter=lfs diff=lfs merge=lfs -text"
    _GITATTRIBUTES_B64=$(printf '%s\n' "$_GITATTRIBUTES_CONTENT" | base64 -w 0)
    _API="https://api.github.com/repos/${_gh_owner}/${_gh_repo}/contents/.gitattributes"

    # Check whether .gitattributes already exists (need its SHA to update it)
    _existing_sha=""
    _check_resp=$(curl -s -o /tmp/_ga_check.json -w "%{http_code}" \
        -H "Authorization: token ${_gh_token}" \
        -H "Accept: application/vnd.github.v3+json" \
        "$_API?ref=${_gh_branch}")

    if [[ "$_check_resp" == "200" ]]; then
        _existing_sha=$(python3 -c "import json,sys; d=json.load(open('/tmp/_ga_check.json')); print(d.get('sha',''))" 2>/dev/null || echo "")
        _existing_content_b64=$(python3 -c "import json,sys; d=json.load(open('/tmp/_ga_check.json')); print(d.get('content','').replace('\n',''))" 2>/dev/null || echo "")

        # Decode existing content and check if LFS is already configured
        _existing_content=$(printf '%s' "$_existing_content_b64" | base64 -d 2>/dev/null || echo "")
        if echo "$_existing_content" | grep -q "filter=lfs"; then
            success ".gitattributes already contains LFS config — no changes needed."
            _skip_lfs_push=true
        else
            info ".gitattributes exists but has no LFS config — will update it."
            _skip_lfs_push=false
            # Merge: append our line to whatever is already there
            _merged_content=$(printf '%s\n%s\n' "$_existing_content" "$_GITATTRIBUTES_CONTENT")
            _GITATTRIBUTES_B64=$(printf '%s' "$_merged_content" | base64 -w 0)
        fi
    elif [[ "$_check_resp" == "404" ]]; then
        info ".gitattributes not found — will create it."
        _skip_lfs_push=false
    else
        warn "Could not check .gitattributes (HTTP ${_check_resp}) — skipping LFS remote setup."
        _skip_lfs_push=true
    fi

    if [[ "${_skip_lfs_push:-false}" == "false" ]]; then
        # Build JSON payload (with or without sha field)
        if [[ -n "$_existing_sha" ]]; then
            _payload=$(printf '{"message":"chore: enable Git LFS for all files","content":"%s","branch":"%s","sha":"%s"}' \
                "$_GITATTRIBUTES_B64" "$_gh_branch" "$_existing_sha")
        else
            _payload=$(printf '{"message":"chore: enable Git LFS for all files","content":"%s","branch":"%s"}' \
                "$_GITATTRIBUTES_B64" "$_gh_branch")
        fi

        _put_resp=$(curl -s -o /tmp/_ga_put.json -w "%{http_code}" \
            -X PUT \
            -H "Authorization: token ${_gh_token}" \
            -H "Accept: application/vnd.github.v3+json" \
            -H "Content-Type: application/json" \
            -d "$_payload" \
            "$_API")

        if [[ "$_put_resp" == "200" || "$_put_resp" == "201" ]]; then
            success ".gitattributes pushed to ${_gh_owner}/${_gh_repo} (branch: ${_gh_branch})."
            success "Git LFS is now active on the remote repository. ✓"
        else
            _err_msg=$(python3 -c "import json; d=json.load(open('/tmp/_ga_put.json')); print(d.get('message','unknown'))" 2>/dev/null || echo "unknown")
            warn "Could not push .gitattributes (HTTP ${_put_resp}: ${_err_msg})."
            warn "You may need to do this manually — see the README for instructions."
        fi
    fi
else
    warn "GitHub credentials not found in .env — skipping remote LFS setup."
    warn "Run setup.sh again after filling in .env, or follow the manual steps in the README."
fi

# Clean up temp files
rm -f /tmp/_ga_check.json /tmp/_ga_put.json

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
