#!/usr/bin/python
# -*- coding: utf-8 -*-

import os
import sys
import time
import glob
import signal
import logging
sys.path.append(os.path.dirname(os.path.realpath(__file__)))
from abc import ABCMeta
from urlparse import urlparse
from baseObject import BaseObject
from subprocess import Popen, PIPE
from os.path import basename, splitext
from rcProfile import RCProfileAbstract, RCProfileRDP
from gi.repository import Gtk, Gdk, GObject, GdkPixbuf, GLib, Wnck

# TODO: 0. Refactoring of code
# DONE	1. Save .conf files into other directory
# DONE	2. Sort by column
# DONE	3. Buttons for Open/Close connection
# DONE	4. Button for "Copy to New" connection
# DONE	5. Groups for connections
#	6. Settings "Close all connections on exit"
#	7. Desctiption field in profile
# DONE	8. Scroll connection list
#	9. Preferences window (dir for .conf files, ...)
# SKIP	10. Embed rdesktop in custom window (?)
# DONE	11. Check existing connections on start
#	12. Group manager
#	13. Settings manager
# DONE	14. Secure save password
#	15. tbAdd button for Profile and Folder in one
#	16. Drag&Drop connections and folders
#	17. Folder size instead logo pixbuf
#	18. Confirmation dialog on delete connection
#	19. Save state for folders (opened/closed) and connections (on/off)
#	20. Support ssh connections

class RCTreeNode(BaseObject):
    """
    Define common behavior for connections and groups
    """
    __metaclass__ = ABCMeta


class RCGroup(RCTreeNode):
    """
    RCGroup is a hierarchical caterory for RCProfileRDP
    """

    def __init__(self, name, parent=None):
        if name is None:
            raise ValueError('RCGroup name can not be None')
        self.name, self.iter = name, None
        self.parent = parent
        self.full_name = self.__get_full_name()

    def __str__(self):
        return '%s: {full_name: %s}' % (self.__class__, self.full_name)

    def __get_full_name(self):
        return '%s%s' % ('%s|' % (self.parent.full_name,) if self.parent
                is not None else '', self.name)


class RCConnection(RCTreeNode):
    """
    RCConnection is a remote session manager
    """

    def __init__(self, profile=None):
        self.profile = RCProfileRDP() if profile is None else profile
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
                self.find_window()
            if self.window is None:
                raise ValueError(
                        'Window not found for connection %s' % (self,))
            else:
                self.window.activate(time.time())
        else:
            self.pid = Popen(self.profile.get_command()).pid
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
            return os.path.exists(os.path.join('/proc', str(self.pid)))
        return False

    def remove(self):
        self.profile.remove()
        self.profile = None
        self.iter = None


