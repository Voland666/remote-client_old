#!/usr/bin/python
# -*- coding: utf-8 -*-

from gi.repository import Gtk
from gi.repository import Gdk
from gi.repository import GObject
from gi.repository import GdkPixbuf
from gi.repository import GLib
from gi.repository import Wnck
from urlparse import urlparse
from ConfigParser import SafeConfigParser
from os.path import basename
from os.path import splitext
from subprocess import Popen
from subprocess import PIPE
import os
import signal
import uuid
import time
import glob
import logging

# TODO: 0. Refactoring of code
# DONE	1. Save .rdpc files into other directory
# DONE	2. Sort by column
# DONE	3. Buttons for Open/Close connection
# DONE	4. Button for "Copy to New" connection
#	5. Groups for connections
#	6. Settings "Close all connections on exit"
#	7. Desctiption field in profile
# DONE	8. Scroll connection list
#	9. Preferences window (dir for .rdpc files, ...)
#	10. Embed rdesktop in custom window
# DONE	11. Check existing connections on start
#	12. Group manager
#	13. Settings manager
# DONE	14. Secure save password

class RDPProfile:

    def __init__(self, id=None):
        if id is None:
            self.id = str(uuid.uuid1(0, 0)).replace('-', '')[:16]
        else:
            self.id = id
            self.__read()

    def __str__(self):
        return '%s: {id: %s, title: %s}' % (self.__class__, self.id,
                self.get_title())

    def __read_password(self):
        self.password = str(Popen(('secret-tool lookup profile %s' % (self.id,
            )).split(), stdout=PIPE).communicate()[0])

    def __save_password(self):
        Popen(('secret-tool store --label="rdpclient" profile %s' % (self.id,
            )).split(), stdin=PIPE).communicate(self.password)

    def __clear_password(self):
        Popen(('secret-tool clear profile %s' % (self.id,)).split())
        self.password = ''

    def __read(self):
        self.__read_password()
        parser = SafeConfigParser()
        parser.read('%s/.rdpclient/%s.rdpc' % (os.getenv('HOME'), self.id))
        if parser.has_section('main'):
            for attr, value in parser.items('main'):
                setattr(self, attr, value)

    def get_title(self, escaped=False):
        return '%(name)s%(slash)s[%(ip)s%(slash)s]' % {
                'ip': self.ip if self.ip is not None else '',
                'name': '%s ' % (self.name,) if (self.name is not None and
                        len(self.name) > 0) else '',
                'slash': '\\' if escaped else ''}

    def save(self):
        parser = SafeConfigParser()
        parser.add_section('main')
        for attr, value in self.__dict__.iteritems():
            if attr not in ['id', 'password'] and value is not None:
                parser.set('main', attr, value)
        self.__save_password()
        with open('%s/.rdpclient/%s.rdpc' % (os.getenv('HOME'), self.id,),
                'wb') as configfile:
            parser.write(configfile)

    def get_rdp_command(self):
        params = 'nohup rdesktop -a 16 -N -g 1918x1040'.split()
        params += ['-r', 'clipboard:PRIMARYCLIPBOARD']
        params += ['-T', self.get_title()]
        if len(self.username) > 0:
            params += ['-u', self.username]
        if len(self.password) > 0:
            params += ['-p', self.password]
        if len(self.domain) > 0:
            params += ['-d', self.domain]
        if len(self.share) > 0:
            params += ['-r', 'disk:rdpshare=%s' % (self.share,)]
        params.append(self.ip)
        return params

    def remove(self):
        self.__clear_password()
        os.remove('%s/.rdpclient/%s.rdpc' % (os.getenv('HOME'), self.id))
        self.id = None


