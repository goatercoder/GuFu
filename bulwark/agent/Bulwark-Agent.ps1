<#
.SYNOPSIS
    Bulwark evidence-collection agent for Windows.

.DESCRIPTION
    Collects configuration state that supports NIST SP 800-171 Rev 2 requirements and posts it to a
    Bulwark server, which maps each check to the requirements and assessment objectives it
    evidences. The script reads configuration; it never changes it.

    Windows PowerShell 5.1 and later. Run elevated: several probes (auditpol, secedit, BitLocker)
    need administrative rights and report a clear error when they do not have them.

.EXAMPLE
    .\Bulwark-Agent.ps1 -Server https://bulwark.example -Key <enrollment key>

.EXAMPLE
    .\Bulwark-Agent.ps1 -Output report.json     # offline: write, carry, upload

.EXAMPLE
    .\Bulwark-Agent.ps1 -Server https://bulwark.example -Key <key> -InstallScheduledTask
#>
[CmdletBinding()]
param(
    [string] $Server,
    [string] $Key,
    [string] $Output,
    [switch] $DryRun,
    [switch] $ListChecks,
    [string] $Check,
    [switch] $NoInventory,
    [switch] $Insecure,
    [int]    $TimeoutSec = 60,
    [switch] $InstallScheduledTask,
    [switch] $UninstallScheduledTask,
    [switch] $Version
)

Set-StrictMode -Version 2
$ErrorActionPreference = 'Continue'

$AgentVersion = '0.1.0'
$SchemaVersion = 1
$ConfigPath = Join-Path $env:ProgramData 'Bulwark\agent.json'

# Thresholds, mirroring catalog/checks.json "params".
$Params = @{
    'os.accounts.admin_count'        = @{ max_admins = 2 }
    'os.accounts.inactive_enabled'   = @{ inactive_days = 90 }
    'os.password.min_length'         = @{ min_length = 14 }
    'os.password.history'            = @{ history = 5 }
    'os.lockout.threshold'           = @{ max_threshold = 10 }
    'os.session.screen_lock'         = @{ max_seconds = 900 }
    'os.session.idle_timeout'        = @{ max_seconds = 3600 }
    'os.time.sync'                   = @{ max_hours = 24 }
    'os.audit.log_retention'         = @{ min_mb = 196 }
    'os.malware.signatures_current'  = @{ max_days = 7 }
    'os.malware.last_scan'           = @{ max_days = 7 }
    'os.patch.last_update'           = @{ max_days = 30 }
}

$script:Checks = New-Object System.Collections.ArrayList
$script:SecPol = $null
$script:AuditPol = $null
$script:Defender = $null

function Get-Param {
    param([string] $CheckId, [string] $Name)
    if ($Params.ContainsKey($CheckId) -and $Params[$CheckId].ContainsKey($Name)) {
        return $Params[$CheckId][$Name]
    }
    return $null
}

function Register-Check {
    param([string] $Id, [scriptblock] $Body)
    [void] $script:Checks.Add([pscustomobject]@{ Id = $Id; Body = $Body })
}

function New-Result {
    param(
        [string] $Status,
        [string] $Observed = '',
        [string] $Expected = $null,
        $Details = $null,
        [string] $ErrorText = $null
    )
    return [pscustomobject]@{
        status   = $Status
        observed = $Observed
        expected = $Expected
        details  = $Details
        error    = $ErrorText
    }
}

function New-ErrorResult {
    param([string] $Message, [string] $Expected = $null)
    return New-Result -Status 'error' -Observed '' -Expected $Expected -ErrorText $Message
}

# ---------------------------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------------------------
function Get-RegistryValue {
    param([string] $Path, [string] $Name)
    try {
        $item = Get-ItemProperty -Path $Path -Name $Name -ErrorAction Stop
        return $item.$Name
    } catch {
        return $null
    }
}

function Get-RegistryInt {
    param([string] $Path, [string] $Name)
    $value = Get-RegistryValue -Path $Path -Name $Name
    if ($null -eq $value) { return $null }
    try { return [int] $value } catch { return $null }
}

function Get-SecurityPolicy {
    <# Local security policy as a hashtable, exported with secedit. #>
    if ($null -ne $script:SecPol) { return $script:SecPol }
    $table = @{}
    $file = Join-Path $env:TEMP ('bulwark_secpol_{0}.inf' -f $PID)
    try {
        $null = & secedit.exe /export /cfg $file /quiet 2>&1
        if (Test-Path $file) {
            foreach ($line in (Get-Content -LiteralPath $file -Encoding Unicode -ErrorAction Stop)) {
                if ($line -match '^\s*([^=\[]+?)\s*=\s*(.+?)\s*$') {
                    $table[$matches[1].Trim().ToLower()] = $matches[2].Trim()
                }
            }
        }
    } catch {
        # secedit needs elevation; callers fall back to "net accounts".
    } finally {
        if (Test-Path $file) { Remove-Item -LiteralPath $file -Force -ErrorAction SilentlyContinue }
    }
    $script:SecPol = $table
    return $table
}

function Get-PolicyInt {
    param([string] $Name)
    $policy = Get-SecurityPolicy
    $key = $Name.ToLower()
    if ($policy.ContainsKey($key)) {
        try { return [int] $policy[$key] } catch { return $null }
    }
    return $null
}

function Get-NetAccounts {
    <# "net accounts" output as a hashtable, for hosts where secedit is unavailable. #>
    $table = @{}
    try {
        foreach ($line in (& net.exe accounts 2>&1)) {
            $text = [string] $line
            if ($text -match '^(.+?):\s+(.+?)\s*$') {
                $table[$matches[1].Trim().ToLower()] = $matches[2].Trim()
            }
        }
    } catch {
        return $table
    }
    return $table
}

function Get-AuditPolicy {
    <# Advanced audit policy subcategories as a hashtable of name -> setting. #>
    if ($null -ne $script:AuditPol) { return $script:AuditPol }
    $table = @{}
    try {
        $lines = & auditpol.exe /get /category:* 2>&1
        foreach ($line in $lines) {
            $text = [string] $line
            if ($text -match '^\s\s+(\S.*?)\s\s+(No Auditing|Success and Failure|Success|Failure)\s*$') {
                $table[$matches[1].Trim().ToLower()] = $matches[2].Trim()
            }
        }
    } catch {
        $table = @{}
    }
    $script:AuditPol = $table
    return $table
}

function Get-DefenderStatus {
    if ($null -ne $script:Defender) { return $script:Defender }
    try {
        $script:Defender = Get-MpComputerStatus -ErrorAction Stop
    } catch {
        $script:Defender = $false
    }
    return $script:Defender
}

function Test-IsElevated {
    try {
        $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
        $principal = New-Object Security.Principal.WindowsPrincipal($identity)
        return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    } catch {
        return $false
    }
}

function ConvertTo-Array {
    param($Value)
    if ($null -eq $Value) { return @() }
    if ($Value -is [System.Array]) { return $Value }
    return @($Value)
}

