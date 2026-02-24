# shit shell integration for zsh
# Add to ~/.zshrc:
#   eval "$(shit init zsh)"

__shit_preexec() {
    __shit_last_command="$1"
}

__shit_precmd() {
    local last_status=$?
    if [ $last_status -ne 0 ] && [ -n "$__shit_last_command" ] && [[ "$__shit_last_command" != shit* ]]; then
        printf '%s\n%s\n' "$__shit_last_command" "$last_status" > "/tmp/shit-$(whoami)-last"
    fi
    __shit_last_command=""
}

autoload -Uz add-zsh-hook
add-zsh-hook preexec __shit_preexec
add-zsh-hook precmd __shit_precmd

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
