#!/usr/bin/env python

from gi.repository import GLib
import platform
import logging
import sys
import os
from os import path
import time
import json
import paho.mqtt.client as mqtt
import configparser # for config/ini file
import _thread

import threading
import requests
from requests.auth import HTTPDigestAuth
from functools import reduce

# import Victron Energy packages
sys.path.insert(1, os.path.join(os.path.dirname(__file__), 'ext', 'velib_python'))
from vedbus import VeDbusService

# use WARNING for default, INFO for displaying actual steps and values, DEBUG for debugging
logging.basicConfig(level=logging.WARNING)

# get values from config.ini file
try:
    config = configparser.ConfigParser()
    config.read("%s/config.ini" % (os.path.dirname(os.path.realpath(__file__))))
    if (config['ENVOY']['address'] == "IP_ADDR_OR_FQDN"):
        logging.error("config.ini file using invalid default values.")
        raise
except:
    logging.error("config.ini file not found. Copy or rename the config.sample.ini to config.ini")
    sys.exit()


# check if MQTT is enabled in config
if 'MQTT' in config and 'enabled' in config['MQTT'] and config['MQTT']['enabled'] == '1':
    MQTT_enabled = 1
else:
    MQTT_enabled = 0

# check if fetch_production_historic_interval is enabled in config and not under minimum value
if 'ENVOY' in config and 'fetch_production_historic_interval' in config['ENVOY'] and int(config['ENVOY']['fetch_production_historic_interval']) > 900:
    fetch_production_historic_interval = int(config['ENVOY']['fetch_production_historic_interval'])
else:
    fetch_production_historic_interval = 900

# check if fetch_production_historic_interval is enabled in config and not under minimum value
if 'PV' in config and 'inverter_count' in config['PV'] and 'inverter_type' in config['PV']:
    hardware = config['PV']['inverter_count'] + 'x ' + config['PV']['inverter_type']
else:
    hardware = 'Microinverters'

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
    fetch_inverters_interval = 60
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


# MQTT
def on_disconnect(client, userdata, rc):
    global connected
    logging.warning("MQTT client: Got disconnected")
    if rc != 0:
        logging.debug('MQTT client: Unexpected MQTT disconnection. Will auto-reconnect')
    else:
        logging.debug('MQTT client: rc value:' + str(rc))

    try:
        logging.info("MQTT client: Trying to reconnect")
        client.connect(config['MQTT']['broker_address'])
        connected = 1
    except Exception as e:
        logging.error("MQTT client: Error in retrying to connect with broker: %s" % e)
        connected = 0

def on_connect(client, userdata, flags, rc):
    global connected
    if rc == 0:
        logging.info("MQTT client: Connected to MQTT broker!")
        connected = 1
    else:
        logging.error("MQTT client: Failed to connect, return code %d\n", rc)

def on_publish(client, userdata, rc):
    pass


