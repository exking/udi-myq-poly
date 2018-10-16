#!/usr/bin/env python3

import polyinterface
import sys
from pymyq import MyQAPI as pymyq

LOGGER = polyinterface.LOGGER


class Controller(polyinterface.Controller):
    def __init__(self, polyglot):
        super().__init__(polyglot)
        self.name = 'MyQ Controller'
        self.address = 'myqctrl'
        self.primary = self.address
        self.myq = None

    def start(self):
        LOGGER.info('Started MyQ Controller')
        if not 'username' in self.polyConfig['customParams']:
            LOGGER.error('Please specify username parameter in the NodeServer configuration')
            return
        if not 'password' in self.polyConfig['customParams']:
            LOGGER.error('Please specify password parameter in the NodeServer configuration')
            return
        if not 'brand' in self.polyConfig['customParams']:
            LOGGER.error('Please specify brand parameter in the NodeServer configuration')
            return

        username = self.polyConfig['customParams']['username']
        password = self.polyConfig['customParams']['password']
        brand = self.polyConfig['customParams']['brand']

        if not brand in ['liftmaster', 'chamberlain', 'craftsman', 'merlin' ]:
            LOGGER.error('Invalid brand specified: {}, valid options are: liftmaster, chamberlain, craftsman, merlin'.format(brand))
            return

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

    def stop(self):
        LOGGER.info('MyQ Controller is stopping')

    def shortPoll(self):
        for node in self.nodes:
            self.nodes[node].updateInfo()
            
    def longPoll(self):
        LOGGER.info('Refreshing token...')
        if self.myq.is_login_valid():
            LOGGER.info('Token Ok')
        else:
            LOGGER.error('Token refresh failure')

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
        self.retry = False
        self.device_id = dev_id

    def start(self):
        LOGGER.info('Starting {}'.format(self.name))
        self.updateInfo()

    def updateInfo(self):
        LOGGER.debug('Updating {}'.format(self.name))
        try:
            state = self.controller.myq.get_status(self.device_id)
        except Exception as ex:
            LOGGER.warning('Unable to update the {} status {}'.format(self.name, ex))
            if not self.retry:
                self.retry = True
                self.updateInfo()
                return
        if state == 'open':
            self.setDriver('ST', 1)
            if self.state != state:
                self.reportCmd('DON')
            self.state = state
        elif state == 'closed':
            self.setDriver('ST', 0)
            if self.state != state:
                self.reportCmd('DOF')
            self.state = state
        elif state == 'stopped':
            self.setDriver('ST', 2)
            self.state = state
        elif state == 'closing':
            self.setDriver('ST', 3)
            self.state = state
        elif state == 'opening':
            self.setDriver('ST', 4)
            self.state = state
        else:
            self.setDriver('ST', 5)
            self.state = state
        self.retry = False

    def query(self, command=None):
        self.updateInfo()

    def door_open(self, command):
        if self.state in ['open', 'opening']:
            LOGGER.warning('{} is already {}'.format(self.name, self.state))
            return
        LOGGER.info('Opening {}'.format(self.name))
        try:
            self.controller.myq.open_device(self.device_id)
        except Exception as ex:
            LOGGER.error('Unable to open the door {} {}'.format(self.name, ex))
            if not self.retry:
                self.retry = True
                self.door_open(command)
        self.retry = False
        self.setDriver('ST', 4)

    def door_close(self, command):
        if self.state in ['closed', 'closing']:
            LOGGER.warning('{} is already {}'.format(self.name, self.state))
            return
        LOGGER.info('Closing {}'.format(self.name))
        try:
            self.controller.myq.close_device(self.device_id)
        except Exception as ex:
            LOGGER.error('Unable to open the door {} {}'.format(self.name, ex))
            if not self.retry:
                self.retry = True
                self.door_close(command)
        self.retry = False
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