# ---------------------------------------------------------------------------------------------
# Inventory checks
# ---------------------------------------------------------------------------------------------
Register-Check 'os.inventory.system' {
    $os = Get-CimInstance Win32_OperatingSystem -ErrorAction Stop
    $cs = Get-CimInstance Win32_ComputerSystem -ErrorAction SilentlyContinue
    $details = @{
        hostname = $env:COMPUTERNAME
        os_name  = $os.Caption
        version  = $os.Version
        build    = $os.BuildNumber
        arch     = $os.OSArchitecture
        domain   = if ($cs) { $cs.Domain } else { $null }
        model    = if ($cs) { $cs.Model } else { $null }
    }
    New-Result -Status 'info' -Observed ("{0} build {1} on {2}" -f $os.Caption, $os.BuildNumber, $env:COMPUTERNAME) -Details $details
}

Register-Check 'os.inventory.software' {
    $software = Get-InstalledSoftware
    New-Result -Status 'info' -Observed ("{0} installed program(s) recorded" -f $software.Count) -Details @{ software = @($software | Select-Object -First 500) }
}

Register-Check 'os.inventory.local_users' {
    $users = Get-LocalUserInventory
    if ($null -eq $users) { return New-ErrorResult 'cannot enumerate local accounts' }
    $enabled = @($users | Where-Object { $_.enabled })
    $admins = @($enabled | Where-Object { $_.admin })
    New-Result -Status 'info' -Observed ("{0} local account(s), {1} enabled; {2} enabled administrator(s)" -f $users.Count, $enabled.Count, $admins.Count) -Details @{ users = $users; administrators = @($admins | ForEach-Object { $_.name }) }
}

Register-Check 'os.inventory.listening_ports' {
    $ports = Get-ListeningPorts
    $sample = (@($ports | Select-Object -First 12 | ForEach-Object { [string] $_.port }) -join ', ')
    New-Result -Status 'info' -Observed ("{0} listening socket(s): {1}" -f $ports.Count, $sample) -Details @{ listening_ports = $ports }
}

# ---------------------------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------------------------
Register-Check 'os.accounts.admin_count' {
    $maximum = Get-Param 'os.accounts.admin_count' 'max_admins'
    $expected = "At most $maximum enabled local administrator accounts"
    $users = Get-LocalUserInventory
    if ($null -eq $users) { return New-ErrorResult 'cannot enumerate local administrators' $expected }
    $admins = @($users | Where-Object { $_.admin -and $_.enabled } | ForEach-Object { $_.name })
    $status = if ($admins.Count -le $maximum) { 'pass' } else { 'fail' }
    $names = if ($admins.Count -gt 0) { $admins -join ', ' } else { 'none' }
    New-Result -Status $status -Observed ("{0} enabled local administrator(s): {1}" -f $admins.Count, $names) -Expected $expected -Details @{ administrators = $admins }
}

Register-Check 'os.accounts.guest_disabled' {
    $expected = 'Guest account disabled'
    try {
        $guest = Get-LocalUser -Name 'Guest' -ErrorAction Stop
        $status = if ($guest.Enabled) { 'fail' } else { 'pass' }
        return New-Result -Status $status -Observed ("Guest account enabled: {0}" -f $guest.Enabled) -Expected $expected
    } catch {
        $text = (& net.exe user Guest 2>&1) -join "`n"
        if ($text -match 'Account active\s+(\S+)') {
            $active = $matches[1]
            $status = if ($active -match '^(No|Nein|Non)$') { 'pass' } else { 'fail' }
            return New-Result -Status $status -Observed ("Guest account active: {0}" -f $active) -Expected $expected
        }
        return New-Result -Status 'pass' -Observed 'Guest account not present' -Expected $expected
    }
}

Register-Check 'os.accounts.no_blank_passwords' {
    $expected = 'Blank passwords limited to console logon (LimitBlankPasswordUse = 1)'
    $value = Get-PolicyInt 'LimitBlankPasswordUse'
    if ($null -eq $value) {
        $value = Get-RegistryInt 'HKLM:\SYSTEM\CurrentControlSet\Control\Lsa' 'LimitBlankPasswordUse'
    }
    if ($null -eq $value) { return New-ErrorResult 'could not read LimitBlankPasswordUse' $expected }
    $status = if ($value -eq 1) { 'pass' } else { 'fail' }
    New-Result -Status $status -Observed ("LimitBlankPasswordUse = {0}" -f $value) -Expected $expected
}

Register-Check 'os.accounts.inactive_enabled' {
    $days = Get-Param 'os.accounts.inactive_enabled' 'inactive_days'
    $expected = "No enabled local account without a logon in $days days"
    $users = Get-LocalUserInventory
    if ($null -eq $users) { return New-ErrorResult 'cannot enumerate local accounts' $expected }
    $stale = @()
    foreach ($user in $users) {
        if (-not $user.enabled) { continue }
        if ($null -ne $user.last_logon_days -and $user.last_logon_days -gt $days) {
            $stale += ("{0} ({1} days)" -f $user.name, $user.last_logon_days)
        }
    }
    $status = if ($stale.Count -eq 0) { 'pass' } else { 'fail' }
    $names = if ($stale.Count -gt 0) { $stale -join ', ' } else { 'none' }
    New-Result -Status $status -Observed ("Inactive enabled account(s): {0}" -f $names) -Expected $expected -Details @{ inactive = $stale }
}

Register-Check 'os.accounts.autologon_disabled' {
    $expected = 'AutoAdminLogon = 0 and no stored DefaultPassword'
    $path = 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon'
    $auto = Get-RegistryValue $path 'AutoAdminLogon'
    $stored = Get-RegistryValue $path 'DefaultPassword'
    $enabled = ($null -ne $auto -and ([string] $auto).Trim() -eq '1')
    $hasPassword = ($null -ne $stored -and ([string] $stored).Length -gt 0)
    $status = if ($enabled -or $hasPassword) { 'fail' } else { 'pass' }
    $suffix = if ($hasPassword) { '; DefaultPassword is set' } else { '' }
    $shown = if ($null -eq $auto) { '0' } else { [string] $auto }
    New-Result -Status $status -Observed ("AutoAdminLogon = {0}{1}" -f $shown, $suffix) -Expected $expected
}

Register-Check 'os.accounts.uac_enabled' {
    $expected = 'EnableLUA = 1 and ConsentPromptBehaviorAdmin >= 2'
    $path = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System'
    $lua = Get-RegistryInt $path 'EnableLUA'
    $consent = Get-RegistryInt $path 'ConsentPromptBehaviorAdmin'
    if ($null -eq $lua) { return New-ErrorResult 'could not read EnableLUA' $expected }
    $ok = ($lua -eq 1) -and (($null -eq $consent) -or ($consent -ge 2))
    $status = if ($ok) { 'pass' } else { 'fail' }
    New-Result -Status $status -Observed ("EnableLUA = {0}, ConsentPromptBehaviorAdmin = {1}" -f $lua, $consent) -Expected $expected
}

# ---------------------------------------------------------------------------------------------
# Password and lockout policy
# ---------------------------------------------------------------------------------------------
Register-Check 'os.password.min_length' {
    $minimum = Get-Param 'os.password.min_length' 'min_length'
    $expected = "Minimum password length >= $minimum"
    $length = Get-PolicyInt 'MinimumPasswordLength'
    if ($null -eq $length) {
        $accounts = Get-NetAccounts
        if ($accounts.ContainsKey('minimum password length')) {
            try { $length = [int] $accounts['minimum password length'] } catch { $length = $null }
        }
    }
    if ($null -eq $length) { return New-ErrorResult 'could not read the password policy (run elevated)' $expected }
    $status = if ($length -ge $minimum) { 'pass' } else { 'fail' }
    New-Result -Status $status -Observed ("Minimum password length {0}" -f $length) -Expected $expected
}

