#!/usr/bin/env python

from gi.repository import GLib  # pyright: ignore[reportMissingImports]
import platform
import logging
import sys
import os
from time import sleep, time
# from datetime import datetime
import json
import paho.mqtt.client as mqtt
import configparser  # for config/ini file
import _thread

import threading
import requests
from requests.auth import HTTPDigestAuth
from functools import reduce

# import to request new token
from enphasetoken import getToken

# import Victron Energy packages
sys.path.insert(1, os.path.join(os.path.dirname(__file__), 'ext', 'velib_python'))
from vedbus import VeDbusService

# disable "InsecureRequestWarning: Unverified HTTPS request is being made." warnings
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# get values from config.ini file
try:
    config_file = (os.path.dirname(os.path.realpath(__file__))) + "/config.ini"
    if os.path.exists(config_file):
        config = configparser.RawConfigParser()
        config.read(config_file)
        if (config['ENVOY']['address'] == "IP_ADDR_OR_FQDN"):
            print("ERROR:The \"config.ini\" is using invalid default values like IP_ADDR_OR_FQDN. The driver restarts in 60 seconds.")
            sleep(60)
            sys.exit()
    else:
        print("ERROR:The \"" + config_file + "\" is not found. Did you copy or rename the \"config.sample.ini\" to \"config.ini\"? The driver restarts in 60 seconds.")
        sleep(60)
        sys.exit()

except Exception:
    exception_type, exception_object, exception_traceback = sys.exc_info()
    file = exception_traceback.tb_frame.f_code.co_filename
    line = exception_traceback.tb_lineno
    print(f"Exception occurred: {repr(exception_object)} of type {exception_type} in {file} line #{line}")
    print("ERROR:The driver restarts in 60 seconds.")
    sleep(60)
    sys.exit()


# Get logging level from config.ini
# ERROR = shows errors only
# WARNING = shows ERROR and warnings
# INFO = shows WARNING and running functions
# DEBUG = shows INFO and data/values
if 'DEFAULT' in config and 'logging' in config['DEFAULT']:
    if config['DEFAULT']['logging'] == 'DEBUG':
        logging.basicConfig(level=logging.DEBUG)
    elif config['DEFAULT']['logging'] == 'INFO':
        logging.basicConfig(level=logging.INFO)
    elif config['DEFAULT']['logging'] == 'ERROR':
        logging.basicConfig(level=logging.ERROR)
    else:
        logging.basicConfig(level=logging.WARNING)
else:
    logging.basicConfig(level=logging.WARNING)


# check if MQTT is enabled in config
if 'MQTT' in config and 'enabled' in config['MQTT'] and config['MQTT']['enabled'] == '1':
    MQTT_enabled = 1
else:
    MQTT_enabled = 0


# checks for D7.x.x firmware
if 'ENVOY' in config and 'firmware' in config['ENVOY'] and config['ENVOY']['firmware'] == "D7":
    request_auth = "token"
    request_schema = "https"
    error = []

    if (
        'ENVOY' in config
        and 'enlighten_user' in config['ENVOY']
        and config['ENVOY']['enlighten_user'] != ""
    ):
        envoy_enlighten_user = config['ENVOY']['enlighten_user']
    else:
        error.append("enlighten_user")

    if (
        'ENVOY' in config
        and 'enlighten_password' in config['ENVOY']
        and config['ENVOY']['enlighten_password'] != ""
    ):
        envoy_enlighten_password = config['ENVOY']['enlighten_password']
    else:
        error.append("enlighten_password")

    if (
        'ENVOY' in config
        and 'serial' in config['ENVOY']
        and config['ENVOY']['serial'] != ""
    ):
        envoy_serial = config['ENVOY']['serial']
    else:
        error.append("serial")

    if len(error) > 0:
        logging.error('This Envoy values are missing in the "config.ini": ' + ", ".join(error))
        logging.error("The driver restarts in 60 seconds.")
        sleep(60)
        sys.exit()

    logging.error("D7 firmware selected")

# checks for D5.x.x firmware
else:
    request_auth = "digest"
    request_schema = "http"

    if "ENVOY" in config and "password" in config['ENVOY'] and config['ENVOY']['password'] != "":
        envoy_password = config['ENVOY']['password']
    else:
        logging.error('This Envoy values are missing in the "config.ini": password')
        logging.error("The driver restarts in 60 seconds.")
        sleep(60)
        sys.exit()

    logging.error("D5 firmware selected")


# check if fetch_production_historic_interval is enabled in config and not under minimum value
if 'ENVOY' in config and 'fetch_production_historic_interval' in config['ENVOY'] and int(config['ENVOY']['fetch_production_historic_interval']) > 900:
    fetch_production_historic_interval = int(config['ENVOY']['fetch_production_historic_interval'])
else:
    fetch_production_historic_interval = 900

# check if fetch_production_historic_interval is enabled in config and not under minimum value
if 'PV' in config and 'inverter_count' in config['PV'] and 'inverter_type' in config['PV']:
    hardware = config['PV']['inverter_count'] + 'x ' + config['PV']['inverter_type']
    inverters = {
        "config": int(config['PV']['inverter_count']),
        "reporting": 0,
        "producing": 0
    }
else:
    hardware = 'Microinverters'
    inverters = {
        "config": None,
        "reporting": 0,
        "producing": 0
    }

# check if fetch_devices is enabled in config
if 'DATA' in config and 'fetch_devices' in config['DATA'] and config['DATA']['fetch_devices'] == '1':
    fetch_devices_enabled = 1
    # check if fetch_devices_interval is enabled in config and not under minimum value
    if 'DATA' in config and 'fetch_devices_interval' in config['DATA'] and int(config['DATA']['fetch_devices_interval']) > 60:
        fetch_devices_interval = int(config['DATA']['fetch_devices_interval'])
    else:
        fetch_devices_interval = 60
    # check fetch_devices_publishing_type
    if 'DATA' in config and 'fetch_devices_publishing_type' in config['DATA'] and config['DATA']['fetch_devices_publishing_type'] == '0':
        fetch_devices_publishing_type = 0
    else:
        fetch_devices_publishing_type = 1
else:
    fetch_devices_enabled = 0
    fetch_devices_interval = 3600
    fetch_devices_publishing_type = 0

# check if fetch_inverters is enabled in config
if 'DATA' in config and 'fetch_inverters' in config['DATA'] and config['DATA']['fetch_inverters'] == '1':
    fetch_inverters_enabled = 1
    # check if fetch_inverters_interval is enabled in config and not under minimum value
    if 'DATA' in config and 'fetch_inverters_interval' in config['DATA'] and int(config['DATA']['fetch_inverters_interval']) > 5:
        fetch_inverters_interval = int(config['DATA']['fetch_inverters_interval'])
    else:
        fetch_inverters_interval = 5
    # check fetch_inverters_publishing_type
    if 'DATA' in config and 'fetch_inverters_publishing_type' in config['DATA'] and config['DATA']['fetch_inverters_publishing_type'] == '0':
        fetch_inverters_publishing_type = 0
    else:
        fetch_inverters_publishing_type = 1
else:
    fetch_inverters_enabled = 0
    fetch_inverters_interval = 300
    fetch_inverters_publishing_type = 0

# check if fetch_events is enabled in config
if 'DATA' in config and 'fetch_events' in config['DATA'] and config['DATA']['fetch_events'] == '1':
    fetch_events_enabled = 1
    # check if fetch_events_interval is enabled in config and not under minimum value
    if 'DATA' in config and 'fetch_events_interval' in config['DATA'] and int(config['DATA']['fetch_events_interval']) > 900:
        fetch_events_interval = int(config['DATA']['fetch_events_interval'])
    else:
        fetch_events_interval = 900
    # check fetch_events_publishing_type
    if 'DATA' in config and 'fetch_events_publishing_type' in config['DATA'] and config['DATA']['fetch_events_publishing_type'] == '0':
        fetch_events_publishing_type = 0
    else:
        fetch_events_publishing_type = 1
else:
    fetch_events_enabled = 0
    fetch_events_interval = 3600
    fetch_events_publishing_type = 0


# set variables
connected = 0
keep_running = True

replace_meters = ('production', 'pv'), ('net-consumption', 'grid'), ('total-consumption', 'consumption')
replace_phases = ('ph-a', 'L1'), ('ph-b', 'L2'), ('ph-c', 'L3')
replace_devices = ('PCU', 'inverters'), ('ACB', 'batteries'), ('NSRB', 'relais')

