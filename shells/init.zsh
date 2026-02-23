# shit shell integration for zsh
# Add to ~/.zshrc:
#   eval "$(shit init zsh)"

__shit_preexec() {
    __shit_last_command="$1"
}

__shit_precmd() {
    local last_status=$?
    if [ $last_status -ne 0 ] && [ -n "$__shit_last_command" ]; then
        printf '%s\n%s\n' "$__shit_last_command" "$last_status" > "/tmp/shit-$(whoami)-last"
    fi
    __shit_last_command=""
}

autoload -Uz add-zsh-hook
add-zsh-hook preexec __shit_preexec
add-zsh-hook precmd __shit_precmd

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
