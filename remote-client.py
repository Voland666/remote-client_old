#!/usr/bin/python
# -*- coding: utf-8 -*-

import os
import sys
import time
import glob
import signal
import logging
sys.path.append(os.path.dirname(os.path.realpath(__file__)))
from abc import ABCMeta, abstractmethod, abstractproperty
from urlparse import urlparse
from baseObject import BaseObject
from subprocess import Popen, PIPE
from os.path import basename, splitext
from rcProfile import RCProfile, RCProfileRDP
from gi.repository import Gtk, Gdk, GObject, GdkPixbuf, GLib, Wnck

# TODO: 0. Refactoring of code
# DONE	1. Save .conf files into other directory
# DONE	2. Sort by column
# DONE	3. Buttons for Open/Close connection
# DONE	4. Button for "Copy to New" connection
# DONE	5. Groups for connections
# TODO	6. Settings "Close all connections on exit"
# TODO	7. Desctiption field in profile
# DONE	8. Scroll connection list
# TODO	9. Preferences window (dir for .conf files, ...)
# SKIP	10. Embed rdesktop in custom window (?)
# DONE	11. Check existing connections on start
# TODO	12. Group manager
# TODO	13. Settings manager
# DONE	14. Secure save password
# DONE	15. tbAdd button for Profile and Folder in one
# TODO	16. Drag&Drop connections and folders
# TODO	17. Folder size instead logo pixbuf
# TODO	18. Confirmation dialog on delete connection
# TODO	19. Save state for folders (opened/closed) and connections (on/off)
# TODO	20. Support ssh connections


class RCTreeNode(BaseObject):
    """
    Define common behavior for connections and groups
    """
    __metaclass__ = ABCMeta

    def __init__(self, tree):
        if not isinstance(tree, Gtk.TreeView):
            raise TypeError(
                'RCTreeNode tree is not an instance of Gtk.TreeView')
        self.tree = tree
        self.model = tree.get_model()

    def add_to_model(self):
        self.iter = self.model.append(
            self.parent.iter if self.parent is not None else None,
            [self, self.title])

    def remove_from_model(self):
        self.model.remove(self.iter)
        self.iter = None

    @abstractmethod
    def open(self):
        pass

    @abstractmethod
    def close(self):
        pass

    @abstractmethod
    def edit(self):
        pass

    @abstractmethod
    def delete(self):
        pass

    @abstractmethod
    def move(self, parent):
        pass

    @abstractproperty
    def title(self):
        return ''

    @abstractproperty
    def is_opened(self):
        return False

    @property
    def parent(self):
        return self.get('_parent')

    @parent.setter
    def parent(self, value):
        self._parent = value

    @property
    def icon(self):
        return self.get('_icon')

    @property
    def icon_opened(self):
        return self.get('_icon_opened')

    @property
    def icon_closed(self):
        return self.get('_icon_closed')


class RCGroup(RCTreeNode):
    """
    RCGroup is a hierarchical caterory for RCProfileRDP
    """

    def __init__(self, tree, name, parent=None):
        super(RCGroup, self).__init__(tree)
        self.name, self.parent = name, parent
        if name is None:
            raise ValueError('RCGroup name can not be None')
        self.full_name = self._get_full_name()
        self._icon_opened = Gtk.IconTheme.get_default().load_icon(
            'document-open', 16, 0)
        self._icon_closed = Gtk.IconTheme.get_default().load_icon(
            'folder', 16, 0)
        self.add_to_model()

    def __str__(self):
        return '{}: {{full_name: {}}}'.format(self.__class__, self.full_name)

    def _get_full_name(self):
        return '{}{}'.format(
            '{}|'.format(self.parent.full_name)
            if self.parent is not None else '', self.name)

    def open(self):
        self.expand_row(self.model.get_path(self.iter), False)

    def close(self):
        self.tree.collapse_row(self.model.get_path(self.iter))

    def edit(self):
        pass

    def delete(self):
        pass

    def move(self):
        pass

    @property
    def title(self):
        return self.name

    @property
    def is_opened(self):
        return self.tree.row_expanded(self.model.get_path(self.iter))