Register-Check 'os.password.complexity' {
    $expected = 'Password complexity requirements enabled'
    $value = Get-PolicyInt 'PasswordComplexity'
    if ($null -eq $value) { return New-ErrorResult 'could not read PasswordComplexity (run elevated)' $expected }
    $status = if ($value -eq 1) { 'pass' } else { 'fail' }
    New-Result -Status $status -Observed ("PasswordComplexity = {0}" -f $value) -Expected $expected
}

Register-Check 'os.password.history' {
    $generations = Get-Param 'os.password.history' 'history'
    $expected = "Password history >= $generations generations"
    $value = Get-PolicyInt 'PasswordHistorySize'
    if ($null -eq $value) {
        $accounts = Get-NetAccounts
        if ($accounts.ContainsKey('length of password history maintained')) {
            try { $value = [int] $accounts['length of password history maintained'] } catch { $value = $null }
        }
    }
    if ($null -eq $value) { return New-ErrorResult 'could not read PasswordHistorySize (run elevated)' $expected }
    $status = if ($value -ge $generations) { 'pass' } else { 'fail' }
    New-Result -Status $status -Observed ("PasswordHistorySize = {0}" -f $value) -Expected $expected
}

Register-Check 'os.lockout.threshold' {
    $maximum = Get-Param 'os.lockout.threshold' 'max_threshold'
    $expected = "Lockout threshold between 1 and $maximum attempts"
    $value = Get-PolicyInt 'LockoutBadCount'
    if ($null -eq $value) {
        $accounts = Get-NetAccounts
        if ($accounts.ContainsKey('lockout threshold')) {
            $raw = $accounts['lockout threshold']
            if ($raw -match '^\d+$') { $value = [int] $raw } else { $value = 0 }
        }
    }
    if ($null -eq $value) { return New-ErrorResult 'could not read the lockout policy (run elevated)' $expected }
    $status = if ($value -ge 1 -and $value -le $maximum) { 'pass' } else { 'fail' }
    $shown = if ($value -eq 0) { 'never' } else { [string] $value }
    New-Result -Status $status -Observed ("Lockout threshold {0}" -f $shown) -Expected $expected
}

# ---------------------------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------------------------
Register-Check 'os.session.screen_lock' {
    $maximum = Get-Param 'os.session.screen_lock' 'max_seconds'
    $expected = "Lock within $maximum seconds of inactivity with a password"
    $machine = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System'
    $inactivity = Get-RegistryInt $machine 'InactivityTimeoutSecs'
    $desktop = 'HKCU:\Control Panel\Desktop'
    $timeout = Get-RegistryValue $desktop 'ScreenSaveTimeOut'
    $secure = Get-RegistryValue $desktop 'ScreenSaverIsSecure'
    $active = Get-RegistryValue $desktop 'ScreenSaveActive'

    $seconds = $null
    if ($null -ne $inactivity -and $inactivity -gt 0) {
        $seconds = $inactivity
    } elseif ($null -ne $timeout -and ([string] $timeout) -match '^\d+$') {
        $seconds = [int] $timeout
    }
    $locked = ($null -ne $secure -and ([string] $secure).Trim() -eq '1')
    $enabled = ($null -ne $active -and ([string] $active).Trim() -eq '1') -or ($null -ne $inactivity -and $inactivity -gt 0)
    $ok = ($null -ne $seconds) -and ($seconds -le $maximum) -and $locked -and $enabled
    $status = if ($ok) { 'pass' } else { 'fail' }
    $shownSeconds = if ($null -eq $seconds) { 'not set' } else { [string] $seconds }
    $shownLock = if ($locked) { 'yes' } else { 'no' }
    New-Result -Status $status -Observed ("Timeout {0} s, password required: {1}" -f $shownSeconds, $shownLock) -Expected $expected -Details @{ InactivityTimeoutSecs = $inactivity; ScreenSaveTimeOut = $timeout; ScreenSaverIsSecure = $secure }
}

Register-Check 'os.session.logon_banner' {
    $expected = 'A logon notice is displayed before authentication'
    $path = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System'
    $caption = Get-RegistryValue $path 'legalnoticecaption'
    $text = Get-RegistryValue $path 'legalnoticetext'
    $hasCaption = ($null -ne $caption -and ([string] $caption).Trim().Length -gt 0)
    $hasText = ($null -ne $text -and ([string] $text).Trim().Length -gt 0)
    $status = if ($hasCaption -or $hasText) { 'pass' } else { 'fail' }
    $shown = if ($hasCaption -or $hasText) { 'yes' } else { 'no' }
    New-Result -Status $status -Observed ("Legal notice configured: {0}" -f $shown) -Expected $expected
}

Register-Check 'os.session.idle_timeout' {
    $maximum = Get-Param 'os.session.idle_timeout' 'max_seconds'
    $expected = "Idle sessions terminate within $maximum seconds"
    $path = 'HKLM:\SOFTWARE\Policies\Microsoft\Windows NT\Terminal Services'
    $idle = Get-RegistryInt $path 'MaxIdleTime'
    $disconnect = Get-RegistryInt $path 'MaxDisconnectionTime'
    if ($null -eq $idle -or $idle -eq 0) {
        return New-Result -Status 'fail' -Observed 'Remote Desktop idle session limit is not configured' -Expected $expected
    }
    $seconds = [math]::Round($idle / 1000)
    $status = if ($seconds -le $maximum) { 'pass' } else { 'fail' }
    New-Result -Status $status -Observed ("MaxIdleTime {0} s, MaxDisconnectionTime {1}" -f $seconds, $disconnect) -Expected $expected
}

# ---------------------------------------------------------------------------------------------
# Network
# ---------------------------------------------------------------------------------------------
Register-Check 'os.firewall.enabled' {
    $expected = 'Host firewall enabled on every profile'
    try {
        $profiles = Get-NetFirewallProfile -ErrorAction Stop
        $states = @($profiles | ForEach-Object { "{0}: {1}" -f $_.Name, $(if ($_.Enabled) { 'On' } else { 'Off' }) })
        $allOn = @($profiles | Where-Object { -not $_.Enabled }).Count -eq 0
        $status = if ($allOn) { 'pass' } else { 'fail' }
        return New-Result -Status $status -Observed ($states -join '; ') -Expected $expected
    } catch {
        $text = (& netsh.exe advfirewall show allprofiles 2>&1) -join "`n"
        $matchesFound = [regex]::Matches($text, '(?m)^State\s+(\w+)')
        if ($matchesFound.Count -eq 0) { return New-ErrorResult 'could not read the firewall state' $expected }
        $values = @($matchesFound | ForEach-Object { $_.Groups[1].Value })
        $allOn = @($values | Where-Object { $_.ToUpper() -ne 'ON' }).Count -eq 0
        $status = if ($allOn) { 'pass' } else { 'fail' }
        return New-Result -Status $status -Observed ("Profile states: {0}" -f ($values -join ', ')) -Expected $expected
    }
}

