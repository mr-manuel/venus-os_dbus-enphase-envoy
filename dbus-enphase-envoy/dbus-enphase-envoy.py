#!/usr/bin/env python
# TODO: Add device statuses
# TODO: Add events

from gi.repository import GLib
import platform
import logging
import sys
import os
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

# use INFO for less logging, DEBUG for debugging
logging.basicConfig(level=logging.INFO)


# get values from config.ini file
try:
    config = configparser.ConfigParser()
    config.read("%s/config.ini" % (os.path.dirname(os.path.realpath(__file__))))
    if (config['ENVOY']['address'] == "IP_ADDR_OR_FQDN"):
        logging.info("config.ini file using invalid default values.")
        raise
except:
    logging.info("config.ini file not found. Copy or rename the config.sample.ini to config.ini")
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

# check if fetch_devices is enabled in config
if 'DATA' in config and 'fetch_devices' in config['DATA'] and config['DATA']['fetch_devices'] == '1':
    fetch_devices_enabled = 1
    # check if fetch_devices_interval is enabled in config and not under minimum value
    if 'DATA' in config and 'fetch_devices_interval' in config['DATA'] and int(config['DATA']['fetch_devices_interval']) > 60:
        fetch_devices_interval = int(config['DATA']['fetch_devices_interval'])
    else:
        fetch_devices_interval = 60
else:
    fetch_devices_enabled = 0
    fetch_devices_interval = 3600

# check if fetch_inverters is enabled in config
if 'DATA' in config and 'fetch_inverters' in config['DATA'] and config['DATA']['fetch_inverters'] == '1':
    fetch_inverters_enabled = 1
    # check if fetch_inverters_interval is enabled in config and not under minimum value
    if 'DATA' in config and 'fetch_inverters_interval' in config['DATA'] and int(config['DATA']['fetch_inverters_interval']) > 5:
        fetch_inverters_interval = int(config['DATA']['fetch_inverters_interval'])
    else:
        fetch_inverters_interval = 5
else:
    fetch_inverters_enabled = 0
    fetch_inverters_interval = 60

# check if fetch_events is enabled in config
if 'DATA' in config and 'fetch_events' in config['DATA'] and config['DATA']['fetch_events'] == '1':
    fetch_events_enabled = 1
    # check if fetch_events_interval is enabled in config and not under minimum value
    if 'DATA' in config and 'fetch_events_interval' in config['DATA'] and int(config['DATA']['fetch_events_interval']) > 900:
        fetch_events_interval = int(config['DATA']['fetch_events_interval'])
    else:
        fetch_events_interval = 900
else:
    fetch_events_enabled = 0
    fetch_events_interval = 3600


# set variables
connected = 0
keep_running = True

replace_meters = ('production', 'pv'), ('net-consumption', 'grid'), ('total-consumption', 'consumption')
replace_phases = ('ph-a', 'L1'), ('ph-b', 'L2'), ('ph-c', 'L3')
replace_devices = ('PCU', 'inverters'), ('ACB', 'batteries'), ('NSRB', 'relais')

pv_power = 0
pv_current = 0
pv_voltage = 0
pv_forward = 0

pv_L1_power = 0
pv_L1_current = 0
pv_L1_voltage = 0
pv_L1_forward = 0

pv_L2_power = 0
pv_L2_current = 0
pv_L2_voltage = 0
pv_L2_forward = 0

pv_L3_power = 0
pv_L3_current = 0
pv_L3_voltage = 0
pv_L3_forward = 0

data_meter_stream = {}
data_production_historic = {}
data_device_statuses = {}
data_inverters = {}
data_events = {}


# MQTT
def on_disconnect(client, userdata, rc):
    global connected
    logging.info("MQTT client: Got disconnected")
    if rc != 0:
        logging.debug('MQTT client: Unexpected MQTT disconnection. Will auto-reconnect')
    else:
        logging.debug('MQTT client: rc value:' + str(rc))

    try:
        logging.info("MQTT client: Trying to reconnect")
        client.connect(config['MQTT']['broker_address'])
        connected = 1
    except Exception as e:
        logging.exception("MQTT client:Error in retrying to connect with broker: %s" % e)
        connected = 0