# ENPHASE - ENOVY-S
def fetch_meter_stream():
    logging.debug("step: fetch_meter_stream")

    global config, data_meter_stream, data_production_historic, keep_running

    marker = b'data: '

    # create dictionary for later to count watt hours
    data_watt_hours = {
        'time_creation': round(time.time(), 0),
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
    timestamp_storage_file = os.path.getmtime(data_watt_hours_storage_file) if path.isfile(data_watt_hours_storage_file) else 0

    ## load data to prevent sending 0 watthours for grid before the first loop
    # check if file in volatile storage exists
    if path.isfile(data_watt_hours_working_file):
        with open(data_watt_hours_working_file, 'r') as file:
            file = open(data_watt_hours_working_file, "r")
            json_data = json.load(file)
            logging.info('Loaded JSON once: %s' % json.dumps(json_data))
    # if not, check if file in persistent storage exists
    elif path.isfile(data_watt_hours_storage_file):
        with open(data_watt_hours_storage_file, 'r') as file:
            file = open(data_watt_hours_storage_file, "r")
            json_data = json.load(file)
            logging.info('Loaded JSON once from persistent storage: %s' % json.dumps(json_data))
    else:
        json_data = {}

    while 1:

        try:

            url = 'http://%s/stream/meter' % config['ENVOY']['address']
            stream = requests.get(
                url,
                auth=HTTPDigestAuth('installer', config['ENVOY']['password']),
                stream=True,
                timeout=5
            )

            for line in stream.iter_lines():

                if keep_running == False:
                    logging.info('--> fetch_meter_stream(): got exit signal')
                    sys.exit()

                if line.startswith(marker):
                    data = json.loads(line.replace(marker, b''))

                    # set timestamp when line is read
                    timestamp = round(time.time(), 0)
                    total_jsonpayload = {}

                    for meter in ['production', 'net-consumption', 'total-consumption']:

                        meter_name = reduce(lambda a, kv: a.replace(*kv), replace_meters, meter)

                        jsonpayload = {}

                        total_power           = 0
                        total_current         = 0
                        total_voltage         = 0
                        total_power_react     = 0
                        total_power_appearent = 0

                        for phase in ['ph-a', 'ph-b', 'ph-c']:

                            phase_name = reduce(lambda a, kv: a.replace(*kv), replace_phases, phase)

                            if data[meter][phase]['v'] > 0:

                                total_power           += float(data[meter][phase]['p'])
                                total_current         += float(data[meter][phase]['i'])
                                total_voltage         += float(data[meter][phase]['v'])
                                total_power_react     += float(data[meter][phase]['q'])
                                total_power_appearent += float(data[meter][phase]['s'])

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


                    ### calculate watthours
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
                                    'energy_forward': round(data_watt_hours['grid']['L1']['energy_forward'] + grid_L1_power_forward if 'grid' in data_watt_hours and 'L1' in data_watt_hours['grid'] else grid_L1_power_forward, 3),
                                    'energy_reverse': round(data_watt_hours['grid']['L1']['energy_reverse'] + grid_L1_power_reverse if 'grid' in data_watt_hours and 'L1' in data_watt_hours['grid'] else grid_L1_power_reverse, 3),
                                }
                            })
                        if 'L2' in total_jsonpayload['grid']:
                            data_watt_hours_grid.update({
                                'L2': {
                                    'energy_forward': round(data_watt_hours['grid']['L2']['energy_forward'] + grid_L2_power_forward if 'grid' in data_watt_hours and 'L2' in data_watt_hours['grid'] else grid_L2_power_forward, 3),
                                    'energy_reverse': round(data_watt_hours['grid']['L2']['energy_reverse'] + grid_L2_power_reverse if 'grid' in data_watt_hours and 'L2' in data_watt_hours['grid'] else grid_L2_power_reverse, 3),
                                }
                            })
                        if 'L3' in total_jsonpayload['grid']:
                            data_watt_hours_grid.update({
                                'L3': {
                                    'energy_forward': round(data_watt_hours['grid']['L3']['energy_forward'] + grid_L3_power_forward if 'grid' in data_watt_hours and 'L3' in data_watt_hours['grid'] else grid_L3_power_forward, 3),
                                    'energy_reverse': round(data_watt_hours['grid']['L3']['energy_reverse'] + grid_L3_power_reverse if 'grid' in data_watt_hours and 'L3' in data_watt_hours['grid'] else grid_L3_power_reverse, 3),
                                }
                            })

                        data_watt_hours.update({
                            ## if PV not needed it can be removed, yet to evaluate
                            #'pv': {
                            #    'energy_forward': round(data_watt_hours['pv']['energy_forward'] + total_jsonpayload['pv']['power'], 3),
                            #},
                            'grid': data_watt_hours_grid,
                            'count': data_watt_hours['count'] + 1,

                        })

                        logging.info('--> data_watt_hours(): %s' % json.dumps(data_watt_hours))

                    # build mean, calculate time diff and Wh and write to file
                    else:
                        # check if file in volatile storage exists
                        if path.isfile(data_watt_hours_working_file):
                            with open(data_watt_hours_working_file, 'r') as file:
                                file = open(data_watt_hours_working_file, "r")
                                data_watt_hours_old = json.load(file)
                                logging.info('Loaded JSON: %s' % json.dumps(data_watt_hours_old))

                        # if not, check if file in persistent storage exists
                        elif path.isfile(data_watt_hours_storage_file):
                            with open(data_watt_hours_storage_file, 'r') as file:
                                file = open(data_watt_hours_storage_file, "r")
                                data_watt_hours_old = json.load(file)
                                logging.info('Loaded JSON from persistent storage: %s' % json.dumps(data_watt_hours_old))

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
                                ## if PV not needed it can be removed, yet to evaluate
                                #'pv': {
                                #    'energy_forward': 0,
                                #},
                                'grid': data_watt_hours_old_grid
                            }
                            logging.info('Generated JSON: %s' % json.dumps(data_watt_hours_old))

                        # factor to calculate Watthours: mean power * measuuring period / 3600 seconds (1 hour)
                        factor = (timestamp - data_watt_hours['time_creation']) / 3600

                        #pv_energy_forward   = data_watt_hours_old['pv']['energy_forward'] + (data_watt_hours['pv']['energy_forward'] / data_watt_hours['count'] * factor)
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

                        ### L1
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

                        ### L2
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

                        ### L3
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
                            ## if PV not needed it can be removed, yet to evaluate
                            #'pv': {
                            #    'energy_forward': pv_energy_forward,
                            #},
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
                            logging.info('Written JSON to persistent storage.')

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
                            ## if PV not needed it can be removed, yet to evaluate
                            #'pv': {
                            #    'energy_forward': round(total_jsonpayload['pv']['power'], 3),
                            #},
                            'grid': data_watt_hours_grid,
                            'count': 1

                        }

                        logging.info('--> data_watt_hours(): %s' % json.dumps(data_watt_hours))

                    # make fetched data globally available
                    data_meter_stream = total_jsonpayload