data_meter_stream = {}
data_production_historic = {}
data_devices = {}
data_inverters = {}
data_events = {}

fetch_production_historic_last = 0
fetch_devices_last = 0
fetch_inverters_last = 0
fetch_events_last = 0

auth_token = {
    "auth_token": "",
    "created": 0,
    "check_last": 0,
    "check_result": False
}
request_headers = {}


# MQTT
def on_disconnect(client, userdata, rc):
    global connected
    logging.warning("MQTT client: Got disconnected")
    if rc != 0:
        logging.warning("MQTT client: Unexpected MQTT disconnection. Will auto-reconnect")
    else:
        logging.warning("MQTT client: rc value:" + str(rc))

    while connected == 0:
        try:
            logging.warning("MQTT client: Trying to reconnect")
            client.connect(config['MQTT']['broker_address'])
            connected = 1
        except Exception:
            exception_type, exception_object, exception_traceback = sys.exc_info()
            file = exception_traceback.tb_frame.f_code.co_filename
            line = exception_traceback.tb_lineno
            logging.error(f"MQTT client: Exception occurred: {repr(exception_object)} of type {exception_type} in {file} line #{line}")

            logging.error(f"MQTT client: Error in retrying to connect with broker ({config['MQTT']['broker_address']}:{config['MQTT']['broker_port']})")
            logging.error("MQTT client: Retrying in 15 seconds")
            connected = 0
            sleep(15)


def on_connect(client, userdata, flags, rc):
    global connected
    if rc == 0:
        logging.info("MQTT client: Connected to MQTT broker!")
        connected = 1
    else:
        logging.error("MQTT client: Failed to connect, return code %d\n", rc)


def on_publish(client, userdata, rc):
    pass


def tokenManager():
    global envoy_enlighten_user, envoy_enlighten_password, envoy_serial, request_headers, auth_token

    logging.info("step: tokenManager")

    while 1:
        # check expiry on first run and then once every minute
        if auth_token["check_last"] < int(time()) - 59:

            # request token from file system or generate a new one if missing or about to expire
            token = getToken(envoy_enlighten_user, envoy_enlighten_password, envoy_serial)
            result = token.refresh()

            if result:
                request_headers = {
                    "Authorization": "Bearer " + result['auth_token']
                }
                auth_token = {
                    "auth_token": result['auth_token'],
                    "created": result['created'],
                    "check_last": int(time()),
                    "check_result": True
                }
                # logging.error(f"Token created on: {datetime.fromtimestamp(result['created'])} UTC")
            else:
                # check again in 5 minutes
                auth_token["check_last"] = int(time()) - 86400 + 900
                logging.error("Token was not loaded/renewed! Check again in 5 minutes")

        sleep(60)


