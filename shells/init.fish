# shit shell integration for fish
# Add to ~/.config/fish/config.fish:
#   eval "$(shit init fish)"

function __shit_preexec --on-event fish_preexec
    set -g __shit_last_command $argv
end

function __shit_postexec --on-event fish_postexec
    set -l last_status $status
    if test $last_status -ne 0; and not string match -q 'shit *' -- "$__shit_last_command"; and test "$__shit_last_command" != "shit"
        printf '%s\n%s\n' "$__shit_last_command" "$last_status" > /tmp/shit-(whoami)-last
    end
end

function shit
    # Pass through subcommands (init, help, etc.) directly to the binary
    if set -q argv[1]; and string match -qr '^[a-z]' -- $argv[1]
        command shit $argv
        return $status
    end

    # Correction mode — re-run last failed command to capture stderr
    if not test -f /tmp/shit-(whoami)-last
        echo "shit: no failed command to fix"
        return 1
    end

    set -l last_cmd (head -1 /tmp/shit-(whoami)-last)
    set -l exit_code (sed -n '2p' /tmp/shit-(whoami)-last)

    # Write context file directly to preserve newlines in stderr
    printf '%s\n%s\n' "$last_cmd" "$exit_code" > /tmp/shit-(whoami)-last
    eval "$last_cmd" 2>>/tmp/shit-(whoami)-last 1>/dev/null

    command shit $argv
end