#        except requests.exceptions.HTTPError as e:
#            logging.error('--> fetch_meter_stream(): HTTPError occurred: \"%s\"' % e)
#            keep_running = False
#            sys.exit()
#
#        except requests.exceptions.ConnectionError as e:
#            logging.error('--> fetch_meter_stream(): ConnectionError occurred: \"%s\"' % e)
#            keep_running = False
#            sys.exit()
#
#        except requests.exceptions.Timeout as e:
#            logging.error('--> fetch_meter_stream(): Timeout occurred: \"%s\"' % e)
#            keep_running = False
#            sys.exit()
#
#        except requests.exceptions.ConnectTimeout as e:
#            logging.error('--> fetch_meter_stream(): ConnectTimeout occurred: \"%s\"' % e)
#            keep_running = False
#            sys.exit()
#
#        except requests.exceptions.ReadTimeout as e:
#            logging.error('--> fetch_meter_stream(): ReadTimeout occurred: \"%s\"' % e)
#            keep_running = False
#            sys.exit()
#
#        except requests.exceptions.RetryError as e:
#            logging.error('--> fetch_meter_stream(): RetryError occurred: \"%s\"' % e)
#            keep_running = False
#            sys.exit()
#
#        except requests.exceptions.RequestException as e:
#            logging.error('--> fetch_meter_stream(): RequestException occurred: \"%s\"' % e)
#            keep_running = False
#            sys.exit()
#
#        except requests.exceptions as e:
#            logging.error('--> fetch_meter_stream(): Request exceptions occurred: \"%s\"' % json.dumps(e))
#            keep_running = False
#            sys.exit()

        except Exception as e:
            logging.error('--> fetch_meter_stream(): Exception occurred: \"%s\"' % e)
            keep_running = False
            sys.exit()


def fetch_production_historic():
    logging.debug("step: fetch_production_historic")

    global replace_meters, data_production_historic

    try:

        url = 'http://%s/production.json?details=1' % config['ENVOY']['address']
        data = requests.get(url, timeout=5).json()

        total_jsonpayload = {}

        for meter in data.values():

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

    except Exception as e:
        logging.error('--> fetch_production_historic(): Exception occurred: \"%s\"' % e)
        keep_running = False
        sys.exit()


