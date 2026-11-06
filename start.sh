#!/usr/bin/env bash
# =====================================================================
#  LM Studio Auto Optimizer - unified launcher (Linux/macOS)
#  One entry point for everything: Web UI, optimize, tests, cleanup.
# =====================================================================
set -euo pipefail
cd "$(dirname "$0")"

LOGFILE="data/logs/startup.log"
mkdir -p "data/logs"

log() {
    echo "[$(date '+%H:%M:%S')] $1" >> "$LOGFILE"
}

log "=== LM Studio Auto Optimizer launcher ==="
log "WorkDir: $(pwd)"

# --- Python / venv check --------------------------------------------------
echo "[1/3] Checking Python..."
if ! command -v python3 >/dev/null 2>&1; then
    echo "[ERROR] python3 not found. Install Python 3.11+ first."
    exit 1
fi
PYVER=$(python3 --version 2>&1)
echo "       Python OK - $PYVER"

echo "[2/3] Checking virtual environment and dependencies..."
if [ -x ".venv/bin/python" ]; then
    PYBIN=".venv/bin/python"
else
    echo "       Creating .venv - one-time step, may take a few minutes..."
    log "creating .venv"
    python3 -m venv .venv >> "$LOGFILE" 2>&1
    echo "       Installing dependencies - one-time step, may take a few minutes..."
    log "command: pip install -e .[dev]"
    .venv/bin/python -m pip install --upgrade pip >> "$LOGFILE" 2>&1
    .venv/bin/python -m pip install -e ".[dev]" >> "$LOGFILE" 2>&1
fi

# Verify import works
if ! "$PYBIN" -c "import lm_optimizer" >> "$LOGFILE" 2>&1; then
    echo "       Dependencies missing, installing - may take a few minutes..."
    log "command: pip install -e .[dev] - repair"
    .venv/bin/python -m pip install --upgrade pip >> "$LOGFILE" 2>&1
    .venv/bin/python -m pip install -e ".[dev]" >> "$LOGFILE" 2>&1
fi
echo "       Dependencies OK"

# --- Menu -----------------------------------------------------------------
menu() {
    echo ""
    echo "========================================"
    echo "  LM Studio Auto Optimizer"
    echo "========================================"
    echo "  [1] Start Web UI - server plus browser"
    echo "  [2] Optimize one model"
    echo "  [3] Optimize all models one by one"
    echo "  [4] Run tests (one file or all)"
    echo "  [5] Check LM Studio connection"
    echo "  [6] List available models"
    echo "  [7] Install / repair environment"
    echo "  [8] Cleanup logs and caches"
    echo "  [9] Delete failed sandbox runs"
    echo "  [10] Exit"
    echo ""
    read -rp "Select 1-10: " choice
    case "$choice" in
        1) webui ;;
        2) optimize_one ;;
        3) optimize_all ;;
        4) tests_menu ;;
        5) check ;;
        6) models ;;
        7) install ;;
        8) cleanup ;;
        9) cleanup_failed_sandbox ;;
        10) exit 0 ;;
        *) echo "Invalid choice."; menu ;;
    esac
}

# --- Web UI ---------------------------------------------------------------
webui() {
    echo ""
    echo "Starting LM Studio Auto Optimizer Web UI..."
    log "starting web server"
    "$PYBIN" -m lm_optimizer.web_main &
    SERVER_PID=$!
    log "server PID: $SERVER_PID"

    echo "[INFO] Waiting for http://127.0.0.1:8080 ..."
    READY=0
    for i in $(seq 1 30); do
        if curl -sf http://127.0.0.1:8080/api/status >/dev/null 2>&1; then
            READY=1
            break
        fi
        sleep 1
    done

    if [ "$READY" = "1" ]; then
        echo ""
        echo "LM Studio Auto Optimizer is running:"
        echo "  http://127.0.0.1:8080"
        echo ""
        echo "Opening browser..."
        log "ready - opening browser"
        if command -v xdg-open >/dev/null 2>&1; then
            xdg-open http://127.0.0.1:8080/ &
        elif command -v open >/dev/null 2>&1; then
            open http://127.0.0.1:8080/ &
        fi
        echo ""
        echo "Server log streams live in this window."
        echo "Launcher log: $(pwd)/$LOGFILE"
        echo ""
        echo "Press ENTER to STOP the server and return to the menu."
        read -r
        kill "$SERVER_PID" 2>/dev/null || true
        wait "$SERVER_PID" 2>/dev/null || true
    else
        echo ""
        echo "========================================"
        echo "LM Studio Auto Optimizer FAILED"
        echo "========================================"
        echo "Reason: server did not answer /api/status within 30 seconds."
        echo ""
        echo "Last log lines:"
        tail -20 "$LOGFILE" 2>/dev/null || true
        echo ""
        echo "Log: $(pwd)/$LOGFILE"
        kill "$SERVER_PID" 2>/dev/null || true
    fi
    menu
}

