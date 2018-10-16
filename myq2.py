#!/usr/bin/env python3

import polyinterface
import sys
import logging
from pymyq import MyQAPI as pymyq

LOGGER = polyinterface.LOGGER

class Controller(polyinterface.Controller):
    def __init__(self, polyglot):
        super().__init__(polyglot)
        self.name = 'MyQ Controller'
        self.address = 'myqctrl'
        self.primary = self.address
        self.myq = None
        self.data = None

    def start(self):
        if 'debug' not in self.polyConfig['customParams']:
            LOGGER.setLevel(logging.INFO)
        LOGGER.info('Started MyQ Controller')
        if not 'username' in self.polyConfig['customParams']:
            LOGGER.error('Please specify username parameter in the NodeServer configuration')
            return
        if not 'password' in self.polyConfig['customParams']:
            LOGGER.error('Please specify password parameter in the NodeServer configuration')
            return
        if not 'brand' in self.polyConfig['customParams']:
            brand = pymyq.CHAMBERLAIN
            LOGGER.info('Please specify brand parameter in the NodeServer configuration, default to {}'.format(brand))
        else:
            brand = self.polyConfig['customParams']['brand']
            if not brand in pymyq.SUPPORTED_BRANDS:
                LOGGER.error('Invalid brand specified: {}, valid options are: '.format(brand, pymyq.SUPPORTED_BRANDS))
                return

        username = self.polyConfig['customParams']['username']
        password = self.polyConfig['customParams']['password']

        self.myq = pymyq(username, password, brand)

        if not self.myq.is_login_valid():
            LOGGER.error('Unable to login to MyQ cloud')
            return

        LOGGER.info('Login successful...')
        self.discover()

    def discover(self, command=None):
        for garage_door in self.myq.get_garage_doors():
            dev_id = garage_door['deviceid']
            address = str(dev_id)
            name = garage_door['name']
            if not address in self.nodes:
                self.addNode(MyQDev(self, self.address, address, name, dev_id))
                LOGGER.info('Adding {} with ID {}'.format(name, address))
        self.get_data()

    def stop(self):
        LOGGER.info('MyQ Controller is stopping')

    def get_data(self):
        self.data = self.myq.get_devices()
        if self.data is False:
            LOGGER.info('Controller - retrying to get data')
            self.data = self.myq.get_devices()
        if self.data:
            return True
        return False

    def shortPoll(self):
        self.get_data()
        for node in self.nodes:
            self.nodes[node].updateInfo()
            
    def longPoll(self):
        pass
        '''
        LOGGER.info('Refreshing token...')
        if self.myq.is_login_valid():
            LOGGER.info('Token Ok')
        else:
            LOGGER.error('Token refresh failure')
        '''

    def updateInfo(self):
        pass

    def query(self, command=None):
        for node in self.nodes:
            self.nodes[node].reportDrivers()

    id = 'MYQCTRL'
    commands = {'QUERY': query, 'DISCOVER': discover}
    drivers = [{'driver': 'ST', 'value': 0, 'uom': 2}
              ]


class MyQDev(polyinterface.Node):
    def __init__(self, controller, primary, address, name, dev_id):
        super().__init__(controller, primary, address, name)
        self.state = None
        self.device_id = dev_id

    def start(self):
        LOGGER.info('Starting {}'.format(self.name))
        self.updateInfo()

    def _get_status(self):
        if self.controller.data is None:
            LOGGER.error('No data from the controller {}'.format(self.name))
            return False

        door_state = False
        for door in self.controller.data:
            if door['MyQDeviceTypeName'] in pymyq.SUPPORTED_DEVICE_TYPE_NAMES and door['MyQDeviceId'] == self.device_id:
                for attribute in door['Attributes']:
                    if attribute['AttributeDisplayName'] == 'doorstate':
                        myq_door_state = attribute['Value']
                        door_state = pymyq.DOOR_STATE[myq_door_state]
        return door_state

    def updateInfo(self):
        LOGGER.debug('Updating {}'.format(self.name))
        state = self._get_status()
        if state == pymyq.STATE_OPEN:
            self.setDriver('ST', 1)
            if self.state != state:
                self.reportCmd('DON')
            self.state = state
        elif state == pymyq.STATE_CLOSED:
            self.setDriver('ST', 0)
            if self.state != state:
                self.reportCmd('DOF')
            self.state = state
        elif state == pymyq.STATE_STOPPED:
            self.setDriver('ST', 2)
            self.state = state
        elif state == pymyq.STATE_CLOSING:
            self.setDriver('ST', 3)
            self.state = state
        elif state == pymyq.STATE_OPENING:
            self.setDriver('ST', 4)
            self.state = state
        else:
            self.setDriver('ST', 5)
            self.state = state

    def query(self, command=None):
        self.controller.get_data()
        self.updateInfo()

    def door_open(self, command):
        self.controller.get_data()
        self.state = self._get_status()
        if self.state in [pymyq.STATE_OPEN, pymyq.STATE_OPENING]:
            LOGGER.warning('{} is already {}'.format(self.name, self.state))
            return
        LOGGER.info('Opening {}'.format(self.name))
        result = self.controller.myq.open_device(self.device_id)
        if result is False:
            LOGGER.error('Unable to open the door {}, retrying...'.format(self.name))
            result = self.controller.myq.open_device(self.device_id)
            if result is False:
                LOGGER.error('Retry failed')
                return
        self.setDriver('ST', 4)

    def door_close(self, command):
        self.controller.get_data()
        self.state = self._get_status()
        if self.state in [pymyq.STATE_CLOSED, pymyq.STATE_CLOSING]:
            LOGGER.warning('{} is already {}'.format(self.name, self.state))
            return
        LOGGER.info('Closing {}'.format(self.name))
        result = self.controller.myq.close_device(self.device_id)
        if result is False:
            LOGGER.error('Unable to close the door {}, retrying...'.format(self.name))
            result = self.controller.myq.close_device(self.device_id)
            if result is False:
                LOGGER.error('Retry failed')
                return
        self.setDriver('ST', 3)

    id = 'MYQDEV'
    commands = {'QUERY': query, 'DON': door_open, 'DOF': door_close}
    drivers = [{'driver': 'ST', 'value': 0, 'uom': 25}
              ]


if __name__ == "__main__":
    try:
        polyglot = polyinterface.Interface('MyQ2')
        polyglot.start()
        control = Controller(polyglot)
        control.runForever()
    except (KeyboardInterrupt, SystemExit):
        sys.exit(0)
