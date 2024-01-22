# Changelog

## v0.2.2
* Changed: Fixed status flapping between running and standby

## v0.2.1
* Changed: Increased timeout for fetch_meter_stream() from 5 seconds to 60 seconds. Output a warning, if it take longer than 5 seconds

## v0.2.0
* Added: StatusCode: 7 = Running; 8 = Standby (if power below 5 W)

## v0.2.0-beta3
* Changed: Fixed that the driver does not start when selecting D5 firmware (#5)

## v0.2.0-beta2
* Added: Publish Enphase auth token, microinverter config, reporting and producing count
* Changed: Set microinveter power to 0 after 1200 seconds instead of 900 seconds

## v0.2.0-beta1
* Added: Support for D7.x.x firmware
* Changed: Improved driver stability
* Changed: Improved further the error handling

## v0.1.5
* Added: Show how much microinverters are currently producing power and if some are not reporting

## v0.1.4
* Changed: Fix crash when rounding none value

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