# --- Optimize one model ---------------------------------------------------
optimize_one() {
    # Preflight check
    if ! "$PYBIN" -m lm_optimizer status --quick >/dev/null 2>&1; then
        echo ""
        echo "========================================"
        echo "LM Studio is not reachable."
        echo "========================================"
        echo "The optimizer cannot start without the server."
        echo "Check that LM Studio is running with the Developer API enabled."
        echo ""
        read -rp "LM Studio URL, empty returns to the menu: " OSRV
        if [ -z "$OSRV" ]; then
            menu
            return
        fi
        if ! "$PYBIN" -m lm_optimizer status --quick --url "$OSRV" >/dev/null 2>&1; then
            echo "Still unreachable at $OSRV - nothing was started."
            menu
            return
        fi
        export LM_STUDIO_BASE_URL="$OSRV"
        echo "Using $OSRV for this session."
    fi

    echo ""
    "$PYBIN" -m lm_optimizer models --full-ids
    echo ""
    read -rp "Model number or full ID - empty returns to menu: " OSEL
    if [ -z "$OSEL" ]; then
        menu
        return
    fi
    OMODEL="$OSEL"
    # Resolve number to full ID if needed
    FOUND=$("$PYBIN" -m lm_optimizer models --full-ids 2>/dev/null | awk -F'|' -v n="$OSEL" '$1==n {print $2}')
    if [ -n "$FOUND" ]; then
        OMODEL="$FOUND"
    fi
    read -rp "Profile speed/balanced/context/quality - default balanced: " OPROFILE
    OPROFILE=${OPROFILE:-balanced}
    echo "Selected model: $OMODEL"
    echo "Profile: $OPROFILE"
    log "optimize $OMODEL profile $OPROFILE"
    "$PYBIN" -m lm_optimizer optimize "$OMODEL" --profile "$OPROFILE"
    echo ""
    echo "Finished with exit code $?. Press any key for menu."
    read -r
    menu
}

# --- Optimize all models --------------------------------------------------
optimize_all() {
    # Preflight check
    if ! "$PYBIN" -m lm_optimizer status --quick >/dev/null 2>&1; then
        echo ""
        echo "========================================"
        echo "LM Studio is not reachable."
        echo "========================================"
        echo "Check that LM Studio is running with the Developer API enabled."
        echo ""
        read -rp "LM Studio URL, empty returns to the menu: " OSRV
        if [ -z "$OSRV" ]; then
            menu
            return
        fi
        if ! "$PYBIN" -m lm_optimizer status --quick --url "$OSRV" >/dev/null 2>&1; then
            echo "Still unreachable at $OSRV - nothing was started."
            menu
            return
        fi
        export LM_STUDIO_BASE_URL="$OSRV"
        echo "Using $OSRV for this session."
    fi

    echo ""
    "$PYBIN" -m lm_optimizer models --full-ids
    echo ""
    echo "Runs the full pipeline per selected model, small first. This takes hours."
    echo "You will pick quick/standard/full/benchmark for each model after connecting."
    read -rp "Profile speed/balanced/context/quality - default balanced: " OPROFILE
    OPROFILE=${OPROFILE:-balanced}
    read -rp "Run ONLY these numbers from the list (e.g. 6,9), empty = all models: " OSELECT
    if [ -z "$OSELECT" ]; then
        log "optimize-all profile $OPROFILE"
        "$PYBIN" -m lm_optimizer auto --profile "$OPROFILE"
    else
        # Convert numbers to model IDs
        OSELECT_IDS=""
        for N in $OSELECT; do
            FOUND=$("$PYBIN" -m lm_optimizer models --full-ids 2>/dev/null | awk -F'|' -v n="$N" '$1==n {print $2}')
            if [ -n "$FOUND" ]; then
                OSELECT_IDS="$OSELECT_IDS $FOUND"
            else
                OSELECT_IDS="$OSELECT_IDS $N"
            fi
        done
        log "optimize-all profile $OPROFILE only $OSELECT"
        "$PYBIN" -m lm_optimizer auto $OSELECT_IDS --profile "$OPROFILE"
    fi
    echo ""
    echo "Finished with exit code $?. Press any key for menu."
    read -r
    menu
}

# --- Tests menu -----------------------------------------------------------
tests_menu() {
    echo ""
    echo "--- Tests ---"
    echo "  [1] Run ALL tests (pytest -q)"
    echo "  [2] Run ONE test file"
    echo "  [3] Back to main menu"
    echo ""
    read -rp "Select 1-3: " TCHOICE
    case "$TCHOICE" in
        1) tests_all ;;
        2) tests_one ;;
        3) menu ;;
        *) echo "Invalid choice."; tests_menu ;;
    esac
}

