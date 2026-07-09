#!/usr/bin/env bash
set -euo pipefail

# Per-repo state: the chosen session slug, and the comment ids already returned
# (so a comment is never shown twice).
STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/human-review"
AGENT_USER="agent"

usage() {
    cat <<EOF
Usage: $(basename "$0") <subcommand> [--repo PATH] [args...]

Subcommands:
  start [--repo PATH] [SCOPE...]
      Open the review for SCOPE and print the session slug. SCOPE is 'working'
      (uncommitted changes, the default), a git revision/range, or 'pr <n>'.
      When the human finishes, a trigger message is sent back to read comments.

  comments [--repo PATH]
      Print new human comments for the current review as a JSON array.

  add [--repo PATH] <flags> [text]
      Post a comment to the current review; prints it as JSON. Supports
      --target-file, --line, --end-line, --side, --type.
EOF
}

die() { echo "error: $*" >&2; exit 1; }

need() { command -v "$1" >/dev/null 2>&1 || die "missing dependency: $1"; }

sha16() { printf '%s' "$1" | sha256sum | cut -c1-16; }

prune_state() {
    [ -d "$STATE_DIR" ] || return 0
    find "$STATE_DIR" -maxdepth 1 -type f -mtime +7 -delete 2>/dev/null || true
}

resolve_repo() {
    local p="$1"
    [ -d "$p" ] || die "repo path does not exist: $p"
    (cd "$p" && pwd)
}

parse_repo_arg() {
    REPO="."
    PASSTHRU=()
    while [ $# -gt 0 ]; do
        case "$1" in
            --repo)
                shift
                [ $# -gt 0 ] || die "--repo requires an argument"
                REPO="$1"
                shift
                ;;
            --repo=*)
                REPO="${1#--repo=}"
                shift
                ;;
            *)
                PASSTHRU+=("$1")
                shift
                ;;
        esac
    done
}

resolve_slug() {
    local repo="$1"
    local repohash slugfile list active_count active_slug saved
    repohash="$(sha16 "$repo")"
    slugfile="$STATE_DIR/${repohash}.slug"

    list="$(tuicr review list --repo "$repo")"

    active_count="$(printf '%s' "$list" | jq '[.[] | select(.active == true)] | length')"
    if [ "$active_count" = "1" ]; then
        active_slug="$(printf '%s' "$list" | jq -r '[.[] | select(.active == true)][0].slug')"
        printf '%s\n' "$active_slug" > "$slugfile"
        printf '%s' "$active_slug"
        return
    fi

    if [ -f "$slugfile" ]; then
        saved="$(cat "$slugfile")"
        if printf '%s' "$list" | jq -e --arg s "$saved" 'any(.slug == $s)' >/dev/null; then
            printf '%s\n' "$saved" > "$slugfile"
            printf '%s' "$saved"
            return
        fi
    fi

    local total
    total="$(printf '%s' "$list" | jq 'length')"
    if [ "$total" = "1" ]; then
        active_slug="$(printf '%s' "$list" | jq -r '.[0].slug')"
        printf '%s\n' "$active_slug" > "$slugfile"
        printf '%s' "$active_slug"
        return
    fi

    {
        echo "error: cannot determine which tuicr session to use; ask the human which slug to use."
        echo "available slugs:"
        printf '%s' "$list" | jq -r '.[].slug' | sed 's/^/  - /'
    } >&2
    exit 1
}

preflight() {
    need tuicr; need jq; need tmux
    [ -n "${TMUX:-}" ] || die "not in tmux; restart the agent inside tmux."
}

scope_to_tuicr() {
    # Translate the wrapper's scope vocabulary into tuicr arguments so the
    # caller never has to know tuicr's own flags.
    if [ "${#PASSTHRU[@]}" -eq 0 ] || [ "${PASSTHRU[0]}" = "working" ] || [ "${PASSTHRU[0]}" = "uncommitted" ]; then
        TUICR_ARGS=(-w)
    elif [ "${PASSTHRU[0]}" = "pr" ]; then
        TUICR_ARGS=("${PASSTHRU[@]}")
    else
        TUICR_ARGS=(-r "${PASSTHRU[@]}")
    fi
}

