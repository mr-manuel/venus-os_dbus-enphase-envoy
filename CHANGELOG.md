# Changelog

## v0.1.3
* Added: Frequency
* Added: Show to which broker and port the connection was made when logging is set to INFO
* Added: Try to reconnect every 15 seconds to MQTT broker, if connection is closed abnormally
* Changed: Fixed code errors
* Changed: Improved error handling and output

## v0.1.2
* Added: Better error handling for secondary requests
* Added: Don't send 0 values on first run
* Added: Set logging level in `config.default.ini`
* Added: Warning message, if a HTTP request took more than 5 s
* Added: Warning message, if stream data is not ready after 15 s
* Changed: Default settings in `config.default.ini`
* Changed: Fetch inverters - Default interval from 60 s to 300 s
* Changed: Fetch inverters - Minimum interval from 5 s to 60 s
* Changed: HTTP request timeout from 5 s to 60 s for secondary requests
* Changed: Logging levels of different messages for clearer output

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