Register-Check 'os.firewall.default_inbound_block' {
    $expected = 'Inbound traffic denied by default on every profile'
    try {
        $profiles = Get-NetFirewallProfile -ErrorAction Stop
        $states = @($profiles | ForEach-Object { "{0}: {1}" -f $_.Name, $_.DefaultInboundAction })
        $blocked = @($profiles | Where-Object { $_.DefaultInboundAction -ne 'Block' }).Count -eq 0
        $status = if ($blocked) { 'pass' } else { 'fail' }
        return New-Result -Status $status -Observed ($states -join '; ') -Expected $expected
    } catch {
        $text = (& netsh.exe advfirewall show allprofiles 2>&1) -join "`n"
        $matchesFound = [regex]::Matches($text, '(?m)^Firewall Policy\s+(.+)$')
        if ($matchesFound.Count -eq 0) { return New-ErrorResult 'could not read the default inbound action' $expected }
        $values = @($matchesFound | ForEach-Object { ($_.Groups[1].Value -split ',')[0].Trim() })
        $blocked = @($values | Where-Object { $_ -notmatch 'Block' }).Count -eq 0
        $status = if ($blocked) { 'pass' } else { 'fail' }
        return New-Result -Status $status -Observed ("Default inbound: {0}" -f ($values -join ', ')) -Expected $expected
    }
}

Register-Check 'os.remote.remote_access' {
    $expected = 'Remote Desktop disabled, or Network Level Authentication required'
    $deny = Get-RegistryInt 'HKLM:\SYSTEM\CurrentControlSet\Control\Terminal Server' 'fDenyTSConnections'
    if ($deny -eq 1) {
        return New-Result -Status 'pass' -Observed 'Remote Desktop is disabled' -Expected $expected
    }
    $path = 'HKLM:\SYSTEM\CurrentControlSet\Control\Terminal Server\WinStations\RDP-Tcp'
    $nla = Get-RegistryInt $path 'UserAuthentication'
    $layer = Get-RegistryInt $path 'SecurityLayer'
    $status = if ($nla -eq 1) { 'pass' } else { 'fail' }
    New-Result -Status $status -Observed ("RDP enabled; NLA (UserAuthentication) = {0}, SecurityLayer = {1}" -f $nla, $layer) -Expected $expected
}

Register-Check 'os.services.legacy_protocols' {
    $expected = 'SMBv1, Telnet and TFTP are not enabled'
    $found = @()
    try {
        $smb = Get-SmbServerConfiguration -ErrorAction Stop
        if ($smb.EnableSMB1Protocol) { $found += 'SMB1' }
    } catch {
        $feature = $null
        try { $feature = Get-WindowsOptionalFeature -Online -FeatureName 'SMB1Protocol' -ErrorAction Stop } catch { $feature = $null }
        if ($null -ne $feature -and $feature.State -eq 'Enabled') { $found += 'SMB1' }
    }
    foreach ($name in @('TelnetClient', 'TelnetServer', 'TFTP')) {
        try {
            $feature = Get-WindowsOptionalFeature -Online -FeatureName $name -ErrorAction Stop
            if ($feature.State -eq 'Enabled') { $found += $name }
        } catch {
            # The feature is not present on this edition.
        }
    }
    $status = if ($found.Count -eq 0) { 'pass' } else { 'fail' }
    $names = if ($found.Count -gt 0) { $found -join ', ' } else { 'none' }
    New-Result -Status $status -Observed ("Legacy services enabled: {0}" -f $names) -Expected $expected -Details @{ found = $found }
}

Register-Check 'os.time.sync' {
    $hours = Get-Param 'os.time.sync' 'max_hours'
    $expected = "Clock synchronized with an authoritative source within $hours hours"
    $text = (& w32tm.exe /query /status 2>&1) -join "`n"
    if ($text -match 'error|not been started|service has not') {
        return New-Result -Status 'fail' -Observed 'The Windows Time service is not running or not configured' -Expected $expected
    }
    $source = 'unknown'
    if ($text -match 'Source:\s*(.+)') { $source = $matches[1].Trim() }
    $last = 'never'
    if ($text -match 'Last Successful Sync Time:\s*(.+)') { $last = $matches[1].Trim() }
    $synced = ($last -ne 'never' -and $last -notmatch 'unspecified')
    $status = if ($synced) { 'pass' } else { 'fail' }
    New-Result -Status $status -Observed ("Source: {0}; last sync: {1}" -f $source, $last) -Expected $expected
}

# ---------------------------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------------------------
Register-Check 'os.audit.logging_enabled' {
    $expected = 'Logon, account management and policy change events are audited'
    $policy = Get-AuditPolicy
    if ($policy.Count -eq 0) {
        return New-ErrorResult 'auditpol requires an elevated session' $expected
    }
    $wanted = @('logon', 'user account management', 'audit policy change')
    $missing = @()
    foreach ($name in $wanted) {
        $setting = if ($policy.ContainsKey($name)) { $policy[$name] } else { 'No Auditing' }
        if ($setting -eq 'No Auditing') { $missing += $name }
    }
    $service = Get-Service -Name 'EventLog' -ErrorAction SilentlyContinue
    $running = ($null -ne $service -and $service.Status -eq 'Running')
    $status = if ($missing.Count -eq 0 -and $running) { 'pass' } else { 'fail' }
    $names = if ($missing.Count -gt 0) { $missing -join ', ' } else { 'none' }
    New-Result -Status $status -Observed ("Subcategories without auditing: {0}; EventLog running: {1}" -f $names, $running) -Expected $expected
}

Register-Check 'os.audit.log_retention' {
    $megabytes = Get-Param 'os.audit.log_retention' 'min_mb'
    $expected = "Security log at least $megabytes MB and not overwritten immediately"
    try {
        $log = Get-WinEvent -ListLog 'Security' -ErrorAction Stop
        $actual = [math]::Round($log.MaximumSizeInBytes / 1MB)
        $status = if ($actual -ge $megabytes) { 'pass' } else { 'fail' }
        return New-Result -Status $status -Observed ("Security log max size {0} MB, mode {1}" -f $actual, $log.LogMode) -Expected $expected
    } catch {
        $size = Get-RegistryInt 'HKLM:\SYSTEM\CurrentControlSet\Services\EventLog\Security' 'MaxSize'
        if ($null -eq $size) { return New-ErrorResult 'could not read the Security log configuration' $expected }
        $actual = [math]::Round($size / 1MB)
        $status = if ($actual -ge $megabytes) { 'pass' } else { 'fail' }
        return New-Result -Status $status -Observed ("Security log max size {0} MB" -f $actual) -Expected $expected
    }
}

Register-Check 'os.audit.privileged_actions' {
    $expected = 'Use of privileged functions is audited'
    $policy = Get-AuditPolicy
    if ($policy.Count -eq 0) { return New-ErrorResult 'auditpol requires an elevated session' $expected }
    $privilege = if ($policy.ContainsKey('sensitive privilege use')) { $policy['sensitive privilege use'] } else { 'No Auditing' }
    $process = if ($policy.ContainsKey('process creation')) { $policy['process creation'] } else { 'No Auditing' }
    $ok = ($privilege -ne 'No Auditing') -or ($process -ne 'No Auditing')
    $status = if ($ok) { 'pass' } else { 'fail' }
    New-Result -Status $status -Observed ("Sensitive Privilege Use: {0}; Process Creation: {1}" -f $privilege, $process) -Expected $expected
}