def fetch_devices():
    logging.debug("step: fetch_devices")

    global replace_devices, data_devices

    try:

        url = 'http://%s/inventory.json' % config['ENVOY']['address']
        data = requests.get(url, timeout=5).json()

        total_jsonpayload = {}

        for device_type in data:

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

    except Exception as e:
        logging.error('--> fetch_devices(): Exception occurred: \"%s\"' % e)
        keep_running = False
        sys.exit()


def fetch_inverters():
    logging.debug("step: fetch_inverters")

    global data_inverters

    try:

        url = 'http://%s/api/v1/production/inverters' % config['ENVOY']['address']
        data = requests.get(url, auth=HTTPDigestAuth('installer', config['ENVOY']['password'])).json()

        total_jsonpayload = {}

        for inverter in data:

            total_jsonpayload.update({
                inverter['serialNumber']: {
                    'lastReportDate': inverter['lastReportDate'],
                    'lastReportWatts': inverter['lastReportWatts']
                }
            })

        # make fetched data globally available
        data_inverters = total_jsonpayload

    except Exception as e:
        logging.error('--> fetch_inverters(): Exception occurred: \"%s\"' % e)
        keep_running = False
        sys.exit()


def fetch_events():
    logging.debug("step: fetch_events")

    global data_events

    try:

        url = 'http://%s/datatab/event_dt.rb?start=0&length=10' % config['ENVOY']['address']
        data = requests.get(url, timeout=5).json()

        total_jsonpayload = {}

        for event in data['aaData']:

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

    except Exception as e:
        logging.error('--> fetch_events(): Exception occurred: \"%s\"' % e)
        keep_running = False
        sys.exit()


def fetch_handler():
    logging.debug("step: fetch_handler")

    global config, keep_running, fetch_production_historic_interval, fetch_devices_interval, fetch_inverters_interval, fetch_events_interval

    fetch_production_historic_last = 0
    fetch_devices_last = 0
    fetch_inverters_last = 0
    fetch_events_last = 0

    while 1:

        if keep_running == False:
            logging.info('--> fetch_handler(): got exit signal')
            sys.exit()

        time_now = int(time.time())

        if ((time_now - fetch_production_historic_last) > fetch_production_historic_interval):
            fetch_production_historic_last = time_now
            try:
                fetch_production_historic()
                logging.info("--> fetch_handler() --> fetch_production_historic(): JSON data feched. Wait %s seconds for next run" % fetch_production_historic_interval)
            except Exception as e:
                logging.error('--> fetch_handler() --> fetch_production_historic(): Exception occurred: \"%s\". Try again in %s seconds' % (e, fetch_production_historic_interval))

        if fetch_devices_enabled == 1 and ((time_now - fetch_devices_last) > fetch_devices_interval):
            fetch_devices_last = time_now
            try:
                fetch_devices()
                logging.info("--> fetch_handler() --> fetch_devices(): JSON data feched. Wait %s seconds for next run" % fetch_devices_interval)
            except Exception as e:
                logging.error('--> fetch_handler() --> fetch_devices(): Exception occurred: \"%s\". Try again in %s seconds' % (e, fetch_devices_interval))

        if fetch_inverters_enabled == 1 and ((time_now - fetch_inverters_last) > fetch_inverters_interval):
            fetch_inverters_last = time_now
            try:
                fetch_inverters()
                logging.info("--> fetch_handler() --> fetch_inverters(): JSON data feched. Wait %s seconds for next run" % fetch_inverters_interval)
            except Exception as e:
                logging.error('--> fetch_handler() --> fetch_inverters(): Exception occurred: \"%s\". Try again in %s seconds' % (e, fetch_inverters_interval))

        if fetch_events_enabled == 1 and ((time_now - fetch_events_last) > fetch_events_interval):
            fetch_events_last = time_now
            try:
                fetch_events()
                logging.info("--> fetch_handler() --> fetch_events(): JSON data feched. Wait %s seconds for next run" % fetch_events_interval)
            except Exception as e:
                logging.error('--> fetch_handler() --> fetch_events(): Exception occurred: \"%s\". Try again in %s seconds' % (e, fetch_events_interval))

        # slow down requests to prevent overloading the Envoy
        time.sleep(1)


