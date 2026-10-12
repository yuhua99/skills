#!/usr/bin/env bash
set -euo pipefail

# Per-repo state: the chosen session slug, and the human comment ids already
# returned (so a comment is never shown twice).
STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/human-review"
AGENT_USER="agent"

usage() {
    cat <<EOF
Usage: $(basename "$0") <subcommand> [--repo PATH] [args...]

Subcommands:
  start [--repo PATH] [SCOPE...] [--comments FILE]
      Open the review for SCOPE and print the session slug. SCOPE is 'working'
      (uncommitted changes, the default), a git revision/range, or 'pr <n>'.
      With --comments, post FILE (see add --input) before showing the review.
      When the human finishes, a trigger message is sent back with new comments.

  comments [--repo PATH] [--mine]
      Print new human comments for the current review as a JSON array.
      --mine prints all agent comments instead (for their ids).

  add [--repo PATH] <flags> [text]
      Post a comment to the current review; prints it as JSON. Supports
      --target-file, --line, --end-line, --side, --type.

  add [--repo PATH] --input FILE
      Post every JSON object in FILE, in order (keys: file, line, end_line,
      side, comment_type, content, commit); prints {id, location} per comment.
      'commit' without 'file' targets that commit's message entry.

  delete [--repo PATH] <comment-id>
      Delete an agent comment from the current review.
EOF
}

die() { echo "error: $*" >&2; exit 1; }

need() { command -v "$1" >/dev/null 2>&1 || die "missing dependency: $1"; }

sha16() { printf '%s' "$1" | sha256sum | cut -c1-16; }

prune_state() {
    [ -d "$STATE_DIR" ] || return 0
    find "$STATE_DIR" -maxdepth 1 -type f -mtime +7 -delete 2>/dev/null || true
}

# Comments file -> one compact JSON object per line; rejects unknown keys,
# which tuicr would silently ignore (misplacing or untyping the comment).
# A commit-level comment ('commit', no 'file') lands on tuicr's synthetic
# "Commit Message (<sha7>)" entry; the libgit2 backend abbreviates to 7.
read_comments() {
    jq -c 'if type == "object" and has("content") and (keys - ["file","line","end_line","side","comment_type","content","commit"] == []) then . else error("bad comment: \(tojson)") end
        | if has("commit") and (has("file") | not) then
            if (.commit | type == "string" and length >= 7) and (has("line") | not) then .file = "Commit Message (\(.commit[0:7]))" else error("commit-level comment needs a sha of 7+ chars and no line: \(tojson)") end
          else . end' "$1"
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
    local repo="$1" slugfile
    slugfile="$STATE_DIR/$(sha16 "$repo").slug"
    if [ -s "$slugfile" ]; then
        touch "$slugfile"
        cat "$slugfile"
        return
    fi
    resolve_slug_from_list "$repo"
}

