# shit shell integration for bash
# Add to ~/.bashrc:
#   eval "$(shit init bash)"

__shit_preexec() {
    __shit_last_command="$1"
}

__shit_postexec() {
    local last_status=$?
    if [ $last_status -ne 0 ] && [ -n "$__shit_last_command" ] && [[ "$__shit_last_command" != shit* ]]; then
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
    # Pass through subcommands (init, help, etc.) directly to the binary
    if [[ -n "$1" && "$1" =~ ^[a-z] ]]; then
        command shit "$@"
        return $?
    fi

    # Correction mode — re-run last failed command to capture stderr
    local context_file="/tmp/shit-$(whoami)-last"
    if [ ! -f "$context_file" ]; then
        echo "shit: no failed command to fix"
        return 1
    fi

    local last_cmd
    last_cmd=$(head -1 "$context_file")
    local exit_code
    exit_code=$(sed -n '2p' "$context_file")

    # Write context file, append stderr directly to preserve newlines
    printf '%s\n%s\n' "$last_cmd" "$exit_code" > "$context_file"
    "$SHELL" -c "$last_cmd" 2>>"$context_file" 1>/dev/null

    command shit "$@"
}
