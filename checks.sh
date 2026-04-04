#!/bin/bash

# Check our project: formatting, linting, testing, building, etc.
# Good to call this from .git/hooks/pre-commit
# Runs checks in parallel for speed.

# Important: run with `uv run` to setup the environment

set -euo pipefail

# Parse command line arguments
# --staged-only: only run checks on the types of files that are staged for commit
# --agent-mode: only print output for failed checks (token-friendly for AI agents)
staged_only=false
agent_mode=false
while [[ $# -gt 0 ]]; do
    case $1 in
        --staged-only)
            staged_only=true
            ;;
        --agent-mode)
            agent_mode=true
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--staged-only] [--agent-mode]"
            exit 1
            ;;
    esac
    shift
done

# work from the root of the repo
cd "$(dirname "$0")"

# Create temp dir for check outputs, clean up on exit
tmp_dir=$(mktemp -d)
trap 'rm -rf "$tmp_dir"' EXIT

# ── Parallel check runner ────────────────────────────────────────────

declare -a check_names=()
declare -a check_pids=()
declare -a failed_names=()

# Start a named check running in the background.
# Usage: start_check "name" command arg1 arg2 ...
start_check() {
    local name="$1"; shift
    check_names+=("$name")
    "$@" > "$tmp_dir/$name.out" 2>&1 &
    check_pids+=($!)
}

# Wait for all checks and report results.
# Shows a spinner with live status while checks are running (skipped in agent mode).
# Returns 0 if all passed, 1 if any failed.
wait_for_checks() {
    local any_failed=0
    local green="\033[32m" red="\033[31m" dim="\033[2m" reset="\033[0m"
    local total=${#check_pids[@]}
    local spin_chars='⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏'
    local interactive=false
    if [ "$agent_mode" = false ] && [ -t 1 ]; then
        interactive=true
    fi

    # Track per-check status: empty=running, 0=pass, non-zero=fail
    declare -a check_status=()
    for i in "${!check_pids[@]}"; do
        check_status[$i]=""
    done

    # Print a result line for a completed check. In interactive mode, clears
    # the spinner line first so the result is on its own permanent line,
    # then redraws the spinner below it.
    print_result() {
        local name="$1" status="$2"
        if [ "$status" -ne 0 ]; then
            any_failed=1
            failed_names+=("$name")
            if [ "$interactive" = true ]; then
                printf "\r\033[K"
            fi
            echo -e "${red}✗ FAIL: ${name}${reset}"
            cat "$tmp_dir/$name.out"
            echo ""
        else
            if [ "$interactive" = true ]; then
                printf "\r\033[K"
                echo -e "${green}✓ PASS: ${name}${reset}"
            fi
        fi
    }

    if [ "$agent_mode" = false ] && [ -t 1 ]; then
        # Poll loop: print results as they arrive, spinner on last line
        local spin_idx=0
        local done_count=0
        while true; do
            for i in "${!check_pids[@]}"; do
                if [ -z "${check_status[$i]}" ]; then
                    if ! kill -0 "${check_pids[$i]}" 2>/dev/null; then
                        wait "${check_pids[$i]}" 2>/dev/null && check_status[$i]=0 || check_status[$i]=$?
                        done_count=$((done_count + 1))
                        print_result "${check_names[$i]}" "${check_status[$i]}"
                    fi
                fi
            done

            [ "$done_count" -eq "$total" ] && break

            local spinner="${spin_chars:$spin_idx:1}"
            spin_idx=$(( (spin_idx + 1) % ${#spin_chars} ))
            local remaining=$((total - done_count))
            printf "\r\033[K%s ${dim}running — %d remaining...${reset}" \
                "$spinner" "$remaining"
            sleep 0.1
        done
    else
        # Agent mode: wait quietly, print only failures
        for i in "${!check_pids[@]}"; do
            wait "${check_pids[$i]}" 2>/dev/null && check_status[$i]=0 || check_status[$i]=$?
            print_result "${check_names[$i]}" "${check_status[$i]}"
        done
    fi

    # Reset for next batch
    check_names=()
    check_pids=()

    return $any_failed
}

# ── Kick off all checks ──────────────────────────────────────────────

changed_files=""
if [ "$staged_only" = true ]; then
    changed_files=$(git diff --name-only --staged)
fi

# Python checks (always run)
start_check "ruff check"         uv run ruff check
start_check "ruff format"        uv run ruff format --check .
start_check "ty check"           uv run ty check

# Misspelling check
if command -v misspell >/dev/null 2>&1; then
    start_check "misspell" bash -c 'find . -type f -not -path "*/node_modules/*" -not -path "*/\.*" -not -path "*/dist/*" -not -path "*/desktop/build/*" -not -path "*/app/web_ui/build/*" -print0 | xargs -0 misspell -error'
else
    echo -e "\033[33mWarning: misspell not found, skipping. Install: https://github.com/golangci/misspell\033[0m"
fi

# OpenAPI schema check
start_check "openapi schema" bash -c 'app/web_ui/src/lib/check_schema.sh'

# Web UI checks
if [ "$staged_only" = false ] || [[ "$changed_files" == *"app/web_ui/"* ]]; then
    start_check "web format"  bash -c 'cd app/web_ui && npm run format_check'
    start_check "web lint"    bash -c 'cd app/web_ui && npm run lint'
    start_check "web check"   bash -c 'cd app/web_ui && npm run check'
    start_check "web test"    bash -c 'cd app/web_ui && npm run test_run'
    start_check "web build"   bash -c 'cd app/web_ui && npm run build'
fi

# Python tests
if [ "$staged_only" = false ] || echo "$changed_files" | grep -q "\.py$"; then
    start_check "python tests" python3 -m pytest --benchmark-quiet -q -n auto .
fi

# ── Wait and summarize ────────────────────────────────────────────────

if ! wait_for_checks; then
    failed_list=$(IFS=','; echo "${failed_names[*]}" | sed 's/,/, /g')
    echo -e "\n\033[31mSome checks failed: ${failed_list}\033[0m"
    exit 1
fi

if [ "$agent_mode" = false ] && [ -t 1 ]; then
    echo -e "\n\033[32mAll checks passed.\033[0m"
fi
