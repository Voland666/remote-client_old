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
import os
import signal
import uuid
import time
import glob
import subprocess

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
#	10. Embed rdpdesktop in custom window
# DONE	11. Check existing connections on start
#	12. Group manager
#	13. Settings manager

class RDPProfile:
    _runtime_attrs = ['_runtimr_attrs', 'id', 'process_pid', 'wnck_window',
    'iter']

    def __init__(self, id=None):
        if id is None:
            self.id = str(uuid.uuid1(0, 0)).replace('-', '')[:16]
        else:
            self.id = id
            self.read()
        self.init_runtime_attrs()

    def init_runtime_attrs(self):
        for attr in self._runtime_attrs[2:]:
            setattr(self, attr, None)

    def get_title(self, escaped=False):
        slash = '\\' if escaped else ''
        if len(self.name) > 0:
            return '%s %s[%s%s]' % (self.name, slash, self.ip, slash)
        else:
            return '%s[%s%s]' % (slash, self.ip, slash)

    def read(self):
        parser = SafeConfigParser()
        parser.read('%s/.rdpclient/%s.rdpc' % (os.getenv('HOME'), self.id))
        for attr, value in parser.items('main'):
            setattr(self, attr, value)

    def save(self):
        parser = SafeConfigParser()
        parser.add_section('main')
        for attr, value in self.__dict__.iteritems():
            if attr not in self._runtime_attrs and value is not None:
                parser.set('main', attr, value)
        with open('%s/.rdpclient/%s.rdpc' % (os.getenv('HOME'), self.id,),
                'wb') as configfile:
            parser.write(configfile)

    def connect(self):
        if self.is_connected() and self.wnck_window is not None:
            self.wnck_window.activate(time.time())
        else:
            params = ['nohup', 'rdesktop', '-a', '16', '-N', '-g',
                    '1915x1040', '-r', 'clipboard:PRIMARYCLIPBOARD',
                    '-T', self.get_title()]
            if len(self.username) > 0:
                params.append('-u')
                params.append(self.username)
            if len(self.password) > 0:
                params.append('-p')
                params.append(self.password.decode(
                    'rot13').decode('base64'))
            if len(self.domain) > 0:
                params.append('-d')
                params.append(self.domain)
            if len(self.share) > 0:
                params.append('-r')
                params.append('disk:andreev=%s' % (self.share,))
            params.append(self.ip)
            self.process_pid = subprocess.Popen(params).pid

    def disconnect(self):
        if self.is_connected():
            os.kill(self.process_pid, signal.SIGTERM)
            self.process_pid = None
            self.wnck_window = None

    def is_connected(self):
        if self.process_pid is not None:
            try:
                pid, sts = os.waitpid(self.process_pid, os.WNOHANG)
                #return pid != self.process_pid
            except OSError:#, err:
                #return err.errno == os.errno.ECHILD
                # TODO: implement correct
                pass
            return os.path.exists('/proc/%s' % (self.process_pid,))
        return False