class RCConnection(RCTreeNode):
    """
    RCConnection is a remote session manager
    """

    def __init__(self, tree, profile=None):
        super(RCConnection, self).__init__(tree)
        # TODO: set RCProfile class and use proper instance copy
        self.profile = RCProfileRDP() if profile is None else profile
        self.parent = self.get_group()
        self.window = self.get_window()
        self.pid = self.get_pid() if self.window is not None else None
        self._icon = GdkPixbuf.Pixbuf.new_from_file_at_scale(
            '%s/icons/windows.svg' % (cur_dir,), 16, 16, True)
        self._icon_opened = Gtk.IconTheme.get_default().load_icon(
            'gtk-connect', 16, 0)
        self._icon_closed = Gtk.IconTheme.get_default().load_icon(
            'gtk-disconnect', 16, 0)
        self.add_to_model()
        if self.is_opened:
            self.watch()

    def __str__(self):
        return '{}: {{profile: {}}}'.format(self.__class__, self.profile)

    def match_column_value(self, row, column, value):
        logger.debug('>')
        logger.debug('match: %s', row[column] == value)
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
            found = self.get_row_by_value(
                row.iterchildren(), func, column, value)
            if found:
                logger.debug('<')
                return found
        logger.debug('<')
        return None

    def get_group(self):
        logger.debug('>')
        if len(self.profile.group) == 0:
            logger.debug('<')
            return None
        groups = self.profile.group.split('|')
        group_tree = self.model
        group = None
        for group_name in groups:
            logger.debug('group_name: {}'.format(group_name))
            row = self.get_row_by_value(
                group_tree, self.match_column_value, 1, group_name)
            if row is None:
                logger.debug('creating group {}...'.format(group_name))
                RCGroup(self.tree, group_name, group)
                group_tree = self.model[group.iter].iterchildren() \
                    if group is not None else group_tree
                row = self.get_row_by_value(
                    group_tree, self.match_column_value, 1, group_name)
                if row is None:
                    raise ValueError(
                        "Can not find group '{}'".format(group_name))
            group_tree = row.iterchildren()
            group = row[0]
            logger.debug('new group: {}'.format(group))
        logger.debug('return group: {}'.format(group))
        logger.debug('<')
        return group

    def open(self):
        logger.debug('is_opened: %s', self.is_opened)
        if self.is_opened:
            logger.debug('window: %s', self.window)
            if self.window is None:
                self.window = self.get_window()
            if self.window is None:
                raise ValueError(
                    'Window not found for connection {}'.format(self))
            else:
                self.window.activate(time.time())
        else:
            self.pid = Popen(self.profile.get_command()).pid
            self.window = self.get_window()
            self.watch()

    def close(self):
        if self.is_opened:
            os.kill(self.pid, signal.SIGTERM)
        self.pid = None
        self.window = None

    def edit(self):
        self.remove_from_model()
        self.parent = self.get_group()
        self.add_to_model()

    def delete(self):
        self.profile.remove()
        self.profile = None
        self.remove_from_model()

    def move(self):
        pass

    @property
    def title(self):
        return self.profile.get_title()

    @property
    def is_opened(self):
        if self.pid is not None:
            try:
                pid, sts = os.waitpid(self.pid, os.WNOHANG)
            except OSError:
                pass
            return os.path.exists(os.path.join(os.sep, 'proc', str(self.pid)))
        return False

    def get_pid(self):
        return int(Popen(['pgrep', '-f', self.escape_chars('[]', self.title)],
                         stdout=PIPE).communicate()[0])

    def check_connection(self):
        return self.is_opened or self.refresh_status() or False

    def refresh_status(self):
        logger.debug('>')
        self.tree.queue_draw()
        self.tree.get_selection().emit('changed')
        if not self.is_opened:
            self.close()
        logger.debug('<')

    def watch(self):
        self.refresh_status()
        GLib.timeout_add_seconds(1, self.check_connection)

    def get_window(self):
        title = self.profile.get_title() if self.profile is not None else '[]'
        logger.debug('title: %s', title)
        if len(title) > 2:
            while Gtk.events_pending():
                Gtk.main_iteration()
            window = [win for win in Wnck.Screen.get_default().get_windows()
                      if win.get_name() == title]
            logger.debug('window: %s', window)
            if len(window) == 1:
                return window[0]
        return None


