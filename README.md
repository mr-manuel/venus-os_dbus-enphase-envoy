# dbus-enphase-envoy - Emulates Enphase Microinverters as a single PV inverter

<small>GitHub repository: [mr-manuel/venus-os_dbus-enphase-envoy](https://github.com/mr-manuel/venus-os_dbus-enphase-envoy)</small>

### Disclaimer

I wrote this script for myself. I'm not responsible, if you damage something using my script.


### Purpose

This script adds the Enphase Microinverters as a single PV system in Venus OS. The data is fetched from the Enphase Envoy-S device and published on the dbus as the service `com.victronenergy.pvinverter.enphase_envoy` with the VRM instance `61`. The number of phases are automatically recognized, so it displays automatically the number of phases you are using (one, two or three).

It is also possible to publish the following data as JSON to an MQTT topic for other use (can be enabled in `config.ini`). For each list element a different topic is needed:

* **Meters** (PV, Grid, Consumption): Power, current, voltage, powerreact, powerappearent, powerfactor, frequency, whToday, vahToday, whLifetime, vahLifetime for total (except: powerfactor and frequency), L1, L2 and L3

* **Devices** (Microinverters, Q-Relay): Serial number, device status, producing, communicating, provisioned and operating. For Q-Relay additionaly: relay [opened/closed] and reason

* **Inverters**: Last report date and last report watts

* **Events**: Latest 10 events from the Enphase Envoy-S


If you also want to have the grid meter from the Enphase Envoy-S in Venus OS, then install the [mr-manuel/venus-os_dbus-mqtt-grid](https://github.com/mr-manuel/venus-os_dbus-mqtt-grid) and insert the same MQTT broker and topic in the `config.ini`. Shoudn't you already have a MQTT broker, than you can enable the Venus OS integrated MQTT broker `Venus OS GUI -> Menu -> Services -> MQTT on LAN (SSL) and if desired MQTT on LAN (Plaintext)`. In the `config.ini` insert the IP address of the Venus OS device or `127.0.0.1`.

### Config

Copy or rename the `config.sample.ini` to `config.ini` in the `dbus-enphase-envoy` folder and change it as you need it.


### JSON structure

<details><summary>PV, Grid, Consumption</summary>

```json
{
  "pv": {
    "L1": {
      "power": 0.000,
      "current": 0.000,
      "voltage": 0.000,
      "power_react": 0.00,
      "power_appearent": 0.000,
      "power_factor": 0.00,
      "frequency": 0,
      "whToday": 0.000,
      "vahToday": 0.000,
      "whLifetime": 0.000,
      "vahLifetime": 0.000
    },
    "L2": {
      "power": 0.000,
      "current": 0.000,
      "voltage": 0.000,
      "power_react": 0.00,
      "power_appearent": 0.000,
      "power_factor": 0.00,
      "frequency": 0,
      "whToday": 0.000,
      "vahToday": 0.000,
      "whLifetime": 0.000,
      "vahLifetime": 0.000
    },
    "L3": {
      "power": 0.000,
      "current": 0.000,
      "voltage": 0.000,
      "power_react": 0.00,
      "power_appearent": 0.000,
      "power_factor": 0.00,
      "frequency": 0,
      "whToday": 0.000,
      "vahToday": 0.000,
      "whLifetime": 0.000,
      "vahLifetime": 0.000
    },
    "power": 0.000,
    "current": 0.000,
    "voltage": 0.000,
    "power_react": 0.00,
    "power_appearent": 0.000,
    "whToday": 0.000,
    "vahToday": 0.000,
    "whLifetime": 0.000,
    "vahLifetime": 0.000
  },
  "grid": {
    "L1": {
      "power": 0.000,
      "current": 0.000,
      "voltage": 0.000,
      "power_react": 0.00,
      "power_appearent": 0.000,
      "power_factor": 0.00,
      "frequency": 0,
      "whToday": 0.000,
      "vahToday": 0.000,
      "whLifetime": 0.000,
      "vahLifetime": 0.000
    },
    "L2": {
      "power": 0.000,
      "current": 0.000,
      "voltage": 0.000,
      "power_react": 0.00,
      "power_appearent": 0.000,
      "power_factor": 0.00,
      "frequency": 0,
      "whToday": 0.000,
      "vahToday": 0.000,
      "whLifetime": 0.000,
      "vahLifetime": 0.000
    },
    "L3": {
      "power": 0.000,
      "current": 0.000,
      "voltage": 0.000,
      "power_react": 0.00,
      "power_appearent": 0.000,
      "power_factor": 0.00,
      "frequency": 0,
      "whToday": 0.000,
      "vahToday": 0.000,
      "whLifetime": 0.000,
      "vahLifetime": 0.000
    },
    "power": 0.000,
    "current": 0.000,
    "voltage": 0.000,
    "power_react": 0.00,
    "power_appearent": 0.000,
    "whToday": 0.000,
    "vahToday": 0.000,
    "whLifetime": 0.000,
    "vahLifetime": 0.000
  },
  "consumption": {
    "L1": {
      "power": 0.000,
      "current": 0.000,
      "voltage": 0.000,
      "power_react": 0.00,
      "power_appearent": 0.000,
      "power_factor": 0.00,
      "frequency": 0,
      "whToday": 0.000,
      "vahToday": 0.000,
      "whLifetime": 0.000,
      "vahLifetime": 0.000
    },
    "L2": {
      "power": 0.000,
      "current": 0.000,
      "voltage": 0.000,
      "power_react": 0.00,
      "power_appearent": 0.000,
      "power_factor": 0.00,
      "frequency": 0,
      "whToday": 0.000,
      "vahToday": 0.000,
      "whLifetime": 0.000,
      "vahLifetime": 0.000
    },
    "L3": {
      "power": 0.000,
      "current": 0.000,
      "voltage": 0.000,
      "power_react": 0.00,
      "power_appearent": 0.000,
      "power_factor": 0.00,
      "frequency": 0,
      "whToday": 0.000,
      "vahToday": 0.000,
      "whLifetime": 0.000,
      "vahLifetime": 0.000
    },
    "power": 0.000,
    "current": 0.000,
    "voltage": 0.000,
    "power_react": 0.00,
    "power_appearent": 0.000,
    "whToday": 0.000,
    "vahToday": 0.000,
    "whLifetime": 0.000,
    "vahLifetime": 0.000
  }
}
```
</details>

<details><summary>Devices</summary>

```json
{
  "inverters": {
    "122000000001": {
      "status": [
        "envoy.global.ok"
      ],
      "producing": true,
      "communicating": true,
      "provisioned": true,
      "operating": true
    },
    "122000000002": {
      "status": [
        "envoy.global.ok"
      ],
      "producing": true,
      "communicating": true,
      "provisioned": true,
      "operating": true
    },
    "122000000003": {
      "status": [
        "envoy.global.ok"
      ],
      "producing": true,
      "communicating": true,
      "provisioned": true,
      "operating": true
    }
  },
  "batteries": {},
  "relais": {
    "122100000001": {
      "status": [
        "envoy.global.ok"
      ],
      "producing": false,
      "communicating": true,
      "provisioned": true,
      "operating": true,
      "relay": "closed",
      "reason": "ok"
    }
  }
}
```
</details>

<details><summary>Inverters</summary>

```json
{
  "122000000001": {
    "lastReportDate": 1667471311,
    "lastReportWatts": 50
  },
  "122000000002": {
    "lastReportDate": 1667471311,
    "lastReportWatts": 60
  },
  "122000000003": {
    "lastReportDate": 1667471311,
    "lastReportWatts": 70
  }
}
```
</details>

<details><summary>Events</summary>

```json
{
  "3015": {
    "message": "Microinverter failed to report: Set",
    "serialNumber": "122000000001",
    "type": "pcu ",
    "datetime": "Wed Nov 02, 2022 04:53 PM CET"
  },
  "3016": {
    "message": "Microinverter failed to report: Clear",
    "serialNumber": "122000000002",
    "type": "pcu ",
    "datetime": "Wed Nov 02, 2022 04:54 PM CET"
  },
  "3017": {
    "message": "Microinverter failed to report: Set",
    "serialNumber": "122000000002",
    "type": "pcu ",
    "datetime": "Wed Nov 02, 2022 04:54 PM CET"
  },
  "3018": {
    "message": "Microinverter failed to report: Clear",
    "serialNumber": "122000000002",
    "type": "pcu ",
    "datetime": "Thu Nov 03, 2022 07:12 AM CET"
  },
  "3019": {
    "message": "Microinverter failed to report: Clear",
    "serialNumber": "122000000001",
    "type": "pcu ",
    "datetime": "Thu Nov 03, 2022 07:12 AM CET"
  },
  "3020": {
    "message": "Power On Reset",
    "serialNumber": "122000000002",
    "type": "pcu ",
    "datetime": "Thu Nov 03, 2022 07:12 AM CET"
  },
  "3021": {
    "message": "DC Voltage Too Low: Clear",
    "serialNumber": "122000000001",
    "type": "pcu channel 1",
    "datetime": "Thu Nov 03, 2022 07:42 AM CET"
  },
  "3022": {
    "message": "Power On Reset",
    "serialNumber": "122000000001",
    "type": "pcu ",
    "datetime": "Thu Nov 03, 2022 07:12 AM CET"
  },
  "3023": {
    "message": "DC Power Too Low: Clear",
    "serialNumber": "122000000002",
    "type": "pcu ",
    "datetime": "Thu Nov 03, 2022 08:01 AM CET"
  },
  "3024": {
    "message": "DC Power Too Low: Clear",
    "serialNumber": "122000000001",
    "type": "pcu ",
    "datetime": "Thu Nov 03, 2022 08:00 AM CET"
  }
}
```
</details>


### Install

1. Copy the `dbus-enphase-envoy` folder to `/data/etc` on your Venus OS device

2. Run `bash /data/etc/dbus-enphase-envoy/install.sh` as root

   The daemon-tools should start this service automatically within seconds.

### Uninstall

Run `/data/etc/dbus-enphase-envoy/uninstall.sh`

### Restart

Run `/data/etc/dbus-enphase-envoy/restart.sh`

### Debugging

The logs can be checked with `tail -n 100 -f /data/log/dbus-enphase-envoy/current`

The service status can be checked with svstat `svstat /service/dbus-enphase-envoy`

This will output somethink like `/service/dbus-enphase-envoy: up (pid 5845) 185 seconds`

If the seconds are under 5 then the service crashes and gets restarted all the time. If you do not see anything in the logs you can increase the log level in `/data/etc/dbus-enphase-envoy/dbus-enphase-envoy.py` by changing `level=logging.WARNING` to `level=logging.INFO` or `level=logging.DEBUG`

If the script stops with the message `dbus.exceptions.NameExistsException: Bus name already exists: com.victronenergy.pvinverter.enphase_envoy"` it means that the service is still running or another service is using that bus name.

### Compatibility

It was tested on Venus OS Large `v2.92` on the following devices:

* RaspberryPi 4b
* MultiPlus II (GX Version)

### Screenshots

<details><summary>Power L1</summary>

![Pv power L1 - pages](/screenshots/pv_power_L1_pages.png)
![Pv power L1 - device list](/screenshots/pv_power_L1_device-list.png)
![Pv power L1 - device list - enphase envoy 1](/screenshots/pv_power_L1_device-list_enphase-envoy-1.png)
![Pv power L1 - device list - enphase envoy 2](/screenshots/pv_power_L1_device-list_enphase-envoy-2.png)

</details>

<details><summary>Power L1 and L2</summary>

![Pv power L1, L2 - pages](/screenshots/pv_power_L2_L1_pages.png)
![Pv power L1, L2 - device list](/screenshots/pv_power_L2_L1_device-list.png)
![Pv power L1, L2 - device list - enphase envoy 1](/screenshots/pv_power_L2_L1_device-list_enphase-envoy-1.png)
![Pv power L1, L2 - device list - enphase envoy 2](/screenshots/pv_power_L2_L1_device-list_enphase-envoy-2.png)

</details>

<details><summary>Power L1, L2 and L3</summary>

![Pv power L1, L2, L3 - pages](/screenshots/pv_power_L3_L2_L1_pages.png)
![Pv power L1, L2, L3 - device list](/screenshots/pv_power_L3_L2_L1_device-list.png)
![Pv power L1, L2, L3 - device list - enphase envoy 1](/screenshots/pv_power_L3_L2_L1_device-list_enphase-envoy-1.png)
![Pv power L1, L2, L3 - device list - enphase envoy 2](/screenshots/pv_power_L3_L2_L1_device-list_enphase-envoy-2.png)

</details>
