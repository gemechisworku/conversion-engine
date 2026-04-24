param(
  [string]$LeadId = "",
  [string]$BookingId = "",
  [string]$SlotId = "",
  [string]$Timezone = "UTC",
  [string]$CalendarRef = "",
  [string]$Status = "confirmed",
  [string]$Start = "",
  [string]$End = "",
  [string]$IdempotencyKey = "",
  [switch]$Unconfirmed
)

$ErrorActionPreference = "Stop"

$argsList = @(
  "agent/scripts/live_smoke.py",
  "hubspot-booking",
  "--timezone", $Timezone,
  "--status", $Status
)

if ($LeadId) {
  $argsList += @("--lead-id", $LeadId)
}
if ($BookingId) {
  $argsList += @("--booking-id", $BookingId)
}
if ($SlotId) {
  $argsList += @("--slot-id", $SlotId)
}
if ($CalendarRef) {
  $argsList += @("--calendar-ref", $CalendarRef)
}
if ($Start) {
  $argsList += @("--start", $Start)
}
if ($End) {
  $argsList += @("--end", $End)
}
if ($IdempotencyKey) {
  $argsList += @("--idempotency-key", $IdempotencyKey)
}
if ($Unconfirmed) {
  $argsList += "--unconfirmed"
}

python @argsList

