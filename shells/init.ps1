# shit shell integration for PowerShell

$global:__shit_last_command = $null
$global:__shit_stderr_file = "/tmp/shit-$([System.Environment]::UserName)-stderr"

# Override prompt to capture last command status
$global:__shit_original_prompt = $function:prompt

function prompt {
    $lastExit = $LASTEXITCODE
    $lastCmd = (Get-History -Count 1).CommandLine

    if ($lastExit -ne 0 -and $null -ne $lastCmd -and -not $lastCmd.StartsWith("shit")) {
        $stderrOutput = ""
        if (Test-Path $global:__shit_stderr_file) {
            $stderrOutput = Get-Content $global:__shit_stderr_file -Raw
        }
        $content = "$lastCmd`n$lastExit`n$stderrOutput"
        $content | Out-File -FilePath "/tmp/shit-$([System.Environment]::UserName)-last" -NoNewline
    }

    if (Test-Path $global:__shit_stderr_file) {
        Remove-Item $global:__shit_stderr_file -Force
    }

    & $global:__shit_original_prompt
}

function shit {
    & (Get-Command shit -CommandType Application) @args
}