Register-Check 'os.audit.powershell_logging' {
    $expected = 'PowerShell script block logging enabled'
    $value = Get-RegistryInt 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\PowerShell\ScriptBlockLogging' 'EnableScriptBlockLogging'
    $status = if ($value -eq 1) { 'pass' } else { 'fail' }
    $shown = if ($null -eq $value) { 'not set' } else { [string] $value }
    New-Result -Status $status -Observed ("EnableScriptBlockLogging = {0}" -f $shown) -Expected $expected
}

# ---------------------------------------------------------------------------------------------
# Endpoint protection and patching
# ---------------------------------------------------------------------------------------------
Register-Check 'os.malware.protection_enabled' {
    $expected = 'Anti-malware present with real-time protection enabled'
    $defender = Get-DefenderStatus
    if ($defender -isnot [bool]) {
        $status = if ($defender.RealTimeProtectionEnabled) { 'pass' } else { 'fail' }
        $mode = 'unknown'
        if (@($defender.PSObject.Properties.Name) -contains 'AMRunningMode') {
            $mode = [string] $defender.AMRunningMode
        }
        $state = if ($defender.RealTimeProtectionEnabled) { 'on' } else { 'off' }
        return New-Result -Status $status -Observed ("Defender real-time protection: {0} (mode {1})" -f $state, $mode) -Expected $expected
    }
    try {
        $products = @(Get-CimInstance -Namespace 'root/SecurityCenter2' -ClassName 'AntiVirusProduct' -ErrorAction Stop | ForEach-Object { $_.displayName })
        $status = if ($products.Count -gt 0) { 'pass' } else { 'fail' }
        $names = if ($products.Count -gt 0) { $products -join ', ' } else { 'none' }
        return New-Result -Status $status -Observed ("Registered anti-virus products: {0}" -f $names) -Expected $expected
    } catch {
        return New-ErrorResult 'anti-malware status is unavailable' $expected
    }
}

Register-Check 'os.malware.signatures_current' {
    $days = Get-Param 'os.malware.signatures_current' 'max_days'
    $expected = "Signatures updated within $days days"
    $defender = Get-DefenderStatus
    if ($defender -is [bool]) { return New-ErrorResult 'anti-malware status is unavailable' $expected }
    $age = $null
    if (@($defender.PSObject.Properties.Name) -contains 'AntivirusSignatureAge') {
        try { $age = [int] $defender.AntivirusSignatureAge } catch { $age = $null }
    }
    if ($null -eq $age) { return New-ErrorResult 'signature age is unavailable' $expected }
    $status = if ($age -le $days) { 'pass' } else { 'fail' }
    New-Result -Status $status -Observed ("Signatures {0} day(s) old" -f $age) -Expected $expected
}

Register-Check 'os.malware.last_scan' {
    $days = Get-Param 'os.malware.last_scan' 'max_days'
    $expected = "A malware scan ran within $days days"
    $defender = Get-DefenderStatus
    if ($defender -is [bool]) { return New-ErrorResult 'anti-malware status is unavailable' $expected }
    $last = $null
    $defenderNames = @($defender.PSObject.Properties.Name)
    if (($defenderNames -contains 'QuickScanEndTime') -and $null -ne $defender.QuickScanEndTime) {
        $last = $defender.QuickScanEndTime
    } elseif (($defenderNames -contains 'FullScanEndTime') -and $null -ne $defender.FullScanEndTime) {
        $last = $defender.FullScanEndTime
    }
    if ($null -eq $last) { return New-Result -Status 'fail' -Observed 'No completed scan is recorded' -Expected $expected }
    $age = [int] ((Get-Date) - $last).TotalDays
    $status = if ($age -le $days) { 'pass' } else { 'fail' }
    New-Result -Status $status -Observed ("Last scan {0} day(s) ago" -f $age) -Expected $expected
}

Register-Check 'os.patch.last_update' {
    $days = Get-Param 'os.patch.last_update' 'max_days'
    $expected = "An operating system update was installed within $days days"
    try {
        $hotfix = Get-HotFix -ErrorAction Stop | Where-Object { $null -ne $_.InstalledOn } | Sort-Object InstalledOn -Descending | Select-Object -First 1
        if ($null -eq $hotfix) { return New-Result -Status 'fail' -Observed 'No update history is recorded' -Expected $expected }
        $age = [int] ((Get-Date) - $hotfix.InstalledOn).TotalDays
        $status = if ($age -le $days) { 'pass' } else { 'fail' }
        return New-Result -Status $status -Observed ("{0} installed {1} day(s) ago" -f $hotfix.HotFixID, $age) -Expected $expected
    } catch {
        return New-ErrorResult 'could not read the update history' $expected
    }
}

Register-Check 'os.patch.pending_updates' {
    $expected = 'No outstanding security updates'
    try {
        $session = New-Object -ComObject Microsoft.Update.Session
        $searcher = $session.CreateUpdateSearcher()
        $found = $searcher.Search('IsInstalled=0 and IsHidden=0')
        $count = $found.Updates.Count
        $status = if ($count -eq 0) { 'pass' } else { 'fail' }
        $titles = @()
        for ($i = 0; $i -lt [math]::Min($count, 5); $i++) { $titles += $found.Updates.Item($i).Title }
        return New-Result -Status $status -Observed ("{0} update(s) pending" -f $count) -Expected $expected -Details @{ titles = $titles }
    } catch {
        return New-ErrorResult 'the Windows Update search did not complete' $expected
    }
}

Register-Check 'os.patch.auto_update' {
    $expected = 'Automatic updates enabled or managed centrally'
    $path = 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU'
    $noAuto = Get-RegistryInt $path 'NoAutoUpdate'
    $options = Get-RegistryInt $path 'AUOptions'
    $wsus = Get-RegistryValue 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate' 'WUServer'
    if ($noAuto -eq 1) {
        return New-Result -Status 'fail' -Observed 'NoAutoUpdate = 1 (automatic updates disabled)' -Expected $expected
    }
    if (($options -eq 3) -or ($options -eq 4) -or ($null -ne $wsus)) {
        $suffix = if ($null -ne $wsus) { '; managed by WSUS' } else { '' }
        return New-Result -Status 'pass' -Observed ("AUOptions = {0}{1}" -f $options, $suffix) -Expected $expected
    }
    if ($null -eq $options -and $null -eq $noAuto) {
        return New-Result -Status 'pass' -Observed 'Windows Update is at its default (automatic)' -Expected $expected
    }
    New-Result -Status 'fail' -Observed ("AUOptions = {0}" -f $options) -Expected $expected
}

Register-Check 'os.patch.os_supported' {
    $expected = 'The operating system release still receives security updates'
    $os = Get-CimInstance Win32_OperatingSystem -ErrorAction Stop
    $caption = [string] $os.Caption
    $build = 0
    try { $build = [int] $os.BuildNumber } catch { $build = 0 }
    if ($caption -match 'Windows (7|8|Server 2008|Server 2012)') {
        return New-Result -Status 'fail' -Observed ("{0} is end of life" -f $caption) -Expected $expected
    }
    if ($caption -match 'LTSC|IoT') {
        return New-Result -Status 'info' -Observed ("{0} (long-term servicing channel: check the vendor lifecycle date)" -f $caption) -Expected $expected
    }
    if ($caption -match 'Windows 10' -and $build -lt 22000) {
        return New-Result -Status 'fail' -Observed ("{0} (build {1}): Windows 10 left support on 2025-10-14" -f $caption, $build) -Expected $expected
    }
    New-Result -Status 'pass' -Observed ("{0} (build {1})" -f $caption, $build) -Expected $expected
}

