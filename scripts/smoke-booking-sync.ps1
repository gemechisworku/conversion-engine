param(
  [Parameter(Mandatory = $true)]
  [string]$ProspectEmail,
  [string]$ProspectName = "",
  [string]$Timezone = "UTC",
  [string]$LeadId = "",
  [string]$CompanyName = "",
  [string]$CompanyDomain = "",
  [string]$SlotId = "",
  [string]$Start = "",
  [string]$End = "",
  [switch]$Unconfirmed,
  [switch]$SkipCrm
)

$ErrorActionPreference = "Stop"

$argsList = @(
  "agent/scripts/live_smoke.py",
  "booking-sync",
  "--prospect-email", $ProspectEmail,
  "--timezone", $Timezone
)

if ($ProspectName) {
  $argsList += @("--prospect-name", $ProspectName)
}
if ($LeadId) {
  $argsList += @("--lead-id", $LeadId)
}
if ($CompanyName) {
  $argsList += @("--company-name", $CompanyName)
}
if ($CompanyDomain) {
  $argsList += @("--company-domain", $CompanyDomain)
}
if ($SlotId) {
  $argsList += @("--slot-id", $SlotId)
}
if ($Start) {
  $argsList += @("--start", $Start)
}
if ($End) {
  $argsList += @("--end", $End)
}
if ($Unconfirmed) {
  $argsList += "--unconfirmed"
}
if ($SkipCrm) {
  $argsList += "--skip-crm"
}

python @argsList
