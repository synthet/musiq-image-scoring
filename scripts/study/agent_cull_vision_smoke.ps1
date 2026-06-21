# Direct CLI vision smoke (Windows host).
param(
    [Parameter(Mandatory = $true)][string]$ImagePath,
    [string]$Provider = "antigravity",
    [int]$ImageId = 0
)

if (-not (Test-Path -LiteralPath $ImagePath)) {
    @{ ok = $false; error = "path_not_found"; path = $ImagePath } | ConvertTo-Json
    exit 2
}

$prompt = @"
Read the image file at this exact path: $ImagePath
Reply with JSON only (no markdown): {`"image_id`": $ImageId, `"species`": `"..."`, `"focus_ok`": true/false, `"blur_foreground`": true/false, `"visual_note`": `"one sentence`"}
"@

$start = Get-Date
switch ($Provider) {
    "antigravity" {
        $agy = Join-Path $env:LOCALAPPDATA "agy\bin\agy.exe"
        if (-not (Test-Path $agy)) { $agy = "agy" }
        $out = & $agy -p $prompt --dangerously-skip-permissions 2>&1 | Out-String
        $code = $LASTEXITCODE
    }
    "codex" {
        $sandbox = if ($env:CODEX_SANDBOX) { $env:CODEX_SANDBOX } else { "workspace" }
        $out = & codex exec --sandbox $sandbox --ask-for-approval never --json $prompt 2>&1 | Out-String
        $code = $LASTEXITCODE
    }
    "gemini" {
        $out = & gemini --skip-trust --output-format json -p $prompt 2>&1 | Out-String
        $code = $LASTEXITCODE
    }
    default {
        @{ ok = $false; error = "unknown_provider"; provider = $Provider } | ConvertTo-Json
        exit 2
    }
}
$duration = ((Get-Date) - $start).TotalSeconds
$visual = @("blur", "focus", "sharp", "soft", "deer", "fawn", "subject", "foreground", "background") | Where-Object { $out -match $_ }
@{
    ok = ($code -eq 0)
    provider = $Provider
    exit_code = $code
    duration_s = [math]::Round($duration, 2)
    path = $ImagePath
    has_visual_language = ($visual.Count -gt 0)
    stdout_head = $out.Substring(0, [Math]::Min(2000, $out.Length))
} | ConvertTo-Json -Depth 4
exit $code