tests_all() {
    # Preflight check
    if ! "$PYBIN" -m lm_optimizer status --quick >/dev/null 2>&1; then
        echo ""
        echo "LM Studio is not reachable."
        read -rp "LM Studio URL, empty returns to the menu: " OSRV
        if [ -z "$OSRV" ]; then
            menu
            return
        fi
        if ! "$PYBIN" -m lm_optimizer status --quick --url "$OSRV" >/dev/null 2>&1; then
            echo "Still unreachable at $OSRV - nothing was started."
            menu
            return
        fi
        export LM_STUDIO_BASE_URL="$OSRV"
    fi
    echo "Running ALL tests..."
    "$PYBIN" -m pytest -q
    echo ""
    echo "Finished with exit code $?. Press any key for menu."
    read -r
    menu
}

tests_one() {
    echo ""
    echo "Available test files:"
    find tests lm_optimizer/tests -name "*.py" -type f 2>/dev/null | sort
    echo ""
    read -rp "Enter test file path (e.g. tests/test_sandbox_lab.py): " TFILE
    if [ -z "$TFILE" ]; then
        tests_menu
        return
    fi
    # Preflight check
    if ! "$PYBIN" -m lm_optimizer status --quick >/dev/null 2>&1; then
        echo ""
        echo "LM Studio is not reachable."
        read -rp "LM Studio URL, empty returns to the menu: " OSRV
        if [ -z "$OSRV" ]; then
            menu
            return
        fi
        if ! "$PYBIN" -m lm_optimizer status --quick --url "$OSRV" >/dev/null 2>&1; then
            echo "Still unreachable at $OSRV - nothing was started."
            menu
            return
        fi
        export LM_STUDIO_BASE_URL="$OSRV"
    fi
    echo "Running: $TFILE"
    "$PYBIN" -m pytest "$TFILE" -q
    echo ""
    echo "Finished with exit code $?. Press any key for menu."
    read -r
    tests_menu
}

# --- Check connection -----------------------------------------------------
check() {
    "$PYBIN" -m lm_optimizer status --quick
    echo ""
    read -rp "Press any key for menu..." -r
    menu
}

# --- List models ----------------------------------------------------------
models() {
    "$PYBIN" -m lm_optimizer models
    echo ""
    "$PYBIN" -m lm_optimizer models --full-ids
    echo ""
    echo "Copy a full ID from the numbered list above."
    read -rp "Press any key for menu..." -r
    menu
}

# --- Install / repair -----------------------------------------------------
install() {
    echo ""
    echo "  [1] Create .venv and install dependencies"
    echo "  [2] Back to main menu"
    echo ""
    read -rp "Select 1-2: " ICHOICE
    case "$ICHOICE" in
        1) do_install ;;
        2) menu ;;
        *) echo "Invalid choice."; install ;;
    esac
}

do_install() {
    if [ ! -d ".venv" ]; then
        echo "Creating .venv..."
        python3 -m venv .venv
    fi
    # shellcheck disable=SC1091
    source ".venv/bin/activate"
    python -m pip install --upgrade pip
    pip install -e ".[dev]"
    if [ ! -f ".env" ]; then
        cp ".env.example" ".env"
        echo "Created .env from example."
    else
        echo ".env already exists - kept."
    fi
    echo ""
    echo "Install complete. Press any key for menu."
    read -r
    menu
}

# --- Cleanup --------------------------------------------------------------
cleanup() {
    echo ""
    echo "This will delete data/logs contents and Python/test caches only."
    echo "Kept: optimizer.db, data/reports, data/checkpoints, results/, models."
    echo ""
    read -rp "Type YES to continue: " CCONFIRM
    if [ "$CCONFIRM" != "YES" ]; then
        menu
        return
    fi
    "$PYBIN" tools/cleanup.py --yes --logs-only
    echo ""
    echo "Done. Press any key for menu."
    read -r
    menu
}

cleanup_failed_sandbox() {
    echo ""
    echo "This will delete ALL failed sandbox runs (history + artifact directories)."
    echo "This cannot be undone."
    echo ""
    read -rp "Type YES to continue: " CCONFIRM
    if [ "$CCONFIRM" != "YES" ]; then
        menu
        return
    fi
    "$PYBIN" -c "from lm_optimizer.services.sandbox_history import clear_failed_sandbox_runs; print('Deleted:', clear_failed_sandbox_runs())"
    echo ""
    echo "Done. Press any key for menu."
    read -r
    menu
}

# --- Entry point ----------------------------------------------------------
menu