# ---------------------------------------------------------------------------------------------
# Cryptography and media
# ---------------------------------------------------------------------------------------------
Register-Check 'os.disk.encryption' {
    $expected = 'The system volume is encrypted'
    $drive = if ($null -ne $env:SystemDrive) { $env:SystemDrive } else { 'C:' }
    try {
        $volume = Get-BitLockerVolume -MountPoint $drive -ErrorAction Stop
        $status = if ($volume.VolumeStatus -eq 'FullyEncrypted') { 'pass' } else { 'fail' }
        return New-Result -Status $status -Observed ("{0} {1} ({2})" -f $drive, $volume.VolumeStatus, $volume.EncryptionMethod) -Expected $expected
    } catch {
        $text = (& manage-bde.exe -status $drive 2>&1) -join "`n"
        if ($text -match 'Conversion Status:\s*(.+)') {
            $state = $matches[1].Trim()
            $status = if ($state -match 'Fully Encrypted') { 'pass' } else { 'fail' }
            return New-Result -Status $status -Observed ("Conversion status: {0}" -f $state) -Expected $expected
        }
        return New-ErrorResult 'BitLocker status is unavailable (run elevated)' $expected
    }
}

Register-Check 'os.crypto.fips_mode' {
    $expected = 'The operating system runs its cryptography in FIPS mode'
    $value = Get-RegistryInt 'HKLM:\SYSTEM\CurrentControlSet\Control\Lsa\FipsAlgorithmPolicy' 'Enabled'
    if ($null -eq $value) {
        return New-Result -Status 'fail' -Observed 'FipsAlgorithmPolicy is not set' -Expected $expected
    }
    $status = if ($value -eq 1) { 'pass' } else { 'fail' }
    New-Result -Status $status -Observed ("FipsAlgorithmPolicy Enabled = {0}" -f $value) -Expected $expected
}

Register-Check 'os.crypto.legacy_tls_disabled' {
    $expected = 'SSL 2.0/3.0 and TLS 1.0/1.1 are disabled for the server and the client'
    $base = 'HKLM:\SYSTEM\CurrentControlSet\Control\SecurityProviders\SCHANNEL\Protocols'
    $enabled = @()
    foreach ($protocol in @('SSL 2.0', 'SSL 3.0', 'TLS 1.0', 'TLS 1.1')) {
        foreach ($role in @('Server', 'Client')) {
            $path = Join-Path (Join-Path $base $protocol) $role
            $value = Get-RegistryInt $path 'Enabled'
            $disabled = Get-RegistryInt $path 'DisabledByDefault'
            if ($null -eq $value -and $null -eq $disabled) {
                $enabled += ("{0} {1} (not configured)" -f $protocol, $role)
            } elseif ($null -ne $value -and $value -ne 0) {
                $enabled += ("{0} {1}" -f $protocol, $role)
            }
        }
    }
    $status = if ($enabled.Count -eq 0) { 'pass' } else { 'fail' }
    $names = if ($enabled.Count -gt 0) { $enabled -join ', ' } else { 'none' }
    New-Result -Status $status -Observed ("Legacy protocols enabled or unconfigured: {0}" -f $names) -Expected $expected
}

Register-Check 'os.crypto.smb_signing' {
    $expected = 'SMB signing is required on the server and the workstation'
    $server = $null
    $client = $null
    try { $server = [int] (Get-SmbServerConfiguration -ErrorAction Stop).RequireSecuritySignature } catch { $server = $null }
    try { $client = [int] (Get-SmbClientConfiguration -ErrorAction Stop).RequireSecuritySignature } catch { $client = $null }
    if ($null -eq $server) {
        $server = Get-RegistryInt 'HKLM:\SYSTEM\CurrentControlSet\Services\LanManServer\Parameters' 'RequireSecuritySignature'
    }
    if ($null -eq $client) {
        $client = Get-RegistryInt 'HKLM:\SYSTEM\CurrentControlSet\Services\LanmanWorkstation\Parameters' 'RequireSecuritySignature'
    }
    $ok = ($server -eq 1) -and ($client -eq 1)
    $status = if ($ok) { 'pass' } else { 'fail' }
    New-Result -Status $status -Observed ("Server RequireSecuritySignature = {0}; client = {1}" -f $server, $client) -Expected $expected
}

Register-Check 'os.media.usb_storage_blocked' {
    $expected = 'USB mass storage is blocked or restricted by policy'
    $start = Get-RegistryInt 'HKLM:\SYSTEM\CurrentControlSet\Services\USBSTOR' 'Start'
    $denyAll = Get-RegistryInt 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\RemovableStorageDevices' 'Deny_All'
    $blocked = ($start -eq 4) -or ($denyAll -eq 1)
    $status = if ($blocked) { 'pass' } else { 'fail' }
    New-Result -Status $status -Observed ("USBSTOR Start = {0}; RemovableStorageDevices Deny_All = {1}" -f $start, $denyAll) -Expected $expected
}

Register-Check 'os.media.autorun_disabled' {
    $expected = 'AutoRun and AutoPlay are disabled'
    $driveTypes = Get-RegistryInt 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\Explorer' 'NoDriveTypeAutoRun'
    $noAutorun = Get-RegistryInt 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\Explorer' 'NoAutorun'
    $ok = ($driveTypes -eq 255) -or ($noAutorun -eq 1)
    $status = if ($ok) { 'pass' } else { 'fail' }
    New-Result -Status $status -Observed ("NoDriveTypeAutoRun = {0}; NoAutorun = {1}" -f $driveTypes, $noAutorun) -Expected $expected
}

Register-Check 'os.platform.secure_boot' {
    $expected = 'Secure Boot is enabled'
    try {
        $enabled = Confirm-SecureBootUEFI -ErrorAction Stop
        $status = if ($enabled) { 'pass' } else { 'fail' }
        $state = if ($enabled) { 'enabled' } else { 'disabled' }
        return New-Result -Status $status -Observed ("Secure Boot {0}" -f $state) -Expected $expected
    } catch {
        return New-Result -Status 'not_applicable' -Observed 'Not a UEFI system, or the Secure Boot state is unavailable' -Expected $expected
    }
}

# ---------------------------------------------------------------------------------------------
# Inventory collection
# ---------------------------------------------------------------------------------------------
function Get-LocalUserInventory {
    <# Local accounts with their enabled and administrator flags. #>
    $adminNames = @()
    try {
        $members = Get-LocalGroupMember -Group 'Administrators' -ErrorAction Stop
        foreach ($member in $members) {
            $parts = ([string] $member.Name) -split '\\'
            $adminNames += $parts[$parts.Length - 1]
        }
    } catch {
        try {
            $capture = $false
            foreach ($line in (& net.exe localgroup Administrators 2>&1)) {
                $text = ([string] $line).Trim()
                if ($text -like '---*') { $capture = $true; continue }
                if ($capture -and $text -and $text -notlike 'The command*') { $adminNames += $text }
            }
        } catch {
            $adminNames = @()
        }
    }

    $users = @()
    try {
        foreach ($user in (Get-LocalUser -ErrorAction Stop)) {
            $lastDays = $null
            try {
                if ($null -ne $user.LastLogon) { $lastDays = [int] ((Get-Date) - $user.LastLogon).TotalDays }
            } catch {
                $lastDays = $null
            }
            $users += [pscustomobject]@{
                name            = $user.Name
                enabled         = [bool] $user.Enabled
                admin           = ($adminNames -contains $user.Name)
                last_logon_days = $lastDays
            }
        }
        return $users
    } catch {
        if ($adminNames.Count -eq 0) { return $null }
        foreach ($name in $adminNames) {
            $users += [pscustomobject]@{ name = $name; enabled = $true; admin = $true; last_logon_days = $null }
        }
        return $users
    }
}