def on_connect(client, userdata, flags, rc):
    global connected
    if rc == 0:
        logging.info("MQTT client: Connected to MQTT broker!")
        connected = 1
    else:
        logging.info("MQTT client: Failed to connect, return code %d\n", rc)

def on_publish(client, userdata, rc):
    pass


# ENPHASE - ENOVY-S
def fetch_meter_stream():
    logging.debug("step: fetch_meter_stream")

    global config, data_meter_stream, data_production_historic, keep_running, pv_power, pv_current, pv_voltage, pv_L1_power, pv_L1_current, pv_L1_voltage, pv_L2_power, pv_L2_current, pv_L2_voltage, pv_L3_power, pv_L3_current, pv_L3_voltage, replace_phases

    marker = b'data: '

    while 1:

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

                total_jsonpayload = {}
                pvVars = globals()

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

                            jsonpayload.update({
                                phase_name: {
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
                            })

                            if meter == 'production':
                                pvVars.__setitem__('pv_' + phase_name + '_power', float(data[meter][phase]['p']))
                                pvVars.__setitem__('pv_' + phase_name + '_current', float(data[meter][phase]['i']))
                                pvVars.__setitem__('pv_' + phase_name + '_voltage', float(data[meter][phase]['v']))


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

                    if meter == 'production':
                        pv_power = total_power
                        pv_current = total_current
                        pv_voltage = total_voltage

                    total_jsonpayload.update({meter_name: jsonpayload})

                # make fetched data globally available
                data_meter_stream = total_jsonpayload


def fetch_production_historic():
    logging.debug("step: fetch_production_historic")

    global replace_meters, data_production_historic

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


def fetch_device_statuses():
    logging.debug("step: fetch_device_statuses")

    global replace_devices, data_device_statuses

    url = 'http://%s/inventory.json' % config['ENVOY']['address']
    data = requests.get(url, timeout=5).json()

    total_jsonpayload = {}

    for device_type in data:

        device_name = reduce(lambda a, kv: a.replace(*kv), replace_devices, device_type['type'])

        jsonpayload = {}

        for device in device_type['devices']:

            # TODO: better option?
            if 'relay' in device:
                jsonpayload.update({
                    device['serial_num']: {
                        "status": device['device_status'],
                        "producing": device['producing'],
                        "communicating": device['communicating'],
                        "provisioned": device['provisioned'],
                        "operating": device['operating'],
                        "relay": device['relay'],
                        "reason": device['reason'],
                    }
                })
            else:
                jsonpayload.update({
                    device['serial_num']: {
                        "status": device['device_status'],
                        "producing": device['producing'],
                        "communicating": device['communicating'],
                        "provisioned": device['provisioned'],
                        "operating": device['operating'],
                    }
                })

        total_jsonpayload.update({device_name: jsonpayload})

    # make fetched data globally available
    data_device_statuses = total_jsonpayload


def fetch_inverters():
    logging.debug("step: fetch_inverters")

    global data_inverters

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


def fetch_events():
    logging.debug("step: fetch_events")

    global data_events

    url = 'http://%s/datatab/event_dt.rb?start=0&length=10' % config['ENVOY']['address']
    data = requests.get(url, timeout=5).json()

    # make fetched data globally available
    data_events = data['aaData']


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

        try:
            if ((time_now - fetch_production_historic_last) > fetch_production_historic_interval):
                fetch_production_historic_last = time_now
                fetch_production_historic()
                logging.info("--> fetch_handler() --> fetch_production_historic(): JSON data feched. Wait %s seconds for next run" % fetch_production_historic_interval)

            if fetch_devices_enabled == 1 and ((time_now - fetch_devices_last) > fetch_devices_interval):
                fetch_devices_last = time_now
                fetch_device_statuses()
                logging.info("--> fetch_handler() --> fetch_device_statuses(): JSON data feched. Wait %s seconds for next run" % fetch_devices_interval)

            if fetch_inverters_enabled == 1 and ((time_now - fetch_inverters_last) > fetch_inverters_interval):
                fetch_inverters_last = time_now
                fetch_inverters()
                logging.info("--> fetch_handler() --> fetch_inverters(): JSON data feched. Wait %s seconds for next run" % fetch_inverters_interval)

            if fetch_events_enabled == 1 and ((time_now - fetch_events_last) > fetch_events_interval):
                fetch_events_last = time_now
                fetch_events()
                logging.info("--> fetch_handler() --> fetch_events(): JSON data feched. Wait %s seconds for next run" % fetch_events_interval)

            # slow down requests to prevent overloading the Envoy
            time.sleep(1)

        except Exception as e:
            if fetch_production_historic_interval > 60:
                sleep = fetch_production_historic_interval
            else:
                sleep = 60

            logging.info('--> fetch_handler(): Exception occurred: \"%s\". Try again in %s seconds' % (e, sleep))
            time.sleep(sleep)



def publish_mqtt_data():
    logging.debug("step: publish_mqtt_data")

    global client, config, keep_running, data_meter_stream, data_device_statuses, data_inverters, data_events

    data_previous_meter_stream = {}
    data_previous_device_statuses = {}
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

            # check if data_device_statuses is enabled, not empty and data is changed
            if fetch_devices_enabled == 1 and data_device_statuses and data_previous_device_statuses != data_device_statuses:
                data_previous_device_statuses = data_device_statuses
                client.publish(config['MQTT']['topic_devices'], json.dumps(data_device_statuses))
                logging.info("--> publish_mqtt_data() --> data_device_statuses: MQTT data published")

            # check if data_inverters is enabled, not empty and data is changed
            if fetch_inverters_enabled == 1 and data_inverters and data_previous_inverters != data_inverters:
                data_previous_inverters = data_inverters
                client.publish(config['MQTT']['topic_inverters'], json.dumps(data_inverters))
                logging.info("--> publish_mqtt_data() --> data_inverters: MQTT data published")

            # check if data_events is enabled, not empty and data is changed
            if fetch_events_enabled == 1 and data_events and data_previous_events != data_events:
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
            logging.info('Exception publishing MQTT data: %s' % e)
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
        connection='Enphase PV service'
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
        self._dbusservice.add_path('/ProductId', 0xFFFF) # value used in ac_sensor_bridge.cpp of dbus-cgwacs
        self._dbusservice.add_path('/ProductName', productname)
        self._dbusservice.add_path('/CustomName', productname)
        self._dbusservice.add_path('/FirmwareVersion', 0.1)
        self._dbusservice.add_path('/HardwareVersion', 0)
        self._dbusservice.add_path('/Connected', 1)

        self._dbusservice.add_path('/Latency', None)
        self._dbusservice.add_path('/Position', int(config['PV']['position'])) # normaly only needed for pvinverter
        self._dbusservice.add_path('/StatusCode', 0)  # Dummy path so VRM detects us as a PV-inverter.

        for path, settings in self._paths.items():
            self._dbusservice.add_path(
                path, settings['initial'], gettextcallback=settings['textformat'], writeable=True, onchangecallback=self._handlechangedvalue
            )

        GLib.timeout_add(1000, self._update) # pause 1000ms before the next request


    def _update(self):

        if keep_running == False:
            logging.info('--> DbusEnphaseEnvoyPvService->_update(): got exit signal')
            sys.exit()

        self._dbusservice['/Ac/Power'] =  round(pv_power, 2)
        self._dbusservice['/Ac/Current'] = round(pv_current, 2)
        self._dbusservice['/Ac/Voltage'] = round(pv_voltage, 2)
        #self._dbusservice['/Ac/Energy/Forward'] = round(pv_forward/1000, 2)

        self._dbusservice['/Ac/L1/Power'] = round(pv_L1_power, 2)
        self._dbusservice['/Ac/L1/Current'] = round(pv_L1_current, 2)
        self._dbusservice['/Ac/L1/Voltage'] = round(pv_L1_voltage, 2)
        #self._dbusservice['/Ac/L1/Energy/Forward'] = round(pv_L1_forward/1000, 2)

        #self._dbusservice['/StatusCode'] = 7

        if pv_L2_power > 0:
            self._dbusservice['/Ac/L2/Power'] = round(pv_L2_power, 2)
            self._dbusservice['/Ac/L2/Current'] = round(pv_L2_current, 2)
            self._dbusservice['/Ac/L2/Voltage'] = round(pv_L2_voltage, 2)
            #self._dbusservice['/Ac/L2/Energy/Forward'] = round(pv_L2_forward/1000, 2)

        if pv_L3_power > 0:
            self._dbusservice['/Ac/L3/Power'] = round(pv_L3_power, 2)
            self._dbusservice['/Ac/L3/Current'] = round(pv_L3_current, 2)
            self._dbusservice['/Ac/L3/Voltage'] = round(pv_L3_voltage, 2)
            #self._dbusservice['/Ac/L3/Energy/Forward'] = round(pv_L3_forward/1000, 2)

        logging.info("PV: {:.1f} W - {:.1f} V - {:.1f} A".format(pv_power, pv_voltage, pv_current))
        if pv_L1_power > 0 and pv_power != pv_L1_power:
            logging.info("|- L1: {:.1f} W - {:.1f} V - {:.1f} A".format(pv_L1_power, pv_L1_voltage, pv_L1_current))
        if pv_L2_power:
            logging.info("|- L2: {:.1f} W - {:.1f} V - {:.1f} A".format(pv_L2_power, pv_L2_voltage, pv_L2_current))
        if pv_L3_power:
            logging.info("|- L3: {:.1f} W - {:.1f} V - {:.1f} A".format(pv_L3_power, pv_L3_voltage, pv_L3_current))


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
        fetch_device_statuses()

    if fetch_inverters_enabled == 1:
        fetch_inverters()

    if fetch_events_enabled == 1:
        fetch_events()


    # start threat for fetching data every x seconds in background
    fetch_handler_thread = threading.Thread(target=fetch_handler)
    fetch_handler_thread.setDaemon(True)
    fetch_handler_thread.start()

    # start threat for fetching continuously the stream in background
    fetch_meter_stream_thread = threading.Thread(target=fetch_meter_stream)
    fetch_meter_stream_thread.setDaemon(True)
    fetch_meter_stream_thread.start()

    # start threat for publishing mqtt data in background
    if MQTT_enabled == 1:
        publish_mqtt_data_thread = threading.Thread(target=publish_mqtt_data)
        publish_mqtt_data_thread.setDaemon(True)
        publish_mqtt_data_thread.start()


    # wait to fetch first data, else dbus initialisation for phase count is wrong
    time.sleep(2)

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

        '/Ac/L1/Power': {'initial': 0, 'textformat': _w},
        '/Ac/L1/Current': {'initial': 0, 'textformat': _a},
        '/Ac/L1/Voltage': {'initial': 0, 'textformat': _v},

        '/Ac/MaxPower': {'initial': int(config['PV']['max']), 'textformat': _w},
        '/Ac/Position': {'initial': int(config['PV']['position']), 'textformat': _n},
        '/Ac/StatusCode': {'initial': 0, 'textformat': _n},
        '/UpdateIndex': {'initial': 0, 'textformat': _n},
    }

    if pv_L2_power > 0:
        paths_dbus.update({
            '/Ac/L2/Power': {'initial': 0, 'textformat': _w},
            '/Ac/L2/Current': {'initial': 0, 'textformat': _a},
            '/Ac/L2/Voltage': {'initial': 0, 'textformat': _v},
        })

    if pv_L3_power > 0:
        paths_dbus.update({
            '/Ac/L3/Power': {'initial': 0, 'textformat': _w},
            '/Ac/L3/Current': {'initial': 0, 'textformat': _a},
            '/Ac/L3/Voltage': {'initial': 0, 'textformat': _v},
        })


    pvac_output = DbusEnphaseEnvoyPvService(
        servicename='com.victronenergy.pvinverter.enphase_envoy',
        deviceinstance=61,
        paths=paths_dbus
    )

    logging.info('Connected to dbus and switching over to GLib.MainLoop() (= event based)')
    mainloop = GLib.MainLoop()
    mainloop.run()



if __name__ == "__main__":
  main()