class RemoteClient:
    """
    RemoteClient is a manager of RCConnections
    """

    def __init__(self):
        self.builder = Gtk.Builder()
        self.builder.add_from_file(
            os.path.join(cur_dir, 'remote-client.glade'))
        self.builder.connect_signals(self)
        self._load_objects(self, self.builder, [
            'awRemoteClient', 'sStatus', 'tvConnections', 'tvcConnections',
            'tselConnection', 'tbMenuAdd', 'tbCopy', 'tbUpdate', 'tbDelete',
            'tbConnect', 'tbDisconnect', 'mAdd'])
        self.required_sign = ' <span foreground="red">*</span>'
        self.tbMenuAdd.set_menu(self.mAdd)
        ids = [splitext(basename(conf))[0] for conf in glob.glob(
            os.path.join(RCProfile.CONFIG_FILE_DIR, '*.conf'))]
        self.tsConnections = Gtk.TreeStore(GObject.TYPE_PYOBJECT, str)
        self.tsConnectionGroups = self.tsConnections.filter_new()
        self.tsConnectionGroups.set_visible_func(self.groups_filter_func)
        self.tvConnections.set_model(self.tsConnections)
        for id in ids:
            RCConnection(self.tvConnections, RCProfileRDP(id))
        render_state = Gtk.CellRendererPixbuf()
        render_logo = Gtk.CellRendererPixbuf()
        render_text = Gtk.CellRendererText()
        self.tvcConnections.pack_start(render_state, expand=False)
        self.tvcConnections.pack_start(render_logo, expand=False)
        self.tvcConnections.pack_start(render_text, expand=True)
        self.tvcConnections.set_cell_data_func(
            render_state, self.conn_cell_state_func)
        self.tvcConnections.set_cell_data_func(
            render_logo, self.conn_cell_logo_func)
        self.tvcConnections.set_cell_data_func(
            render_text, self.conn_cell_title_func)
        self.tvcConnections.clicked()

    def _load_objects(self, owner, builder, objects):
        logger.debug('>')
        for obj in objects:
            setattr(owner, obj, builder.get_object(obj))
        logger.debug('<')

    def groups_filter_func(self, model, iter, data):
        logger.debug('>')
        logger.debug(
            'filter: %s', isinstance(model.get_value(iter, 0), RCGroup))
        logger.debug('<')
        return isinstance(model.get_value(iter, 0), RCGroup)

    def conn_cell_state_func(self, column, cell, model, iter, data):
        logger.debug('>')
        node = model.get_value(iter, 0)
        cell.set_property(
            'pixbuf', node.icon_opened if node.is_opened else node.icon_closed)
        logger.debug('<')

    def conn_cell_logo_func(self, column, cell, model, iter, data):
        logger.debug('>')
        cell.set_property('pixbuf', model.get_value(iter, 0).icon)
        logger.debug('<')

    def conn_cell_title_func(self, column, cell, model, iter, data):
        logger.debug('>')
        cell.set_property('text', model.get_value(iter, 0).title)
        logger.debug('<')

    def on_tvConnections_double_click(self, widget, event):
        logger.debug('>')
        if (event.button == 1 and
                event.type == Gdk.EventType.DOUBLE_BUTTON_PRESS):
            (model, iter) = self.tselConnection.get_selected()
            node = model.get_value(iter, 0)
            if isinstance(node, RCGroup) and node.is_opened:
                node.close()
            else:
                node.open()
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
        self._load_objects(dialog, self.dlgBuilder, [
            'eIPorName', 'eName', 'chbHasGroup', 'cbGroup', 'lGroup', 'eGroup',
            'eDomain', 'eUsername', 'ePassword', 'lShare', 'chbHasShare',
            'fcbShare', 'btnSave', 'bAddGroup'])
        dialog.cbGroup.set_model(self.tsConnectionGroups)
        dialog.connection = None if is_copy else connection
        if connection is not None:
            dialog.eIPorName.set_text(connection.profile.ip)
            dialog.eName.set_text(connection.profile.name)
            dialog.chbHasGroup.set_active(len(connection.profile.group) > 0)
            if dialog.chbHasGroup.get_active():
                logger.debug('group: %s', connection.profile.group)
                dialog.cbGroup.set_active_iter(
                    self.tsConnectionGroups.convert_child_iter_to_iter(
                        connection.parent.iter)[1])
            dialog.eUsername.set_text(connection.profile.username)
            dialog.ePassword.set_text(connection.profile.password)
            dialog.eDomain.set_text(connection.profile.domain)
            dialog.chbHasShare.set_active(len(connection.profile.share) > 0)
            if dialog.chbHasShare.get_active():
                dialog.fcbShare.set_uri(
                    'file://{}'.format(connection.profile.share))
        dialog.show_all()
        self.check_save_connection()
        dialog.run()
        logger.debug('<')

    def on_tbMenuAdd_clicked(self, button):
        self.sStatus.push(self.sStatus.get_context_id('menu'), 'Menu clicked')

    def on_miAddConnection_activate(self, menuitem):
        logger.debug('>')
        self.load_connection_dialog(None)
        logger.debug('<')

    def on_miAddGroup_activate(self, menuitem):
        logger.debug('>')
        self.load_group_dialog(None)
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
        model.get_value(iter, 0).delete()
        logger.debug('<')

    def on_tbConnect_clicked(self, button):
        logger.debug('>')
        (model, iter) = self.tselConnection.get_selected()
        # if button is not None:
        #    status_context = self.sStatus.get_context_id('rdesktop')
        #    self.sStatus.push(status_context,
        #        'Connecting to %s...' % (connection.profile.ip,))
        model.get_value(iter, 0).open()
        # self.sStatus.pop(status_context)
        logger.debug('<')

    def on_tbDisconnect_clicked(self, button):
        logger.debug('>')
        (model, iter) = self.tselConnection.get_selected()
        model.get_value(iter, 0).close()
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
        if dlg.connection is not None:
            dlg.connection.edit()
        else:
            RCConnection(self.tvConnections, profile)
        profile.save()
        dlg.destroy()
        logger.debug('<')

    def on_tselConnection_changed(self, selection):
        logger.debug('>')
        (model, iter) = self.tselConnection.get_selected()
        is_folder = isinstance(model.get_value(iter, 0), RCGroup) \
            if iter is not None else False
        selected = iter is not None and not is_folder
        connected = selected and model.get_value(iter, 0).is_opened
        logger.debug('selected: %s, connected: %s', selected, connected)
        # self.tbMenuAdd.set_sensitive(not is_folder)
        self.tbCopy.set_sensitive(selected)
        self.tbUpdate.set_sensitive(selected)
        self.tbDelete.set_sensitive(selected)
        self.tbConnect.set_sensitive(selected and not connected)
        self.tbDisconnect.set_sensitive(selected and connected)
        logger.debug('<')

    def on_chbHasGroup_toggled(self, button):
        logger.debug('>')
        selected = button.get_active()
        logger.debug('selected: %s', selected)
        self.dlgConnection.lGroup.set_markup(
            'Группа{}'.format(self.required_sign if selected else ''))
        self.dlgConnection.cbGroup.set_sensitive(selected)
        self.dlgConnection.bAddGroup.set_sensitive(selected)
        self.check_save_connection()
        logger.debug('<')

    def on_combobox_entry_button_press_event(self, entry, event):
        logger.debug('>')
        combo = entry.get_parent()
        logger.debug('parent: %s', combo)
        if combo.props.popup_shown:
            logger.debug('do popdown')
            combo.emit('popdown')
        else:
            logger.debug('do popup')
            combo.emit('popup')
        logger.debug('<')

    def on_cbGroup_changed(self, button):
        logger.debug('>')
        logger.debug('new value: %s', button.get_active_id())
        self.check_save_connection()
        logger.debug('<')

    def on_chbHasShare_toggled(self, button):
        logger.debug('>')
        selected = button.get_active()
        logger.debug('selected: %s', selected)
        self.dlgConnection.lShare.set_markup(
            'Общая папка{}'.format(self.required_sign if selected else ''))
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
        group_valid = not self.dlgConnection.chbHasGroup.get_active() or \
            self.dlgConnection.cbGroup.get_active_iter() is not None
        share_valid = not self.dlgConnection.chbHasShare.get_active() or \
            self.dlgConnection.fcbShare.get_uri() is not None
        logger.debug('len_eIPorName: %s, group_valid: %s, share_valid: %s',
                     len(self.dlgConnection.eIPorName.get_text()),
                     group_valid, share_valid)
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
        self._load_objects(
            dialog, self.dlgGroupBuilder, [
                'btnGroupSave', 'lParentGroup', 'chbHasParentGroup',
                'cbParentGroup', 'eGroupName'])
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
        logger.debug('parent: %s', parent)
        RCGroup(
            self.tvConnections, self.dlgGroup.eGroupName.get_text(), parent)
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
        self.dlgGroup.lParentGroup.set_markup(
            'Родительская группа{}'.format(
                self.required_sign if selected else ''))
        self.dlgGroup.cbParentGroup.set_sensitive(selected)
        self.check_save_group()
        logger.debug('<')

    def check_save_group(self):
        logger.debug('>')
        parent_group_valid = not self.dlgGroup.chbHasParentGroup.get_active() \
            or self.dlgGroup.cbParentGroup.get_active_iter() is not None
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
    level=logging.INFO)
logger = logging.getLogger('remote-client')

try:
    os.makedirs(RCProfile.CONFIG_FILE_DIR)
    logger.debug('trying to create .remote-client directory')
except OSError as exception:
    if exception.errno != os.errno.EEXIST:
        logger.debug('can not create .remote-client directory')
        raise
    logger.debug('.remote-client directory already exists')

app = RemoteClient()
app.awRemoteClient.show_all()

Gtk.main()