def publish_mqtt_data():
    logging.debug("step: publish_mqtt_data")

    global client, config, keep_running, data_meter_stream, data_devices, data_inverters, data_events

    data_previous_meter_stream = {}
    data_previous_devices = {}
    data_previous_inverters = {}
    data_previous_events = {}

    while 1:

        if keep_running == False:
            logging.info('--> publish_mqtt_data(): got exit signal')
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
            time.sleep(publish_interval)


        except Exception as e:
            logging.error('--> publish_mqtt_data(): Exception publishing MQTT data: %s' % e)
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
        self._dbusservice.add_path('/FirmwareVersion', '0.1.0')
        self._dbusservice.add_path('/HardwareVersion', hardware)
        self._dbusservice.add_path('/Connected', 1)

        self._dbusservice.add_path('/Latency', None)
        self._dbusservice.add_path('/ErrorCode', 0)
        self._dbusservice.add_path('/Position', int(config['PV']['position'])) # only needed for pvinverter
        self._dbusservice.add_path('/StatusCode', 0)  # Dummy path so VRM detects us as a PV-inverter

        for path, settings in self._paths.items():
            self._dbusservice.add_path(
                path, settings['initial'], gettextcallback=settings['textformat'], writeable=True, onchangecallback=self._handlechangedvalue
            )

        GLib.timeout_add(1000, self._update) # pause 1000ms before the next request


    def _update(self):

        if keep_running == False:
            logging.info('--> DbusEnphaseEnvoyPvService->_update(): got exit signal')
            sys.exit()

        self._dbusservice['/Ac/Power']  =  round(data_meter_stream['pv']['power'], 2)
        self._dbusservice['/Ac/Current'] = round(data_meter_stream['pv']['current'], 2)
        self._dbusservice['/Ac/Voltage'] = round(data_meter_stream['pv']['voltage'], 2)
        self._dbusservice['/Ac/Energy/Forward'] = round(data_meter_stream['pv']['energy_forward'], 2)   # needed for VRM historical data

        self._dbusservice['/ErrorCode'] = 0
        self._dbusservice['/StatusCode'] = 7

        if 'L1' in data_meter_stream['pv']:
            self._dbusservice['/Ac/L1/Power']  = round(data_meter_stream['pv']['L1']['power'], 2)
            self._dbusservice['/Ac/L1/Current'] = round(data_meter_stream['pv']['L1']['current'], 2)
            self._dbusservice['/Ac/L1/Voltage'] = round(data_meter_stream['pv']['L1']['voltage'], 2)
            self._dbusservice['/Ac/L1/Energy/Forward'] = round(data_meter_stream['pv']['L1']['energy_forward'], 2)   # needed for VRM historical data

        if 'L2' in data_meter_stream['pv']:
            self._dbusservice['/Ac/L2/Power']  = round(data_meter_stream['pv']['L2']['power'], 2)
            self._dbusservice['/Ac/L2/Current'] = round(data_meter_stream['pv']['L2']['current'], 2)
            self._dbusservice['/Ac/L2/Voltage'] = round(data_meter_stream['pv']['L2']['voltage'], 2)
            self._dbusservice['/Ac/L2/Energy/Forward'] = round(data_meter_stream['pv']['L2']['energy_forward'], 2)   # needed for VRM historical data

        if 'L3' in data_meter_stream['pv']:
            self._dbusservice['/Ac/L3/Power']  = round(data_meter_stream['pv']['L3']['power'], 2)
            self._dbusservice['/Ac/L3/Current'] = round(data_meter_stream['pv']['L3']['current'], 2)
            self._dbusservice['/Ac/L3/Voltage'] = round(data_meter_stream['pv']['L3']['voltage'], 2)
            self._dbusservice['/Ac/L3/Energy/Forward'] = round(data_meter_stream['pv']['L3']['energy_forward'], 2)   # needed for VRM historical data

        logging.info("PV: {:.1f} W - {:.1f} V - {:.1f} A".format(data_meter_stream['pv']['power'], data_meter_stream['pv']['voltage'], data_meter_stream['pv']['current']))
        if 'L1' in data_meter_stream['pv'] and data_meter_stream['pv']['power'] != data_meter_stream['pv']['L1']['power']:
            logging.info("|- L1: {:.1f} W - {:.1f} V - {:.1f} A".format(data_meter_stream['pv']['L1']['power'], data_meter_stream['pv']['L1']['voltage'], data_meter_stream['pv']['L1']['current']))
        if 'L2' in data_meter_stream['pv']:
            logging.info("|- L2: {:.1f} W - {:.1f} V - {:.1f} A".format(data_meter_stream['pv']['L2']['power'], data_meter_stream['pv']['L2']['voltage'], data_meter_stream['pv']['L2']['current']))
        if 'L3' in data_meter_stream['pv']:
            logging.info("|- L3: {:.1f} W - {:.1f} V - {:.1f} A".format(data_meter_stream['pv']['L3']['power'], data_meter_stream['pv']['L3']['voltage'], data_meter_stream['pv']['L3']['current']))


        # increment UpdateIndex - to show that new data is available
        index = self._dbusservice['/UpdateIndex'] + 1  # increment index
        if index > 255:   # maximum value of the index
            index = 0       # overflow from 255 to 0
        self._dbusservice['/UpdateIndex'] = index
        return True

    def _handlechangedvalue(self, path, value):
        logging.debug("someone else updated %s to %s" % (path, value))
        return True # accept the change