function Get-InstalledSoftware {
    <# The uninstall registry keys, never Win32_Product (which repairs packages as a side effect). #>
    $paths = @(
        'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*',
        'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*'
    )
    $software = @()
    foreach ($path in $paths) {
        try {
            $entries = Get-ItemProperty -Path $path -ErrorAction SilentlyContinue
            foreach ($entry in $entries) {
                $name = $null
                try { $name = $entry.DisplayName } catch { $name = $null }
                if (-not $name) { continue }
                $version = $null
                $publisher = $null
                try { $version = $entry.DisplayVersion } catch { $version = $null }
                try { $publisher = $entry.Publisher } catch { $publisher = $null }
                $software += [pscustomobject]@{ name = $name; version = $version; publisher = $publisher }
            }
        } catch {
            continue
        }
    }
    return @($software | Sort-Object name -Unique)
}

function Get-ListeningPorts {
    $ports = @()
    try {
        foreach ($connection in (Get-NetTCPConnection -State Listen -ErrorAction Stop)) {
            $process = $null
            try {
                $process = (Get-Process -Id $connection.OwningProcess -ErrorAction SilentlyContinue).ProcessName
            } catch {
                $process = $null
            }
            $ports += [pscustomobject]@{ proto = 'tcp'; port = [int] $connection.LocalPort; process = $process }
        }
    } catch {
        foreach ($line in (& netstat.exe -ano 2>&1)) {
            $text = [string] $line
            if ($text -match '^\s*(TCP|UDP)\s+\S+:(\d+)\s+.*LISTENING') {
                $ports += [pscustomobject]@{ proto = $matches[1].ToLower(); port = [int] $matches[2]; process = $null }
            }
        }
    }
    try {
        foreach ($endpoint in (Get-NetUDPEndpoint -ErrorAction Stop)) {
            $ports += [pscustomobject]@{ proto = 'udp'; port = [int] $endpoint.LocalPort; process = $null }
        }
    } catch {
        # UDP endpoints are optional detail.
    }
    return @($ports | Sort-Object proto, port -Unique)
}

function Get-ServiceInventory {
    $services = @()
    try {
        foreach ($service in (Get-Service -ErrorAction Stop)) {
            $services += [pscustomobject]@{ name = $service.Name; state = ([string] $service.Status).ToLower() }
        }
    } catch {
        return @()
    }
    return @($services | Select-Object -First 400)
}

function Get-NetworkAddresses {
    $ips = @()
    $macs = @()
    try {
        foreach ($address in (Get-NetIPAddress -ErrorAction Stop | Where-Object { $_.AddressFamily -eq 'IPv4' -and $_.IPAddress -notlike '127.*' })) {
            $ips += [string] $address.IPAddress
        }
    } catch {
        try {
            foreach ($config in (Get-CimInstance Win32_NetworkAdapterConfiguration -ErrorAction Stop | Where-Object { $_.IPEnabled })) {
                foreach ($address in (ConvertTo-Array $config.IPAddress)) {
                    if ($address -notlike '127.*' -and $address -notlike '*:*') { $ips += [string] $address }
                }
            }
        } catch {
            $ips = @()
        }
    }
    try {
        foreach ($adapter in (Get-NetAdapter -ErrorAction Stop | Where-Object { $_.Status -eq 'Up' })) {
            if ($adapter.MacAddress) { $macs += ([string] $adapter.MacAddress).Replace('-', ':').ToLower() }
        }
    } catch {
        try {
            foreach ($config in (Get-CimInstance Win32_NetworkAdapterConfiguration -ErrorAction Stop | Where-Object { $_.IPEnabled })) {
                if ($config.MACAddress) { $macs += ([string] $config.MACAddress).ToLower() }
            }
        } catch {
            $macs = @()
        }
    }
    return @{ ips = @($ips | Select-Object -Unique); macs = @($macs | Select-Object -Unique) }
}

function Get-LoggedInUsers {
    $names = @()
    try {
        foreach ($line in (& query.exe user 2>&1)) {
            $text = ([string] $line).Trim()
            if ($text -and $text -notmatch '^USERNAME') {
                $names += ($text -split '\s+')[0].TrimStart('>')
            }
        }
    } catch {
        try {
            $cs = Get-CimInstance Win32_ComputerSystem -ErrorAction Stop
            if ($cs.UserName) { $names += [string] $cs.UserName }
        } catch {
            $names = @()
        }
    }
    return @($names | Select-Object -Unique)
}

function Get-SerialNumber {
    try {
        return [string] (Get-CimInstance Win32_BIOS -ErrorAction Stop).SerialNumber
    } catch {
        return $null
    }
}

# ---------------------------------------------------------------------------------------------
# Report assembly
# ---------------------------------------------------------------------------------------------
function Invoke-Checks {
    param([string] $Only)
    $results = @()
    foreach ($entry in $script:Checks) {
        if ($Only -and $entry.Id -ne $Only) { continue }
        Write-Verbose ("running {0}" -f $entry.Id)
        $outcome = $null
        try {
            $outcome = & $entry.Body
        } catch {
            $outcome = New-ErrorResult ("{0}" -f $_.Exception.Message)
        }
        if ($null -eq $outcome) {
            $outcome = New-ErrorResult 'the check returned no result'
        }
        $results += [pscustomobject]@{
            check_id = $entry.Id
            status   = $outcome.status
            observed = $outcome.observed
            expected = $outcome.expected
            details  = $outcome.details
            error    = $outcome.error
        }
    }
    return $results
}