class RDPClient:

    def __init__(self):
        self.builder = Gtk.Builder()
        self.builder.add_from_file('rdpclient.glade')
        self.builder.connect_signals(self)
        self.load_objects()
        self.screen = Wnck.Screen.get_default()

        self.tsConnections = Gtk.TreeStore(GObject.TYPE_PYOBJECT,
                GdkPixbuf.Pixbuf, GdkPixbuf.Pixbuf, str)
        ids = [splitext(basename(rdpc))[0] for rdpc in
                glob.glob('%s/.rdpclient/*.rdpc' % (os.getenv('HOME'),))]
        self.win_ico = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                'icons/windows.svg', 16, 16, True)
        self.con_ico = Gtk.IconTheme.get_default().load_icon(
                'gtk-connect', 16, 0)
        self.discon_ico = Gtk.IconTheme.get_default().load_icon(
                'gtk-disconnect', 16, 0)
        self.refresh_window_list()
        for id in ids:
            profile = RDPProfile(id)
            title = profile.get_title()
            logo_ico = self.discon_ico
            if self.windows.has_key(title):
                profile.wnck_window = self.windows[title]
                profile.process_pid = int(subprocess.Popen(['pgrep', '-f',
                    profile.get_title(True)],
                    stdout=subprocess.PIPE).stdout.read())
                logo_ico = self.con_ico
            profile.iter = self.tsConnections.append(None, [profile, logo_ico,
                self.win_ico, title])
            if logo_ico == self.con_ico:
                GLib.timeout_add_seconds(1, self.check_process, profile)
        self.tvConnections.set_model(self.tsConnections)
        render_state = Gtk.CellRendererPixbuf()
        render_logo = Gtk.CellRendererPixbuf()
        render_text = Gtk.CellRendererText()
        self.tvcConnections.pack_start(render_state, expand=False)
        self.tvcConnections.pack_start(render_logo, expand=False)
        self.tvcConnections.pack_start(render_text, expand=True)
        self.tvcConnections.add_attribute(render_state, 'pixbuf', 1)
        self.tvcConnections.add_attribute(render_logo, 'pixbuf', 2)
        self.tvcConnections.set_cell_data_func(render_text,
                self.conn_cell_data_func)
        self.tvcConnections.clicked()

    def load_objects(self):
        for obj in ['awRDPClient', 'sStatus', 'tvConnections',
                'tvcConnections', 'tselConnection']:
            setattr(self, obj, self.builder.get_object(obj))

    def refresh_window_list(self):
        while Gtk.events_pending():
            Gtk.main_iteration()
        self.windows = {win.get_name(): win for win in
                self.screen.get_windows()}

    def check_process(self, profile):
        return profile.is_connected() or \
                self.refresh_connection_status(profile) or False

    def conn_cell_data_func(self, column, cell, model, iter, col_key):
        profile = model.get_value(iter, 0)
        cell.set_property('text', profile.get_title())

    def refresh_connection_status(self, profile):
        if profile.is_connected():
            self.builder.get_object('tbConnect').set_sensitive(False)
            self.builder.get_object('tbDisconnect').set_sensitive(True)
            self.tsConnections.set_value(profile.iter, 1, self.con_ico)
        else:
            self.builder.get_object('tbConnect').set_sensitive(True)
            self.builder.get_object('tbDisconnect').set_sensitive(False)
            self.tsConnections.set_value(profile.iter, 1, self.discon_ico)

    def on_tvConnections_double_click(self, widget, event):
        if (event.button == 1 and
            event.type == Gdk.EventType.DOUBLE_BUTTON_PRESS):
                self.on_tbConnect_clicked(False)

    def on_tbAdd_clicked(self, button):
        self.dlgBuilder = Gtk.Builder()
        self.dlgBuilder.add_objects_from_file('rdpclient.glade',
                ['dlgConnection', 'tsConnectionGroups', 'tsConnections',
                    'awRDPClient'])
        self.dlgBuilder.connect_signals(self)
        self.dlgConnection = self.dlgBuilder.get_object('dlgConnection')
        self.dlgBuilder.get_object('btnSave').set_sensitive(False)
        self.active_profile = None
        self.dlgConnection.run()

    def on_tbCopy_clicked(self, button):
        self.dlgBuilder = Gtk.Builder()
        self.dlgBuilder.add_objects_from_file('rdpclient.glade',
                ['dlgConnection', 'tsConnectionGroups', 'awRDPClient'])
        self.dlgBuilder.connect_signals(self)
        self.dlgConnection = self.dlgBuilder.get_object('dlgConnection')
        (model, iter) = self.tselConnection.get_selected()
        copy_profile = model.get_value(iter, 0)
        self.dlgBuilder.get_object('eIPorName').set_text(copy_profile.ip)
        self.dlgBuilder.get_object('eName').set_text(copy_profile.name)
        if len(copy_profile.group) > 0:
            # TODO: set group correctly via model
            self.dlgBuilder.get_object('eGroup').set_text(copy_profile.group)
        self.dlgBuilder.get_object('eUsername').set_text(copy_profile.username)
        self.dlgBuilder.get_object('ePassword').set_text(
                copy_profile.password.decode('rot13').decode('base64'))
        self.dlgBuilder.get_object('eDomain').set_text(copy_profile.domain)
        if len(copy_profile.share) > 0:
            self.dlgBuilder.get_object('fcbShare').set_uri('file://%s' %
                (copy_profile.share,))
        self.dlgConnection.show_all()
        self.active_profile = None
        self.dlgConnection.run()

    def on_tbUpdate_clicked(self, button):
        self.dlgBuilder = Gtk.Builder()
        self.dlgBuilder.add_objects_from_file('rdpclient.glade',
                ['dlgConnection', 'tsConnectionGroups', 'awRDPClient'])
        self.dlgBuilder.connect_signals(self)
        self.dlgConnection = self.dlgBuilder.get_object('dlgConnection')
        (model, iter) = self.tselConnection.get_selected()
        edit_profile = model.get_value(iter, 0)
        self.dlgBuilder.get_object('eIPorName').set_text(edit_profile.ip)
        self.dlgBuilder.get_object('eName').set_text(edit_profile.name)
        if len(edit_profile.group) > 0:
            # TODO: set group correctly via model
            self.dlgBuilder.get_object('eGroup').set_text(edit_profile.group)
        self.dlgBuilder.get_object('eUsername').set_text(edit_profile.username)
        self.dlgBuilder.get_object('ePassword').set_text(
                edit_profile.password.decode('rot13').decode('base64'))
        self.dlgBuilder.get_object('eDomain').set_text(edit_profile.domain)
        if len(edit_profile.share) > 0:
            self.dlgBuilder.get_object('fcbShare').set_uri('file://%s' %
                (edit_profile.share,))
        self.dlgConnection.show_all()
        self.active_profile = edit_profile
        self.dlgConnection.run()

    def on_tbDelete_clicked(self, button):
        (model, iter) = self.tselConnection.get_selected()
        os.remove('%s/.rdpclient/%s.rdpc' % (os.getenv('HOME'),
            model.get_value(iter, 0).id))
        self.tsConnections.remove(iter)

    def on_tbConnect_clicked(self, button):
        (model, iter) = self.tselConnection.get_selected()
        profile = model.get_value(iter, 0)
        if profile.wnck_window is None:
            self.refresh_window_list()
            title = profile.get_title()
            if self.windows.has_key(title):
                profile.wnck_window = self.windows[title]
        if button is not None:
            status_context = self.sStatus.get_context_id('rdesktop')
            self.sStatus.push(status_context,
                    'Connecting to %s...' % (profile.ip,))
            profile.connect()
        self.refresh_connection_status(profile)
        self.sStatus.pop(status_context)
        GLib.timeout_add_seconds(1, self.check_process, profile)

    def on_tbDisconnect_clicked(self, button):
        (model, iter) = self.tselConnection.get_selected()
        profile = model.get_value(iter, 0)
        profile.disconnect()

    def on_tbPreferences_clicked(self, button):
        # TODO: implement
        pass

    def on_btnSave_clicked(self, button):
        self.dlgConnection.hide()
        if self.active_profile is None:
            profile = RDPProfile()
        else:
            profile = self.active_profile
        profile.ip = self.dlgBuilder.get_object('eIPorName').get_text()
        profile.name = self.dlgBuilder.get_object('eName').get_text()
        group_list = self.dlgBuilder.get_object('cbGroup')
        if group_list.get_active_id() is None:
            profile.group = ''
        else:
            profile.group = group_list.get_model().get_value(
                    group_list.get_active_iter(), 0)
        profile.username = \
                self.dlgBuilder.get_object('eUsername').get_text()
        profile.password = \
                self.dlgBuilder.get_object('ePassword').get_text().encode(
                        'base64').encode('rot13')
        profile.domain = self.dlgBuilder.get_object('eDomain').get_text()
        share_folder = self.dlgBuilder.get_object('fcbShare').get_uri()
        if share_folder is None:
            profile.share = ''
        else:
            profile.share = urlparse(share_folder).path
        if self.active_profile is None:
            profile.iter = self.tsConnections.append(None, [profile,
                self.discon_ico, self.win_ico, profile.get_title()])
        profile.save()
        self.dlgConnection.destroy()

    def on_tselConnection_changed(self, selection):
        self.builder.get_object('tbCopy').set_sensitive(True)
        self.builder.get_object('tbUpdate').set_sensitive(True)
        self.builder.get_object('tbDelete').set_sensitive(True)
        (model, iter) = self.tselConnection.get_selected()
        if iter is not None:
            profile = model.get_value(iter, 0)
            self.refresh_connection_status(profile)

    def on_eIPorName_changed(self, widget):
        self.dlgBuilder.get_object('btnSave').set_sensitive(len(widget.get_text()) > 0)

    def on_eGroupName_changed(self, widget):
        self.dlgGroupBuilder.get_object('btnGroupSave').set_sensitive(len(widget.get_text()) > 0)

    def on_bAddGroup_clicked(self, button):
        self.dlgGroupBuilder = Gtk.Builder()
        self.dlgGroupBuilder.add_objects_from_file('rdpclient.glade',
                ['dlgGroup', 'tsConnectionGroups', 'dlgConnection'])
        self.dlgGroupBuilder.connect_signals(self)
        self.dlgGroup = self.dlgGroupBuilder.get_object('dlgGroup')
        self.dlgGroupBuilder.get_object('btnGroupSave').set_sensitive(False)
        self.active_profile = None
        self.dlgGroup.run()

    def on_btnGroupSave_clicked(self, button):
        self.dlgGroup.hide()
        # TODO: Save group
        self.dlgGroup.destroy()

    def on_btnGroupCancel_clicked(self, button):
        self.dlgGroup.hide()
        self.dlgGroup.destroy()

    def on_btnCancel_clicked(self, button):
        self.dlgConnection.hide()
        self.dlgConnection.destroy()

    def gtk_main_quit(self, *args):
        Gtk.main_quit()


try:
    os.makedirs('%s/.rdpclient' % (os.getenv('HOME'),))
except OSError as exception:
    if exception.errno != os.errno.EEXIST:
        raise

app = RDPClient()
app.awRDPClient.show_all()

Gtk.main()