# ENPHASE - ENOVY-S
def fetch_meter_stream():
    logging.info("step: fetch_meter_stream")

    global config, error_count, keep_running, \
        request_auth, request_headers, request_schema,\
        data_meter_stream, data_production_historic

    error_count = 0
    marker = b'data: '

    # create dictionary for later to count watt hours
    data_watt_hours = {
        'time_creation': round(time(), 0),
        'count': 0
    }
    # calculate and save watthours after every x seconds
    data_watt_hours_timespan = 60
    # save file to non volatile storage after x seconds
    data_watt_hours_save = 900
    # file to save watt hours on persistent storage
    data_watt_hours_storage_file = '/data/etc/dbus-enphase-envoy/data_watt_hours.json'
    # file to save many writing operations (best on ramdisk to not wear SD card)
    data_watt_hours_working_file = '/var/volatile/tmp/dbus-enphase-envoy_data_watt_hours.json'
    # get last modification timestamp
    timestamp_storage_file = os.path.getmtime(data_watt_hours_storage_file) if os.path.isfile(data_watt_hours_storage_file) else 0

    # load data to prevent sending 0 watthours for grid before the first loop
    # check if file in volatile storage exists
    if os.path.isfile(data_watt_hours_working_file):
        with open(data_watt_hours_working_file, 'r') as file:
            file = open(data_watt_hours_working_file, "r")
            json_data = json.load(file)
            logging.info("Loaded JSON for energy forward/reverse once")
            logging.debug(json.dumps(json_data))
    # if not, check if file in persistent storage exists
    elif os.path.isfile(data_watt_hours_storage_file):
        with open(data_watt_hours_storage_file, 'r') as file:
            file = open(data_watt_hours_storage_file, "r")
            json_data = json.load(file)
            logging.info("Loaded JSON for energy forward/reverse once from persistent storage")
            logging.debug(json.dumps(json_data))
    else:
        json_data = {}

    while 1:
        try:
            url = '%s://%s/stream/meter' % (request_schema, config['ENVOY']['address'])
            if request_auth == "token":
                response = requests.get(
                    url,
                    stream=True,
                    timeout=5,
                    headers=request_headers,
                    verify=False
                )
            else:
                response = requests.get(
                    url,
                    stream=True,
                    timeout=5,
                    auth=HTTPDigestAuth('installer', config['ENVOY']['password'])
                )

            if response.status_code != 200:
                logging.error(f"--> fetch_meter_stream(): Received HTTP status code {response.status_code}. Restarting the driver in 60 seconds.")
                sleep(60)
                keep_running = False
                sys.exit()

            for row in response.iter_lines():

                if keep_running is False:
                    logging.info("--> fetch_meter_stream(): got exit signal")
                    sys.exit()

                if row.startswith(marker):
                    data = json.loads(row.replace(marker, b''))

                    # set timestamp when row is read
                    timestamp = round(time(), 0)
                    total_jsonpayload = {}

                    for meter in ['production', 'net-consumption', 'total-consumption']:

                        meter_name = reduce(lambda a, kv: a.replace(*kv), replace_meters, meter)

                        jsonpayload = {}

                        total_power = 0
                        total_current = 0
                        total_voltage = 0
                        total_power_react = 0
                        total_power_appearent = 0

                        for phase in ['ph-a', 'ph-b', 'ph-c']:

                            phase_name = reduce(lambda a, kv: a.replace(*kv), replace_phases, phase)

                            if data[meter][phase]['v'] > 0:

                                total_power += float(data[meter][phase]['p'])
                                total_current += float(data[meter][phase]['i'])
                                total_voltage += float(data[meter][phase]['v'])
                                total_power_react += float(data[meter][phase]['q'])
                                total_power_appearent += float(data[meter][phase]['s'])

                                # if PV power is below 5 W, than show 0 W. This prevents showing 1-2 W on PV when no sun is shining
                                if meter_name == 'pv' and data[meter][phase]['p'] < 5:
                                    data[meter][phase]['p'] = 0
                                    data[meter][phase]['i'] = 0

                                phase_data = {
                                    'power': float(data[meter][phase]['p']),
                                    'current': float(data[meter][phase]['i']),
                                    'voltage': float(data[meter][phase]['v']),
                                    'power_react': float(data[meter][phase]['q']),
                                    'power_appearent': float(data[meter][phase]['s']),
                                    'power_factor': float(data[meter][phase]['pf']),
                                    'frequency': float(data[meter][phase]['f']),
                                    'whToday': data_production_historic[meter_name][phase_name]['whToday'],
                                    'vahToday': data_production_historic[meter_name][phase_name]['vahToday'],
                                    'whLifetime': data_production_historic[meter_name][phase_name]['whLifetime'],
                                    'vahLifetime': data_production_historic[meter_name][phase_name]['vahLifetime'],
                                }

                                if meter_name == 'pv':
                                    phase_data.update({
                                        'energy_forward': float(round(data_production_historic[meter_name][phase_name]['whLifetime']/1000, 3)),
                                    })

                                if meter_name == 'grid':
                                    phase_data.update({
                                        'energy_forward': json_data['grid'][phase_name]['energy_forward'] if 'grid' in json_data and phase_name in json_data['grid'] else 0,
                                        'energy_reverse': json_data['grid'][phase_name]['energy_reverse'] if 'grid' in json_data and phase_name in json_data['grid'] else 0,
                                    })

                                if meter_name == 'consumption':
                                    phase_data.update({
                                        'energy_forward': float(round(data_production_historic[meter_name][phase_name]['whLifetime']/1000, 3)),
                                    })

                                jsonpayload.update({
                                    phase_name: phase_data
                                })

                        # if PV power is below 5 W, than show 0 W. This prevents showing 1-2 W on PV when no sun is shining
                        if meter_name == 'pv' and total_power < 5:
                            total_power = 0
                            total_current = 0

                        jsonpayload.update({
                            'power': total_power,
                            'current': total_current,
                            'voltage': total_voltage,
                            'power_react': total_power_react,
                            'power_appearent': total_power_appearent,
                            'whToday': data_production_historic[meter_name]['whToday'],
                            'vahToday': data_production_historic[meter_name]['vahToday'],
                            'whLifetime': data_production_historic[meter_name]['whLifetime'],
                            'vahLifetime': data_production_historic[meter_name]['vahLifetime'],
                        })

                        if meter_name == 'pv':
                            jsonpayload.update({
                                'energy_forward': round(data_production_historic[meter_name]['whLifetime']/1000, 3),
                            })

                        if meter_name == 'grid':
                            jsonpayload.update({
                                'energy_forward': json_data['grid']['energy_forward'] if 'grid' in json_data else 0,
                                'energy_reverse': json_data['grid']['energy_reverse'] if 'grid' in json_data else 0,
                            })

                        if meter_name == 'consumption':
                            jsonpayload.update({
                                'energy_forward': round(data_production_historic[meter_name]['whLifetime']/1000, 3),
                            })

                        total_jsonpayload.update({meter_name: jsonpayload})

                    # # # calculate watthours
                    # measure power and calculate watthours, since enphase provides only watthours for production/import/consumption and no export
                    # divide import and export from grid
                    grid_power_forward = total_jsonpayload['grid']['power'] if total_jsonpayload['grid']['power'] > 0 else 0
                    grid_power_reverse = total_jsonpayload['grid']['power'] * -1 if total_jsonpayload['grid']['power'] < 0 else 0

                    if 'L1' in total_jsonpayload['grid']:
                        grid_L1_power_forward = total_jsonpayload['grid']['L1']['power'] if total_jsonpayload['grid']['L1']['power'] > 0 else 0
                        grid_L1_power_reverse = total_jsonpayload['grid']['L1']['power'] * -1 if total_jsonpayload['grid']['L1']['power'] < 0 else 0

                    if 'L2' in total_jsonpayload['grid']:
                        grid_L2_power_forward = total_jsonpayload['grid']['L2']['power'] if total_jsonpayload['grid']['L2']['power'] > 0 else 0
                        grid_L2_power_reverse = total_jsonpayload['grid']['L2']['power'] * -1 if total_jsonpayload['grid']['L2']['power'] < 0 else 0

                    if 'L3' in total_jsonpayload['grid']:
                        grid_L3_power_forward = total_jsonpayload['grid']['L3']['power'] if total_jsonpayload['grid']['L3']['power'] > 0 else 0
                        grid_L3_power_reverse = total_jsonpayload['grid']['L3']['power'] * -1 if total_jsonpayload['grid']['L3']['power'] < 0 else 0

                    # check if x seconds are passed, if not sum values for calculation
                    if data_watt_hours['time_creation'] + data_watt_hours_timespan > timestamp:

                        data_watt_hours_grid = {
                            'energy_forward': round(data_watt_hours['grid']['energy_forward'] + grid_power_forward if 'grid' in data_watt_hours else grid_power_forward, 3),
                            'energy_reverse': round(data_watt_hours['grid']['energy_reverse'] + grid_power_reverse if 'grid' in data_watt_hours else grid_power_reverse, 3),
                        }
                        if 'L1' in total_jsonpayload['grid']:
                            data_watt_hours_grid.update({
                                'L1': {
                                    'energy_forward': round(data_watt_hours['grid']['L1']['energy_forward']
                                                        + grid_L1_power_forward if 'grid' in data_watt_hours and 'L1' in data_watt_hours['grid'] else grid_L1_power_forward, 3),
                                    'energy_reverse': round(data_watt_hours['grid']['L1']['energy_reverse']
                                                        + grid_L1_power_reverse if 'grid' in data_watt_hours and 'L1' in data_watt_hours['grid'] else grid_L1_power_reverse, 3),
                                }
                            })
                        if 'L2' in total_jsonpayload['grid']:
                            data_watt_hours_grid.update({
                                'L2': {
                                    'energy_forward': round(data_watt_hours['grid']['L2']['energy_forward']
                                                        + grid_L2_power_forward if 'grid' in data_watt_hours and 'L2' in data_watt_hours['grid'] else grid_L2_power_forward, 3),
                                    'energy_reverse': round(data_watt_hours['grid']['L2']['energy_reverse']
                                                        + grid_L2_power_reverse if 'grid' in data_watt_hours and 'L2' in data_watt_hours['grid'] else grid_L2_power_reverse, 3),
                                }
                            })
                        if 'L3' in total_jsonpayload['grid']:
                            data_watt_hours_grid.update({
                                'L3': {
                                    'energy_forward': round(data_watt_hours['grid']['L3']['energy_forward']
                                                        + grid_L3_power_forward if 'grid' in data_watt_hours and 'L3' in data_watt_hours['grid'] else grid_L3_power_forward, 3),
                                    'energy_reverse': round(data_watt_hours['grid']['L3']['energy_reverse']
                                                        + grid_L3_power_reverse if 'grid' in data_watt_hours and 'L3' in data_watt_hours['grid'] else grid_L3_power_reverse, 3),
                                }
                            })

                        data_watt_hours.update({
                            # if PV not needed it can be removed, yet to evaluate
                            # 'pv': {
                            #     'energy_forward': round(data_watt_hours['pv']['energy_forward'] + total_jsonpayload['pv']['power'], 3),
                            # },
                            'grid': data_watt_hours_grid,
                            'count': data_watt_hours['count'] + 1,

                        })

                        logging.debug("--> data_watt_hours(): %s" % json.dumps(data_watt_hours))

                    # build mean, calculate time diff and Wh and write to file
                    else:
                        # check if file in volatile storage exists
                        if os.path.isfile(data_watt_hours_working_file):
                            with open(data_watt_hours_working_file, 'r') as file:
                                file = open(data_watt_hours_working_file, "r")
                                data_watt_hours_old = json.load(file)
                                logging.info("Loaded JSON")
                                logging.debug(json.dumps(data_watt_hours_old))

                        # if not, check if file in persistent storage exists
                        elif os.path.isfile(data_watt_hours_storage_file):
                            with open(data_watt_hours_storage_file, 'r') as file:
                                file = open(data_watt_hours_storage_file, "r")
                                data_watt_hours_old = json.load(file)
                                logging.info("Loaded JSON from persistent storage")
                                logging.debug(json.dumps(data_watt_hours_old))

                        # if not, generate data
                        else:
                            data_watt_hours_old_grid = {
                                'energy_forward': 0,
                                'energy_reverse': 0,
                            }
                            if 'L1' in total_jsonpayload['grid']:
                                data_watt_hours_old_grid.update({
                                    'L1': {
                                        'energy_forward': 0,
                                        'energy_reverse': 0,
                                    }
                                })
                            if 'L2' in total_jsonpayload['grid']:
                                data_watt_hours_old_grid.update({
                                    'L2': {
                                        'energy_forward': 0,
                                        'energy_reverse': 0,
                                    }
                                })
                            if 'L3' in total_jsonpayload['grid']:
                                data_watt_hours_old_grid.update({
                                    'L3': {
                                        'energy_forward': 0,
                                        'energy_reverse': 0,
                                    }
                                })
                            data_watt_hours_old = {
                                # if PV not needed it can be removed, yet to evaluate
                                # 'pv': {
                                #     'energy_forward': 0,
                                # },
                                'grid': data_watt_hours_old_grid
                            }
                            logging.info("Generated JSON")
                            logging.debug(json.dumps(data_watt_hours_old))

                        # factor to calculate Watthours: mean power * measuuring period / 3600 seconds (1 hour)
                        factor = (timestamp - data_watt_hours['time_creation']) / 3600

                        # pv_energy_forward   = data_watt_hours_old['pv']['energy_forward'] + (data_watt_hours['pv']['energy_forward'] / data_watt_hours['count'] * factor)
                        grid_energy_forward = round(data_watt_hours_old['grid']['energy_forward'] + (data_watt_hours['grid']['energy_forward'] / data_watt_hours['count'] * factor)/1000, 3)
                        grid_energy_reverse = round(data_watt_hours_old['grid']['energy_reverse'] + (data_watt_hours['grid']['energy_reverse'] / data_watt_hours['count'] * factor)/1000, 3)

                        # update previously set data
                        total_jsonpayload['grid'].update({
                            'energy_forward': grid_energy_forward,
                            'energy_reverse': grid_energy_reverse,
                        })
                        # prepare for save data
                        json_data_grid = {
                            'energy_forward': grid_energy_forward,
                            'energy_reverse': grid_energy_reverse,
                        }

                        # # # L1
                        if 'L1' in data_watt_hours_old['grid'] and 'L1' in data_watt_hours['grid']:
                            grid_L1_energy_forward = round(data_watt_hours_old['grid']['L1']['energy_forward'] + (data_watt_hours['grid']['L1']['energy_forward'] / data_watt_hours['count'] * factor)/1000, 3)
                            grid_L1_energy_reverse = round(data_watt_hours_old['grid']['L1']['energy_reverse'] + (data_watt_hours['grid']['L1']['energy_reverse'] / data_watt_hours['count'] * factor)/1000, 3)
                        # in case phase count changed
                        elif 'L1' in data_watt_hours['grid']:
                            grid_L1_energy_forward = round((data_watt_hours['grid']['L1']['energy_forward'] / data_watt_hours['count'] * factor)/1000, 3)
                            grid_L1_energy_reverse = round((data_watt_hours['grid']['L1']['energy_reverse'] / data_watt_hours['count'] * factor)/1000, 3)

                        if 'L1' in data_watt_hours['grid']:
                            # update previously set data
                            total_jsonpayload['grid']['L1'].update({
                                'energy_forward': grid_L1_energy_forward,
                                'energy_reverse': grid_L1_energy_reverse,
                            })

                            json_data_grid.update({
                                'L1': {
                                    'energy_forward': grid_L1_energy_forward,
                                    'energy_reverse': grid_L1_energy_reverse,
                                }
                            })

                        # # # L2
                        if 'L2' in data_watt_hours_old['grid'] and 'L2' in data_watt_hours['grid']:
                            grid_L2_energy_forward = round(data_watt_hours_old['grid']['L2']['energy_forward'] + (data_watt_hours['grid']['L2']['energy_forward'] / data_watt_hours['count'] * factor)/1000, 3)
                            grid_L2_energy_reverse = round(data_watt_hours_old['grid']['L2']['energy_reverse'] + (data_watt_hours['grid']['L2']['energy_reverse'] / data_watt_hours['count'] * factor)/1000, 3)
                        # in case phase count changed
                        elif 'L2' in data_watt_hours['grid']:
                            grid_L2_energy_forward = round((data_watt_hours['grid']['L2']['energy_forward'] / data_watt_hours['count'] * factor)/1000, 3)
                            grid_L2_energy_reverse = round((data_watt_hours['grid']['L2']['energy_reverse'] / data_watt_hours['count'] * factor)/1000, 3)

                        if 'L2' in data_watt_hours['grid']:
                            # update previously set data
                            total_jsonpayload['grid']['L2'].update({
                                'energy_forward': grid_L2_energy_forward,
                                'energy_reverse': grid_L2_energy_reverse,
                            })

                            json_data_grid.update({
                                'L2': {
                                    'energy_forward': grid_L2_energy_forward,
                                    'energy_reverse': grid_L2_energy_reverse,
                                }
                            })

                        # # # L3
                        if 'L3' in data_watt_hours_old['grid'] and 'L3' in data_watt_hours['grid']:
                            grid_L3_energy_forward = round(data_watt_hours_old['grid']['L3']['energy_forward'] + (data_watt_hours['grid']['L3']['energy_forward'] / data_watt_hours['count'] * factor)/1000, 3)
                            grid_L3_energy_reverse = round(data_watt_hours_old['grid']['L3']['energy_reverse'] + (data_watt_hours['grid']['L3']['energy_reverse'] / data_watt_hours['count'] * factor)/1000, 3)
                        # in case phase count changed
                        elif 'L3' in data_watt_hours['grid']:
                            grid_L3_energy_forward = round((data_watt_hours['grid']['L3']['energy_forward'] / data_watt_hours['count'] * factor)/1000, 3)
                            grid_L3_energy_reverse = round((data_watt_hours['grid']['L3']['energy_reverse'] / data_watt_hours['count'] * factor)/1000, 3)

                        if 'L3' in data_watt_hours['grid']:
                            # update previously set data
                            total_jsonpayload['grid']['L3'].update({
                                'energy_forward': grid_L3_energy_forward,
                                'energy_reverse': grid_L3_energy_reverse,
                            })

                            json_data_grid.update({
                                'L3': {
                                    'energy_forward': grid_L3_energy_forward,
                                    'energy_reverse': grid_L3_energy_reverse,
                                }
                            })

                        json_data = {
                            # # if PV not needed it can be removed, yet to evaluate
                            # 'pv': {
                            #     'energy_forward': pv_energy_forward,
                            # },
                            'grid': json_data_grid
                        }

                        # save data to volatile storage
                        with open(data_watt_hours_working_file, 'w') as file:
                            file.write(json.dumps(json_data))

                        # save data to persistent storage if time is passed
                        if timestamp_storage_file + data_watt_hours_save < timestamp:
                            with open(data_watt_hours_storage_file, 'w') as file:
                                file.write(json.dumps(json_data))
                            timestamp_storage_file = timestamp
                            logging.info("Written JSON for energy forward/reverse to persistent storage.")

                        # begin a new cycle
                        data_watt_hours_grid = {
                            'energy_forward': round(grid_power_forward, 3),
                            'energy_reverse': round(grid_power_reverse, 3),
                        }
                        if 'L1' in total_jsonpayload['grid']:
                            data_watt_hours_grid.update({
                                'L1': {
                                    'energy_forward': round(grid_L1_power_forward, 3),
                                    'energy_reverse': round(grid_L1_power_reverse, 3),
                                }
                            })
                        if 'L2' in total_jsonpayload['grid']:
                            data_watt_hours_grid.update({
                                'L2': {
                                    'energy_forward': round(grid_L2_power_forward, 3),
                                    'energy_reverse': round(grid_L2_power_reverse, 3),
                                }
                            })
                        if 'L3' in total_jsonpayload['grid']:
                            data_watt_hours_grid.update({
                                'L3': {
                                    'energy_forward': round(grid_L3_power_forward, 3),
                                    'energy_reverse': round(grid_L3_power_reverse, 3),
                                }
                            })

                        data_watt_hours = {
                            'time_creation': timestamp,
                            # # if PV not needed it can be removed, yet to evaluate
                            # 'pv': {
                            #     'energy_forward': round(total_jsonpayload['pv']['power'], 3),
                            # },
                            'grid': data_watt_hours_grid,
                            'count': 1

                        }

                        logging.debug("--> data_watt_hours(): %s" % json.dumps(data_watt_hours))

                    # make fetched data globally available
                    data_meter_stream = total_jsonpayload

                # reset error count
                error_count = 0

        except requests.exceptions.ConnectTimeout as e:
            logging.error("--> fetch_meter_stream(): ConnectTimeout occurred: %s" % e)
            error_count += 1
            sleep(15)

        except requests.exceptions.ReadTimeout as e:
            logging.error("--> fetch_meter_stream(): ReadTimeout occurred: %s" % e)
            error_count += 1
            sleep(1)

        except requests.exceptions.Timeout as e:
            logging.error("--> fetch_meter_stream(): Timeout occurred: %s" % e)
            error_count += 1
            sleep(1)

        except KeyError:
            exception_type, exception_object, exception_traceback = sys.exc_info()
            file = exception_traceback.tb_frame.f_code.co_filename
            line = exception_traceback.tb_lineno
            logging.error(f"--> fetch_meter_stream(): {repr(exception_object)} in {file} line #{line}")
            error_count += 1
            sleep(1)

        except Exception:
            exception_type, exception_object, exception_traceback = sys.exc_info()
            file = exception_traceback.tb_frame.f_code.co_filename
            line = exception_traceback.tb_lineno
            logging.error(f"--> fetch_meter_stream(): Exception occurred: {repr(exception_object)} of type {exception_type} in {file} line #{line}")
            error_count += 1
            sleep(1)

        # stopping driver, if error count is exceeded
        if error_count >= 5:
            logging.error(f'--> fetch_meter_stream(): {error_count} errors accured. Stopping driver...')
            keep_running = False
            sys.exit()