resolve_slug_from_list() {
    local repo="$1"
    local repohash slugfile list active_count active_slug
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
    need tuicr; need jq
    if [ "${HERDR_ENV:-}" = 1 ]; then
        need herdr
        MUX=herdr
    elif [ -n "${TMUX:-}" ]; then
        need tmux
        MUX=tmux
    else
        die "not in herdr or tmux; restart the agent inside one."
    fi
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

    local repo wrapper_path source comments_file="" i
    local -a scope=()
    for ((i = 0; i < ${#PASSTHRU[@]}; i++)); do
        if [ "${PASSTHRU[i]}" = "--comments" ]; then
            i=$((i + 1))
            comments_file="${PASSTHRU[i]:-}"
            [ -n "$comments_file" ] || die "--comments requires a file"
        else
            scope+=("${PASSTHRU[i]}")
        fi
    done
    PASSTHRU=("${scope[@]}")
    # Reject a bad file before a review window opens.
    if [ -n "$comments_file" ]; then
        local drafts
        drafts="$(read_comments "$comments_file")" || die "invalid comments file $comments_file"
        [ -n "$drafts" ] || die "no comments in $comments_file"
    fi
    repo="$(resolve_repo "$REPO")"
    source="${BASH_SOURCE[0]}"
    if [[ "$source" != */* ]]; then
        source="$(command -v "$source")"
    fi
    wrapper_path="$(cd -- "$(dirname -- "$source")" && pwd -P)/$(basename -- "$source")"

    local agent_pane tuicr_cmd new_window tab_id before
    if [ "$MUX" = herdr ]; then
        if herdr tab list --workspace "$HERDR_WORKSPACE_ID" | jq -e '.result.tabs | any(.label == "review")' >/dev/null; then
            die "review tab already open; ask the human to close it first (press q)."
        fi
        agent_pane="$HERDR_PANE_ID"
    else
        if tmux list-windows -F '#{window_name}' 2>/dev/null | grep -qx review; then
            die "review window already open; ask the human to close it first (press q)."
        fi
        agent_pane="$TMUX_PANE"
    fi
    before="$(tuicr review list --repo "$repo" 2>/dev/null | jq -r '.[].slug' || true)"

    local -a TUICR_ARGS
    scope_to_tuicr
    tuicr_cmd="tuicr"
    local a
    for a in "${TUICR_ARGS[@]}"; do
        tuicr_cmd+=" $(printf '%q' "$a")"
    done

    local launcher
    launcher="$(mktemp "${TMPDIR:-/tmp}/tuicr-launch.XXXXXX")"
    {
        printf '#!/usr/bin/env bash\n'
        printf 'if %s; then\n' "$tuicr_cmd"
        printf '  if comments="$(%q comments --repo %q)"; then\n' "$wrapper_path" "$repo"
        printf '    submit=1\n'
        printf '    if printf "%%s" "$comments" | jq -e "type == \\\"array\\\" and length == 0" >/dev/null; then\n'
        printf '      progress="$(tuicr review list --repo %q | jq -r --arg s "$(cat %q)" ".[] | select(.slug == \\$s) | \\"\\(.reviewed_count)/\\(.file_count)\\"")"\n' "$repo" "$STATE_DIR/$(sha16 "$repo").slug"
        printf '      if [ "${progress%%%%/*}" = "${progress#*/}" ]; then\n'
        printf '        message="approved"\n'
        printf '      else\n'
        printf '        message="Human quit with $progress files reviewed and no new comments."\n'
        printf '      fi\n'
        printf '      submit=0\n'
        printf '    else\n'
        printf '      comments_text="$(printf "%%s" "$comments" | jq -r ".[] | \\"- \\(.location): \\(.content)\\"")"\n'
        printf '      message="Human finished the review. New comments:\n$comments_text"\n'
        printf '    fi\n'
        printf '  else\n'
        printf '    message="Human finished the review, but fetching new comments failed. Run the human-review comments subcommand manually."\n'
        printf '    submit=1\n'
        printf '  fi\n'
        if [ "$MUX" = herdr ]; then
            # agent prompt pastes multi-line text safely before pressing Enter.
            printf '  if [ "$submit" = 1 ]; then\n'
            # Fall back to plain text (not submitted) so comments are not lost when the agent is blocked.
            printf '    herdr agent prompt %q "$message" >/dev/null 2>&1 || herdr pane send-text %q "$message" >/dev/null 2>&1\n' "$agent_pane" "$agent_pane"
            printf '  else\n'
            printf '    herdr pane send-text %q "$message" >/dev/null 2>&1\n' "$agent_pane"
            printf '  fi\n'
        else
            printf '  if tmux send-keys -t %q -l "$message" 2>/dev/null; then\n' "$agent_pane"
            printf '    if [ "$submit" = 1 ]; then\n'
            printf '      tmux send-keys -t %q Enter 2>/dev/null || true\n' "$agent_pane"
            printf '    fi\n'
            printf '  fi\n'
        fi
        printf 'fi\n'
        printf 'rm -f -- "$0"\n'
        # A herdr tab keeps its shell after tuicr exits; close it so the next start is not blocked.
        if [ "$MUX" = herdr ]; then
            printf 'herdr tab close "$HERDR_TAB_ID" >/dev/null 2>&1\n'
        fi
    } > "$launcher"

    if [ "$MUX" = herdr ]; then
        local tab_json
        tab_json="$(herdr tab create --workspace "$HERDR_WORKSPACE_ID" --label review --cwd "$repo")"
        new_window="$(printf '%s' "$tab_json" | jq -r '.result.root_pane.pane_id')"
        tab_id="$(printf '%s' "$tab_json" | jq -r '.result.tab.tab_id')"
        if ! herdr pane run "$new_window" "exec bash $(printf '%q' "$launcher")" >/dev/null; then
            herdr tab close "$tab_id" >/dev/null 2>&1 || true
            rm -f -- "$launcher"
            die "failed to launch tuicr in the review tab."
        fi
    else
        new_window="$(tmux new-window -d -P -F '#{window_id}' -a -n review -c "$repo" "bash $(printf '%q' "$launcher")")"
    fi

    local repohash slugfile slug slughash roundfile round i
    repohash="$(sha16 "$repo")"
    slugfile="$STATE_DIR/${repohash}.slug"
    rm -f "$slugfile"

    for i in $(seq 1 30); do
        sleep 1
        slug="$(tuicr review list --repo "$repo" 2>/dev/null | jq -r --arg before "$before" '
            ($before | split("\n") | map(select(length > 0))) as $b
            | [.[] | select(.active == true) | .slug] as $act
            | ([$act[] | select(($b | index(.)) | not)][0])
              // (if ($act | length) == 1 then $act[0] else empty end)')"
        if [ -n "$slug" ]; then
            printf '%s\n' "$slug" > "$slugfile"
            slughash="$(sha16 "$slug")"
            roundfile="$STATE_DIR/${slughash}.round"
            round=0
            [ -s "$roundfile" ] && round="$(<"$roundfile")"
            round=$((round + 1))
            printf '%s\n' "$round" > "$roundfile"
            printf '%s\n' "$slug"
            # Post before showing the review so the human never sees it half-filled.
            local posted=0
            if [ -n "$comments_file" ]; then
                ( cmd_add --repo "$repo" --input "$comments_file" ) || posted=1
            fi
            if [ "$MUX" = herdr ]; then
                herdr tab focus "$tab_id" >/dev/null
            else
                tmux select-window -t "$new_window"
            fi
            return "$posted"
        fi
    done
    die "tuicr did not create a session within 30s (maybe it failed to start)."
}

cmd_comments() {
    parse_repo_arg "$@"
    need tuicr; need jq
    local repo slug slughash seenfile comments filtered
    repo="$(resolve_repo "$REPO")"
    slug="$(resolve_slug "$repo")"

    if ! comments="$(tuicr review comments --repo "$repo" --session "$slug" 2>/dev/null)"; then
        slug="$(resolve_slug_from_list "$repo")"
        comments="$(tuicr review comments --repo "$repo" --session "$slug")"
    fi

    if [ "${PASSTHRU[0]:-}" = "--mine" ]; then
        printf '%s' "$comments" | jq --arg agent "${AGENT_USER}[" 'map(select((.author // "") | startswith($agent)))'
        return
    fi

    slughash="$(sha16 "$slug")"
    seenfile="$STATE_DIR/${slughash}.seen"
    touch "$seenfile"

    filtered="$(printf '%s' "$comments" | jq --rawfile seenraw "$seenfile" --arg agent "${AGENT_USER}[" '
        ($seenraw | split("\n") | map(select(length > 0))) as $s
        | map(select((.author // "") | startswith($agent) | not))
        | map(select(.id as $id | ($s | index($id | tostring)) | not))
    ')"

    printf '%s\n' "$filtered"

    printf '%s' "$filtered" | jq -r '.[].id | tostring' >> "$seenfile"
}

cmd_add() {
    parse_repo_arg "$@"
    need tuicr; need jq
    local repo slug slughash roundfile round active_slug
    repo="$(resolve_repo "$REPO")"

    # Prefer the slug start picked; another tuicr may be open on the same repo.
    active_slug="$(tuicr review list --repo "$repo" 2>/dev/null | jq -r --arg s "$(cat "$STATE_DIR/$(sha16 "$repo").slug" 2>/dev/null)" '[.[] | select(.active == true) | .slug] | if index($s) then $s elif length == 1 then .[0] else empty end')"
    if [ -z "$active_slug" ]; then
        die "no active review session; run 'start <scope>' first, then re-post this comment."
    fi
    slug="$active_slug"
    printf '%s\n' "$slug" > "$STATE_DIR/$(sha16 "$repo").slug"
    slughash="$(sha16 "$slug")"
    roundfile="$STATE_DIR/${slughash}.round"
    [ -s "$roundfile" ] || die "no review round for this session; run 'start <scope>' before posting a comment."
    round="$(<"$roundfile")"
    touch "$roundfile"

    add_once() {
        if [ "${#PASSTHRU[@]}" -gt 0 ]; then
            tuicr review add --repo "$repo" --session "$slug" --username "${AGENT_USER}[r${round}]" "${PASSTHRU[@]}"
        else
            tuicr review add --repo "$repo" --session "$slug" --username "${AGENT_USER}[r${round}]"
        fi
    }

    if [ "${PASSTHRU[0]:-}" = "--input" ]; then
        [ "${#PASSTHRU[@]}" -eq 2 ] || die "usage: add [--repo PATH] --input FILE"
        local drafts obj out n=0 failed=0
        drafts="$(read_comments "${PASSTHRU[1]}")" || die "invalid comments file ${PASSTHRU[1]}"
        [ -n "$drafts" ] || die "no comments in ${PASSTHRU[1]}"
        while IFS= read -r obj; do
            n=$((n + 1))
            if ! out="$(tuicr review add --repo "$repo" --session "$slug" --username "${AGENT_USER}[r${round}]" --input "$obj")"; then
                echo "error: comment $n failed: $obj" >&2
                failed=$((failed + 1))
                continue
            fi
            # Posted either way; a parse failure must not trigger a re-post.
            printf '%s' "$out" | jq -c '{id, location}' 2>/dev/null || printf '%s\n' "$out"
        done <<< "$drafts"
        [ "$failed" -eq 0 ] || die "$failed of $n comments failed; re-post only those with add --input."
        return
    fi

    add_once || die "posting failed (session may have just closed); run 'start <scope>' and re-post."
}

cmd_delete() {
    parse_repo_arg "$@"
    need tuicr; need jq
    [ "${#PASSTHRU[@]}" -eq 1 ] || die "usage: delete [--repo PATH] <comment-id>"
    local repo slug id comments
    repo="$(resolve_repo "$REPO")"
    slug="$(resolve_slug "$repo")"
    id="${PASSTHRU[0]}"
    comments="$(tuicr review comments --repo "$repo" --session "$slug")" || die "cannot read session $slug"
    # Only agent comments; human comments are the reviewer's record.
    printf '%s' "$comments" \
        | jq -e --arg id "$id" --arg agent "${AGENT_USER}[" 'any(.[]; .id == $id and ((.author // "") | startswith($agent)))' >/dev/null \
        || die "comment $id is not an agent comment in session $slug"
    tuicr review delete --repo "$repo" --session "$slug" --comment-id "$id"
}

main() {
    [ $# -ge 1 ] || { usage >&2; exit 1; }
    case "$1" in
        -h|--help) usage; exit 0 ;;
        start) shift; cmd_start "$@" ;;
        comments) shift; cmd_comments "$@" ;;
        add) shift; cmd_add "$@" ;;
        delete) shift; cmd_delete "$@" ;;
        *) usage; exit 1 ;;
    esac
}

mkdir -p "$STATE_DIR"
main "$@"
