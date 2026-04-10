Get-Process python -ErrorAction SilentlyContinue |
    Select-Object Id,
        @{N='Mem(MB)';E={[int]($_.WorkingSet64/1MB)}},
        @{N='CPU(s)';E={[int]$_.CPU}},
        StartTime,
        Path |
    Format-Table -AutoSize