def fetch_production_historic():
    logging.info("step: fetch_production_historic")

    global replace_meters, data_production_historic, keep_running, request_auth, request_headers, request_schema

    try:
        url = '%s://%s/production.json?details=1' % (request_schema, config['ENVOY']['address'])
        if request_auth == "token":
            response = requests.get(
                url,
                timeout=60,
                headers=request_headers,
                verify=False
            )
        else:
            response = requests.get(
                url,
                timeout=60,
                auth=HTTPDigestAuth('installer', config['ENVOY']['password'])
            )

        if response.status_code != 200:
            logging.error(f"--> fetch_production_historic(): Received HTTP status code {response.status_code}. Restarting the driver in 60 seconds.")
            sleep(60)
            keep_running = False
            sys.exit()

        if response.elapsed.total_seconds() > 5:
            logging.warning("--> fetch_production_historic(): HTTP request took longer than 5 seconds: %s seconds" % response.elapsed.total_seconds())

        total_jsonpayload = {}

        for meter in response.json().values():

            for content in meter:

                if 'measurementType' in content and (
                        content['measurementType'] == 'production'
                        or
                        content['measurementType'] == 'total-consumption'
                        or
                        content['measurementType'] == 'net-consumption'
                ):

                    meter_name = reduce(lambda a, kv: a.replace(*kv), replace_meters, content['measurementType'])

                    jsonpayload = {}

                    i = 1

                    if 'lines' in content:

                        for phase in content['lines']:

                            jsonpayload.update({
                                'L' + str(i): {
                                    "whLifetime": float(phase['whLifetime']),
                                    "vahLifetime": float(phase['vahLifetime']),
                                    "whToday": float(phase['whToday']),
                                    "vahToday": float(phase['vahToday']),
                                }
                            })
                            i += 1

                    jsonpayload.update({
                        "whLifetime": float(content['whLifetime']),
                        "vahLifetime": float(content['vahLifetime']),
                        "whToday": float(content['whToday']),
                        "vahToday": float(content['vahToday']),
                    })

                    total_jsonpayload.update({meter_name: jsonpayload})

        # make fetched data globally available
        data_production_historic = total_jsonpayload

    except requests.exceptions.ConnectTimeout as e:
        logging.error("--> fetch_production_historic(): ConnectTimeout occurred: %s" % e)

    except requests.exceptions.ReadTimeout as e:
        logging.error("--> fetch_production_historic(): ReadTimeout occurred: %s" % e)

    except requests.exceptions.Timeout as e:
        logging.error("--> fetch_production_historic(): Timeout occurred: %s" % e)

    except Exception:
        exception_type, exception_object, exception_traceback = sys.exc_info()
        file = exception_traceback.tb_frame.f_code.co_filename
        line = exception_traceback.tb_lineno
        logging.error(f"--> fetch_production_historic(): Exception occurred: {repr(exception_object)} of type {exception_type} in {file} line #{line}")
        keep_running = False
        sys.exit()


