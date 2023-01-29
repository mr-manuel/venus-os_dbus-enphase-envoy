# Changelog

## v0.1.1
* Added: Better error handling
* Added: If PV power is below 5 W, than show 0 W. This prevents showing 1-2 W on PV when no sun is shining and during night

## v0.1.0
* Added: Calculation of `energy_forward` and `energy_reverse`, which are not provided by the Enphase Envoy. This allows you now, in combination with the `dbus-mqtt-grid` driver, to see import and export.
* Changed: Small bug fixes
* Changed: Code optimizations and cleanup

## v0.0.2
* Changed: Fixed some minor bugs
* Changed: Fixed that no historical data is shown in VRM portal
* Added: informations of PV system

## v0.0.1
Initial release