function New-Report {
    param([string] $Only, [switch] $SkipInventory)
    $os = $null
    try { $os = Get-CimInstance Win32_OperatingSystem -ErrorAction Stop } catch { $os = $null }
    $cs = $null
    try { $cs = Get-CimInstance Win32_ComputerSystem -ErrorAction Stop } catch { $cs = $null }
    $addresses = Get-NetworkAddresses
    $fqdn = $env:COMPUTERNAME
    try {
        $fqdn = [System.Net.Dns]::GetHostEntry($env:COMPUTERNAME).HostName
    } catch {
        $fqdn = $env:COMPUTERNAME
    }

    $inventory = @{}
    if (-not $SkipInventory) {
        $users = Get-LocalUserInventory
        $inventory = @{
            local_users     = @(ConvertTo-Array $users | ForEach-Object {
                @{ name = $_.name; enabled = $_.enabled; admin = $_.admin; last_logon = $_.last_logon_days }
            })
            software        = @(Get-InstalledSoftware | Select-Object -First 500)
            listening_ports = @(Get-ListeningPorts)
            services        = @(Get-ServiceInventory)
        }
    }

    return [pscustomobject]@{
        schema_version = $SchemaVersion
        agent          = @{ name = 'bulwark-agent'; version = $AgentVersion; platform = 'windows' }
        asset          = @{
            hostname        = $env:COMPUTERNAME
            fqdn            = $fqdn
            os_family       = 'windows'
            os_name         = if ($os) { [string] $os.Caption } else { 'Windows' }
            os_version      = if ($os) { [string] $os.Version } else { [string] [System.Environment]::OSVersion.Version }
            arch            = if ($os) { [string] $os.OSArchitecture } else { $env:PROCESSOR_ARCHITECTURE }
            domain          = if ($cs -and $cs.PartOfDomain) { [string] $cs.Domain } else { $null }
            serial_number   = Get-SerialNumber
            ip_addresses    = @($addresses.ips)
            mac_addresses   = @($addresses.macs)
            logged_in_users = @(Get-LoggedInUsers)
        }
        collected_at   = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
        checks         = @(Invoke-Checks -Only $Only)
        inventory      = $inventory
    }
}

function Send-Report {
    param([string] $ServerUrl, [string] $EnrollmentKey, $Report, [int] $Timeout, [switch] $SkipCertificateCheck)
    $url = $ServerUrl.TrimEnd('/') + '/api/agents/report'
    $body = $Report | ConvertTo-Json -Depth 8 -Compress
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    if ($SkipCertificateCheck) {
        Write-Warning 'TLS certificate verification is disabled.'
        [System.Net.ServicePointManager]::ServerCertificateValidationCallback = { $true }
    }
    $headers = @{ Authorization = ('Bearer ' + $EnrollmentKey) }
    return Invoke-RestMethod -Uri $url -Method Post -Body $body -ContentType 'application/json' -Headers $headers -TimeoutSec $Timeout
}

function Install-Task {
    param([string] $ServerUrl, [string] $EnrollmentKey, [switch] $SkipCertificateCheck)
    $directory = Split-Path -Parent $ConfigPath
    if (-not (Test-Path $directory)) { $null = New-Item -ItemType Directory -Path $directory -Force }
    $config = @{ server = $ServerUrl; key = $EnrollmentKey; insecure = [bool] $SkipCertificateCheck }
    $config | ConvertTo-Json | Set-Content -LiteralPath $ConfigPath -Encoding UTF8
    try {
        $acl = Get-Acl -LiteralPath $ConfigPath
        $acl.SetAccessRuleProtection($true, $false)
        $acl.Access | ForEach-Object { $null = $acl.RemoveAccessRule($_) }
        foreach ($account in @('NT AUTHORITY\SYSTEM', 'BUILTIN\Administrators')) {
            $rule = New-Object System.Security.AccessControl.FileSystemAccessRule($account, 'FullControl', 'Allow')
            $acl.AddAccessRule($rule)
        }
        Set-Acl -LiteralPath $ConfigPath -AclObject $acl
    } catch {
        Write-Warning ("Could not restrict permissions on {0}: {1}" -f $ConfigPath, $_.Exception.Message)
    }

    $minute = [math]::Abs($env:COMPUTERNAME.GetHashCode()) % 60
    $time = '03:{0:d2}' -f $minute
    $scriptPath = $PSCommandPath
    if (-not $scriptPath) { $scriptPath = Join-Path $PSScriptRoot 'Bulwark-Agent.ps1' }
    $command = ('powershell.exe -NoProfile -ExecutionPolicy Bypass -File "{0}"' -f $scriptPath)
    $output = & schtasks.exe /Create /TN 'Bulwark Agent' /TR $command /SC DAILY /ST $time /RU SYSTEM /RL HIGHEST /F 2>&1
    return ($output -join "`n")
}

function Uninstall-Task {
    $output = & schtasks.exe /Delete /TN 'Bulwark Agent' /F 2>&1
    return ($output -join "`n")
}

# ---------------------------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------------------------
if ($Version) {
    Write-Output ('bulwark-agent {0}' -f $AgentVersion)
    exit 0
}

if ($ListChecks) {
    foreach ($entry in ($script:Checks | Sort-Object Id)) { Write-Output $entry.Id }
    exit 0
}

# Parameters win over the stored configuration.
if ((-not $Server -or -not $Key) -and (Test-Path $ConfigPath)) {
    try {
        $stored = Get-Content -LiteralPath $ConfigPath -Raw | ConvertFrom-Json
        $storedNames = @($stored.PSObject.Properties.Name)
        if (-not $Server -and ($storedNames -contains 'server')) { $Server = [string] $stored.server }
        if (-not $Key -and ($storedNames -contains 'key')) { $Key = [string] $stored.key }
        if (($storedNames -contains 'insecure') -and $stored.insecure) { $Insecure = [switch]::Present }
    } catch {
        Write-Warning ("Could not read {0}" -f $ConfigPath)
    }
}

if ($UninstallScheduledTask) {
    Write-Output (Uninstall-Task)
    exit 0
}

if ($InstallScheduledTask) {
    if (-not $Server -or -not $Key) {
        Write-Error 'InstallScheduledTask needs -Server and -Key'
        exit 3
    }
    Write-Output (Install-Task -ServerUrl $Server -EnrollmentKey $Key -SkipCertificateCheck:$Insecure)
    exit 0
}

if ($Check -and -not ($script:Checks | Where-Object { $_.Id -eq $Check })) {
    Write-Error ("Unknown check: {0}" -f $Check)
    exit 3
}

if (-not (Test-IsElevated)) {
    Write-Warning 'Not running elevated: audit, password policy and BitLocker checks will report errors.'
}

$report = New-Report -Only $Check -SkipInventory:$NoInventory
$counts = @{}
foreach ($item in $report.checks) {
    if ($counts.ContainsKey($item.status)) { $counts[$item.status] = $counts[$item.status] + 1 }
    else { $counts[$item.status] = 1 }
}
$summary = (@($counts.Keys | Sort-Object | ForEach-Object { "{0} {1}" -f $counts[$_], $_ }) -join ', ')

if ($Output) {
    $report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $Output -Encoding UTF8
    Write-Output ("Wrote {0} ({1} checks: {2})" -f $Output, $report.checks.Count, $summary)
    exit 0
}

if ($DryRun -or -not ($Server -and $Key)) {
    $report | ConvertTo-Json -Depth 8
    Write-Output ("{0} checks: {1}" -f $report.checks.Count, $summary)
    if ($DryRun) { exit 0 }
    Write-Error 'No server or key configured.'
    exit 3
}

try {
    $response = Send-Report -ServerUrl $Server -EnrollmentKey $Key -Report $report -Timeout $TimeoutSec -SkipCertificateCheck:$Insecure
} catch {
    Write-Error ("Could not send the report: {0}" -f $_.Exception.Message)
    exit 2
}

$responseNames = @()
if ($null -ne $response) { $responseNames = @($response.PSObject.Properties.Name) }
if (($responseNames -contains 'message') -and $response.message) {
    Write-Output $response.message
} else {
    Write-Output 'Report accepted'
}
if (($responseNames -contains 'findings') -and $response.findings -gt 0) {
    Write-Output ("{0} failing check(s) recorded as findings" -f $response.findings)
}
exit 0