def fetch_devices():
    logging.info("step: fetch_devices")

    global replace_devices, data_devices, keep_running, request_auth, request_headers, request_schema

    try:

        url = '%s://%s/inventory.json' % (request_schema, config['ENVOY']['address'])
        if request_auth == "token":
            response = requests.get(
                url,
                timeout=60,
                headers=request_headers,
                verify=False
            )
        else:
            response = requests.get(
                url,
                timeout=60,
                auth=HTTPDigestAuth('installer', config['ENVOY']['password'])
            )

        if response.status_code != 200:
            logging.error(f"--> fetch_devices(): Received HTTP status code {response.status_code}. Restarting the driver in 60 seconds.")
            sleep(60)
            keep_running = False
            sys.exit()

        if response.elapsed.total_seconds() > 5:
            logging.warning("--> fetch_devices(): HTTP request took longer than 5 seconds: %s seconds" % response.elapsed.total_seconds())

        total_jsonpayload = {}

        for device_type in response.json():

            device_name = reduce(lambda a, kv: a.replace(*kv), replace_devices, device_type['type'])

            jsonpayload = {}

            for device in device_type['devices']:

                device_data = {
                    "status": device['device_status'],
                    "producing": device['producing'],
                    "communicating": device['communicating'],
                    "provisioned": device['provisioned'],
                    "operating": device['operating'],
                }

                if 'relay' in device:
                    device_data.update({
                            "relay": device['relay'],
                            "reason": device['reason'],
                    })

                jsonpayload.update({device['serial_num']: device_data})

            total_jsonpayload.update({device_name: jsonpayload})

        # make fetched data globally available
        data_devices = total_jsonpayload

    except requests.exceptions.ConnectTimeout as e:
        logging.error("--> fetch_devices(): ConnectTimeout occurred: %s" % e)

    except requests.exceptions.ReadTimeout as e:
        logging.error("--> fetch_devices(): ReadTimeout occurred: %s" % e)

    except requests.exceptions.Timeout as e:
        logging.error("--> fetch_devices(): Timeout occurred: %s" % e)

    except Exception:
        exception_type, exception_object, exception_traceback = sys.exc_info()
        file = exception_traceback.tb_frame.f_code.co_filename
        line = exception_traceback.tb_lineno
        logging.error(f"--> fetch_devices(): Exception occurred: {repr(exception_object)} of type {exception_type} in {file} line #{line}")
        keep_running = False
        sys.exit()


def fetch_inverters():
    logging.info("step: fetch_inverters")

    global data_inverters, inverters, keep_running, request_auth, request_headers, request_schema

    try:

        url = '%s://%s/api/v1/production/inverters' % (request_schema, config['ENVOY']['address'])
        if request_auth == "token":
            response = requests.get(
                url,
                timeout=60,
                headers=request_headers,
                verify=False
            )
        else:
            response = requests.get(
                url,
                timeout=60,
                auth=HTTPDigestAuth('installer', config['ENVOY']['password'])
            )

        if response.status_code != 200:
            logging.error(f"--> fetch_inverters(): Received HTTP status code {response.status_code}. Restarting the driver in 60 seconds.")
            sleep(60)
            keep_running = False
            sys.exit()

        if response.elapsed.total_seconds() > 5:
            logging.warning("--> fetch_inverters(): HTTP request took longer than 5 seconds: %s seconds" % response.elapsed.total_seconds())

        total_jsonpayload = {}

        inverters_producing = 0
        inverters_total = 0
        for inverter in response.json():

            # count reporting inverters and set power to 0 if lastReportDate is older than 900 (default microinverter reporting interval) seconds + 300 seconds
            if inverter['lastReportDate'] + 1200 > int(time()):
                inverters_total += 1
                inverter_power = inverter['lastReportWatts']
            else:
                inverter_power = 0

            total_jsonpayload.update({
                inverter['serialNumber']: {
                    'lastReportDate': inverter['lastReportDate'],
                    'lastReportWatts': inverter['lastReportWatts'],
                    'currentWatts': inverter_power
                }
            })

            # count producing inverters
            if inverter_power > 5:
                inverters_producing += 1

        inverters.update({
            "reporting": inverters_total,
            "producing": inverters_producing
        })

        if inverters["config"] is None:
            inverters.update({
                "config": inverters_total
            })

        # make fetched data globally available
        data_inverters = total_jsonpayload

    except requests.exceptions.ConnectTimeout as e:
        logging.error("--> fetch_inverters(): ConnectTimeout occurred: %s" % e)

    except requests.exceptions.ReadTimeout as e:
        logging.error("--> fetch_inverters(): ReadTimeout occurred: %s" % e)

    except requests.exceptions.Timeout as e:
        logging.error("--> fetch_inverters(): Timeout occurred: %s" % e)

    except Exception:
        exception_type, exception_object, exception_traceback = sys.exc_info()
        file = exception_traceback.tb_frame.f_code.co_filename
        line = exception_traceback.tb_lineno
        logging.error(f"--> fetch_inverters(): Exception occurred: {repr(exception_object)} of type {exception_type} in {file} line #{line}")
        keep_running = False
        sys.exit()