class RDPConnection:

    def __init__(self, profile=None):
        self.profile = RDPProfile() if profile is None else profile
        self.pid = None
        self.iter = None
        self.window = None

    def __str__(self):
        return '%s: {profile: %s}' % (self.__class__, self.profile)

    def find_window(self):
        title = self.profile.get_title() if self.profile is not None else '[]'
        logger.debug('title: %s' % (title,))
        if len(title) > 2:
            while Gtk.events_pending():
                Gtk.main_iteration()
            window = [win for win in Wnck.Screen.get_default().get_windows()
                    if win.get_name() == title]
            logger.debug('window: %s' % (window,))
            if len(window) == 1:
                self.window = window[0]
                return True
        self.window = None
        return False

    def connect(self):
        logger.debug('{is_connected: %s}', self.is_connected())
        if self.is_connected():
            logger.debug('{window: %s}', self.window)
            if self.window is None:
                raise ValueError('Window not found for connection %s' % (self,))
            else:
                self.window.activate(time.time())
        else:
            self.pid = Popen(self.profile.get_rdp_command()).pid
            self.find_window()

    def disconnect(self):
        if self.is_connected():
            os.kill(self.pid, signal.SIGTERM)
        self.pid = None
        self.window = None

    def is_connected(self):
        if self.pid is not None:
            try:
                pid, sts = os.waitpid(self.pid, os.WNOHANG)
                #return pid != self.pid
            except OSError:#, err:
                #return err.errno == os.errno.ECHILD
                # TODO: implement correct
                pass
            return os.path.exists('/proc/%s' % (self.pid,))
        return False

    def remove(self):
        self.profile.remove()
        self.profile = None
        self.iter = None


