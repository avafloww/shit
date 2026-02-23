# shit shell integration for fish
# Add to ~/.config/fish/config.fish:
#   eval "$(shit init fish)"

function __shit_preexec --on-event fish_preexec
    set -g __shit_last_command $argv
end

function __shit_postexec --on-event fish_postexec
    set -l last_status $status
    if test $last_status -ne 0
        printf '%s\n%s\n' "$__shit_last_command" "$last_status" > /tmp/shit-(whoami)-last
    end
end

function shit
    # If no context file exists, bail
    if not test -f /tmp/shit-(whoami)-last
        echo "shit: no failed command to fix"
        return 1
    end

    # Read the last failed command and re-run to capture stderr
    set -l last_cmd (head -1 /tmp/shit-(whoami)-last)
    set -l exit_code (sed -n '2p' /tmp/shit-(whoami)-last)

    eval "$last_cmd" 2>/tmp/shit-(whoami)-stderr 1>/dev/null
    set -l stderr_output ""
    if test -f /tmp/shit-(whoami)-stderr
        set stderr_output (cat /tmp/shit-(whoami)-stderr)
        rm -f /tmp/shit-(whoami)-stderr
    end

    # Write full context with stderr
    printf '%s\n%s\n%s' "$last_cmd" "$exit_code" "$stderr_output" > /tmp/shit-(whoami)-last

    command shit $argv
end