def fetch_events():
    logging.info("step: fetch_events")

    global data_events, keep_running, request_auth, request_headers, request_schema

    try:

        url = '%s://%s/datatab/event_dt.rb?start=0&length=10' % (request_schema, config['ENVOY']['address'])
        if request_auth == "token":
            response = requests.get(
                url,
                timeout=60,
                headers=request_headers,
                verify=False
            )
        else:
            response = requests.get(
                url,
                timeout=60,
                auth=HTTPDigestAuth('installer', config['ENVOY']['password'])
            )

        if response.status_code != 200:
            logging.error(f"--> fetch_events(): Received HTTP status code {response.status_code}. Restarting the driver in 60 seconds.")
            sleep(60)
            keep_running = False
            sys.exit()

        if response.elapsed.total_seconds() > 5:
            logging.warning("--> fetch_events(): HTTP request took longer than 5 seconds: %s seconds" % response.elapsed.total_seconds())

        total_jsonpayload = {}

        for event in response.json()['aaData']:

            total_jsonpayload.update({
                event[0]: {
                    'message': event[1],
                    'serialNumber': event[2],
                    'type': event[3],
                    'datetime': event[4],
                }
            })

        # make fetched data globally available
        data_events = total_jsonpayload

    except requests.exceptions.ConnectTimeout as e:
        logging.error("--> fetch_events(): ConnectTimeout occurred: %s" % e)

    except requests.exceptions.ReadTimeout as e:
        logging.error("--> fetch_events(): ReadTimeout occurred: %s" % e)

    except requests.exceptions.Timeout as e:
        logging.error("--> fetch_events(): Timeout occurred: %s" % e)

    except Exception:
        exception_type, exception_object, exception_traceback = sys.exc_info()
        file = exception_traceback.tb_frame.f_code.co_filename
        line = exception_traceback.tb_lineno
        logging.error(f"--> fetch_events(): Exception occurred: {repr(exception_object)} of type {exception_type} in {file} line #{line}")
        keep_running = False
        sys.exit()


def fetch_handler():
    logging.info("step: fetch_handler")

    global config, keep_running, \
        fetch_production_historic_interval, fetch_devices_interval, fetch_inverters_interval, fetch_events_interval, \
        fetch_production_historic_last, fetch_devices_last, fetch_inverters_last, fetch_events_last

    while 1:

        if keep_running is False:
            logging.info("--> fetch_handler(): got exit signal")
            sys.exit()

        time_now = int(time())

        if ((time_now - fetch_production_historic_last) > fetch_production_historic_interval):
            try:
                fetch_production_historic()
                fetch_production_historic_last = time_now
                logging.info("--> fetch_handler() --> fetch_production_historic(): JSON data feched. Wait %s seconds for next run" % fetch_production_historic_interval)
            except Exception:
                exception_type, exception_object, exception_traceback = sys.exc_info()
                file = exception_traceback.tb_frame.f_code.co_filename
                line = exception_traceback.tb_lineno
                logging.error(f"--> fetch_handler() --> fetch_production_historic(): Exception occurred: {repr(exception_object)} of type {exception_type} in {file} line #{line}")
                logging.error(f"Try again in {fetch_production_historic_interval} seconds")

        if fetch_devices_enabled == 1 and ((time_now - fetch_devices_last) > fetch_devices_interval):
            try:
                fetch_devices()
                fetch_devices_last = time_now
                logging.info("--> fetch_handler() --> fetch_devices(): JSON data feched. Wait %s seconds for next run" % fetch_devices_interval)
            except Exception:
                exception_type, exception_object, exception_traceback = sys.exc_info()
                file = exception_traceback.tb_frame.f_code.co_filename
                line = exception_traceback.tb_lineno
                logging.error(f"--> fetch_handler() --> fetch_devices(): Exception occurred: {repr(exception_object)} of type {exception_type} in {file} line #{line}")
                logging.error(f"Try again in {fetch_devices_interval} seconds")

        if fetch_inverters_enabled == 1 and ((time_now - fetch_inverters_last) > fetch_inverters_interval):
            try:
                fetch_inverters()
                fetch_inverters_last = time_now
                logging.info("--> fetch_handler() --> fetch_inverters(): JSON data feched. Wait %s seconds for next run" % fetch_inverters_interval)
            except Exception:
                exception_type, exception_object, exception_traceback = sys.exc_info()
                file = exception_traceback.tb_frame.f_code.co_filename
                line = exception_traceback.tb_lineno
                logging.error(f"--> fetch_handler() --> fetch_inverters(): Exception occurred: {repr(exception_object)} of type {exception_type} in {file} line #{line}")
                logging.error(f"Try again in {fetch_inverters_interval} seconds")

        if fetch_events_enabled == 1 and ((time_now - fetch_events_last) > fetch_events_interval):
            try:
                fetch_events()
                fetch_events_last = time_now
                logging.info("--> fetch_handler() --> fetch_events(): JSON data feched. Wait %s seconds for next run" % fetch_events_interval)
            except Exception:
                exception_type, exception_object, exception_traceback = sys.exc_info()
                file = exception_traceback.tb_frame.f_code.co_filename
                line = exception_traceback.tb_lineno
                logging.error(f"--> fetch_handler() --> fetch_events(): Exception occurred: {repr(exception_object)} of type {exception_type} in {file} line #{line}")
                logging.error(f"Try again in {fetch_events_interval} seconds")

        # slow down requests to prevent overloading the Envoy
        sleep(1)


def publish_mqtt_data():
    logging.info("step: publish_mqtt_data")

    global client, config, keep_running, \
        data_meter_stream, data_devices, data_inverters, data_events

    data_previous_meter_stream = {}
    data_previous_devices = {}
    data_previous_inverters = {}
    data_previous_events = {}

    while 1:

        if keep_running is False:
            logging.info("--> publish_mqtt_data(): got exit signal")
            sys.exit()

        try:
            # check if data_meter_stream is not empty and data is changed
            if data_meter_stream and data_previous_meter_stream != data_meter_stream:
                data_previous_meter_stream = data_meter_stream
                client.publish(config['MQTT']['topic_meters'], json.dumps(data_meter_stream))
                logging.info("--> publish_mqtt_data() --> data_meter_stream: MQTT data published")

            # check if data_devices is enabled, not empty and data is changed
            if (
                fetch_devices_enabled == 1
                and
                data_devices
                and
                (
                    (
                        fetch_devices_publishing_type == 0
                        and
                        data_previous_devices != data_devices
                    )
                    or
                    fetch_devices_publishing_type == 1
                )
            ):
                data_previous_devices = data_devices
                client.publish(config['MQTT']['topic_devices'], json.dumps(data_devices))
                logging.info("--> publish_mqtt_data() --> data_devices: MQTT data published")

            # check if data_inverters is enabled, not empty and data is changed
            if (
                fetch_inverters_enabled == 1
                and
                data_inverters
                and
                (
                    (
                        fetch_inverters_publishing_type == 0
                        and
                        data_previous_inverters != data_inverters
                    )
                    or
                    fetch_inverters_publishing_type == 1
                )
            ):
                data_previous_inverters = data_inverters
                client.publish(config['MQTT']['topic_inverters'], json.dumps(data_inverters))
                logging.info("--> publish_mqtt_data() --> data_inverters: MQTT data published")

            # check if data_events is enabled, not empty and data is changed
            if (
                fetch_events_enabled == 1
                and
                data_events
                and
                (
                    (
                        fetch_events_publishing_type == 0
                        and
                        data_previous_events != data_events
                    )
                    or
                    fetch_events_publishing_type == 1
                )
            ):
                data_previous_events = data_events
                client.publish(config['MQTT']['topic_events'], json.dumps(data_events))
                logging.info("--> publish_mqtt_data() --> data_events: MQTT data published")

            # check if publish_interval is greater or equals 1, else the load is too much
            if int(config['MQTT']['publish_interval']) >= 1:
                publish_interval = int(config['MQTT']['publish_interval'])
            else:
                publish_interval = 1

            logging.info("--> publish_mqtt_data(): MQTT data published. Wait %s seconds for next run" % publish_interval)

            # slow down publishing to prevent overloading the Venus OS
            sleep(publish_interval)

        except Exception:
            exception_type, exception_object, exception_traceback = sys.exc_info()
            file = exception_traceback.tb_frame.f_code.co_filename
            line = exception_traceback.tb_lineno
            logging.error(f"--> publish_mqtt_data(): Exception occurred: {repr(exception_object)} of type {exception_type} in {file} line #{line}")
            keep_running = False
            sys.exit()


