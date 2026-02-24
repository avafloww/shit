# shit shell integration for tcsh

alias postcmd 'set __shit_last_status = $status; if ($__shit_last_status != 0 && "\!:0" != "shit") then; printf "%s\n%s\n" "\!:q" "$__shit_last_status" > /tmp/shit-`whoami`-last; endif'

alias shit 'command shit \!*'