def main():
    global client, data_production_historic

    _thread.daemon = True # allow the program to quit

    from dbus.mainloop.glib import DBusGMainLoop
    # Have a mainloop, so we can send/receive asynchronous calls to and from dbus
    DBusGMainLoop(set_as_default=True)


    ## MQTT configuration
    if MQTT_enabled == 1:
        # create new instance
        client = mqtt.Client("EnphaseEnvoyPV")
        client.on_disconnect = on_disconnect
        client.on_connect = on_connect
        client.on_publish = on_publish

        # check tls and use settings, if provided
        if 'tls_enabled' in config['MQTT'] and config['MQTT']['tls_enabled'] == '1':
            logging.debug("MQTT client: TLS is enabled")

            if 'tls_path_to_ca' in config['MQTT'] and config['MQTT']['tls_path_to_ca'] != '':
                logging.debug("MQTT client: TLS: custom ca \"%s\" used" % config['MQTT']['tls_path_to_ca'])
                client.tls_set(config['MQTT']['tls_path_to_ca'], tls_version=2)
            else:
                client.tls_set(tls_version=2)

            if 'tls_insecure' in config['MQTT'] and config['MQTT']['tls_insecure'] != '':
                logging.debug("MQTT client: TLS certificate server hostname verification disabled")
                client.tls_insecure_set(True)

        # check if username and password are set
        if 'username' in config['MQTT'] and 'password' in config['MQTT'] and config['MQTT']['username'] != '' and config['MQTT']['password'] != '':
            logging.debug("MQTT client: Using username \"%s\" and password to connect" % config['MQTT']['username'])
            client.username_pw_set(username=config['MQTT']['username'], password=config['MQTT']['password'])

         # connect to broker
        client.connect(
            host=config['MQTT']['broker_address'],
            port=int(config['MQTT']['broker_port'])
        )
        client.loop_start()


    ## Enphase Envoy-S
    # fetch data for the first time to be able to use it in fetch_meter_stream()
    fetch_production_historic()
    logging.info("--> fetch_production_historic(): JSON production historic data feched")

    # fetch data for the first time alse MQTT outputs an empty status once
    if fetch_devices_enabled == 1:
        fetch_devices()

    if fetch_inverters_enabled == 1:
        fetch_inverters()

    if fetch_events_enabled == 1:
        fetch_events()


    # start threat for fetching data every x seconds in background
    fetch_handler_thread = threading.Thread(target=fetch_handler, name='Thread-FetchHandler')
    fetch_handler_thread.daemon = True
    fetch_handler_thread.start()

    # start threat for fetching continuously the stream in background
    fetch_meter_stream_thread = threading.Thread(target=fetch_meter_stream, name='Thread-FetchMeterStream')
    fetch_meter_stream_thread.daemon = True
    fetch_meter_stream_thread.start()

    # start threat for publishing mqtt data in background
    if MQTT_enabled == 1:
        publish_mqtt_data_thread = threading.Thread(target=publish_mqtt_data, name='Thread-PublishMqttData')
        publish_mqtt_data_thread.daemon = True
        publish_mqtt_data_thread.start()


    # wait to fetch first data, else dbus initialisation for phase count is wrong
    while not bool(data_meter_stream):
        time.sleep(1)
        logging.info('--> data_meter_stream not yet ready')

    #formatting
    _kwh = lambda p, v: (str(round(v, 2)) + 'kWh')
    _a = lambda p, v: (str(round(v, 2)) + 'A')
    _w = lambda p, v: (str(round(v, 2)) + 'W')
    _v = lambda p, v: (str(round(v, 2)) + 'V')
    _n = lambda p, v: (str(round(v, 0)))

    paths_dbus = {
        '/Ac/Power': {'initial': 0, 'textformat': _w},
        '/Ac/Current': {'initial': 0, 'textformat': _a},
        '/Ac/Voltage': {'initial': 0, 'textformat': _v},
        '/Ac/Energy/Forward': {'initial': 0, 'textformat': _kwh},

        '/Ac/MaxPower': {'initial': int(config['PV']['max']), 'textformat': _w},
        '/Ac/Position': {'initial': int(config['PV']['position']), 'textformat': _n},
        '/Ac/StatusCode': {'initial': 0, 'textformat': _n},
        '/UpdateIndex': {'initial': 0, 'textformat': _n},
    }

    if 'L1' in data_meter_stream['pv']:
        paths_dbus.update({
            '/Ac/L1/Power': {'initial': 0, 'textformat': _w},
            '/Ac/L1/Current': {'initial': 0, 'textformat': _a},
            '/Ac/L1/Voltage': {'initial': 0, 'textformat': _v},
            '/Ac/L1/Energy/Forward': {'initial': 0, 'textformat': _kwh},
        })

    if 'L2' in data_meter_stream['pv']:
        paths_dbus.update({
            '/Ac/L2/Power': {'initial': 0, 'textformat': _w},
            '/Ac/L2/Current': {'initial': 0, 'textformat': _a},
            '/Ac/L2/Voltage': {'initial': 0, 'textformat': _v},
            '/Ac/L2/Energy/Forward': {'initial': 0, 'textformat': _kwh},
        })

    if 'L3' in data_meter_stream['pv']:
        paths_dbus.update({
            '/Ac/L3/Power': {'initial': 0, 'textformat': _w},
            '/Ac/L3/Current': {'initial': 0, 'textformat': _a},
            '/Ac/L3/Voltage': {'initial': 0, 'textformat': _v},
            '/Ac/L3/Energy/Forward': {'initial': 0, 'textformat': _kwh},
        })

    pvac_output = DbusEnphaseEnvoyPvService(
        servicename='com.victronenergy.pvinverter.enphase_envoy',
        deviceinstance=61,
        paths=paths_dbus,
        hardware=hardware
    )

    logging.info('Connected to dbus and switching over to GLib.MainLoop() (= event based)')
    mainloop = GLib.MainLoop()
    mainloop.run()



if __name__ == "__main__":
  main()
