#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import uuid
sys.path.append(os.path.dirname(os.path.realpath(__file__)))
from baseObject import BaseObject
from subprocess import Popen, PIPE
from abc import ABCMeta, abstractmethod
from ConfigParser import SafeConfigParser


class RCProfileAbstract(BaseObject):
    """
    Common profile for rdp and ssh
    """
    __metaclass__ = ABCMeta
    CONFIG_FILE_DIR = os.path.join(os.getenv('HOME'), '.remote-client')

    def __init__(self, id=None):
        self.config_store = {
                'main': ['ip', 'name', 'group', 'domain', 'username', 'share']
                }
        self.name, self.title, self.title_escaped = None, None, None
        self.id = self.get_value(id,
                str(uuid.uuid1(0, 0)).replace('-', '')[:16])
        self.config_file_name = os.path.join(self.CONFIG_FILE_DIR,
                '{}.conf'.format(self.id))
        if id is not None:
            self.__read()

    def __str__(self):
        return '{}: {{id: {}, title: {}}}'.format(
                self.__class__, self.id, self.get_title())

    def __repr__(self):
        return '<class {}: {{id: {}, title: {}}}>'.format(
                self.__class__, self.id, self.get_title())

    def __read_password(self):
        return str(Popen(('secret-tool lookup profile {}'.format(self.id
            )).split(), stdout=PIPE).communicate()[0])

    def __save_password(self):
        Popen(('secret-tool store --label="remote-client" profile {}'.format(
            self.id)).split(), stdin=PIPE).communicate(self.password)

    def __clear_password(self):
        Popen(('secret-tool clear profile {}'.format(self.id)).split())
        self.password = ''

    def __read(self):
        if not os.path.exists(self.config_file_name):
            raise IOError("Config file '{}' not found".format(
                self.config_file_name))
        self.password = self.__read_password()
        parser = SafeConfigParser()
        parser.read(self.config_file_name)
        for section, attributes in self.config_store.iteritems():
            if not parser.has_section(section):
                raise KeyError("Config section '{}' not found".format(section))
            for attribute, value in parser.items(section):
                if attribute not in attributes:
                    raise KeyError(
                            "Invalid attribute '{}' in config file".format(
                                attribute))
                setattr(self, attribute, value)

    def get_title(self):
        if self.title is None:
            self.title = '{1}[{0}]'.format(self.get_value(self.ip, ''),
                    '{} '.format(self.name) if self.is_non_zero(
                        self.name) else '')
        return self.title

    def save(self):
        parser = SafeConfigParser()
        for section, attributes in self.config_store.iteritems():
            parser.add_section(section)
            for attribute in attributes:
                parser.set(section, attribute, self.get(attribute, ''))
            self.__save_password()
            with open(self.config_file_name, 'wb') as configfile:
                parser.write(configfile)
        self.title = None

    def remove(self):
        self.__clear_password()
        os.remove(self.config_file_name)
        self.id = None

    @abstractmethod
    def get_command(self):
        return None

class RCProfileRDP(RCProfileAbstract):
    """
    Data source with information for establishing of RDP connection
    """

    def __init__(self, id=None):
        super(RCProfileRDP, self).__init__(id)

    def get_command(self):
        params = 'nohup rdesktop -a 16 -N -g 1918x1040'.split()
        params += ['-k', 'en-us']
        params += ['-r', 'clipboard:PRIMARYCLIPBOARD']
        params += ['-T', self.get_title()]
        if len(self.username) > 0:
            params += ['-u', self.username]
        if len(self.password) > 0:
            params += ['-p', self.password]
        if len(self.domain) > 0:
            params += ['-d', self.domain]
        if len(self.share) > 0:
            params += ['-r', 'disk:share=%s' % (self.share,)]
        params.append(self.ip)
        return params

class RCProfileSSH(RCProfileAbstract):
    """
    Data source with information for establishing of SSH connection
    """

    def __init__(self, id=None):
        super(RCProfileSSH, self).__init__(id)