# VICTRON ENERGY - VENUS OS
class DbusEnphaseEnvoyPvService:
    def __init__(
        self,
        servicename,
        deviceinstance,
        paths,
        productname='Enphase PV',
        connection='Enphase PV service',
        hardware='Microinverters'
    ):

        global config

        self._dbusservice = VeDbusService(servicename)
        self._paths = paths

        logging.debug("%s /DeviceInstance = %d" % (servicename, deviceinstance))

        # Create the management objects, as specified in the ccgx dbus-api document
        self._dbusservice.add_path('/Mgmt/ProcessName', __file__)
        self._dbusservice.add_path('/Mgmt/ProcessVersion', 'Unkown version, and running on Python ' + platform.python_version())
        self._dbusservice.add_path('/Mgmt/Connection', connection)

        # Create the mandatory objects
        self._dbusservice.add_path('/DeviceInstance', deviceinstance)
        # 0xFFFF Default
        # 0xA142 Fronius Symo 8.2-3-M
        self._dbusservice.add_path('/ProductId', 0xFFFF)
        self._dbusservice.add_path('/ProductName', productname)
        self._dbusservice.add_path('/CustomName', productname)
        self._dbusservice.add_path('/FirmwareVersion', '0.2.0-beta2 (20230716)')
        self._dbusservice.add_path('/HardwareVersion', hardware)
        self._dbusservice.add_path('/Connected', 1)

        self._dbusservice.add_path('/Latency', None)
        self._dbusservice.add_path('/ErrorCode', 0)
        self._dbusservice.add_path('/Position', int(config['PV']['position']))  # only needed for pvinverter
        self._dbusservice.add_path('/StatusCode', 0)  # Dummy path so VRM detects us as a PV-inverter

        self._dbusservice.add_path('/DeviceName', "")  # used to populate working inverters after

        for path, settings in self._paths.items():
            self._dbusservice.add_path(
                path, settings['initial'], gettextcallback=settings['textformat'], writeable=True, onchangecallback=self._handlechangedvalue
            )

        GLib.timeout_add(1000, self._update)  # pause 1000ms before the next request

    def _update(self):

        if keep_running is False:
            logging.info("--> DbusEnphaseEnvoyPvService->_update(): got exit signal")
            sys.exit()

        self._dbusservice['/Ac/Power'] = round(data_meter_stream['pv']['power'], 2) if data_meter_stream['pv']['power'] is not None else None
        self._dbusservice['/Ac/Current'] = round(data_meter_stream['pv']['current'], 2) if data_meter_stream['pv']['current'] is not None else None
        self._dbusservice['/Ac/Voltage'] = round(data_meter_stream['pv']['voltage'], 2) if data_meter_stream['pv']['voltage'] is not None else None
        # needed for VRM historical data
        self._dbusservice['/Ac/Energy/Forward'] = round(data_meter_stream['pv']['energy_forward'], 2) if data_meter_stream['pv']['energy_forward'] is not None else None

        self._dbusservice['/ErrorCode'] = 0
        self._dbusservice['/StatusCode'] = 7

        self._dbusservice["/DeviceName"] = (
            str(inverters["producing"])
            + " of "
            + str(inverters["config"])
            + " ⚡️"
            + (
                " (" + str(inverters["config"] - inverters["reporting"]) + " u/a)"
                if inverters["config"] > inverters["reporting"]
                else ""
            )
        )

        self._dbusservice["/Enphase/AuthToken"] = auth_token["auth_token"]
        self._dbusservice["/Enphase/MicroInvertersConfig"] = inverters["config"]
        self._dbusservice["/Enphase/MicroInvertersReporting"] = inverters["reporting"]
        self._dbusservice["/Enphase/MicroInvertersProducing"] = inverters["producing"]

        if 'L1' in data_meter_stream['pv']:
            self._dbusservice['/Ac/L1/Power'] = round(data_meter_stream['pv']['L1']['power'], 2) if data_meter_stream['pv']['L1']['power'] is not None else None
            self._dbusservice['/Ac/L1/Current'] = round(data_meter_stream['pv']['L1']['current'], 2) if data_meter_stream['pv']['L1']['current'] is not None else None
            self._dbusservice['/Ac/L1/Voltage'] = round(data_meter_stream['pv']['L1']['voltage'], 2) if data_meter_stream['pv']['L1']['voltage'] is not None else None
            self._dbusservice['/Ac/L1/Frequency'] = round(data_meter_stream['pv']['L1']['frequency'], 4) if data_meter_stream['pv']['L1']['frequency'] is not None else None
            # needed for VRM historical data
            self._dbusservice['/Ac/L1/Energy/Forward'] = round(data_meter_stream['pv']['L1']['energy_forward'], 2) if data_meter_stream['pv']['L1']['energy_forward'] is not None else None

        if 'L2' in data_meter_stream['pv']:
            self._dbusservice['/Ac/L2/Power'] = round(data_meter_stream['pv']['L2']['power'], 2) if data_meter_stream['pv']['L2']['power'] is not None else None
            self._dbusservice['/Ac/L2/Current'] = round(data_meter_stream['pv']['L2']['current'], 2) if data_meter_stream['pv']['L2']['current'] is not None else None
            self._dbusservice['/Ac/L2/Voltage'] = round(data_meter_stream['pv']['L2']['voltage'], 2) if data_meter_stream['pv']['L2']['voltage'] is not None else None
            self._dbusservice['/Ac/L2/Frequency'] = round(data_meter_stream['pv']['L2']['frequency'], 4) if data_meter_stream['pv']['L2']['frequency'] is not None else None
            # needed for VRM historical data
            self._dbusservice['/Ac/L2/Energy/Forward'] = round(data_meter_stream['pv']['L2']['energy_forward'], 2) if data_meter_stream['pv']['L2']['energy_forward'] is not None else None

        if 'L3' in data_meter_stream['pv']:
            self._dbusservice['/Ac/L3/Power'] = round(data_meter_stream['pv']['L3']['power'], 2) if data_meter_stream['pv']['L3']['power'] is not None else None
            self._dbusservice['/Ac/L3/Current'] = round(data_meter_stream['pv']['L3']['current'], 2) if data_meter_stream['pv']['L3']['current'] is not None else None
            self._dbusservice['/Ac/L3/Voltage'] = round(data_meter_stream['pv']['L3']['voltage'], 2) if data_meter_stream['pv']['L3']['voltage'] is not None else None
            self._dbusservice['/Ac/L3/Frequency'] = round(data_meter_stream['pv']['L3']['frequency'], 4) if data_meter_stream['pv']['L3']['frequency'] is not None else None
            # needed for VRM historical data
            self._dbusservice['/Ac/L3/Energy/Forward'] = round(data_meter_stream['pv']['L3']['energy_forward'], 2) if data_meter_stream['pv']['L3']['energy_forward'] is not None else None

        logging.debug("PV: {:.1f} W - {:.1f} V - {:.1f} A".format(data_meter_stream['pv']['power'], data_meter_stream['pv']['voltage'], data_meter_stream['pv']['current']))
        if 'L1' in data_meter_stream['pv'] and data_meter_stream['pv']['power'] != data_meter_stream['pv']['L1']['power']:
            logging.debug("|- L1: {:.1f} W - {:.1f} V - {:.1f} A".format(data_meter_stream['pv']['L1']['power'], data_meter_stream['pv']['L1']['voltage'], data_meter_stream['pv']['L1']['current']))
        if 'L2' in data_meter_stream['pv']:
            logging.debug("|- L2: {:.1f} W - {:.1f} V - {:.1f} A".format(data_meter_stream['pv']['L2']['power'], data_meter_stream['pv']['L2']['voltage'], data_meter_stream['pv']['L2']['current']))
        if 'L3' in data_meter_stream['pv']:
            logging.debug("|- L3: {:.1f} W - {:.1f} V - {:.1f} A".format(data_meter_stream['pv']['L3']['power'], data_meter_stream['pv']['L3']['voltage'], data_meter_stream['pv']['L3']['current']))

        # increment UpdateIndex - to show that new data is available
        index = self._dbusservice['/UpdateIndex'] + 1  # increment index
        if index > 255:   # maximum value of the index
            index = 0       # overflow from 255 to 0
        self._dbusservice['/UpdateIndex'] = index
        return True

    def _handlechangedvalue(self, path, value):
        logging.debug("someone else updated %s to %s" % (path, value))
        return True  # accept the change


