Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public class KeepAwake {
    public const uint ES_CONTINUOUS = 0x80000000;
    public const uint ES_SYSTEM_REQUIRED = 0x00000001;
    public const uint ES_DISPLAY_REQUIRED = 0x00000002;

    [DllImport("kernel32.dll")]
    public static extern uint SetThreadExecutionState(uint esFlags);

    public static void PreventSleep() {
        SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED);
    }
}
'@

Write-Host 'Keeping Windows awake (display + system). Stop with Ctrl+C or: Stop-Process -Id' $PID
while ($true) {
    [KeepAwake]::PreventSleep()
    Start-Sleep -Seconds 30
}
