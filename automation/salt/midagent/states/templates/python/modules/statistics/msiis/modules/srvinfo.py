

def SRVFUNC():
    return {
        "AppPoolState": r'''
Param(
    [string]$serverName = '{serverName}'
)
Import-Module WebAdministration
$timestamp = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")

$appPools = Get-ChildItem IIS:\AppPools
$output = @()

foreach ($pool in $appPools) {{
    $config = Get-ItemProperty "IIS:\AppPools\$($pool.Name)"
    $state  = Get-WebAppPoolState -Name $pool.Name
    $numericState = switch ($state.Value) {{
        "Started" {{ 1 }}
        "Stopped" {{ 0 }}
        default   {{ -1 }}
    }}
    $output += [PSCustomObject]@{{
        metric = "AppPoolState"
        pool  = $pool.Name
        server = $serverName
        time   = $timestamp
        value  = $numericState
    }}
    $output += [PSCustomObject]@{{
        metric = "IdleTimeout_Minutes"
        pool  = $pool.Name
        server = $serverName
        time   = $timestamp
        value  = $config.processModel.idleTimeout.TotalMinutes
    }}
    $output += [PSCustomObject]@{{
        metric = "RecyclingTime_Minutes"
        pool  = $pool.Name
        server = $serverName
        time   = $timestamp
        value  = $config.recycling.periodicRestart.time.TotalMinutes
    }}
    $output += [PSCustomObject]@{{
        metric = "CPULimit"
        pool  = $pool.Name
        server = $serverName
        time   = $timestamp
        value  = $config.cpu.limit
    }}
}}
$output | ConvertTo-Json -Depth 4
''',
       "PerfMetrics": r'''
Param(
    [string]$serverName = "{serverName}"
)
Import-Module WebAdministration
$timestamp = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")

$set = Get-Counter -ListSet WAS_W3WP
$instances = $set.Instances

$output = @()
$counters = @(
    "Active Listener Channels",
    "Active Protocol Handlers",
    "Health Ping Reply Latency",
    "Total Health Pings.",
    "Total Messages Sent to WAS",
    "Total Requests Served",
    "Total Runtime Status Queries",
    "Total WAS Messages Received"
)

foreach ($instance in $instances) {{
    foreach ($counterName in $counters) {{
        $fullCounterPath = "\\WAS_W3WP($instance)\\$counterName"
        try {{
            $counterSample = Get-Counter -Counter $fullCounterPath -ErrorAction Stop
            $value = $counterSample.CounterSamples[0].CookedValue
            if ($value -is [double]) {{
                $output += [PSCustomObject]@{{
                    metric = $counterName
                    instance = $instance
                    server = $serverName
                    time = $timestamp
                    value = [math]::Round($value, 2)
                }}
            }}
        }}
        catch {{
            Write-Host "Failed to read counter $fullCounterPath"
        }}
    }}
}}
$output | ConvertTo-Json -Depth 4
''',


}