class RemoteClient:
    """
    RemoteClient is a manager of RCConnections
    """

    def __init__(self):
        self.builder = Gtk.Builder()
        self.builder.add_from_file(
                os.path.join(cur_dir, 'remote-client.glade'))
        self.builder.connect_signals(self)
        self.__load_objects(self, self.builder, ['awRemoteClient', 'sStatus',
            'tvConnections', 'tvcConnections', 'tselConnection', 'tbAdd',
            'tbCopy', 'tbUpdate', 'tbDelete', 'tbConnect', 'tbDisconnect'])
        self.win_ico = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                '%s/icons/windows.svg' % (cur_dir,), 16, 16, True)
        self.con_ico = Gtk.IconTheme.get_default().load_icon(
                'gtk-connect', 16, 0)
        self.discon_ico = Gtk.IconTheme.get_default().load_icon(
                'gtk-disconnect', 16, 0)
        self.dir_ico = Gtk.IconTheme.get_default().load_icon(
                'folder', 16, 0)
        self.opendir_ico = Gtk.IconTheme.get_default().load_icon(
                'document-open', 16, 0)
        self.required_sign = ' <span foreground="red">*</span>'
        ids = [splitext(basename(conf))[0] for conf in
                glob.glob(os.path.join(RCProfileAbstract.CONFIG_FILE_DIR,
                    '*.conf'))]
        self.tsConnections = Gtk.TreeStore(GObject.TYPE_PYOBJECT, str)
        self.tsConnectionGroups = self.tsConnections.filter_new()
        self.tsConnectionGroups.set_visible_func(self.groups_filter_func)
        for id in ids:
            profile = RCProfileRDP(id)
            connection = RCConnection(profile)
            logger.debug('profile group: %s' % (profile.group,))
            connection.group = self.get_group_by_full_name(profile.group)
            is_window_found = connection.find_window()
            logger.debug('connection %s; window: %s' % (connection,
                connection.window))
            if is_window_found:
                connection.pid = int(Popen(['pgrep', '-f',
                    profile.escape_chars('[]', profile.get_title())],
                    stdout=PIPE).communicate()[0])
                logger.debug('found pid: %d' % (connection.pid,))
            logger.debug('connection group: %s' % (connection.group,))
            connection.iter = self.tsConnections.append(connection.group.iter
                    if connection.group is not None else None,
                    [connection, profile.get_title()])
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

    def __load_objects(self, owner, builder, objects):
        logger.debug('>')
        for obj in objects:
            setattr(owner, obj, builder.get_object(obj))
        logger.debug('<')

    def groups_filter_func(self, model, iter, data):
        logger.debug('>')
        logger.debug('filter: %s' % (isinstance(model.get_value(iter, 0),
            RCGroup),))
        logger.debug('<')
        return isinstance(model.get_value(iter, 0), RCGroup)

    def match_column_value(self, row, column, value):
        logger.debug('>')
        logger.debug('match: %s' % (row[column] == value,))
        logger.debug('<')
        return row[column] == value

    def get_row_by_value(self, rows, func, column, value):
        logger.debug('>')
        if rows is None:
            logger.debug('<')
            return None
        for row in rows:
            if func(row, column, value):
                logger.debug('<')
                return row
            found = self.get_row_by_value(row.iterchildren(), func, column,
                    value)
            if found:
                logger.debug('<')
                return found
        logger.debug('<')
        return None

    def get_group_by_full_name(self, full_name):
        # TODO: use get_row_by_value
        logger.debug('>')
        if len(full_name) == 0:
            logger.debug('<')
            return None
        group_tree = full_name.split('|')
        group_level = 0
        max_group_level = len(group_tree)
        cur_group = None
        store = self.tsConnections
        cur_iter = store.get_iter_first()
        while group_level < max_group_level:
            if (cur_iter is not None and
                    group_tree[group_level] == store[cur_iter][1]):
                cur_group = store[cur_iter][0]
                group_level += 1
                if store.iter_has_child(cur_iter):
                    cur_iter = store.iter_children(cur_iter)
                else:
                    while group_level < max_group_level:
                        cur_group = RCGroup(
                                group_tree[group_level], cur_group)
                        cur_group.iter = store.append(cur_group.parent.iter,
                                [cur_group, cur_group.name])
                        group_level += 1
                    logger.debug('return group: %s' % (cur_group,))
                    logger.debug('<')
                    return cur_group
            else:
                cur_iter = store.iter_next(cur_iter) if cur_iter is not None \
                        else None
                if cur_iter is None:
                    while group_level < max_group_level:
                        cur_group = RCGroup(
                                group_tree[group_level], cur_group)
                        cur_group.iter = store.append(cur_group.parent.iter if
                                cur_group.parent is not None else None,
                                [cur_group, cur_group.name])
                        group_level += 1
                    logger.debug('return group: %s' % (cur_group,))
                    logger.debug('<')
                    return cur_group
        logger.debug('return group: %s' % (cur_group,))
        logger.debug('<')
        return cur_group

    def check_connection(self, connection):
        return (connection.is_connected() or
                self.refresh_connection_status(connection) or False)

    def conn_cell_state_func(self, column, cell, model, iter, data):
        logger.debug('>')
        node = model.get_value(iter, 0)
        if isinstance(node, RCGroup):
            if self.tvConnections.row_expanded(model.get_path(iter)):
                cell.set_property('pixbuf', self.opendir_ico)
            else:
                cell.set_property('pixbuf', self.dir_ico)
        else:
            cell.set_property('pixbuf', self.con_ico
                if model.get_value(iter, 0).is_connected() \
                        else self.discon_ico)
        logger.debug('<')

    def conn_cell_logo_func(self, column, cell, model, iter, data):
        logger.debug('>')
        node = model.get_value(iter, 0)
        if isinstance(node, RCGroup):
            # TODO: draw node size
            cell.set_property('pixbuf', None)
        else:
            cell.set_property('pixbuf', self.win_ico)
        logger.debug('<')

    def conn_cell_title_func(self, column, cell, model, iter, data):
        logger.debug('>')
        node = model.get_value(iter, 0)
        if isinstance(node, RCGroup):
            cell.set_property('text', node.name)
        else:
            cell.set_property('text', node.profile.get_title())
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
            (model, iter) = self.tselConnection.get_selected()
            node = model.get_value(iter, 0)
            if isinstance(node, RCGroup):
                if widget.row_expanded(model.get_path(iter)):
                    widget.collapse_row(model.get_path(iter))
                else:
                    widget.expand_row(model.get_path(iter), False)
            else:
                self.on_tbConnect_clicked(False)
        logger.debug('<')

    def load_connection_dialog(self, connection, is_copy=False):
        logger.debug('>')
        self.dlgBuilder = Gtk.Builder()
        self.dlgBuilder.add_objects_from_file(
                os.path.join(cur_dir, 'remote-client.glade'),
                ['dlgConnection', 'tsConnections', 'awRemoteClient'])
        self.dlgBuilder.connect_signals(self)
        self.dlgConnection = self.dlgBuilder.get_object('dlgConnection')
        dialog = self.dlgConnection
        self.__load_objects(dialog, self.dlgBuilder, ['eIPorName',
            'eName', 'chbHasGroup', 'cbGroup', 'lGroup', 'eGroup', 'eDomain',
            'eUsername', 'ePassword', 'lShare', 'chbHasShare', 'fcbShare',
            'btnSave', 'bAddGroup'])
        dialog.cbGroup.set_model(self.tsConnectionGroups)
        dialog.connection = None if is_copy else connection
        if connection is not None:
            dialog.eIPorName.set_text(connection.profile.ip)
            dialog.eName.set_text(connection.profile.name)
            dialog.chbHasGroup.set_active(len(connection.profile.group) > 0)
            if dialog.chbHasGroup.get_active():
                logger.debug('group: %s' % (connection.profile.group,))
                dialog.cbGroup.set_active_iter(
                        self.tsConnectionGroups.convert_child_iter_to_iter(
                            self.get_group_by_full_name(
                                connection.profile.group).iter)[1])
            dialog.eUsername.set_text(connection.profile.username)
            dialog.ePassword.set_text(connection.profile.password)
            dialog.eDomain.set_text(connection.profile.domain)
            dialog.chbHasShare.set_active(len(connection.profile.share) > 0)
            if dialog.chbHasShare.get_active():
                dialog.fcbShare.set_uri('file://%s' %
                    (connection.profile.share,))
        dialog.show_all()
        self.check_save_connection()
        dialog.run()
        logger.debug('<')

    def on_tbAdd_clicked(self, button):
        logger.debug('>')
        self.load_connection_dialog(None)
        logger.debug('<')

    def on_tbCopy_clicked(self, button):
        logger.debug('>')
        (model, iter) = self.tselConnection.get_selected()
        self.load_connection_dialog(model.get_value(iter, 0), True)
        logger.debug('<')

    def on_tbUpdate_clicked(self, button):
        logger.debug('>')
        (model, iter) = self.tselConnection.get_selected()
        self.load_connection_dialog(model.get_value(iter, 0))
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
        dlg = self.dlgConnection
        dlg.hide()
        profile = dlg.connection.profile if dlg.connection is not None \
                else RCProfileRDP()
        profile.ip = dlg.eIPorName.get_text()
        profile.name = dlg.eName.get_text()
        group_iter = self.tsConnectionGroups.convert_iter_to_child_iter(
                dlg.cbGroup.get_active_iter()) \
                        if dlg.chbHasGroup.get_active() else None
        profile.group = self.tsConnections.get_value(group_iter, 0).full_name \
                if group_iter is not None else ''
        profile.username = dlg.eUsername.get_text()
        profile.password = dlg.ePassword.get_text()
        profile.domain = dlg.eDomain.get_text()
        profile.share = urlparse(dlg.fcbShare.get_uri()).path \
                if dlg.chbHasShare.get_active() else ''
        connection = dlg.connection or RCConnection(profile)
        connection.group = self.get_group_by_full_name(profile.group)
        if dlg.connection is not None:
            self.tsConnections.remove(dlg.connection.iter)
        connection.iter = self.tsConnections.append(group_iter,
                [connection, profile.get_title()])
        profile.save()
        dlg.destroy()
        logger.debug('<')

    def on_tselConnection_changed(self, selection):
        logger.debug('>')
        (model, iter) = self.tselConnection.get_selected()
        is_folder = isinstance(model.get_value(iter, 0), RCGroup) \
                if iter is not None else False
        selected = iter is not None and not is_folder
        connected = selected and model.get_value(iter, 0).is_connected()
        logger.debug('selected: %s, connected: %s' % (selected, connected))
        self.tbAdd.set_sensitive(not is_folder)
        self.tbCopy.set_sensitive(selected)
        self.tbUpdate.set_sensitive(selected)
        self.tbDelete.set_sensitive(selected)
        self.tbConnect.set_sensitive(selected and not connected)
        self.tbDisconnect.set_sensitive(selected and connected)
        logger.debug('<')

    def on_chbHasGroup_toggled(self, button):
        logger.debug('>')
        selected = button.get_active()
        logger.debug('selected: %s' % (selected,))
        self.dlgConnection.lGroup.set_markup('Группа%s' %
                (self.required_sign if selected else '',))
        self.dlgConnection.cbGroup.set_sensitive(selected)
        self.dlgConnection.bAddGroup.set_sensitive(selected)
        self.check_save_connection()
        logger.debug('<')

    def on_combobox_entry_button_press_event(self, entry, event):
        logger.debug('>')
        combo = entry.get_parent()
        logger.debug('parent: %s' % (combo,))
        if combo.props.popup_shown:
            logger.debug('do popdown')
            combo.emit('popdown')
        else:
            logger.debug('do popup')
            combo.emit('popup')
        logger.debug('<')

    def on_cbGroup_changed(self, button):
        logger.debug('>')
        logger.debug('new value: %s' % (button.get_active_id(),))
        self.check_save_connection()
        logger.debug('<')

    def on_chbHasShare_toggled(self, button):
        logger.debug('>')
        selected = button.get_active()
        logger.debug('selected: %s' % (selected,))
        self.dlgConnection.lShare.set_markup('Общая папка%s' %
                (self.required_sign if selected else '',))
        self.dlgConnection.fcbShare.set_sensitive(selected)
        self.check_save_connection()
        logger.debug('<')

    def on_fcbShare_file_set(self, button):
        logger.debug('>')
        self.check_save_connection()
        logger.debug('<')

    def on_eIPorName_changed(self, entry):
        logger.debug('>')
        self.dlgBuilder.get_object('btnSave').set_sensitive(
                len(entry.get_text()) > 0)
        self.check_save_connection()
        logger.debug('<')

    def check_save_connection(self):
        logger.debug('>')
        group_valid = (not self.dlgConnection.chbHasGroup.get_active() or
                self.dlgConnection.cbGroup.get_active_iter() is not None)
        share_valid = (not self.dlgConnection.chbHasShare.get_active() or
                self.dlgConnection.fcbShare.get_uri() is not None)
        logger.debug('len_eIPorName: %s, group_valid: %s, share_valid: %s'
                % (len(self.dlgConnection.eIPorName.get_text()),
                    group_valid, share_valid))
        self.dlgConnection.btnSave.set_sensitive(
                len(self.dlgConnection.eIPorName.get_text()) > 0 and
                group_valid and share_valid)
        logger.debug('<')

    def load_group_dialog(self, group):
        logger.debug('>')
        self.dlgGroupBuilder = Gtk.Builder()
        self.dlgGroupBuilder.add_objects_from_file(
                os.path.join(cur_dir, 'remote-client.glade'),
                ['awRemoteClient', 'dlgGroup', 'dlgConnection'])
        self.dlgGroupBuilder.connect_signals(self)
        self.dlgGroup = self.dlgGroupBuilder.get_object('dlgGroup')
        dialog = self.dlgGroup
        self.__load_objects(dialog, self.dlgGroupBuilder,
        ['btnGroupSave', 'lParentGroup', 'chbHasParentGroup', 'cbParentGroup',
            'eGroupName'])
        dialog.cbParentGroup.set_model(self.tsConnectionGroups)
        dialog.group = group
        self.check_save_group()
        dialog.run()
        logger.debug('<')

    def on_bAddGroup_clicked(self, button):
        logger.debug('>')
        self.load_group_dialog(None)
        logger.debug('<')

    def on_btnGroupSave_clicked(self, button):
        logger.debug('>')
        self.dlgGroup.hide()
        has_parent = self.dlgGroup.chbHasParentGroup.get_active()
        parent_iter = self.tsConnectionGroups.convert_iter_to_child_iter(
                self.dlgGroup.cbParentGroup.get_active_iter()) \
                        if has_parent else None
        parent = None if parent_iter is None else \
                self.tsConnections.get_value(parent_iter, 0)
        logger.debug('parent: %s' % (parent,))
        group = RCGroup(self.dlgGroup.eGroupName.get_text(), parent)
        if self.get_group_by_full_name(group.full_name) is None:
            group.iter = self.tsConnections.append(parent_iter,
                    [group, group.name])
        self.dlgGroup.destroy()
        logger.debug('<')

    def on_btnGroupCancel_clicked(self, button):
        logger.debug('>')
        self.dlgGroup.hide()
        self.dlgGroup.destroy()
        logger.debug('<')

    def on_eGroupName_changed(self, entry):
        logger.debug('>')
        self.check_save_group()
        logger.debug('<')

    def on_cbParentGroup_changed(self, button):
        logger.debug('>')
        self.check_save_group()
        logger.debug('<')

    def on_chbHasParentGroup_toggled(self, button):
        logger.debug('>')
        selected = button.get_active()
        self.dlgGroup.lParentGroup.set_markup('Родительская группа%s' %
                (self.required_sign if selected else '',))
        self.dlgGroup.cbParentGroup.set_sensitive(selected)
        self.check_save_group()
        logger.debug('<')

    def check_save_group(self):
        logger.debug('>')
        parent_group_valid = (not self.dlgGroup.chbHasParentGroup.get_active()
                or self.dlgGroup.cbParentGroup.get_active_iter() is not None)
        self.dlgGroup.btnGroupSave.set_sensitive(
                len(self.dlgGroup.eGroupName.get_text()) > 0 and
                parent_group_valid)
        logger.debug('<')

    def on_btnCancel_clicked(self, button):
        logger.debug('>')
        self.dlgConnection.hide()
        self.dlgConnection.destroy()
        logger.debug('<')

    def gtk_main_quit(self, *args):
        Gtk.main_quit()

cur_dir = os.path.dirname(os.path.realpath(__file__))
logging.basicConfig(
        filename=os.path.join(cur_dir, 'remote-client.log'),
        format='%(asctime)s %(name)s %(funcName)s %(levelname)s %(message)s',
        level=logging.DEBUG)
logger = logging.getLogger('remote-client')

try:
    os.makedirs(RCProfileAbstract.CONFIG_FILE_DIR)
    logger.debug('trying to create .remote-client directory')
except OSError as exception:
    if exception.errno != os.errno.EEXIST:
        logger.debug('can not create .remote-client directory')
        raise
    logger.debug('.remote-client directory already exists')

app = RemoteClient()
app.awRemoteClient.show_all()

Gtk.main()
