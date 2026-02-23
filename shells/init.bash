# shit shell integration for bash
# Add to ~/.bashrc:
#   eval "$(shit init bash)"

__shit_preexec() {
    __shit_last_command="$1"
}

__shit_postexec() {
    local last_status=$?
    if [ $last_status -ne 0 ] && [ -n "$__shit_last_command" ]; then
        printf '%s\n%s\n' "$__shit_last_command" "$last_status" > "/tmp/shit-$(whoami)-last"
    fi
    __shit_last_command=""
}

# Use DEBUG trap for preexec
trap '__shit_preexec "$BASH_COMMAND"' DEBUG

# Use PROMPT_COMMAND for postexec
if [[ -z "$PROMPT_COMMAND" ]]; then
    PROMPT_COMMAND="__shit_postexec"
else
    PROMPT_COMMAND="__shit_postexec;$PROMPT_COMMAND"
fi

shit() {
    local context_file="/tmp/shit-$(whoami)-last"
    if [ ! -f "$context_file" ]; then
        echo "shit: no failed command to fix"
        return 1
    fi

    # Read last failed command and re-run to capture stderr
    local last_cmd
    last_cmd=$(head -1 "$context_file")
    local exit_code
    exit_code=$(sed -n '2p' "$context_file")

    local stderr_output
    stderr_output=$("$SHELL" -c "$last_cmd" 2>&1 1>/dev/null)

    # Write full context with stderr
    printf '%s\n%s\n%s' "$last_cmd" "$exit_code" "$stderr_output" > "$context_file"

    command shit "$@"
}