class RDPClient:

    def __init__(self):
        self.builder = Gtk.Builder()
        self.builder.add_from_file('rdpclient.glade')
        self.builder.connect_signals(self)
        self.__load_objects()

        self.tsConnections = Gtk.TreeStore(GObject.TYPE_PYOBJECT, str)
        ids = [splitext(basename(rdpc))[0] for rdpc in
                glob.glob('%s/.rdpclient/*.rdpc' % (os.getenv('HOME'),))]
        self.win_ico = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                'icons/windows.svg', 16, 16, True)
        self.con_ico = Gtk.IconTheme.get_default().load_icon(
                'gtk-connect', 16, 0)
        self.discon_ico = Gtk.IconTheme.get_default().load_icon(
                'gtk-disconnect', 16, 0)
        for id in ids:
            profile = RDPProfile(id)
            title = profile.get_title()
            connection = RDPConnection(profile)
            is_window_found = connection.find_window()
            logger.debug('connection %s; window: %s' % (connection,
                connection.window))
            if is_window_found:
                connection.pid = int(Popen(['pgrep', '-f',
                    profile.get_title(True)], stdout=PIPE).communicate()[0])
                logger.debug('found pid: %s' % (connection.pid,))
            connection.iter = self.tsConnections.append(None,
                    [connection, title])
            if is_window_found:
                GLib.timeout_add_seconds(1, self.check_connection, connection)
        self.tvConnections.set_model(self.tsConnections)
        render_state = Gtk.CellRendererPixbuf()
        render_logo = Gtk.CellRendererPixbuf()
        render_text = Gtk.CellRendererText()
        self.tvcConnections.pack_start(render_state, expand=False)
        self.tvcConnections.pack_start(render_logo, expand=False)
        self.tvcConnections.pack_start(render_text, expand=True)
        self.tvcConnections.set_cell_data_func(render_state,
                self.conn_cell_state_func)
        self.tvcConnections.set_cell_data_func(render_logo,
                self.conn_cell_logo_func)
        self.tvcConnections.set_cell_data_func(render_text,
                self.conn_cell_title_func)
        self.tvcConnections.clicked()

    def __load_objects(self):
        logger.debug('>')
        for obj in ['awRDPClient', 'sStatus', 'tvConnections',
                'tvcConnections', 'tselConnection']:
            setattr(self, obj, self.builder.get_object(obj))
        logger.debug('<')

    def check_connection(self, connection):
        return (connection.is_connected() or
                self.refresh_connection_status(connection) or False)

    def conn_cell_state_func(self, column, cell, model, iter, data):
        logger.debug('>')
        cell.set_property('pixbuf', self.con_ico
                if model.get_value(iter, 0).is_connected() else self.discon_ico)
        logger.debug('<')

    def conn_cell_logo_func(self, column, cell, model, iter, data):
        logger.debug('>')
        cell.set_property('pixbuf', self.win_ico)
        logger.debug('<')

    def conn_cell_title_func(self, column, cell, model, iter, data):
        logger.debug('>')
        cell.set_property('text', model.get_value(iter, 0).profile.get_title())
        logger.debug('<')

    def refresh_connection_status(self, connection):
        logger.debug('>')
        self.tvConnections.queue_draw()
        self.on_tselConnection_changed(self.tselConnection)
        if not connection.is_connected():
            connection.disconnect()
        logger.debug('<')

    def on_tvConnections_double_click(self, widget, event):
        logger.debug('>')
        if (event.button == 1 and
            event.type == Gdk.EventType.DOUBLE_BUTTON_PRESS):
                self.on_tbConnect_clicked(False)
        logger.debug('<')

    def on_tbAdd_clicked(self, button):
        logger.debug('>')
        self.dlgBuilder = Gtk.Builder()
        self.dlgBuilder.add_objects_from_file('rdpclient.glade',
                ['dlgConnection', 'tsConnectionGroups', 'tsConnections',
                    'awRDPClient'])
        self.dlgBuilder.connect_signals(self)
        self.dlgConnection = self.dlgBuilder.get_object('dlgConnection')
        self.dlgBuilder.get_object('btnSave').set_sensitive(False)
        self.active_profile = None
        self.dlgConnection.run()
        logger.debug('<')

    def on_tbCopy_clicked(self, button):
        logger.debug('>')
        self.dlgBuilder = Gtk.Builder()
        self.dlgBuilder.add_objects_from_file('rdpclient.glade',
                ['dlgConnection', 'tsConnectionGroups', 'awRDPClient'])
        self.dlgBuilder.connect_signals(self)
        self.dlgConnection = self.dlgBuilder.get_object('dlgConnection')
        (model, iter) = self.tselConnection.get_selected()
        copy_profile = model.get_value(iter, 0).profile
        self.dlgBuilder.get_object('eIPorName').set_text(copy_profile.ip)
        self.dlgBuilder.get_object('eName').set_text(copy_profile.name)
        if len(copy_profile.group) > 0:
            # TODO: set group correctly via model
            self.dlgBuilder.get_object('eGroup').set_text(copy_profile.group)
        self.dlgBuilder.get_object('eUsername').set_text(copy_profile.username)
        self.dlgBuilder.get_object('ePassword').set_text(copy_profile.password)
        self.dlgBuilder.get_object('eDomain').set_text(copy_profile.domain)
        if len(copy_profile.share) > 0:
            self.dlgBuilder.get_object('fcbShare').set_uri('file://%s' %
                (copy_profile.share,))
        self.dlgConnection.show_all()
        self.active_profile = None
        self.dlgConnection.run()
        logger.debug('<')

    def on_tbUpdate_clicked(self, button):
        logger.debug('>')
        self.dlgBuilder = Gtk.Builder()
        self.dlgBuilder.add_objects_from_file('rdpclient.glade',
                ['dlgConnection', 'tsConnectionGroups', 'awRDPClient'])
        self.dlgBuilder.connect_signals(self)
        self.dlgConnection = self.dlgBuilder.get_object('dlgConnection')
        (model, iter) = self.tselConnection.get_selected()
        edit_profile = model.get_value(iter, 0).profile
        self.dlgBuilder.get_object('eIPorName').set_text(edit_profile.ip)
        self.dlgBuilder.get_object('eName').set_text(edit_profile.name)
        if len(edit_profile.group) > 0:
            # TODO: set group correctly via model
            self.dlgBuilder.get_object('eGroup').set_text(edit_profile.group)
        self.dlgBuilder.get_object('eUsername').set_text(edit_profile.username)
        self.dlgBuilder.get_object('ePassword').set_text(edit_profile.password)
        self.dlgBuilder.get_object('eDomain').set_text(edit_profile.domain)
        if len(edit_profile.share) > 0:
            self.dlgBuilder.get_object('fcbShare').set_uri('file://%s' %
                (edit_profile.share,))
        self.dlgConnection.show_all()
        self.active_profile = edit_profile
        self.dlgConnection.run()
        logger.debug('<')

    def on_tbDelete_clicked(self, button):
        logger.debug('>')
        (model, iter) = self.tselConnection.get_selected()
        model.get_value(iter, 0).remove()
        self.tsConnections.remove(iter)
        logger.debug('<')

    def on_tbConnect_clicked(self, button):
        logger.debug('>')
        logger.debug('{button: %s}', button)
        (model, iter) = self.tselConnection.get_selected()
        connection = model.get_value(iter, 0)
        logger.debug(connection)
        #if button is not None:
            #status_context = self.sStatus.get_context_id('rdesktop')
            #self.sStatus.push(status_context,
            #        'Connecting to %s...' % (connection.profile.ip,))
        connection.connect()
        self.refresh_connection_status(connection)
        #self.sStatus.pop(status_context)
        GLib.timeout_add_seconds(1, self.check_connection, connection)
        logger.debug('<')

    def on_tbDisconnect_clicked(self, button):
        logger.debug('>')
        (model, iter) = self.tselConnection.get_selected()
        model.get_value(iter, 0).disconnect()
        logger.debug('<')

    def on_tbPreferences_clicked(self, button):
        logger.debug('>')
        # TODO: implement
        logger.debug('<')

    def on_btnSave_clicked(self, button):
        logger.debug('>')
        self.dlgConnection.hide()
        if self.active_profile is None:
            profile = RDPProfile()
        else:
            profile = self.active_profile
        profile.ip = self.dlgBuilder.get_object('eIPorName').get_text()
        profile.name = self.dlgBuilder.get_object('eName').get_text()
        group_list = self.dlgBuilder.get_object('cbGroup')
        # TODO: optimize assigning of group
        if group_list.get_active_id() is None:
            profile.group = ''
        else:
            profile.group = group_list.get_model().get_value(
                    group_list.get_active_iter(), 0)
        profile.username = self.dlgBuilder.get_object('eUsername').get_text()
        profile.password = self.dlgBuilder.get_object('ePassword').get_text()
        profile.domain = self.dlgBuilder.get_object('eDomain').get_text()
        uri = self.dlgBuilder.get_object('fcbShare').get_uri()
        profile.share = urlparse(uri).path if uri is not None else ''
        if self.active_profile is None:
            connection = RDPConnection(profile)
            connection.iter = self.tsConnections.append(None, [connection,
                connection.profile.get_title()])
        profile.save()
        self.dlgConnection.destroy()
        logger.debug('<')

    def on_tselConnection_changed(self, selection):
        logger.debug('>')
        (model, iter) = self.tselConnection.get_selected()
        selected = iter is not None
        connected = selected and model.get_value(iter, 0).is_connected()
        logger.debug('selected: %s, connected: %s' % (selected, connected))
        self.builder.get_object('tbCopy').set_sensitive(selected)
        self.builder.get_object('tbUpdate').set_sensitive(selected)
        self.builder.get_object('tbDelete').set_sensitive(selected)
        self.builder.get_object('tbConnect').set_sensitive(selected and
                not connected)
        self.builder.get_object('tbDisconnect').set_sensitive(selected and
                connected)
        logger.debug('<')

    def on_eIPorName_changed(self, widget):
        logger.debug('>')
        self.dlgBuilder.get_object('btnSave').set_sensitive(
                len(widget.get_text()) > 0)
        logger.debug('<')

    def on_eGroupName_changed(self, widget):
        logger.debug('>')
        self.dlgGroupBuilder.get_object('btnGroupSave').set_sensitive(
                len(widget.get_text()) > 0)
        logger.debug('<')

    def on_bAddGroup_clicked(self, button):
        logger.debug('>')
        self.dlgGroupBuilder = Gtk.Builder()
        self.dlgGroupBuilder.add_objects_from_file('rdpclient.glade',
                ['dlgGroup', 'tsConnectionGroups', 'dlgConnection'])
        self.dlgGroupBuilder.connect_signals(self)
        self.dlgGroup = self.dlgGroupBuilder.get_object('dlgGroup')
        self.dlgGroupBuilder.get_object('btnGroupSave').set_sensitive(False)
        self.active_profile = None
        self.dlgGroup.run()
        logger.debug('<')

    def on_btnGroupSave_clicked(self, button):
        logger.debug('>')
        self.dlgGroup.hide()
        # TODO: Save group
        self.dlgGroup.destroy()
        logger.debug('<')

    def on_btnGroupCancel_clicked(self, button):
        logger.debug('>')
        self.dlgGroup.hide()
        self.dlgGroup.destroy()
        logger.debug('<')

    def on_btnCancel_clicked(self, button):
        logger.debug('>')
        self.dlgConnection.hide()
        self.dlgConnection.destroy()
        logger.debug('<')

    def gtk_main_quit(self, *args):
        Gtk.main_quit()

logging.basicConfig(filename='rdpclient.log',
    format='%(asctime)s %(name)s %(funcName)s %(levelname)s %(message)s',
    level=logging.DEBUG)
logger = logging.getLogger('rdpclient')

try:
    os.makedirs('%s/.rdpclient' % (os.getenv('HOME'),))
    logger.debug('trying to create .rdpclient directory')
except OSError as exception:
    if exception.errno != os.errno.EEXIST:
        logger.debug('can not create .rdpclient directory')
        raise
    logger.debug('.rdpclient directory already exists')

app = RDPClient()
app.awRDPClient.show_all()

Gtk.main()