cmd_start() {
    parse_repo_arg "$@"
    preflight
    prune_state

    local repo
    repo="$(resolve_repo "$REPO")"

    if tmux list-panes -a -F '#{pane_current_command}' 2>/dev/null | grep -qx tuicr; then
        die "tuicr already running in another pane; ask the human to close it first (press q)."
    fi

    local agent_pane win_h lines trigger tuicr_cmd new_pane
    agent_pane="$TMUX_PANE"
    win_h="$(tmux display-message -p '#{window_height}')"
    lines=$(( win_h * 80 / 100 ))
    [ "$lines" -lt 1 ] && lines=1

    local -a TUICR_ARGS
    scope_to_tuicr
    tuicr_cmd="tuicr"
    local a
    for a in "${TUICR_ARGS[@]}"; do
        tuicr_cmd+=" $(printf '%q' "$a")"
    done

    trigger="Human finished the review. Run the human-review 'comments' subcommand to read the new comments."

    local launcher
    launcher="$(mktemp "${TMPDIR:-/tmp}/tuicr-launch.XXXXXX")"
    {
        printf '#!/usr/bin/env bash\n'
        printf 'if %s; then\n' "$tuicr_cmd"
        printf '  tmux send-keys -t %q -l %q\n' "$agent_pane" "$trigger"
        printf '  tmux send-keys -t %q Enter\n' "$agent_pane"
        printf 'fi\n'
        printf 'rm -f -- "$0"\n'
    } > "$launcher"

    new_pane="$(tmux split-window -d -P -F '#{pane_id}' -b -l "$lines" -c "$repo" "bash $(printf '%q' "$launcher")")"
    tmux select-pane -t "$new_pane"

    mkdir -p "$STATE_DIR"
    local repohash slugfile slug i
    repohash="$(sha16 "$repo")"
    slugfile="$STATE_DIR/${repohash}.slug"

    for i in $(seq 1 30); do
        sleep 1
        slug="$(tuicr review list --repo "$repo" 2>/dev/null | jq -r '[.[] | select(.active == true)][0].slug // empty')"
        if [ -n "$slug" ]; then
            printf '%s\n' "$slug" > "$slugfile"
            printf '%s\n' "$slug"
            return
        fi
    done
    die "tuicr did not create a session within 30s (maybe it failed to start)."
}

cmd_comments() {
    parse_repo_arg "$@"
    need tuicr; need jq
    local repo slug slughash seenfile comments filtered
    repo="$(resolve_repo "$REPO")"
    mkdir -p "$STATE_DIR"
    slug="$(resolve_slug "$repo")"
    slughash="$(sha16 "$slug")"
    seenfile="$STATE_DIR/${slughash}.seen"
    touch "$seenfile"

    comments="$(tuicr review comments --repo "$repo" --session "$slug")"
    filtered="$(printf '%s' "$comments" | jq --rawfile seenraw "$seenfile" '
        ($seenraw | split("\n") | map(select(length > 0))) as $s
        | map(select(.id as $id | ($s | index($id | tostring)) | not))
    ')"

    printf '%s\n' "$filtered"

    printf '%s' "$filtered" | jq -r '.[].id | tostring' >> "$seenfile"
}

cmd_add() {
    parse_repo_arg "$@"
    need tuicr; need jq
    local repo slug slughash seenfile out id
    repo="$(resolve_repo "$REPO")"
    mkdir -p "$STATE_DIR"
    slug="$(resolve_slug "$repo")"
    slughash="$(sha16 "$slug")"
    seenfile="$STATE_DIR/${slughash}.seen"
    touch "$seenfile"

    if [ "${#PASSTHRU[@]}" -gt 0 ]; then
        out="$(tuicr review add --repo "$repo" --session "$slug" --username "$AGENT_USER" "${PASSTHRU[@]}")"
    else
        out="$(tuicr review add --repo "$repo" --session "$slug" --username "$AGENT_USER")"
    fi
    if ! id="$(printf '%s' "$out" | jq -r '.id // empty' 2>/dev/null)" || [ -z "$id" ] || [ "$id" = "null" ]; then
        printf '%s\n' "$out"
        die "comment was posted but its id could not be parsed; it may resurface in 'comments' output"
    fi
    printf '%s\n' "$id" >> "$seenfile"
    printf '%s\n' "$out"
}

main() {
    [ $# -ge 1 ] || { usage >&2; exit 1; }
    case "$1" in
        -h|--help) usage; exit 0 ;;
        start) shift; cmd_start "$@" ;;
        comments) shift; cmd_comments "$@" ;;
        add) shift; cmd_add "$@" ;;
        *) usage; exit 1 ;;
    esac
}

mkdir -p "$STATE_DIR"
main "$@"