def main():
    global client, \
        fetch_production_historic_last, fetch_devices_last, fetch_inverters_last, fetch_events_last, request_schema, auth_token, keep_running

    _thread.daemon = True  # allow the program to quit

    from dbus.mainloop.glib import DBusGMainLoop  # pyright: ignore[reportMissingImports]
    # Have a mainloop, so we can send/receive asynchronous calls to and from dbus
    DBusGMainLoop(set_as_default=True)

    # MQTT configuration
    if MQTT_enabled == 1:
        # create new instance
        client = mqtt.Client("EnphaseEnvoyPV")
        client.on_disconnect = on_disconnect
        client.on_connect = on_connect
        client.on_publish = on_publish

        # check tls and use settings, if provided
        if 'tls_enabled' in config['MQTT'] and config['MQTT']['tls_enabled'] == '1':
            logging.info("MQTT client: TLS is enabled")

            if 'tls_path_to_ca' in config['MQTT'] and config['MQTT']['tls_path_to_ca'] != '':
                logging.info("MQTT client: TLS: custom ca %s used" % config['MQTT']['tls_path_to_ca'])
                client.tls_set(config['MQTT']['tls_path_to_ca'], tls_version=2)
            else:
                client.tls_set(tls_version=2)

            if 'tls_insecure' in config['MQTT'] and config['MQTT']['tls_insecure'] != '':
                logging.info("MQTT client: TLS certificate server hostname verification disabled")
                client.tls_insecure_set(True)

        # check if username and password are set
        if 'username' in config['MQTT'] and 'password' in config['MQTT'] and config['MQTT']['username'] != '' and config['MQTT']['password'] != '':
            logging.info("MQTT client: Using username %s and password to connect" % config['MQTT']['username'])
            client.username_pw_set(username=config['MQTT']['username'], password=config['MQTT']['password'])

        # connect to broker
        logging.info(f"MQTT client: Connecting to broker {config['MQTT']['broker_address']} on port {config['MQTT']['broker_port']}")
        client.connect(
            host=config['MQTT']['broker_address'],
            port=int(config['MQTT']['broker_port'])
        )
        client.loop_start()

    # check auth token
    # start threat for fetching data every x seconds in background
    tokenManager_thread = threading.Thread(target=tokenManager, name='Thread-TokenManager')
    tokenManager_thread.daemon = True
    tokenManager_thread.start()

    # wait to fetch data_production_historic else data_meter_stream cannot be fully merged
    i = 0
    while auth_token["auth_token"] == "":
        if i % 60 != 0 or i == 0:
            logging.info("--> token still empty")
        else:
            logging.warning(
                "token still empty"
            )

        if keep_running is False:
            logging.info("--> wait for first data: got exit signal")
            sys.exit()

        if i > 300:
            logging.error("Maximum of 300 seconds wait time reached. Restarting the driver.")
            keep_running = False
            sys.exit()

        sleep(1)
        i += 1

    # Enphase Envoy-S
    # start threat for fetching data every x seconds in background
    fetch_handler_thread = threading.Thread(target=fetch_handler, name='Thread-FetchHandler')
    fetch_handler_thread.daemon = True
    fetch_handler_thread.start()

    # wait to fetch data_production_historic else data_meter_stream cannot be fully merged
    i = 0
    while not bool(data_production_historic):
        if i % 60 != 0 or i == 0:
            logging.info("--> data_production_historic not yet ready")
        else:
            logging.warning(
                f"--> data_production_historic not yet ready after {i} seconds.\n" +
                f"Try accessing {request_schema}://{config['ENVOY']['address']}/production.json?details=1 from your PC and see,\n" +
                "if it downloads a file with JSON content."
            )

        if keep_running is False:
            logging.info("--> wait for first data: got exit signal")
            sys.exit()

        if i > 300:
            logging.error("Maximum of 300 seconds wait time reached. Restarting the driver.")
            keep_running = False
            sys.exit()

        sleep(1)
        i += 1

    # start threat for fetching continuously the stream in background
    fetch_meter_stream_thread = threading.Thread(target=fetch_meter_stream, name='Thread-FetchMeterStream')
    fetch_meter_stream_thread.daemon = True
    fetch_meter_stream_thread.start()

    # wait to fetch fetch_meter_stream else dbus initialisation for phase count is wrong
    i = 0
    while not bool(data_meter_stream):
        if i % 60 != 0 or i == 0:
            logging.info("--> data_meter_stream not yet ready")
        else:
            logging.warning(
                f"--> data_meter_stream not yet ready after {i} seconds.\n" +
                f"Try accessing {request_schema}://{config['ENVOY']['address']}/stream/meter from your PC with the Envoy-S installer credentials and see,\n" +
                "if it downloads a file with JSON content (one JSON per line). When it's working like expected you have\n" +
                "to interrupt the download after a few seconds, since the Envoy-S is streaming the data."
            )

        if keep_running is False:
            logging.info("--> wait for first data: got exit signal")
            sys.exit()

        if i > 300:
            logging.error("Maximum of 300 seconds wait time reached. Restarting the driver.")
            keep_running = False
            sys.exit()

        sleep(1)
        i += 1

    # start threat for publishing mqtt data in background
    if MQTT_enabled == 1:
        publish_mqtt_data_thread = threading.Thread(target=publish_mqtt_data, name='Thread-PublishMqttData')
        publish_mqtt_data_thread.daemon = True
        publish_mqtt_data_thread.start()

    # formatting
    def _kwh(p, v): return (str("%.2f" % v) + "kWh")
    def _a(p, v): return (str("%.1f" % v) + "A")
    def _w(p, v): return (str("%i" % v) + "W")
    def _v(p, v): return (str("%.2f" % v) + "V")
    def _hz(p, v): return (str("%.4f" % v) + "Hz")
    def _n(p, v): return (str("%i" % v))
    def _str(p, v): return (str("%s" % v))

    paths_dbus = {
        '/Ac/Power': {'initial': 0, 'textformat': _w},
        '/Ac/Current': {'initial': 0, 'textformat': _a},
        '/Ac/Voltage': {'initial': 0, 'textformat': _v},
        '/Ac/Energy/Forward': {'initial': 0, 'textformat': _kwh},

        '/Ac/MaxPower': {'initial': int(config['PV']['max']), 'textformat': _w},
        '/Ac/Position': {'initial': int(config['PV']['position']), 'textformat': _n},
        '/Ac/StatusCode': {'initial': 0, 'textformat': _n},
        '/UpdateIndex': {'initial': 0, 'textformat': _n},

        '/Enphase/AuthToken': {'initial': "", 'textformat': _str},  # used to populate chaging token
        '/Enphase/MicroInvertersConfig': {'initial': inverters["config"], 'textformat': _n},
        '/Enphase/MicroInvertersReporting': {'initial': inverters["reporting"], 'textformat': _n},
        '/Enphase/MicroInvertersProducing': {'initial': inverters["producing"], 'textformat': _n},
    }

    if 'L1' in data_meter_stream['pv']:
        paths_dbus.update({
            '/Ac/L1/Power': {'initial': 0, 'textformat': _w},
            '/Ac/L1/Current': {'initial': 0, 'textformat': _a},
            '/Ac/L1/Voltage': {'initial': 0, 'textformat': _v},
            '/Ac/L1/Frequency': {'initial': None, 'textformat': _hz},
            '/Ac/L1/Energy/Forward': {'initial': None, 'textformat': _kwh},
        })

    if 'L2' in data_meter_stream['pv']:
        paths_dbus.update({
            '/Ac/L2/Power': {'initial': 0, 'textformat': _w},
            '/Ac/L2/Current': {'initial': 0, 'textformat': _a},
            '/Ac/L2/Voltage': {'initial': 0, 'textformat': _v},
            '/Ac/L2/Frequency': {'initial': None, 'textformat': _hz},
            '/Ac/L2/Energy/Forward': {'initial': None, 'textformat': _kwh},
        })

    if 'L3' in data_meter_stream['pv']:
        paths_dbus.update({
            '/Ac/L3/Power': {'initial': 0, 'textformat': _w},
            '/Ac/L3/Current': {'initial': 0, 'textformat': _a},
            '/Ac/L3/Voltage': {'initial': 0, 'textformat': _v},
            '/Ac/L3/Frequency': {'initial': None, 'textformat': _hz},
            '/Ac/L3/Energy/Forward': {'initial': None, 'textformat': _kwh},
        })

    DbusEnphaseEnvoyPvService(
        servicename='com.victronenergy.pvinverter.enphase_envoy',
        deviceinstance=61,
        paths=paths_dbus,
        hardware=hardware
    )

    logging.info("Connected to dbus and switching over to GLib.MainLoop() (= event based)")
    mainloop = GLib.MainLoop()
    mainloop.run()


if __name__ == "__main__":
    main()
