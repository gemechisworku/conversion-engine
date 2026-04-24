param(
  [switch]$Strict
)

$ErrorActionPreference = "Stop"

$argsList = @("agent/scripts/live_smoke.py", "hubspot-tools")
if ($Strict) {
  $argsList += "--strict"
}
python @argsList
