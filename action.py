#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=4:sw=4:sta:et:sts=4:ai
from __future__ import (division, absolute_import, print_function)

__license__   = 'GPL v3'
__copyright__ = '2014, Derek Broughton <auspex@pointerstop.ca>'
__docformat__ = 'restructuredtext en'

import ConfigParser
import os, threading, time, shutil
from datetime import datetime, timedelta
from contextlib import closing
from collections import OrderedDict
from calibre.devices.prst1.driver import DBPATH 
try:
    from PyQt5.Qt import QUrl, pyqtSignal, QTimer
#     from PyQt5.Qt import (Qt, QApplication, QMenu, QToolButton, QStandardItemModel, QStandardItem, QUrl, QModelIndex, QFileDialog)
    from PyQt5.Qt import (QMenu, QUrl, QModelIndex, QFileDialog)
except ImportError:
    from PyQt4.Qt import QUrl, pyqtSignal, QTimer
    from PyQt4.Qt import (QMenu, QUrl, QModelIndex, QFileDialog)

from calibre import strftime
from calibre.gui2 import error_dialog, info_dialog, open_url, question_dialog, FileDialog
from calibre.gui2.actions import InterfaceAction
from calibre.ptempfile import remove_dir
from calibre.gui2.dialogs.message_box import ViewLog
from calibre.gui2.library.views import DeviceBooksView
from calibre.utils.icu import sort_key
from calibre.utils.config import config_dir
from calibre.ebooks.metadata.book.base import Metadata
from calibre.gui2.device import device_signals

from calibre.devices.prst1.driver import PRST1
from calibre.devices.usbms.books import Book
# from calibre.devices.usbms.books import CollectionsBookList
from calibre.devices.usbms.driver import USBMS

from calibre_plugins.sonyutilities.dialogs import (
                    ReaderOptionsDialog, CoverUploadOptionsDialog, RemoveCoverOptionsDialog, AboutDialog, 
                    UpdateMetadataOptionsDialog, ChangeReadingStatusOptionsDialog, ShowBooksNotInDeviceDatabaseDialog, 
                    ManageSeriesDeviceDialog, BookmarkOptionsDialog, QueueProgressDialog, CleanImagesDirOptionsDialog, BlockAnalyticsOptionsDialog,
                    FixDuplicateShelvesDialog, OrderSeriesShelvesDialog, ShowReadingPositionChangesDialog
                    )
from calibre_plugins.sonyutilities.common_utils import (set_plugin_icon_resources, get_icon, ProgressBar,
                                         create_menu_action_unique,  debug_print)
from calibre_plugins.sonyutilities.book import SeriesBook
import calibre_plugins.sonyutilities.config as cfg

PLUGIN_ICONS = ['images/icon.png', 'images/logo_sony.png', 'images/manage_series.png', 'images/lock.png', 'images/lock32.png',
                'images/lock_delete.png', 'images/lock_open.png', 'images/sort.png',
                'images/ms_ff.png']

MIMETYPE_SONY = 'application/epub+zip'

BOOKMARK_SEPARATOR = '|@ @|'       # Spaces are included to allow wrapping in the details panel

EPUB_FETCH_QUERY = """
    SELECT cp.mark,
           np.percent,
           books.reading_time,
           np.client_create_date
    FROM books
    LEFT OUTER JOIN current_position cp ON cp.content_id=books._id
    LEFT OUTER JOIN network_position np ON np.content_id=books._id
    where books._id = ?
    """
SET_FRONT_PAGE_QUERY = """
select min(reading_time) from (select _id, reading_time from books order by 2 desc limit 4);
"""
# TODO: remove this when done
KOBO_QUERY = 'SELECT c1.bookmark, ' \
                        'c2.adobe_location, '      \
                        'c1.ReadStatus, '          \
                        'c1.___PercentRead, '      \
                        'c1.Attribution, '         \
                        'c1.DateLastRead, '        \
                        'c1.Title, '               \
                        'c1.MimeType, '            \
                        'NULL as rating, '         \
                        'c1.contentId '            \
                    'FROM content c1 LEFT OUTER JOIN content c2 ON c1.bookmark = c2.ContentID ' \
                    'WHERE c1.ContentID = ?'

#TODO: convert Sony bookmark to Calibre bookmark
# SONY format:     PATH#point(/1/4/227/1:0)
# calibre format:  calibre_current_page_bookmark*|!|?|*IDX*|!|?|*/2/4/227/1:0
# apparently: find the opf file in the epub,
#             enumerate the <item> tags and find the index of the one with the 
#             href equal to the PATH component of the Sony bookmark
#             extract the arg from point() and add 1 to first value 
#             - something makes me think this might actually be N*2, not N+1

try:
    debug_print("SonyUtilites::action.py - loading translations")
    load_translations()
except NameError:
    debug_print("SonyUtilites::action.py - exception when loading translations")
    pass # load_translations() added in calibre 1.9


# Implementation of QtQHash for strings. This doesn't seem to be in the Python implemention. 
def qhash (inputstr):
    instr = ""
    if isinstance (inputstr, str):
        instr = inputstr 
    elif isinstance (inputstr, unicode):
        instr = inputstr.encode ("utf8")
    else:
        return -1

    h = 0x00000000
    for i in range (0, len (instr)):
        h = (h << 4) + ord(instr[i])
        h ^= (h & 0xf0000000) >> 23
        h &= 0x0fffffff

    return h


class sonyutilitiesAction(InterfaceAction):

    name = 'sonyutilities'
    # Create our top-level menu/toolbar action (text, icon_path, tooltip, keyboard shortcut)
    action_spec = ( "sonyutilities", None, _("Utilities to use with Sony ereaders"), ())
    action_type = 'current'

    timestamp_string = None

    plugin_device_connection_changed = pyqtSignal(object);
    plugin_device_metadata_available = pyqtSignal();

    def genesis(self):
        base = self.interface_action_base_plugin
        self.version = base.name+" v%d.%d.%d"%base.version

        self.menu = QMenu(self.gui)
        icon_resources = self.load_resources(PLUGIN_ICONS)
        set_plugin_icon_resources(self.name, icon_resources)
        self.old_actions_unique_map = {}
        self.device_actions_map     = {}
        self.library_actions_map    = {}
        
        # Assign our menu to this action and an icon
        self.qaction.setMenu(self.menu)
        self.qaction.setIcon(get_icon(PLUGIN_ICONS[0]))
        self.qaction.triggered.connect(self.toolbar_button_clicked)
        self.menu.aboutToShow.connect(self.about_to_show_menu)
        self.menus_lock = threading.RLock()

    def initialization_complete(self):
        # otherwise configured hot keys won't work until the menu's
        # been displayed once.
        self.rebuild_menus()
        # Subscribe to device connection events
        device_signals.device_connection_changed.connect(self._on_device_connection_changed)
        device_signals.device_metadata_available.connect(self._on_device_metadata_available)

    def about_to_show_menu(self):
        self.rebuild_menus()


    def haveSony(self):
        return self.device is not None and isinstance(self.device, PRST1)


    def library_changed(self, db):
        # We need to reset our menus after switching libraries
        self.device   = self.get_device()

        if self.haveSony() and cfg.get_plugin_pref(cfg.COMMON_OPTIONS_STORE_NAME, cfg.KEY_STORE_ON_CONNECT):
            debug_print('SonyUtilites:library_changed - About to do auto store')
            self.rebuild_menus()
            QTimer.singleShot(1000, self.auto_store_current_bookmark)


    def do_work(self):
        self.auto_store_current_bookmark()


    def _on_device_connection_changed(self, is_connected):
        debug_print("sonyutilities:_on_device_connection_changed - self.plugin_device_connection_changed.__class__: ", self.plugin_device_connection_changed.__class__)
        debug_print("Methods for self.plugin_device_connection_changed: ", dir(self.plugin_device_connection_changed))
        self.plugin_device_connection_changed.emit(is_connected)
        if not is_connected:
            debug_print('SonyUtilites:_on_device_connection_changed - Device disconnected')
            self.connected_device_info = None
            self.rebuild_menus()


    def _on_device_metadata_available(self):
        self.plugin_device_metadata_available.emit()
        self.connected_device_info = self.gui.device_manager.get_current_device_information().get('info', None)
        location_info = self.connected_device_info[4]
        debug_print('sonyutilities:_on_device_metadata_available - Metadata available:', location_info)
        self.device   = self.get_device()
        
        for self.current_location in location_info.values():
            if self.haveSony() and cfg.get_plugin_pref(cfg.BACKUP_OPTIONS_STORE_NAME, cfg.KEY_DO_DAILY_BACKUP):
                debug_print('SonyUtilites:_on_device_metadata_available - About to start auto backup')
                self.auto_backup_device_database()

        if self.haveSony() and cfg.get_plugin_pref(cfg.COMMON_OPTIONS_STORE_NAME, cfg.KEY_STORE_ON_CONNECT):
            debug_print('SonyUtilites:_on_device_metadata_available - About to start auto store')
            self.auto_store_current_bookmark()

        self.rebuild_menus()


    def rebuild_menus(self):
        with self.menus_lock:
            # Show the config dialog
            # The config dialog can also be shown from within
            # Preferences->Plugins, which is why the do_user_config
            # method is defined on the base plugin class
            do_user_config = self.interface_action_base_plugin.do_user_config
            self.menu.clear()
            self.actions_unique_map = {}

            self.device   = self.get_device()
            haveSony      = self.haveSony()
#             debug_print("rebuild_menus - self.supports_ratings=%s" % self.supports_ratings)

            if haveSony:
                self.set_reader_fonts_action = self.create_menu_item_ex(self.menu,  _("&Set Reader Font for Selected Books"), 
                                                              unique_name='Set Reader Font for Selected Books',
                                                              shortcut_name= _("Set Reader Font for Selected Books"),
                                                              triggered=self.set_reader_fonts,
                                                              enabled=haveSony, 
                                                              is_library_action=True, 
                                                              is_device_action=True)
                self.library_actions_map['Set Reader Font for Selected Books'] = self.set_reader_fonts_action
                self.device_actions_map['Set Reader Font for Selected Books']  = self.set_reader_fonts_action
    
                self.remove_reader_fonts_action = self.create_menu_item_ex(self.menu,  _("&Remove Reader Font for Selected Books"), 
                                                              unique_name='Remove Reader Font for Selected Books',
                                                              shortcut_name= _("Remove Reader Font for Selected Books"),
                                                              triggered=self.remove_reader_fonts,
                                                              enabled=haveSony, 
                                                              is_library_action=True, 
                                                              is_device_action=True)
                self.library_actions_map['Remove Reader Font for Selected Books'] = self.remove_reader_fonts_action
                self.device_actions_map['Remove Reader Font for Selected Books']  = self.remove_reader_fonts_action
        
                self.menu.addSeparator()

            self.update_metadata_action = self.create_menu_item_ex(self.menu,  _("Update &metadata in device library"), 
                                                          unique_name='Update metadata in device library',
                                                          shortcut_name= _("Update metadata in device library"),
                                                          triggered=self.update_metadata,
                                                          enabled=not self.isDeviceView() and haveSony, 
                                                          is_library_action=True)

            self.change_reading_status_action = self.create_menu_item_ex(self.menu,  _("&Change Reading Status in device library"), 
                                                          unique_name='Change Reading Status in device library',
                                                          shortcut_name= _("Change Reading Status in device library"),
                                                          triggered=self.change_reading_status,
                                                          enabled=self.isDeviceView() and haveSony, 
                                                          is_device_action=True)

            if self.supports_series:
                self.manage_series_on_device_action = self.create_menu_item_ex(self.menu,  _("&Manage Series Information in device library"), 
                                                              unique_name='Manage Series Information in device library',
                                                              shortcut_name= _("Manage Series Information in device library"),
                                                              triggered=self.manage_series_on_device,
                                                              enabled=self.isDeviceView() and haveSony and self.supports_series, 
                                                              is_device_action=True)

            self.handle_bookmarks_action = self.create_menu_item_ex(self.menu,  _("&Store/Restore current bookmark"), 
                                                          unique_name='Store/Restore current bookmark',
                                                          shortcut_name= _("Store/Restore current bookmark"),
                                                          triggered=self.handle_bookmarks,
                                                          enabled=not self.isDeviceView() and haveSony, 
                                                          is_library_action=True)

#            self.store_current_bookmark_action = self.create_menu_item_ex(self.menu, '&Store current bookmark', 
#                                                          unique_name='Store current bookmark',
#                                                          shortcut_name='Store current bookmark',
#                                                          triggered=self.store_current_bookmark)
#
#            self.restore_current_bookmark_action = self.create_menu_item_ex(self.menu, '&Restore current bookmark', 
#                                                          unique_name='Restore current bookmark',
#                                                          shortcut_name='Restore current bookmark',
#                                                          triggered=self.restore_current_bookmark)

            self.menu.addSeparator()
            self.upload_covers_action = self.create_menu_item_ex(self.menu,  _("&Upload covers for Selected Books"), 
                                                          unique_name='Upload/covers for Selected Books',
                                                          shortcut_name= _("Upload covers for Selected Books"),
                                                          triggered=self.upload_covers,
                                                          enabled=not self.isDeviceView() and haveSony, 
                                                          is_library_action=True)
            if haveSony:
                self.remove_covers_action = self.create_menu_item_ex(self.menu,  _("&Remove covers for Selected Books"), 
                                                              unique_name='Remove covers for Selected Books',
                                                              shortcut_name= _("Remove covers for Selected Books"),
                                                              triggered=self.remove_covers,
                                                              enabled=haveSony, 
                                                              is_library_action=True, 
                                                              is_device_action=True)

            if haveSony:
                self.order_series_shelves_action = self.create_menu_item_ex(self.menu,  _("Order Series Shelves"),
                                                                unique_name='Order Series  Shelves',
                                                                shortcut_name= _("Order Series  Shelves"),
                                                                triggered=self.order_series_shelves,
                                                                enabled=haveSony ,
                                                                is_library_action=True,
                                                                is_device_action=True)
            self.menu.addSeparator()
            self.getAnnotationForSelected_action = self.create_menu_item_ex(self.menu,  _("Copy annotation for Selected Book"), image='bookmarks.png',
                                                            unique_name='Copy annotation for Selected Book',
                                                            shortcut_name= _("Copy annotation for Selected Book"),
                                                            triggered=self.getAnnotationForSelected,
                                                            enabled=not self.isDeviceView() and haveSony, 
                                                            is_library_action=True)
            self.menu.addSeparator()

            self.show_books_not_in_database_action = self.create_menu_item_ex(self.menu,  _("Show books not in the device database"),
                                                            unique_name='Show books not in the device database',
                                                            shortcut_name= _("Show books not in the device database"),
                                                            triggered=self.show_books_not_in_database,
                                                            enabled=self.isDeviceView() and haveSony, 
                                                            is_device_action=True)

            self.refresh_device_books_action = self.create_menu_item_ex(self.menu,  _("Refresh the list of books on the device"),
                                                            unique_name='Refresh the list of books on the device',
                                                            shortcut_name= _("Refresh the list of books on the device"),
                                                            triggered=self.refresh_device_books,
                                                            enabled=haveSony, 
                                                            is_library_action=True, 
                                                            is_device_action=True)
            self.databaseMenu = self.menu.addMenu(_("Database"))
            if haveSony:
                self.block_analytics_action = self.create_menu_item_ex(self.databaseMenu,  _("Block Analytics Events"),
                                                                unique_name='Block Analytics Events',
                                                                shortcut_name= _("Block Analytics Events"),
                                                                triggered=self.block_analytics,
                                                                enabled=haveSony,
                                                                is_library_action=True,
                                                                is_device_action=True)
                self.databaseMenu.addSeparator()
                self.fix_duplicate_shelves_action = self.create_menu_item_ex(self.databaseMenu,  _("Fix Duplicate Shelves"),
                                                                unique_name='Fix Duplicate Shelves',
                                                                shortcut_name= _("Fix Duplicate Shelves"),
                                                                triggered=self.fix_duplicate_shelves,
                                                                enabled=haveSony,
                                                                is_library_action=True,
                                                                is_device_action=True)
            self.check_device_database_action = self.create_menu_item_ex(self.databaseMenu,  _("Check the device database"),
                                                            unique_name='Check the device database',
                                                            shortcut_name= _("Check the device database"),
                                                            triggered=self.check_device_database,
                                                            enabled=haveSony, 
                                                            is_library_action=True, 
                                                            is_device_action=True)
            self.vacuum_device_database_action = self.create_menu_item_ex(self.databaseMenu,  _("Compress the device database"),
                                                            unique_name='Compress the device database',
                                                            shortcut_name= _("Compress the device database"),
                                                            triggered=self.vacuum_device_database,
                                                            enabled=haveSony, 
                                                            is_library_action=True, 
                                                            is_device_action=True)
            self.backup_device_database_action = self.create_menu_item_ex(self.databaseMenu,  _("Backup device database"),
                                                            unique_name='Backup device database',
                                                            shortcut_name= _("Backup device database"),
                                                            triggered=self.backup_device_database,
                                                            enabled=haveSony, 
                                                            is_library_action=True, 
                                                            is_device_action=True)

#            self.menu.addSeparator()
#            self.get_list_action = self.create_menu_item_ex(self.menu, 'Update TOC for Selected Book',
#                                                            unique_name='Update TOC for Selected Book',
#                                                            shortcut_name='Update TOC for Selected Book',
#                                                            triggered=self.updateTOCForSelected)


#             self.menu.addSeparator()
#             self.firmware_update_action = self.create_menu_item_ex(self.menu, _('Check for Sony Updates') + '...', shortcut=False,
#                                                                    unique_name='Check for Sony Updates',
#                                                                    shortcut_name=_('Check for Sony Updates'),
#                                                                    triggered=self.menu_firmware_update_check,
#                                                                    enabled=haveSony,
#                                                                    is_library_action=True,
#                                                                    is_device_action=True)

#            self.backup_device_database_action = self.create_menu_item_ex(self.menu, _('Do Auto Database Backup'), shortcut=False,
#                                                                   unique_name='Do Auto Database Backup',
#                                                                   shortcut_name=_('Do Auto Database Backup'),
#                                                                   triggered=self.menu_backup_device_database,
#                                                                   enabled=haveSony,
#                                                                   is_library_action=True,
#                                                                   is_device_action=True)

            self.menu.addSeparator()
#            self.config_action = create_menu_action_unique(self, self.menu, _('&Customize plugin')+'...', shortcut=False,
#                                                           image= 'config.png',
#                                                           triggered=self.show_configuration)
            self.config_action = self.create_menu_item_ex(self.menu, _('&Customize plugin')+'...', shortcut=False,
                                                            unique_name='Customize plugin',
                                                            shortcut_name= _("Customize plugin"),
                                                            image= 'config.png',
                                                            triggered=self.show_configuration,
                                                            enabled=True,  
                                                            is_library_action=True, 
                                                            is_device_action=True)
            
            self.about_action = create_menu_action_unique(self, self.menu,  _("&About Plugin"), shortcut=False,
                                                           image= 'images/icon.png',
                                                           unique_name='About sonyutilities',
                                                           shortcut_name= _("About sonyutilities"),
                                                           triggered=self.about)

            # Before we finalize, make sure we delete any actions for menus that are no longer displayed
            for menu_id, unique_name in self.old_actions_unique_map.iteritems():
                if menu_id not in self.actions_unique_map:
                    self.gui.keyboard.unregister_shortcut(unique_name)
            self.old_actions_unique_map = self.actions_unique_map
            self.gui.keyboard.finalize()            

    def about(self):
        # Get the about text from a file inside the plugin zip file
        # The get_resources function is a builtin function defined for all your
        # plugin code. It loads files from the plugin zip file. It returns
        # the bytes from the specified file.
        #
        # Note that if you are loading more than one file, for performance, you
        # should pass a list of names to get_resources. In this case,
        # get_resources will return a dictionary mapping names to bytes. Names that
        # are not found in the zip file will not be in the returned dictionary.
        
        self.about_text = get_resources('about.txt')
        AboutDialog(self.gui, self.qaction.icon(), self.version + self.about_text).exec_()
        
    def create_menu_item_ex(self, parent_menu, menu_text, image=None, tooltip=None,
                           shortcut=None, triggered=None, is_checked=None, shortcut_name=None,
                           unique_name=None, enabled=False, is_library_action=False, is_device_action=False):
        ac = create_menu_action_unique(self, parent_menu, menu_text, image, tooltip,
                                       shortcut, triggered, is_checked, shortcut_name, unique_name)
        self.actions_unique_map[ac.calibre_shortcut_unique_name] = ac.calibre_shortcut_unique_name
        ac.setEnabled(enabled)

        if is_library_action:
            self.library_actions_map[shortcut_name] = ac
        if is_device_action:
            self.device_actions_map[shortcut_name] = ac
        return ac

    def toolbar_button_clicked(self):
        self.rebuild_menus()

        if not self.haveSony():
            self.show_configuration()
        elif len(self.gui.current_view().selectionModel().selectedRows()) >= 0:
            self.device     = self.get_device()

            if self.isDeviceView():
                if self.supports_series:
                    button_action = cfg.get_plugin_pref(cfg.COMMON_OPTIONS_STORE_NAME, cfg.KEY_BUTTON_ACTION_DEVICE)
                    if button_action == '':
                        self.show_configuration()
                    else:
                        self.device_actions_map[button_action].trigger()
#                    self.manage_series_on_device()
#                    self.show_books_not_in_database()
#                    self.mark_not_interested()
                else:
                    self.change_reading_status()
            else:
                button_action = cfg.get_plugin_pref(cfg.COMMON_OPTIONS_STORE_NAME, cfg.KEY_BUTTON_ACTION_LIBRARY)
                if button_action == '':
                    debug_print("toolbar_button_clicked - no button action")
                    self.show_configuration()
                else:
                    try:
                        self.library_actions_map[button_action].trigger()
                    except:
                        debug_print("toolbar_button_clicked - exception running button action")
                        self.show_configuration()
#                self.library_actions_map.values()[0].trigger()
#                self.handle_bookmarks()
#                self.upload_covers()
#                self.update_metadata()
#                self.set_reader_fonts_action.trigger()
#                self.show_configuration()

    def isDeviceView(self):
        view = self.gui.current_view()
        return isinstance(view, DeviceBooksView)

    def _get_contentIDs_for_selected(self):
        view = self.gui.current_view()
        if self.isDeviceView():
            rows = view.selectionModel().selectedRows()
            books = [view.model().db[view.model().map[r.row()]] for r in rows]
            contentIDs = [book.contentID for book in books]
#            debug_print("_get_contentIDs_for_selected - book.ImageID=", book.ImageID)
        else:
            book_ids = view.get_selected_ids()
            contentIDs = self.get_contentIDs_for_books(book_ids)
            
        return contentIDs

    def show_configuration(self):
        self.interface_action_base_plugin.do_user_config(self.gui)

    def set_reader_fonts(self):
        if len(self.gui.current_view().selectionModel().selectedRows()) == 0:
            return
        self.device = self.get_device()
        if self.device is None:
            return error_dialog(self.gui,  _("Cannot set reader font settings."),
                                 _("No device connected."),
                                show=True)
        self.device_path = self.get_device_path()
        self.singleSelected = len(self.gui.current_view().selectionModel().selectedRows()) == 1

        contentIDs = self._get_contentIDs_for_selected()

        debug_print('set_reader_fonts - contentIDs', contentIDs)

        #print("update books:%s"%books)

        if len(contentIDs) == 0:
            return

        if len(contentIDs) == 1:
            self.single_contentID = contentIDs[0]

        dlg = ReaderOptionsDialog(self.gui, self)
        dlg.exec_()
        if dlg.result() != dlg.Accepted:
            return
        self.options = dlg.prefs

        if self.options[cfg.KEY_UPDATE_CONFIG_FILE]:
            self._update_config_reader_settings(self.options)

        updated_fonts, added_fonts, deleted_fonts, count_books = self._set_reader_fonts(contentIDs)
#        result_message =  _("Change summary:\n\tFont settings updated=%d\n\tFont settings added=%d\n\tTotal books=%d") % (updated_fonts, added_fonts, count_books)
        result_message =  _("Change summary:") + "\n\t" + _("Font settings updated={0}\n\tFont settings added={1}\n\tTotal books={2}").format(updated_fonts, added_fonts, count_books)
        info_dialog(self.gui,  _("Sony Utilities") + " - " + _("Device library updated"),
                    result_message,
                    show=True)


    def remove_reader_fonts(self):
        if len(self.gui.current_view().selectionModel().selectedRows()) == 0:
            return
        self.device = self.get_device()
        if self.device is None:
            return error_dialog(self.gui,  _("Cannot remove reader font settings"),
                     _("No device connected."),
                    show=True)
        self.device_path = self.get_device_path()

        contentIDs = self._get_contentIDs_for_selected()
        
        if len(contentIDs) == 0:
            return

        mb = question_dialog(self.gui,  _("Remove Reader settings"),  _("Do you want to remove the reader settings for the selected books?"), show_copy_button=False)
        if not mb:
            return

        
        updated_fonts, added_fonts, deleted_fonts, count_books = self._set_reader_fonts(contentIDs, delete=True)
        result_message = _("Change summary:") + "\n\t" + _("Font settings deleted={0}").format(deleted_fonts)
        info_dialog(self.gui,  _("Sony Utilities") + " - " + _("Device library updated"),
                    result_message,
                    show=True)

    def update_metadata(self):
        import pydevd;pydevd.settrace() #TODO: pydevd
        if len(self.gui.current_view().selectionModel().selectedRows()) == 0:
            return
        #debug_print("upload_covers - start")
        self.device = self.get_device()
        if self.device is None:
            return error_dialog(self.gui,  _("Cannot update metadata in device library."),
                     _("No device connected."),
                    show=True)
        self.device_path = self.get_device_path()

        selectedIDs = self._get_selected_ids()
        
        if len(selectedIDs) == 0:
            return
        debug_print("update_metadata - selectedIDs:", selectedIDs)
        books = self._convert_calibre_ids_to_books(self.gui.current_view().model().db, selectedIDs)
        for book in books:
            device_book_paths = self.get_device_paths_from_id(book.calibre_id)
            debug_print("update_metadata - device_book_paths:", device_book_paths)
            book.paths = device_book_paths
            book.contentIDs = [self.contentid_from_path(path) for path in device_book_paths]
            book.series_index_string = None
        
        dlg = UpdateMetadataOptionsDialog(self.gui, self)
        dlg.exec_()
        if dlg.result() != dlg.Accepted:
            return
        self.options = dlg.new_prefs

        updated_books, unchanged_books, not_on_device_books, count_books = self._update_metadata(books)
        result_message = _("Update summary:") + "\n\t" + _("Books updated={0}\n\tUnchanged books={1}\n\tBooks not on device={2}\n\tTotal books={3}").format(updated_books, unchanged_books, not_on_device_books, count_books)
        info_dialog(self.gui,  _("Sony Utilities") + " - " + _("Device library updated"),
                    result_message,
                    show=True)


    def handle_bookmarks(self):
        if len(self.gui.current_view().selectionModel().selectedRows()) == 0:
            return
        #debug_print("upload_covers - start")
        self.device = self.get_device()
        if self.device is None:
            return error_dialog(self.gui,  _("Cannot store or restore current reading position."),
                     _("No device connected."),
                    show=True)
        self.device_path = self.get_device_path()

        selectedIDs = self._get_selected_ids()
        
        if len(selectedIDs) == 0:
            return

        dlg = BookmarkOptionsDialog(self.gui, self)
        dlg.exec_()
        if dlg.result() != dlg.Accepted:
            return
        self.options = dlg.options

        if self.options['storeBookmarks']:
            self.store_current_bookmark()
        else:
            self.restore_current_bookmark()


    def auto_store_current_bookmark(self):
        debug_print("auto_store_current_bookmark - start")
        db = self.gui.current_db

        self.options = {}
        self.options[cfg.KEY_STORE_BOOKMARK]    = True
        self.options[cfg.KEY_READING_STATUS]    = False
        self.options[cfg.KEY_DATE_TO_NOW]       = False
        self.options[cfg.KEY_CLEAR_IF_UNREAD]   = False
        self.options[cfg.KEY_BACKGROUND_JOB]    = True
        self.options[cfg.KEY_PROMPT_TO_STORE]          = cfg.get_plugin_pref(cfg.COMMON_OPTIONS_STORE_NAME, cfg.KEY_PROMPT_TO_STORE)
        self.options[cfg.KEY_STORE_IF_MORE_RECENT]     = cfg.get_plugin_pref(cfg.COMMON_OPTIONS_STORE_NAME, cfg.KEY_STORE_IF_MORE_RECENT)
        self.options[cfg.KEY_DO_NOT_STORE_IF_REOPENED] = cfg.get_plugin_pref(cfg.COMMON_OPTIONS_STORE_NAME, cfg.KEY_DO_NOT_STORE_IF_REOPENED)

        self.options["device_database_path"] = self.device_database_path()
        self.options["job_function"]         = 'store_current_bookmark'
        self.options["supports_ratings"]     = False
        self.options['allOnDevice']          = True

        # it takes forever to figure out that this actually calls dialogs.do_books to get the book list...
        QueueProgressDialog(self.gui, [], None, self.options, self._store_queue_job, db, plugin_action=self)


    def backup_device_database(self):
        self.device = self.get_device()
        if self.device is None:
            return error_dialog(self.gui,  _("Cannot backup the device database."),
                                 _("No device connected."),
                                show=True)
        self.device_path = self.get_device_path()

        debug_print("backup_device_database")

        fd = FileDialog(parent=self.gui, name='Sony Utilities plugin:choose backup destination', 
                        title= _("Choose Backup Destination"),
                        filters=[( _("SQLite database"), ['sqlite'])], 
                        add_all_files_filter=False,
                        mode=QFileDialog.AnyFile
                        )
        if not fd.accepted:
            return
        backup_file = fd.get_files()[0]

        if not backup_file:
            return

        debug_print("backup_device_database - backup file selected=", backup_file)
        # TODO: This needs to be fixed to work for both DBs
        source_file = self.device_database_path()
        shutil.copyfile(source_file, backup_file)

    def auto_backup_device_database(self, from_menu=False):
        debug_print('auto_backup_device_database - start')
        
        self.device_path = self.get_device_path()

        dest_dir = cfg.get_plugin_pref(cfg.BACKUP_OPTIONS_STORE_NAME, cfg.KEY_BACKUP_DEST_DIRECTORY)
        debug_print('auto_backup_device_database - destination directory=', dest_dir)
        if not dest_dir or len(dest_dir) == 0:
            debug_print('auto_backup_device_database - destination directory not set, not doing backup')
            return
        
        # Backup file names will be devicename-location-uuid-timestamp
        backup_file_template = '{0}-{1}-{2}-{3}'
        backup_options = self.current_location
        debug_print('auto_backup_device_database - device_information=', backup_options)

        backup_options[cfg.KEY_BACKUP_DEST_DIRECTORY] = dest_dir
        backup_options[cfg.KEY_BACKUP_COPIES_TO_KEEP] = cfg.get_plugin_pref(cfg.BACKUP_OPTIONS_STORE_NAME, cfg.KEY_BACKUP_COPIES_TO_KEEP)
        backup_options['from_menu']                   = from_menu
        backup_options['backup_file_template']        = backup_file_template
        backup_options['database_file']               = self.device_database_path()
        debug_print('auto_backup_device_database - backup_options=', backup_options)

        self._device_database_backup(backup_options)
        debug_print('auto_backup_device_database - end')


    def store_current_bookmark(self):
        if len(self.gui.current_view().selectionModel().selectedRows()) == 0:
            return
        #debug_print("upload_covers - start")
        self.device = self.get_device()
        if self.device is None:
            return error_dialog(self.gui,  _("Cannot update metadata in device library."),
                     _("No device connected."),
                    show=True)
        self.device_path = self.get_device_path()

#         self.options["device_database_path"]       = self.device_database_path(location_info)
        self.options["job_function"]               = 'store_current_bookmark'
#         self.options["supports_ratings"]           = self.supports_ratings
        self.options['allOnDevice']                = False
        self.options[cfg.KEY_PROMPT_TO_STORE]      = True
        debug_print("store_current_bookmark - self.options:", self.options)

        if self.options[cfg.KEY_BACKGROUND_JOB]:
            QueueProgressDialog(self.gui, [], None, self.options, self._store_queue_job, self.gui.current_view().model().db, plugin_action=self)
        else:
            selectedIDs = self._get_selected_ids()
        
            if len(selectedIDs) == 0:
                return
            debug_print("store_current_bookmark - selectedIDs:", selectedIDs)
            books = self._convert_calibre_ids_to_books(self.gui.current_view().model().db, selectedIDs)
            for book in books:
                device_book_paths = self.get_device_paths_from_id(book.calibre_id)
    #            debug_print("store_current_bookmark - device_book_paths:", device_book_paths)
                book.paths = device_book_paths
                book.contentIDs = [self.contentid_from_path(path) for path in device_book_paths]

            books_with_bookmark, books_without_bookmark, count_books = self._store_current_bookmark(books)
            result_message = _("Update summary:") + "\n\t" + _("Bookmarks retrieved={0}\n\tBooks with no bookmarks={1}\n\tTotal books={2}").format(books_with_bookmark, books_without_bookmark, count_books)
            info_dialog(self.gui,  _("Sony Utilities") + " - " + _("Library updated"),
                        result_message,
                        show=True)

    def restore_current_bookmark(self):
        if len(self.gui.current_view().selectionModel().selectedRows()) == 0:
            return
        #debug_print("upload_covers - start")
        self.device = self.get_device()
        if self.device is None:
            return error_dialog(self.gui,  _("Cannot set bookmark in device library."),
                     _("No device connected."),
                    show=True)
        self.device_path = self.get_device_path()

        selectedIDs = self._get_selected_ids()
        
        if len(selectedIDs) == 0:
            return
        debug_print("restore_current_bookmark - selectedIDs:", selectedIDs)
        books = self._convert_calibre_ids_to_books(self.gui.current_view().model().db, selectedIDs)
        for book in books:
            device_book_paths = self.get_device_paths_from_id(book.calibre_id)
            debug_print("store_current_bookmark - device_book_paths:", device_book_paths)
            book.paths = device_book_paths
            book.contentIDs = [self.contentid_from_path(path) for path in device_book_paths]
        
        updated_books, not_on_device_books, count_books = self._restore_current_bookmark(books)
        result_message = _("Update summary:") + "\n\t" + _("Books updated={0}\n\tBooks not on device={1}\n\tTotal books={2}").format(updated_books, not_on_device_books, count_books)
        info_dialog(self.gui,  _("Sony Utilities") + " - " + _("Device library updated"),
                    result_message,
                    show=True)

    def refresh_device_books(self):
        self.gui.device_detected(True, PRST1)

    def change_reading_status(self):
        if len(self.gui.current_view().selectionModel().selectedRows()) == 0:
            return
        #debug_print("upload_covers - start")
        self.device = self.get_device()
        if self.device is None:
            return error_dialog(self.gui,  _("Cannot change reading status in device library."),
                     _("No device connected."),
                    show=True)
        self.device_path = self.get_device_path()

        books = self._get_books_for_selected()
        
        if len(books) == 0:
            return
        for book in books:
#            device_book_paths = self.get_device_paths_from_id(book.calibre_id)
            debug_print("change_reading_status - book:", book)
            book.contentIDs = [book.contentID]
        debug_print("change_reading_status - books:", books)

        dlg = ChangeReadingStatusOptionsDialog(self.gui, self)
        dlg.exec_()
        if dlg.result() != dlg.Accepted:
            return
        self.options = dlg.options
        self.options[cfg.KEY_USE_PLUGBOARD]        = False
        self.options[cfg.KEY_USE_TITLE_SORT]       = False
        self.options[cfg.KEY_USE_AUTHOR_SORT]      = False
        self.options[cfg.KEY_SET_TAGS_IN_SUBTITLE] = False

        updated_books, unchanged_books, not_on_device_books, count_books = self._update_metadata(books)
        result_message = _("Update summary:") + "\n\t" + _("Books updated={0}\n\tUnchanged books={1}\n\tBooks not on device={2}\n\tTotal books={3}").format(updated_books, unchanged_books, not_on_device_books, count_books)
        info_dialog(self.gui,  _("Sony Utilities") + " - " + _("Device library updated"),
                    result_message,
                    show=True)


    def mark_not_interested(self):
        if len(self.gui.current_view().selectionModel().selectedRows()) == 0:
            return
        #debug_print("upload_covers - start")
        self.device = self.get_device()
        if self.device is None:
            return error_dialog(self.gui,  _("Cannot change reading status in device library."),
                     _("No device connected."),
                    show=True)
        self.device_path = self.get_device_path()

        books = self._get_books_for_selected()
        
        if len(books) == 0:
            return
        recommendations = []
        for book in books:
#            device_book_paths = self.get_device_paths_from_id(book.calibre_id)
            if 'Recommendation' in book.device_collections:
                debug_print("mark_not_interested - book:", book)
                book.contentIDs = [book.contentID]
                recommendations.append(book)
                debug_print("mark_not_interested - book.device_collections:", book.device_collections)
        debug_print("mark_not_interested - recommendations:", recommendations)
        self.options = self.default_options()
        self.options['mark_not_interested'] = True

        updated_books, unchanged_books, not_on_device_books, count_books = self._update_metadata(recommendations)
        result_message = _("Books marked as Not Interested:\n\tBooks updated={0}\n\tUnchanged books={1}\n\tTotal books={2}").format(updated_books, unchanged_books, count_books)
        info_dialog(self.gui,  _("Sony Utilities") + " - " + _("Device library updated"),
                    result_message,
                    show=True)


    def show_books_not_in_database(self):

        #debug_print("upload_covers - start")
        self.device = self.get_device()
        if self.device is None:
            return error_dialog(self.gui,  _("Cannot list books not in device library."),
                     _("No device connected."),
                    show=True)
        self.device_path = self.get_device_path()

        books = self._get_books_for_selected()
        
        if len(books) == 0:
            books = self.gui.current_view().model().db

        books_not_in_database = self._check_book_in_database(books)
#        for book in books:
#            debug_print("show_books_not_in_database - book.title='%s'" % book.title)
#            if not book.contentID:
#                books_not_in_database.append(book)
#            else:
#                debug_print("show_books_not_in_database - book.contentID='%s'" % book.contentID)

        dlg = ShowBooksNotInDeviceDatabaseDialog(self.gui, books_not_in_database)
        dlg.show()


    def fix_duplicate_shelves(self):

        #debug_print("fix_duplicate_shelves - start")
        self.device = self.get_device()
        if self.device is None:
            return error_dialog(self.gui,  _("Cannot fix the duplicate shelves in the device library."),
                     _("No device connected."),
                    show=True)
        self.device_path = self.get_device_path()

        shelves = self._get_shelf_count()
        dlg = FixDuplicateShelvesDialog(self.gui, self, shelves)
        dlg.exec_()
        if dlg.result() != dlg.Accepted:
            debug_print("fix_duplicate_shelves - dialog cancelled")
            return
        self.options = dlg.options
        debug_print("fix_duplicate_shelves - about to fix shelves - options=%s" % self.options)

        starting_shelves, shelves_removed, finished_shelves = self._remove_duplicate_shelves(shelves, self.options)
        result_message = _("Update summary:") + "\n\t" + _("Starting number of shelves={0}\n\tShelves removed={1}\n\tTotal shelves={2}").format(starting_shelves, shelves_removed, finished_shelves)
        info_dialog(self.gui,  _("Sony Utilities") + " - " + _("Duplicate Shelves Fixed"),
                    result_message,
                    show=True)


    def order_series_shelves(self):

        #debug_print("order_series_shelves - start")
        self.device = self.get_device()
        if self.device is None:
            return error_dialog(self.gui,  _("Cannot order the series shelves in the device library."),
                     _("No device connected."),
                    show=True)
        self.device_path = self.get_device_path()

        shelves = []
        dlg = OrderSeriesShelvesDialog(self.gui, self, shelves)
        dlg.exec_()
        if dlg.result() != dlg.Accepted:
            debug_print("order_series_shelves - dialog cancelled")
            return
        self.options = dlg.options
        shelves      = dlg.get_shelves()
        debug_print("order_series_shelves - about to order shelves - options=%s" % self.options)
        debug_print("order_series_shelves - shelves=", shelves)

        starting_shelves, shelves_ordered = self._order_series_shelves(shelves, self.options)
        result_message = _("Update summary:") + "\n\t" + _("Starting number of shelves={0}\n\tShelves reordered={1}").format(starting_shelves, shelves_ordered)
        info_dialog(self.gui,  _("Sony Utilities") + " - " + _("Order Series Shelves"),
                    result_message,
                    show=True)


    def check_device_database(self):
        #debug_print("check_device_database - start")
        self.device = self.get_device()
        if self.device is None:
            return error_dialog(self.gui,  _("Cannot check Sony device database."),
                     _("No device connected."),
                    show=True)
        self.device_path = self.get_device_path()

        check_result = self._check_device_database()

        check_result = _("Result of running 'PRAGMA integrity_check' on database on the Sony device:\n\n") + check_result

        d = ViewLog("Sony Utilities - Device Database Check", check_result, parent=self.gui)
        d.setWindowIcon(self.qaction.icon())
        d.exec_()


    def block_analytics(self):
        debug_print("block_analytics - start")
        self.device = self.get_device()
        if self.device is None:
            return error_dialog(self.gui,  _("Cannot block analytics events."), 
                 _("No device connected."), show=True)
        self.device_path = self.get_device_path()

        debug_print("block_analytics")

        dlg = BlockAnalyticsOptionsDialog(self.gui, self)
        dlg.exec_()
        if dlg.result() != dlg.Accepted:
            return
        self.options = dlg.options

        block_analytics_result = self._block_analytics()
        if block_analytics_result:
            info_dialog(self.gui,  _("Sony Utilities") + " - " + _("Block Analytics Events"),
                    block_analytics_result, show=True)
        else:
            result_message = _("Failed to block analytics events.")
            d = ViewLog( _("Sony Utilities") + " - " + _("Block Analytics Events"),
                    result_message, parent=self.gui)
            d.setWindowIcon(self.qaction.icon())
            d.exec_()

    
    def vacuum_device_database(self):
        debug_print("vacuum_device_database - start")
        self.device = self.get_device()
        if self.device is None:
            return error_dialog(self.gui,  _("Cannot compress Sony device database."),
                     _("No device connected."),
                    show=True)
        self.device_path = self.get_device_path()

        uncompressed_db_size = os.path.getsize(self.device_database_path())
        vacuum_result = self._vacuum_device_database()

        if vacuum_result == '':
            compressed_db_size = os.path.getsize(self.device_database_path())
            result_message = _("The database on the device has been compressed.\n\tOriginal size = {0}MB\n\tCompressed size = {1}MB").format("%.3f"%(uncompressed_db_size / 1024 / 1024), "%.3f"%(compressed_db_size / 1024 / 1024))
            info_dialog(self.gui,  _("Sony Utilities") + " - " + _("Compress Device Database"),
                    result_message,
                    show=True)

        else:
            vacuum_result = _("Result of running 'vacuum' on database on the Sony device:\n\n") + vacuum_result

            d = ViewLog("Sony Utilities - Compress Device Database", vacuum_result, parent=self.gui)
            d.setWindowIcon(self.qaction.icon())
            d.exec_()


    def default_options(self):
        options = cfg.METADATA_OPTIONS_DEFAULTS
        return options

    def manage_series_on_device(self):
        def digits(f):
            return len(str(f).split('.')[1].rstrip('0'))

        if len(self.gui.current_view().selectionModel().selectedRows()) == 0:
            return

        self.device = self.get_device()
        if self.device is None:
            return error_dialog(self.gui,  _("Cannot manage series in device library."),
                     _("No device connected."),
                    show=True)
        series_columns = self.get_series_columns()
        self.device_path = self.get_device_path()

        books = self._get_books_for_selected()
        debug_print("manage_series_on_device - books[0].__class__=", books[0].__class__)

        
        if len(books) == 0:
            return
        seriesBooks = [SeriesBook(book, series_columns) for book in books]
        seriesBooks = sorted(seriesBooks, key=lambda k: k.sort_key(sort_by_name=True))
        debug_print("manage_series_on_device - seriesBooks[0]._mi.__class__=", seriesBooks[0]._mi.__class__)
        debug_print("manage_series_on_device - seriesBooks[0]._mi.sony_series=", seriesBooks[0]._mi.sony_series)
        debug_print("manage_series_on_device - seriesBooks[0]._mi.sony_series_number=", seriesBooks[0]._mi.sony_series_number)
        debug_print("manage_series_on_device - books:", seriesBooks)

        library_db = self.gui.library_view.model().db
        all_series = library_db.all_series()
        all_series.sort(key=lambda x : sort_key(x[1]))

        d = ManageSeriesDeviceDialog(self.gui, self, seriesBooks, all_series, series_columns)
        d.exec_()
        if d.result() != d.Accepted:
            return
        
        debug_print("manage_series_on_device - done series management - books:", seriesBooks)

        self.options = self.default_options()
        books = []
        for seriesBook in seriesBooks:
            debug_print("manage_series_on_device - seriesBook._mi.contentID=", seriesBook._mi.contentID)
            if seriesBook.is_title_changed() or seriesBook.is_pubdate_changed() or seriesBook.is_series_changed():
                book = seriesBook._mi
                book.series_index_string = seriesBook.series_index_string()
                book.sony_series_number  = seriesBook.series_index_string()
                book.sony_series         = seriesBook.series_name()
                book._new_book           = True
                book.contentIDs          = [book.contentID]
                books.append(book)
                self.options['title']          = self.options['title'] or seriesBook.is_title_changed()
                self.options['series']         = self.options['series'] or seriesBook.is_series_changed()
                self.options['published_date'] = self.options['published_date'] or seriesBook.is_pubdate_changed()
                debug_print("manage_series_on_device - seriesBook._mi.__class__=", seriesBook._mi.__class__)
                debug_print("manage_series_on_device - seriesBook.is_pubdate_changed()=%s"%seriesBook.is_pubdate_changed())
                debug_print("manage_series_on_device - book.sony_series=", book.sony_series)
                debug_print("manage_series_on_device - book.sony_series_number=", book.sony_series_number)
                debug_print("manage_series_on_device - book.series=", book.series)
                debug_print("manage_series_on_device - book.series_index=%s"%unicode(book.series_index))


        if self.options['title'] or self.options['series'] or self.options['published_date']:
            updated_books, unchanged_books, not_on_device_books, count_books = self._update_metadata(books)
            
            debug_print("manage_series_on_device - about to call sync_booklists")
    #        self.device.sync_booklists((self.gui.current_view().model().db, None, None))
            USBMS.sync_booklists(self.device, (self.gui.current_view().model().db, None, None))
            result_message = _("Update summary:") + "\n\t" + _("Books updated={0}\n\tUnchanged books={1}\n\tBooks not on device={2}\n\tTotal books={3}").format(updated_books, unchanged_books, not_on_device_books, count_books)
        else:
            result_message = _("No changes made to series information.")
        info_dialog(self.gui,  _("Sony Utilities") + " - " + _("Manage Series On Device"),
                    result_message,
                    show=True)


    def get_series_columns(self):
        custom_columns = self.gui.library_view.model().custom_columns
        series_columns = OrderedDict()
        for key, column in custom_columns.iteritems():
            typ = column['datatype']
            if typ == 'series':
                series_columns[key] = column
        return series_columns

    def get_selected_books(self, rows, series_columns):
        def digits(f):
            return len(str(f).split('.')[1].rstrip('0'))

        db = self.gui.library_view.model().db
        idxs = [row.row() for row in rows]
        books = []
        for idx in idxs:
            mi = db.get_metadata(idx)
            book = SeriesBook(mi, series_columns)
            books.append(book)
        # Sort books by the current series
        books = sorted(books, key=lambda k: k.sort_key())
        return books


    def upload_covers(self):
        if len(self.gui.current_view().selectionModel().selectedRows()) == 0:
            return
        #debug_print("upload_covers - start")
        self.device = self.get_device()
        if self.device is None:
            return error_dialog(self.gui,
                                 _("Cannot upload covers."),
                                 _("No device connected."),
                                show=True)
        self.device_path = self.get_device_path()

        selectedIDs = self._get_selected_ids()
        
        if len(selectedIDs) == 0:
            return
        debug_print("upload_covers - selectedIDs:", selectedIDs)
        books = self._convert_calibre_ids_to_books(self.gui.current_view().model().db, selectedIDs)
        
        dlg = CoverUploadOptionsDialog(self.gui, self)
        dlg.exec_()
        if dlg.result() != dlg.Accepted:
            return
        self.options = dlg.options
        
        total_books, uploaded_covers, not_on_device_books = self._upload_covers(books)
        result_message = _("Change summary:") + "\n\t" + _("Covers uploaded={0}\n\tBooks not on device={1}\n\tTotal books={2}").format(uploaded_covers, not_on_device_books, total_books)
        info_dialog(self.gui,  _("Sony Utilities") + " - " + _("Covers uploaded"),
                    result_message,
                    show=True)

    def remove_covers(self):
        if len(self.gui.current_view().selectionModel().selectedRows()) == 0:
            return
        #debug_print("remove_covers - start")
        self.device = self.get_device()
        if self.device is None:
            return error_dialog(self.gui,  _("Cannot remove covers."),
                     _("No device connected."),
                    show=True)
        self.device_path = self.get_device_path()
        debug_print("remove_covers - self.device_path", self.device_path)

#        contentIDs = self._get_contentIDs_for_selected()
        if self.gui.stack.currentIndex() == 0:
            selectedIDs = self._get_selected_ids()
            books = self._convert_calibre_ids_to_books(self.gui.current_view().model().db, selectedIDs)

        else:
            books = self._get_books_for_selected()

        
        if len(books) == 0:
            return

        dlg = RemoveCoverOptionsDialog(self.gui, self)
        dlg.exec_()
        if dlg.result() != dlg.Accepted:
            return
        self.options = dlg.options
        
        removed_covers, not_on_device_books, total_books = self._remove_covers(books)
        result_message = _("Change summary:") + "\n\t" + _("Covers removed={0}\n\tBooks not on device={1}\n\tTotal books={2}").format(removed_covers, not_on_device_books, total_books)
        info_dialog(self.gui,  _("Sony Utilities") + " - " + _("Covers removed"),
                    result_message,
                    show=True)


    def test_covers(self):
        if len(self.gui.current_view().selectionModel().selectedRows()) == 0:
            return
        #debug_print("remove_covers - start")
        self.device = self.get_device()
        if self.device is None:
            return error_dialog(self.gui,  _("Cannot remove covers."),
                     _("No device connected."),
                    show=True)
        self.device_path = self.get_device_path()
        debug_print("test_covers - self.device_path", self.device_path)

#        contentIDs = self._get_contentIDs_for_selected()
        if self.gui.stack.currentIndex() == 0:
            selectedIDs = self._get_selected_ids()
            books = self._convert_calibre_ids_to_books(self.gui.current_view().model().db, selectedIDs)

        else:
            books = self._get_books_for_selected()

        
        if len(books) == 0:
            return

        dlg = RemoveCoverOptionsDialog(self.gui, self)
        dlg.exec_()
        if dlg.result() != dlg.Accepted:
            return
        self.options = dlg.options
        
        removed_covers, not_on_device_books, total_books = self._test_covers(books)
        result_message = _("Change summary:") + "\n\t" + _("Covers removed={0}\n\tBooks not on device={1}\n\tTotal books={2}").format(removed_covers, not_on_device_books, total_books)
        info_dialog(self.gui,  _("Sony Utilities") + " - " + _("Covers removed"),
                    result_message,
                    show=True)



    def getAnnotationForSelected(self):
        if len(self.gui.current_view().selectionModel().selectedRows()) == 0:
            return
        #debug_print("upload_covers - start")
        self.device = self.get_device()
        if self.device is None:
            return error_dialog(self.gui,
                                 _("Cannot upload covers."),
                                 _("No device connected."),
                                show=True)

        self._getAnnotationForSelected()


    def _get_selected_ids(self):
        rows = self.gui.current_view().selectionModel().selectedRows()
        if not rows or len(rows) == 0:
            return []
        return map(self.gui.current_view().model().id, rows)

    def contentid_from_path(self, path):
        debug_print("sonyutilities.action:contentid_from_path - self.device._main_prefix='%s'"%self.device._main_prefix, "self.device.device._card_a_prefix='%s'"%self.device._card_a_prefix)
        # Remove the prefix on the file.  it could be either
        if path.startswith(self.device._main_prefix):
            internal_path = path.replace(self.device._main_prefix, '')
            db = self.device_database_path(self.device._main_prefix)
        else:
            internal_path = path.replace(self.device._card_a_prefix, "")
            db = self.device_database_path(self.device._card_a_prefix)
        
        import sqlite3 
        with closing(sqlite3.connect(db)) as connection:
            # return bytestrings if the content cannot the decoded as unicode
            connection.text_factory = lambda x: unicode(x, "utf-8", "ignore")

            query = 'SELECT _id FROM books WHERE file_path = ?'
            cursor = connection.cursor()
            cursor.execute(query, (internal_path,))
            row = cursor.fetchone()
            ContentID = row[0]
            cursor.close()

#        debug_print("sonyutilities.action:contentid_from_path - end - ContentID='%s'"%ContentID)
        return ContentID

    def get_contentIDs_for_books(self, ids):
        contentIDs= []
        for book_id in ids:
            device_book_path = self.get_device_path_from_id(book_id)
            debug_print('get_contentIDs_for_books - device_book_path', device_book_path)
            if device_book_path is None:
                continue
            contentID = self.contentid_from_path(device_book_path)
            debug_print('get_contentIDs_for_books - contentID', contentID)
            contentIDs.append(contentID)
        return contentIDs

    def _get_books_for_selected(self):
        view = self.gui.current_view()
        if self.isDeviceView():
            rows  = view.selectionModel().selectedRows()
            books = []
            for r in rows:
#                debug_print('_get_books_for_selected - r.row()', r.row())
                book = view.model().db[view.model().map[r.row()]]
                book.calibre_id = r.row()
                books.append(book)
            #books = [view.model().db[view.model().map[r.row()]] for r in rows]
        else:
            books = []
            
        return books

    def _convert_calibre_ids_to_books(self, db, ids):
        books = []
        for book_id in ids:
            book = self._convert_calibre_id_to_book(db, book_id)
#            debug_print('_convert_calibre_ids_to_books - book', book)
            books.append(book)
        return books

    def _convert_calibre_id_to_book(self, db, book_id):
        mi = db.get_metadata(book_id, index_is_id=True, get_cover=True)
#        debug_print('_convert_calibre_id_to_book - mi', mi)
#        debug_print('_convert_calibre_id_to_book - mi.application_id', mi.application_id)
#        debug_print('_convert_calibre_id_to_book - mi.in_library', mi.in_library)
        book = Book('', 'lpath', other=mi)
        book.calibre_id  = mi.id

        return book


    def get_device_path(self):
        debug_print('BEGIN Get Device Path')
    
        device_path = ''
            # If we're in test mode TEST_DEVICE is defined, use the predefined test directory
            #device_path = 'fakeKindleDir2'
        if device_path:
            debug_print('RUNNING IN TEST MODE')
        else:
            # Not in test mode, so confirm a device is connected
            device_connected = self.gui.library_view.model().device_connected
            try:
                device_connected = self.gui.library_view.model().device_connected
            except:
                debug_print('No device connected')
                device_connected = None
    
            # If there is a device connected, test if we can retrieve the mount point from Calibre
            if device_connected is not None:
                try:
                    # _main_prefix is not reset when device is ejected so must be sure device_connected above
                    device_path = self.current_location['prefix']
                    debug_print('Root path of device: %s' % device_path)
                except:
                    debug_print('A device appears to be connected, but device path not defined')
            else:
                debug_print('No device appears to be connected')
    
        debug_print('END Get Device Path')
        return device_path

    def get_device(self):
        debug_print('BEGIN Get Device')

        self.device = None
        try:
            self.device = self.gui.device_manager.connected_device
        except:
            debug_print('No device connected')
            self.device = None
    
        # If there is a device connected, test if we can retrieve the mount point from Calibre
        if self.device is None or not isinstance(self.device, PRST1):
            debug_print('No Sony PRS device appears to be connected')
        else:
            debug_print('Have a Sony device connected')

        self.supports_series  = True

        debug_print('END Get Device')
        return self.device
    
    def device_fwversion(self):
        return self.device.fwversion

    def get_device_path_from_id(self, book_id):
        paths = self.get_device_paths_from_id(book_id)
        return paths[0] if paths else None


    def get_device_paths_from_id(self, book_id):
        paths = []
        for x in ('memory', 'card_a', 'card_b'):
            x = getattr(self.gui, x+'_view').model()
            paths += x.paths_for_db_ids(set([book_id]), as_map=True)[book_id]
#        debug_print("get_device_paths_from_id - paths=", paths)
        return [r.path for r in paths]

    def get_contentIDs_from_id(self, book_id):
        debug_print("get_contentIDs_from_id - book_id=", book_id)
        paths = []
        import pydevd;pydevd.settrace()
        for x in ('memory', 'card_a', 'card_b'):
#            debug_print("get_contentIDs_from_id - x=", x)
            x = getattr(self.gui, x+'_view').model()
#            debug_print("get_contentIDs_from_id - x=", x)
            paths += x.paths_for_db_ids(set([book_id]), as_map=True)[book_id]
        debug_print("get_contentIDs_from_id - paths=", paths)
#        return [r.contentID if r.contentID else self.contentid_from_path(r.path) for r in paths]
        return [r.contentID for r in paths]


    def _store_queue_job(self, tdir, options, books_to_modify):
        debug_print("sonyutilitiesAction::_store_queue_job")
        if not books_to_modify:
            # All failed so cleanup our temp directory
            remove_dir(tdir)
            return

#         cpus = 1# self.gui.device_manager.server.pool_size
        from calibre_plugins.sonyutilities.jobs import do_store_locations
        args = [books_to_modify, options, ]
        desc = _('Storing reading positions for {0} books').format(len(books_to_modify))
        job = self.gui.device_manager.create_job(do_store_locations, self.Dispatcher(self._store_completed), description=desc, args=args)
        job._tdir = tdir
        self.gui.status_bar.show_message(_('Sony Utilities') + ' - ' + desc, 3000)


    def _store_completed(self, job):
        import pydevd;pydevd.settrace()
        if job.failed:
            self.gui.job_exception(job, dialog_title=_('Failed to get reading positions'))
            return
        modified_epubs_map, options = job.result
        debug_print("sonyutilitiesAction::_store_completed - options", options)

        update_count = len(modified_epubs_map) if modified_epubs_map else 0
        if update_count == 0:
            msg = _('No reading positions were found that need to be updated')
            if options[cfg.KEY_PROMPT_TO_STORE]:
                return info_dialog(self.gui, _('Sony Utilities'), msg,
                                    show_copy_button=True, show=True,
                                    det_msg=job.details)
            else:
                self.gui.status_bar.show_message(_('Sony Utilities') + ' - ' + _('Storing reading positions completed - No changes found'), 3000)
        else:
            msg = _('Sony Utilities stored reading locations for <b>{0} book(s)</b>').format(update_count)

            if options[cfg.KEY_PROMPT_TO_STORE]:
                db = self.gui.current_db
                dlg = ShowReadingPositionChangesDialog(self.gui, self, job.result, db)
                dlg.exec_()
                if dlg.result() != dlg.Accepted:
                    debug_print("_store_completed - dialog cancelled")
                    return
                modified_epubs_map = dlg.reading_locations
            self._update_database_columns(modified_epubs_map)


    def _device_database_backup(self, backup_options):
        debug_print("sonyutilitiesAction::_device_database_backup")

#        func = 'arbitrary_n'
#         cpus = 1# self.gui.device_manager.server.pool_size
        from calibre_plugins.sonyutilities.jobs import do_device_database_backup
        args = [backup_options,  ]
        desc = _("Backing up Sony device database")
        job = self.gui.device_manager.create_job(do_device_database_backup, self.Dispatcher(self._device_database_backup_completed), description=desc, args=args)
        job._tdir = None
        self.gui.status_bar.show_message(_("Sony Utilities") + " - " + desc, 3000)


    def _device_database_backup_completed(self, job):
        if job.failed:
            self.gui.job_exception(job, dialog_title=_("Failed to backup device database"))
            return


    def _update_database_columns(self, reading_locations):
#        reading_locations, options = payload
#        debug_print("_store_current_bookmark - reading_locations=", reading_locations)
        
        debug_print("_update_database_columns - start number of reading_locations= %d" % (len(reading_locations)))
        pb = ProgressBar(parent=self.gui, window_title=_("Storing reading positions"), on_top=True)
        total_books = len(reading_locations)
        pb.set_maximum(total_books)
        pb.set_value(0)
        pb.show()

        db = self.gui.current_db
        custom_cols = db.field_metadata.custom_field_metadata()

        library_db     = self.gui.current_db
        library_config = cfg.get_library_config(library_db)
        sony_bookmark_column    = library_config.get(cfg.KEY_CURRENT_LOCATION_CUSTOM_COLUMN, cfg.DEFAULT_LIBRARY_VALUES[cfg.KEY_CURRENT_LOCATION_CUSTOM_COLUMN])
        sony_percentRead_column = library_config.get(cfg.KEY_PERCENT_READ_CUSTOM_COLUMN, cfg.DEFAULT_LIBRARY_VALUES[cfg.KEY_PERCENT_READ_CUSTOM_COLUMN])
        last_read_column        = library_config.get(cfg.KEY_LAST_READ_CUSTOM_COLUMN, cfg.DEFAULT_LIBRARY_VALUES[cfg.KEY_LAST_READ_CUSTOM_COLUMN])
        if sony_bookmark_column:
            debug_print("_update_database_columns - sony_bookmark_column=", sony_bookmark_column)
            sony_bookmark_col = custom_cols[sony_bookmark_column]
#                debug_print("_update_database_columns - sony_bookmark_col=", sony_bookmark_col)
            sony_bookmark_col_label = library_db.field_metadata.key_to_label(sony_bookmark_column)
            debug_print("_update_database_columns - sony_bookmark_col_label=", sony_bookmark_col_label)
        if sony_percentRead_column:
            sony_percentRead_col = custom_cols[sony_percentRead_column]
#            sony_percentRead_col_label = library_db.field_metadata.key_to_label(sony_percentRead_column)

        if last_read_column:
            last_read_col = custom_cols[last_read_column]
#            last_read_col_label = library_db.field_metadata.key_to_label(last_read_column)

        debug_print("_update_database_columns - sony_bookmark_column=", sony_bookmark_column)
        debug_print("_update_database_columns - sony_percentRead_column=", sony_percentRead_column) 
#         debug_print("_update_database_columns - rating_column=", rating_column) 
        debug_print("_update_database_columns - last_read_column=", last_read_column) 
        # At this point we want to re-use code in edit_metadata to go ahead and
        # apply the changes. So we will create empty Metadata objects so only
        # the custom column field gets updated
        id_map = {}
        id_map_percentRead = {}
        id_map_bookmark    = {}
        id_map_last_read   = {}
        for book_id, reading_location in reading_locations.iteritems():
            mi      = Metadata(_('Unknown'))
            book_mi = db.get_metadata(book_id, index_is_id=True, get_cover=True)
            book    = Book('', 'lpath', title=book_mi.title, other=book_mi)
            pb.set_label(_("Updating ") + book_mi.title)
            pb.increment()

            sony_bookmark    = None
            sony_percentRead = None
            last_read        = None
            if reading_location is not None: 
                debug_print("_update_database_columns - result=", reading_location)
                sony_bookmark = reading_location['mark']
                sony_percentRead = reading_location['percent']
#                 debug_print("_update_database_columns - reading_location[5]=", reading_location[5])
                last_read = reading_location['reading_time']
#                 debug_print("_update_database_columns - last_read=", last_read)

            elif self.options[cfg.KEY_CLEAR_IF_UNREAD]:
#                books_with_bookmark      += 1
                sony_bookmark    = None
                sony_percentRead = None
                last_read        = None
            else:
#                books_without_bookmark += 1
                continue
            
            debug_print("_update_database_columns - sony_bookmark='%s'" % (sony_bookmark))
            debug_print("_update_database_columns - sony_percentRead=", sony_percentRead)
            if sony_bookmark_column:
                if sony_bookmark:
                    new_value = sony_bookmark
                else:
                    sony_bookmark_col['#value#'] = None
                    new_value        = None
#                    debug_print("_update_database_columns - setting bookmark column to None")
                sony_bookmark_col['#value#'] = new_value
                if not hasattr(db, 'new_api'):
                    mi.set_user_metadata(sony_bookmark_column, sony_bookmark_col)
                else:
                    old_value = book.get_user_metadata(sony_bookmark_column, True)['#value#']
                    if not old_value == new_value: 
                        id_map_bookmark[book_id] = new_value
#                library_db.set_custom(book.calibre_id, new_value, label=sony_bookmark_col_label, commit=False)

            if sony_percentRead_column:
                sony_percentRead_col['#value#'] = sony_percentRead
                debug_print("_update_database_columns - setting mi.sony_percentRead=", sony_percentRead)
#                library_db.set_custom(book.calibre_id, sony_percentRead, label=sony_percentRead_col_label, commit=False)
                if not hasattr(db, 'new_api'):
                    mi.set_user_metadata(sony_percentRead_column, sony_percentRead_col)
                current_percentRead = book.get_user_metadata(sony_percentRead_column, True)['#value#']
                debug_print("_update_database_columns - percent read - in book=", current_percentRead)
                if not current_percentRead == sony_percentRead:
                    id_map_percentRead[book_id] = sony_percentRead

            if last_read_column:
                current_last_read = book.get_user_metadata(last_read_column, True)['#value#']
                last_read_col['#value#'] = last_read
                debug_print("_update_database_columns - last_read=", last_read)
                if not hasattr(db, 'new_api'):
                    mi.set_user_metadata(last_read_column, last_read_col)
                if not current_last_read == last_read:
                    id_map_last_read[book_id] = last_read

#            debug_print("_update_database_columns - mi=", mi)
            id_map[book_id] = mi

        if hasattr(db, 'new_api'):
            if sony_bookmark_column:
                debug_print("_update_database_columns - Updating metadata - for column: %s number of changes=%d" % (sony_bookmark_column, len(id_map_bookmark)))
                library_db.new_api.set_field(sony_bookmark_column, id_map_bookmark)
            if sony_percentRead_column:
                debug_print("_update_database_columns - Updating metadata - for column: %s number of changes=%d" % (sony_percentRead_column, len(id_map_percentRead)))
                library_db.new_api.set_field(sony_percentRead_column, id_map_percentRead)
            if last_read_column:
                debug_print("_update_database_columns - Updating metadata - for column: %s number of changes=%d" % (last_read_column, len(id_map_last_read)))
                library_db.new_api.set_field(last_read_column, id_map_last_read)

        
        if hasattr(db, 'new_api'):
            debug_print("_update_database_columns - Updating GUI - new DB engine")
            self.gui.iactions['Edit Metadata'].refresh_gui(list(reading_locations))
        else:
            edit_metadata_action = self.gui.iactions['Edit Metadata']
            debug_print("_update_database_columns - Updating GUI - old DB engine")
            edit_metadata_action.apply_metadata_changes(id_map)
        debug_print("_update_database_columns - finished")

        pb.hide()
        self.gui.status_bar.show_message(_('Sony Utilities') + ' - ' + _('Storing reading positions completed - {0} changed.').format(len(reading_locations)), 3000)


    def _getAnnotationForSelected(self, *args):
        # Generate a path_map from selected ids
        def get_ids_from_selected_rows():
            rows = self.gui.library_view.selectionModel().selectedRows()
            if not rows or len(rows) < 1:
                rows = xrange(self.gui.library_view.model().rowCount(QModelIndex()))
            ids = map(self.gui.library_view.model().id, rows)
            return ids

        def get_formats(_id):
            formats = db.formats(_id, index_is_id=True)
            fmts = []
            if formats:
                for fmt in formats.split(','):
                    fmts.append(fmt.lower())
            return fmts

        def get_device_path_from_id(id_):
            paths = []
            for x in ('memory', 'card_a', 'card_b'):
                x = getattr(self.gui, x+'_view').model()
                paths += x.paths_for_db_ids(set([id_]), as_map=True)[id_]
            return paths[0].path if paths else None

        def generate_annotation_paths(ids, db, device):
            # Generate path templates
            # Individual storage mount points scanned/resolved in driver.get_annotations()
            path_map = {}
            for _id in ids:
                paths = self.get_device_paths_from_id(_id)
                debug_print("generate_annotation_paths - paths=", paths)
#                mi = db.get_metadata(_id, index_is_id=True)
#                a_path = device.create_annotations_path(mi, device_path=paths)
                if len(paths) > 0:
                    the_path = paths[0]
                    if len(paths) > 1:
                        if os.path.splitext(paths[0]) > 1: # No extension - is kepub
                            the_path = paths[1]
                    path_map[_id] = dict(path=the_path, fmts=get_formats(_id))
            return path_map

        annotationText = []

        if self.gui.current_view() is not self.gui.library_view:
            return error_dialog(self.gui,  _("Use library only"),
                     _("User annotations generated from main library only"),
                    show=True)
        db = self.gui.library_view.model().db

        # Get the list of ids
        ids = get_ids_from_selected_rows()
        if not ids:
            return error_dialog(self.gui,  _("No books selected"),
                     _("No books selected to fetch annotations from"),
                    show=True)

        debug_print("_getAnnotationForSelected - ids=", ids)
        # Map ids to paths
        path_map = generate_annotation_paths(ids, db, self.device)
        debug_print("_getAnnotationForSelected - path_map=", path_map)
        if len(path_map) == 0:
            return error_dialog(self.gui,  _("No books on device selected"),
                     _("None of the books selected were on the device. Annotations can only be copied for books on the device."),
                    show=True)

        from calibre.ebooks.BeautifulSoup import BeautifulSoup, Tag, NavigableString
        from calibre.ebooks.metadata import authors_to_string

        # Dispatch to the device get_annotations()
        debug_print("_getAnnotationForSelected - path_map=", path_map)
        bookmarked_books = self.device.get_annotations(path_map)
        debug_print("_getAnnotationForSelected - bookmarked_books=", bookmarked_books)

        for id_ in bookmarked_books.keys():
            bm = self.device.UserAnnotation(bookmarked_books[id_][0], bookmarked_books[id_][1])

            mi = db.get_metadata(id_, index_is_id=True)

            user_notes_soup = self.device.generate_annotation_html(bm.value)
            spanTag = Tag(user_notes_soup, 'span')
            spanTag['style'] = 'font-weight:normal'
            spanTag.insert(0,NavigableString(
                "<hr /><b>%(title)s</b> by <b>%(author)s</b>" % \
                            dict(title=mi.title,
                            #loc=last_read_location,
                            author=authors_to_string(mi.authors))))
            user_notes_soup.insert(0, spanTag)
            bookmark_html = unicode(user_notes_soup.prettify())
            debug_print(bookmark_html)
            annotationText.append(bookmark_html)

        d = ViewLog("Sony Annotation", "\n".join(annotationText), parent=self.gui)
#        d = ViewLog("Sony Annotation", unicode(j), parent=self.gui)
        d.setWindowIcon(self.qaction.icon())
#       d.setWindowIcon(get_icon('bookmarks.png'))
        d.exec_()


    def _upload_covers(self, books):

        uploaded_covers     = 0
        total_books         = 0
        not_on_device_books = len(books)

        for book in books:
            total_books += 1
            debug_print("_upload_covers - book=", book)
            debug_print("_upload_covers - thumbnail=", book.thumbnail)
            paths = self.get_device_paths_from_id(book.calibre_id)
            not_on_device_books -= 1 if len(paths) > 0 else 0
            for path in paths:
                debug_print("_upload_covers - path=", path)
                self.device.upload_cover(None, None, book, path)
#                 self.device._upload_cover(path, '', book, path, self.options['blackandwhite'], keep_cover_aspect=self.options['keep_cover_aspect'])
                uploaded_covers += 1

        return total_books, uploaded_covers, not_on_device_books


    def _remove_covers(self, books):
        import sqlite3 
        with closing(sqlite3.connect(self.device_database_path())) as connection:
            # return bytestrings if the content cannot the decoded as unicode
            connection.text_factory = lambda x: unicode(x, "utf-8", "ignore")

            total_books         = 0
            removed_covers      = 0
            not_on_device_books = 0

            imageId_query = 'SELECT ImageId '       \
                            'FROM content '         \
                            'WHERE ContentId = ?'
            cursor = connection.cursor()

            for book in books:
                debug_print("_remove_covers - book=", book)
                debug_print("_remove_covers - book.__class__=", book.__class__)
                debug_print("_remove_covers - book.contentID=", book.contentID)
                debug_print("_remove_covers - book.lpath=", book.lpath)
                debug_print("_remove_covers - book.path=", book.path)
                contentIDs = [book.contentID] if book.contentID is not None else self.get_contentIDs_from_id(book.calibre_id)
                debug_print("_remove_covers - contentIDs=", contentIDs)
                for contentID in contentIDs:
                    debug_print("_remove_covers - contentID=", contentID)

                    if book.lpath.startswith(self.device._card_a_prefix):
                        path = self.device._card_a_prefix
                    else:
                        path = self.device._main_prefix

                    query_values = (contentID,)
                    cursor.execute(imageId_query, query_values)
                    result = cursor.fetchone()
                    if result is not None:
                        debug_print("_remove_covers - contentId='%s', imageId='%s'" % (contentID, result[0]))
                        self.device.delete_images(result[0], path)
                        removed_covers +=1
                    else:
                        debug_print("_remove_covers - no match for contentId='%s'" % (contentID,))
                        not_on_device_books += 1
                    connection.commit()
                    total_books += 1

            cursor.close()

        return removed_covers, not_on_device_books, total_books


    def _test_covers(self, books):


        import sqlite3 
        with closing(sqlite3.connect(self.device_database_path())) as connection:
            # return bytestrings if the content cannot the decoded as unicode
            connection.text_factory = lambda x: unicode(x, "utf-8", "ignore")

            total_books         = 0
            removed_covers      = 0
            not_on_device_books = 0

            imageId_query = 'SELECT ImageId '       \
                            'FROM content '         \
                            'WHERE ContentId = ?'
            cursor = connection.cursor()

            for book in books:
                debug_print("_test_covers - book=", book)
                debug_print("_test_covers - book.__class__=", book.__class__)
                debug_print("_test_covers - book.contentID=", book.contentID)
                debug_print("_test_covers - book.lpath=", book.lpath)
                debug_print("_test_covers - book.path=", book.path)
                contentIDs = [book.contentID] if book.contentID is not None else self.get_contentIDs_from_id(book.calibre_id)
                debug_print("_test_covers - contentIDs=", contentIDs)
                for contentID in contentIDs:
                    debug_print("_test_covers - contentID=", contentID)
                    
                    if book.lpath.startswith(self.device._card_a_prefix):
                        path = self.device._card_a_prefix
                    else:
                        path = self.device._main_prefix

                    query_values = (contentID,)
                    cursor.execute(imageId_query, query_values)
                    result = cursor.fetchone()
                    if result is not None:
                        debug_print("_test_covers - contentId='%s', imageId='%s'" % (contentID, result[0]))
                        hash1 = qhash(result[0])
#                        debug_print("_test_covers - hash1='%s'" % (hash1))
                        xff   = 0xff
                        dir1  = hash1 & xff
                        dir1  &= 0xff
#                        debug_print("_test_covers - dir1='%s', xff='%s'" % (dir1, xff))
                        xff00 = 0xff00
                        dir2  = (hash1 & xff00) >> 8
#                        debug_print("_test_covers - hash1='%s', dir1='%s', dir2='%s'" % (hash1, dir1, dir2))
                        cover_dir = os.path.join(path, ".sony-images", "%s" % dir1, "%s" % dir2)
                        debug_print("_test_covers - cover_dir='%s'" % (cover_dir))
#                        self.device.delete_images(result[0], path)
                        removed_covers +=1
                    else:
                        debug_print("_test_covers - no match for contentId='%s'" % (contentID,))
                        not_on_device_books += 1
                    connection.commit()
                    total_books += 1

            cursor.close()

        return removed_covers, not_on_device_books, total_books


    def _get_imageid_set(self):
        import sqlite3 
        with closing(sqlite3.connect(self.device_database_path())) as connection:
            # return bytestrings if the content cannot the decoded as unicode
            connection.text_factory = lambda x: unicode(x, "utf-8", "ignore")

            imageId_query = 'SELECT DISTINCT ImageId '       \
                            'FROM content '         \
                            'WHERE BookID IS NULL'
            cursor = connection.cursor()

            imageIDs = []
            cursor.execute(imageId_query)
            for row in cursor:
                imageIDs.append(row[0])
#                debug_print("_get_imageid_set - row[0]='%s'" % (row[0]))
            connection.commit()

            cursor.close()

        return set(imageIDs)


    def _check_book_in_database(self, books):
        import sqlite3 
        with closing(sqlite3.connect(self.device_database_path())) as connection:
            # return bytestrings if the content cannot the decoded as unicode
            connection.text_factory = lambda x: unicode(x, "utf-8", "ignore")

            not_on_device_books = []

            # TODO: check return from self.contentid_from_path() - should return null for book not on device
            for book in books:
                if not book.contentID:
                    book.contentID = self.contentid_from_path(book.path)

                if not book.contentID:
                    debug_print("_check_book_in_database - no match for contentId='%s'" % (book.contentID,))
                    not_on_device_books.append(book)

        return not_on_device_books


    def _get_shelf_count(self):
        import sqlite3 
        with closing(sqlite3.connect(self.device_database_path())) as connection:
            # return bytestrings if the content cannot the decoded as unicode
            connection.text_factory = lambda x: unicode(x, "utf-8", "ignore")

            shelves = []

            shelves_query = ("SELECT Name, MIN(CreationDate), MAX(CreationDate), COUNT(*) "
                            "FROM Shelf "
                            "WHERE _IsDeleted = 'false' "
                            "GROUP BY Name")

            cursor = connection.cursor()
            cursor.execute(shelves_query)
    #        count_bookshelves = 0
            for i, row in enumerate(cursor):
                debug_print("_get_shelf_count - row:", i, row[0], row[1], row[2], row[3])
                shelves.append([row[0], convert_sony_date(row[1]), convert_sony_date(row[2]), int(row[3]) ])
    
            cursor.close()
        return shelves


    def _get_series_shelf_count(self, order_shelf_type):
        debug_print("_get_series_shelf_count - order_shelf_type:", order_shelf_type)
        import sqlite3 
        with closing(sqlite3.connect(self.device_database_path())) as connection:
            # return bytestrings if the content cannot the decoded as unicode
            connection.text_factory = lambda x: unicode(x, "utf-8", "ignore")

            shelves = []

            series_query = ("SELECT Name, count(*) "
                            "FROM Shelf s JOIN ShelfContent sc on name = ShelfName "
                            "WHERE s._IsDeleted = 'false' "
                            "AND sc._IsDeleted = 'false' "
                            "AND EXISTS (SELECT 1 FROM content c WHERE s.Name = c.Series ) "
                            "GROUP BY Name"
                            )
            authors_query = ("SELECT Name, count(*) "
                            "FROM Shelf s JOIN ShelfContent sc on name = ShelfName "
                            "WHERE s._IsDeleted = 'false' "
                            "AND sc._IsDeleted = 'false' "
                            "AND EXISTS (SELECT 1 FROM content c WHERE s.Name = c.Attribution ) "
                            "GROUP BY Name"
                            )
            other_query = ("SELECT Name, count(*) "
                            "FROM Shelf s JOIN ShelfContent sc on name = ShelfName "
                            "WHERE s._IsDeleted = 'false' "
                            "AND sc._IsDeleted = 'false' "
                            "AND NOT EXISTS (SELECT 1 FROM content c WHERE s.Name = c.Attribution ) "
                            "AND NOT EXISTS (SELECT 1 FROM content c WHERE s.Name = c.Series ) "
                            "GROUP BY Name"
                            )
            all_query = ("SELECT Name, count(*) "
                            "FROM Shelf s JOIN ShelfContent sc on name = ShelfName "
                            "WHERE s._IsDeleted = 'false' "
                            "AND sc._IsDeleted = 'false' "
                            "GROUP BY Name"
                            )

            shelves_queries= [series_query, authors_query, other_query, all_query]
            shelves_query = shelves_queries[order_shelf_type]
            debug_print("_get_series_shelf_count - shelves_query:", shelves_query)

            cursor = connection.cursor()
            cursor.execute(shelves_query)
    #        count_bookshelves = 0
            for i, row in enumerate(cursor):
                debug_print("_get_series_shelf_count - row:", i, row[0], row[1])
                shelf = {}
                shelf['name']  = row[0]
                shelf['count'] = int(row[1])
                shelves.append(shelf)

            cursor.close()
        debug_print("_get_series_shelf_count - shelves:", shelves)
        return shelves


    def _order_series_shelves(self, shelves, options):
        
        def urlquote(shelf_name):
            """ Quote URL-unsafe characters, For unsafe characters, need "%xx" rather than the 
            other encoding used for urls.  
            Pulled from calibre.ebooks.oeb.base.py:urlquote"""
            ASCII_CHARS   = set(chr(x) for x in xrange(128))
            UNIBYTE_CHARS = set(chr(x) for x in xrange(256))
            URL_SAFE      = set('ABCDEFGHIJKLMNOPQRSTUVWXYZ'
                                'abcdefghijklmnopqrstuvwxyz'
                                '0123456789' '_.-/~')
            URL_UNSAFE = [ASCII_CHARS - URL_SAFE, UNIBYTE_CHARS - URL_SAFE]
            result = []
            unsafe = 1 if isinstance(shelf_name, unicode) else 0
            unsafe = URL_UNSAFE[unsafe]
            for char in shelf_name:
                try:
                    if not char in URL_SAFE:
                        char = ("%%%02x" % ord(char)).upper()
                        debug_print("urlquote - unsafe after ord char=", char)
                except:
                    char = "%%%02x" % ord(char).upper()
                result.append(char)
            return ''.join(result)


        debug_print("_order_series_shelves - shelves:", shelves, " options:", options)
        import re
        from urllib import quote
#        from calibre.ebooks.oeb.base import urlquote
        
        starting_shelves = 0
        shelves_ordered  = 0
        timeDiff         = timedelta(0, 1)
        sort_descending  = not options[cfg.KEY_SORT_DESCENDING]
        order_by         = options[cfg.KEY_ORDER_SHELVES_BY]
        update_config = options[cfg.KEY_SORT_UPDATE_CONFIG]
        if update_config:
            sonyConfig, config_file_path = self.get_config_file()

        import sqlite3 
        with closing(sqlite3.connect(self.device_database_path())) as connection:
            # return bytestrings if the content cannot the decoded as unicode
            connection.text_factory = lambda x: unicode(x, "utf-8", "ignore")
            connection.row_factory  = sqlite3.Row

            shelves_query = ("SELECT ShelfName, c.ContentId, c.Title, c.DateCreated, DateModified, Series, SeriesNumber "
                             "FROM ShelfContent sc JOIN content c on sc.ContentId= c.ContentId "
                             "WHERE sc._IsDeleted = 'false' "
                             "AND ShelfName = ? "
                             "ORDER BY ShelfName, SeriesNumber"
                            )
            update_query = ("UPDATE ShelfContent "
                            "SET DateModified = ? "
                            "WHERE ShelfName = ? "
                            "AND ContentID = ? "
                            )

            cursor = connection.cursor()
            for shelf in shelves:
                starting_shelves += 1
                debug_print("_order_series_shelves - shelf=%s, count=%d" % (shelf['name'], shelf['count']))
                if shelf['count'] <= 1:
                    continue
                shelves_ordered += 1
                shelf_data = (shelf['name'],)
                debug_print("_order_series_shelves - shelf_data:", shelf_data)
                cursor.execute(shelves_query, shelf_data)
                shelf_dict = {}
                for i, row in enumerate(cursor):
                    debug_print("_order_series_shelves - row:", i, row["ShelfName"], row["ContentId"], row['Series'], row["SeriesNumber"])
                    series_name = row['Series'] if row['Series'] else ''
                    try:
                        series_index = float(row["SeriesNumber"]) if row["SeriesNumber"] is not None else None
                    except:
                        debug_print("_order_series_shelves - non numeric number")
                        numbers = re.findall(r"\d*\.?\d+", row["SeriesNumber"])
                        if len(numbers) > 0:
                            series_index = float(numbers[0])
                    debug_print("_order_series_shelves - series_index=", series_index)
#                    series_index_str = "%10.4f"%series_index if series_index else ''
#                    sort_str = series_name + series_index_str + row['Title']
                    if order_by == cfg.KEY_ORDER_SHELVES_PUBLISHED:
                        sort_key = (row['DateCreated'], row['Title'])
                    else:
                        sort_key = (series_name, series_index, row['Title']) if not series_name == '' else (row['Title'])
                    series_entry = shelf_dict.get(sort_key, None)
                    if series_entry:
                        shelf_dict[sort_key].append(row['ContentId'])
                    else:
                        shelf_dict[sort_key] = [row['ContentId']]
                debug_print("_order_series_shelves - shelf_dict:", shelf_dict)
                
                debug_print("_order_series_shelves - sorted shelf_dict:", sorted(shelf_dict))
                
                lastModifiedTime = datetime.fromtimestamp(time.mktime(time.gmtime()))
                
                debug_print("_order_series_shelves - lastModifiedTime=", lastModifiedTime, " timeDiff:", timeDiff)
                for sort_key in sorted(shelf_dict, reverse=sort_descending):
                    for contentId in shelf_dict[sort_key]:
                        update_data = (strftime(self.device_timestamp_string(), lastModifiedTime.timetuple()), shelf['name'], contentId)
                        debug_print("_order_series_shelves - sort_key: ", sort_key,  " update_data:", update_data)
                        cursor.execute(update_query, update_data)
                        lastModifiedTime += timeDiff
                if update_config:
                    try:
                        shelf_key = quote("LastLibrarySorter_shelf_filterByBookshelf(" + shelf['name'] + ")")
                    except:
                        debug_print("_order_series_shelves - cannot encode shelf name=", shelf['name'])
                        if isinstance(shelf['name'], unicode):
                            debug_print("_order_series_shelves - is unicode")
                            shelf_key = urlquote(shelf['name'])
                            shelf_key = quote("LastLibrarySorter_shelf_filterByBookshelf(") + shelf_key + quote(")")
                        else:
                            debug_print("_order_series_shelves - not unicode")
                            shelf_key = "LastLibrarySorter_shelf_filterByBookshelf(" + shelf['name'] + ")"
                    sonyConfig.set('ApplicationPreferences', shelf_key , "sortByDateAddedToShelf()")
#                    debug_print("_order_series_shelves - set shelf_key=", shelf_key)

            cursor.close()
            connection.commit()
            if update_config:
                with open(config_file_path, 'wb') as config_file:
                    debug_print("_order_series_shelves - writing config file")
                    sonyConfig.write(config_file)
        debug_print("_order_series_shelves - end")
        return starting_shelves, shelves_ordered


    def _remove_duplicate_shelves(self, shelves, options):
        debug_print("_remove_duplicate_shelves - total shelves=%d: options=%s" % (len(shelves), options))
        import sqlite3 
        with closing(sqlite3.connect(self.device_database_path())) as connection:
            # return bytestrings if the content cannot the decoded as unicode
            connection.text_factory = lambda x: unicode(x, "utf-8", "ignore")
            connection.row_factory = sqlite3.Row

            starting_shelves    = 0
            shelves_removed     = 0
            finished_shelves    = 0

            shelves_update = ("UPDATE Shelf "
                              "SET _IsDeleted = 'true', "
                              "LastModified = ? "
                              "WHERE _IsSynced = 'true' "
                              "AND Name = ? "
                              "AND CreationDate <> ?"
                              )
            shelves_query = ("SELECT * FROM Shelf "
                              "WHERE _IsSynced = 'true' "
                              "AND Name = ? "
                              "AND CreationDate = ?"
                              )

            shelves_delete = ("DELETE FROM Shelf "
                              "WHERE _IsSynced = 'false' "
                              "AND Name = ? "
                              "AND CreationDate <> ? "
                              "AND _IsDeleted = 'true'"
                              )

            shelves_purge = ("DELETE FROM Shelf "
                             "WHERE _IsDeleted = 'true'"
                            )

            purge_shelves = options[cfg.KEY_PURGE_SHELVES]
            keep_newest   = options[cfg.KEY_KEEP_NEWEST_SHELF]

            cursor = connection.cursor()
    #        count_bookshelves = 0
            for shelf in shelves:
                starting_shelves += shelf[3]
                finished_shelves += 1
                if shelf[3] > 1:
                    debug_print("_remove_duplicate_shelves - shelf:", shelf[0], shelf[1], shelf[2], shelf[3])
                    timestamp = shelf[2] if keep_newest else shelf[1]
                    shelves_values = (shelf[0], timestamp.strftime(self.device_timestamp_string()))

                    cursor.execute(shelves_query, shelves_values)
                    for row in cursor:
                        debug_print("_remove_duplicate_shelves - row: ", row['Name'], row['CreationDate'], row['_IsDeleted'], row['_IsSynced'])

                    shelves_update_values = (strftime(self.device_timestamp_string(), time.gmtime()), shelf[0], timestamp.strftime(self.device_timestamp_string()))
                    debug_print("_remove_duplicate_shelves - marking as deleted:", shelves_update_values)
                    cursor.execute(shelves_update, shelves_update_values)
                    cursor.execute(shelves_delete, shelves_values)
                    shelves_removed += shelf[3] - 1

            if purge_shelves:
                debug_print("_remove_duplicate_shelves - purging all shelves marked as deleted")
                cursor.execute(shelves_purge)

            cursor.close()
            connection.commit()

        return starting_shelves, shelves_removed, finished_shelves


    def _check_device_database(self):
        return check_device_database(self.device_database_path())


    def _block_analytics(self):
        import sqlite3 
        with closing(sqlite3.connect(self.device_database_path())) as connection:
            connection.text_factory = lambda x: unicode(x, "utf-8", "ignore")
            cursor = connection.cursor()

            block_result = "The trigger on the AnalyticsEvents table has been removed."

            cursor.execute("DROP TRIGGER IF EXISTS BlockAnalyticsEvents")
            # Delete the Extended drvier version if it is there.
            cursor.execute("DROP TRIGGER IF EXISTS KTE_BlockAnalyticsEvents")

            if self.options[cfg.KEY_CREATE_ANALYTICSEVENTS_TRIGGER]:
                cursor.execute('DELETE FROM AnalyticsEvents')
                debug_print("sonyutilities:_block_analytics - creating trigger.")
                trigger_query = ('CREATE TRIGGER IF NOT EXISTS BlockAnalyticsEvents '
                                'AFTER INSERT ON AnalyticsEvents '
                                'BEGIN '
                                'DELETE FROM AnalyticsEvents; '
                                'END'
                                )
                cursor.execute(trigger_query)
                result = cursor.fetchall()

                if result is None:
                    block_result = None
                else:
                    debug_print("_block_analytics - result=", result)
                    block_result = "AnalyticsEvents have been blocked in the database."

            connection.commit()
            cursor.close()
        return block_result


    def _vacuum_device_database(self):
        import sqlite3 
        with closing(sqlite3.connect(self.device_database_path())) as connection:
            # return bytestrings if the content cannot the decoded as unicode
            connection.text_factory = lambda x: unicode(x, "utf-8", "ignore")

            compress_query = 'VACUUM'
            cursor = connection.cursor()

            compress_result = ''
            cursor.execute(compress_query)
            result = cursor.fetchall()
            if not result is None:
                debug_print("_vacuum_device_database - result=", result)
                for line in result:
                    compress_result += '\n' + line[0]
                    debug_print("_vacuum_device_database - result line=", line[0])
            else:
                compress_result = _("Execution of '%s' failed") % compress_query

            connection.commit()

            cursor.close()

        return compress_result


    def generate_metadata_query(self):
        debug_print("generate_metadata_query - self.supports_series=", self.supports_series)
        test_query = 'SELECT Title,   '\
                    '    Attribution, '\
                    '    Description, '\
                    '    Publisher,   '
        if self.supports_series:
            debug_print("generate_metadata_query - supports series is true")
            test_query += ' Series,       '\
                          ' SeriesNumber, '\
                          ' Subtitle, '
        else:
            test_query += ' null as Series, '      \
                          ' null as SeriesNumber,'
        test_query += ' ReadStatus, '        \
                      ' DateCreated, '       \
                      ' Language, '
        test_query += ' NULL as ISBN, '              \
                          ' NULL as FeedbackType, '      \
                          ' NULL as FeedbackTypeSynced, '\
                          ' NULL as Rating, '            \
                          ' NULL as DateModified '

        test_query += 'FROM content c1 '
        if self.supports_ratings:
            test_query += ' left outer join ratings r on c1.ContentID = r.ContentID '

        test_query += 'WHERE c1.BookId IS NULL '  \
                      'AND c1.ContentId = ?'
        debug_print("generate_metadata_query - test_query=%s" % test_query)
        return test_query

    def _update_metadata(self, books):
        from calibre.ebooks.metadata import authors_to_string
        from calibre.utils.localization import canonicalize_lang, lang_as_iso639_1

        updated_books       = 0
        not_on_device_books = 0
        unchanged_books     = 0
        count_books         = 0

        from calibre.library.save_to_disk import find_plugboard
        plugboards = self.gui.library_view.model().db.prefs.get('plugboards', {})
        debug_print("update_metadata: plugboards=", plugboards)
        debug_print("update_metadata: self.device.__class__.__name__=", self.device.__class__.__name__)

        library_db     = self.gui.current_db
        library_config = cfg.get_library_config(library_db)
#         rating_column  = library_config.get(cfg.KEY_RATING_CUSTOM_COLUMN, cfg.DEFAULT_LIBRARY_VALUES[cfg.KEY_RATING_CUSTOM_COLUMN])

        import sqlite3 
        with closing(sqlite3.connect(self.device_database_path())) as connection:
            # return bytestrings if the content cannot the decoded as unicode
            connection.text_factory = lambda x: unicode(x, "utf-8", "ignore")
            connection.row_factory = sqlite3.Row

            test_query = self.generate_metadata_query()
            cursor = connection.cursor()

            for book in books:
#                device_book_paths = self.get_device_paths_from_id(book.id)
                for contentID in book.contentIDs:
                    debug_print("_update_metadata - searching for contentId='%s'" % (contentID))
                    if not contentID:
                        contentID = self.contentid_from_path(book.path)
                    count_books += 1
                    query_values = (contentID,)
                    cursor.execute(test_query, query_values)
                    result = cursor.fetchone()
                    if result is not None:
                        debug_print("_update_metadata - found contentId='%s'" % (contentID))
#                        debug_print("    result=", result)
#                        debug_print("    result.keys()=", result.keys())
#                        debug_print("    result[0]=", result[0])
#                        debug_print("    result['Title']=", result[result.keys()[0]])
#                        debug_print("    result.keys()[0]=", result.keys()[0])
#                        debug_print("    type(result.keys()[0])=", type(result.keys()[0]))
#                        debug_print("    type('title')=", type('title'))
#                        debug_print("    type('title)=", type("title"))
                        #self.device.delete_images(result[0])

                        title_string = None
                        authors_string = None
                        if self.options[cfg.KEY_USE_PLUGBOARD] and plugboards is not None:
                            book_format = os.path.splitext(contentID)[1][1:]
                            debug_print("_update_metadata - format='%s'" % (book_format))
                            plugboard = find_plugboard(self.device.__class__.__name__,
                                                       book_format, plugboards)
                            debug_print("update_metadata: plugboard=", plugboard)
                            newmi = book.deepcopy_metadata()
                            if plugboard is not None:
                                newmi.template_to_attribute(book, plugboard)
                            newmi.series_index_string = book.series_index_string
                        else:
                            newmi = book
                            if self.options[cfg.KEY_USE_TITLE_SORT]:
                                title_string = newmi.title_sort
                            if self.options[cfg.KEY_USE_AUTHOR_SORT]:
                                debug_print("update_metadata: author=", newmi.authors)
                                debug_print("update_metadata: using author_sort=", newmi.author_sort)
#                                newmi.authors = newmi.author_sort
                                debug_print("update_metadata: using author_sort - author=", newmi.authors)
                                authors_string = newmi.author_sort
                        debug_print("update_metadata: title_string=", title_string)
                        title_string   = newmi.title if title_string is None else title_string
                        debug_print("update_metadata: title_string=", title_string)
                        debug_print("update_metadata: authors_string=", authors_string)
                        authors_string = authors_to_string(newmi.authors) if authors_string is None else authors_string
                        debug_print("update_metadata: authors_string=", authors_string)

                        update_query  = 'UPDATE content SET '
                        update_values = []
                        set_clause    = ''
                        changes_found = False
                        rating_values = []
                        rating_change_query = None
    
                        if self.options[cfg.KEY_SET_TITLE] and not result["Title"] == title_string:
                            set_clause += ', Title  = ? '
                            update_values.append(title_string)
                        if self.options[cfg.KEY_SET_AUTHOR] and not result["Attribution"] == authors_string:
                            set_clause += ', Attribution  = ? '
                            update_values.append(authors_string)
                        if self.options[cfg.KEY_SET_DESCRIPTION]  and not result["Description"] == newmi.comments:
                            set_clause += ', Description = ? '
                            update_values.append(newmi.comments)
                        if self.options[cfg.KEY_SET_PUBLISHER]  and not result["Publisher"] == newmi.publisher:
                            set_clause += ', Publisher = ? '
                            update_values.append(newmi.publisher)
                        if self.options[cfg.KEY_SET_PUBLISHED_DATE]:
                            pubdate_string = strftime(self.device_timestamp_string(), newmi.pubdate)
                            if not (result["DateCreated"] == pubdate_string):
                                set_clause += ', DateCreated = ? '
                                debug_print("_update_metadata - convert_sony_date(result['DateCreated'])=", convert_sony_date(result["DateCreated"]))
                                debug_print("_update_metadata - convert_sony_date(result['DateCreated']).__class__=", convert_sony_date(result["DateCreated"]).__class__)
                                debug_print("_update_metadata - newmi.pubdate  =", newmi.pubdate)
                                debug_print("_update_metadata - result['DateCreated']     =", result["DateCreated"])
                                debug_print("_update_metadata - pubdate_string=", pubdate_string)
                                debug_print("_update_metadata - newmi.pubdate.__class__=", newmi.pubdate.__class__)
                                update_values.append(pubdate_string)

                        if self.options[cfg.KEY_SET_ISBN]  and not result["ISBN"] == newmi.isbn:
                            set_clause += ', ISBN = ? '
                            update_values.append(newmi.isbn)

                        if self.options[cfg.KEY_SET_LANGUAGE] and not result["Language"] == lang_as_iso639_1(newmi.language):
                            debug_print("_update_metadata - newmi.language =", newmi.language)
                            debug_print("_update_metadata - lang_as_iso639_1(newmi.language)=", lang_as_iso639_1(newmi.language))
                            debug_print("_update_metadata - canonicalize_lang(newmi.language)=", canonicalize_lang(newmi.language))
#                            set_clause += ', ISBN = ? '
#                            update_values.append(newmi.isbn)

                        if self.options[cfg.KEY_SET_NOT_INTERESTED] and not (result["FeedbackType"] == 2 or result["FeedbackTypeSynced"] == 1):
                            set_clause += ', FeedbackType = ? '
                            update_values.append(2)
                            set_clause += ', FeedbackTypeSynced = ? '
                            update_values.append(1)

                        if self.supports_series:
                            debug_print("_update_metadata - self.options['series']", self.options['series'])
                            debug_print("_update_metadata - newmi.series=", newmi.series, "newmi.series_index=", newmi.series_index)
                            debug_print("_update_metadata - result['Series'] ='%s' result['SeriesNumber'] =%s" % (result["Series"], result["SeriesNumber"]))
                            debug_print("_update_metadata - result['Series'] == newmi.series =", (result["Series"] == newmi.series))
                            series_index_str = ("%g" % newmi.series_index) if newmi.series_index is not None else None
                            debug_print('_update_metadata - result["SeriesNumber"] == series_index_str =', (result["SeriesNumber"] == series_index_str))
                            debug_print('_update_metadata - not (result["Series"] == newmi.series or result["SeriesNumber"] == series_index_str) =', not (result["Series"] == newmi.series or result["SeriesNumber"] == series_index_str))
                            if self.options['series'] and not (result["Series"] == newmi.series and (result["SeriesNumber"] == book.series_index_string or result["SeriesNumber"] == series_index_str)):
                                debug_print("_update_metadata - setting series")
                                set_clause += ', Series  = ? '
                                set_clause += ', SeriesNumber   = ? '
                                if newmi.series is None or newmi.series == '':
                                    update_values.append(None)
                                    update_values.append(None)
                                else:
                                    update_values.append(newmi.series)
    #                                update_values.append("%g" % newmi.series_index)
                                    if newmi.series_index_string is not None:
                                        update_values.append(newmi.series_index_string)
                                    elif newmi.series_index is None:
                                        update_values.append(None)
                                    else:
                                        update_values.append("%g" % newmi.series_index)
    
                        if self.options[cfg.KEY_SET_TAGS_IN_SUBTITLE] and (
                                result["Subtitle"] is None or result["Subtitle"] == '' or result["Subtitle"][:3] == "t::" or result["Subtitle"][1] == "@"):
                            debug_print("_update_metadata - newmi.tags =", newmi.tags)
                            tag_str = None
                            if len(newmi.tags):
                                tag_str = " @".join(newmi.tags)
                                tag_str = "@" + " @".join(newmi.tags)
                            debug_print("_update_metadata - tag_str =", tag_str)
                            set_clause += ', Subtitle = ? '
                            update_values.append(tag_str)

    #                    debug_print("_update_metadata - self.options['setRreadingStatus']", self.options['setRreadingStatus'])
    #                    debug_print("_update_metadata - self.options['readingStatus']", self.options['readingStatus'])
    #                    debug_print("_update_metadata - not (result[6] == self.options['readingStatus'])", not (result[6] == self.options['readingStatus']))
                        if self.options['setRreadingStatus'] and (not (result["ReadStatus"] == self.options['readingStatus']) or self.options['resetPosition']):
                            set_clause += ', ReadStatus  = ? '
                            update_values.append(self.options['readingStatus'])
                            if self.options['resetPosition']:
                                set_clause += ', DateLastRead = ?'
                                update_values.append(None)
                                set_clause += ', bookmark = ?'
                                update_values.append(None)
                                set_clause += ', ___PercentRead = ?'
                                update_values.append(0)
                                set_clause += ', FirstTimeReading = ? '
                                update_values.append(self.options['readingStatus'] < 2)
    
                        if len(set_clause) > 0:
                            update_query += set_clause[1:]
                            changes_found = True

                        if not (changes_found or rating_change_query):
                            debug_print("_update_metadata - no changes found to selected metadata. No changes being made.")
                            unchanged_books += 1
                            continue
    
                        update_query += 'WHERE ContentID = ? AND BookID IS NULL'
                        update_values.append(contentID)
                        debug_print("_update_metadata - update_query=%s" % update_query)
                        debug_print("_update_metadata - update_values= ", update_values)
                        try:
                            if changes_found:
                                cursor.execute(update_query, update_values)

                            if rating_change_query:
                                debug_print("_update_metadata - rating_change_query=%s" % rating_change_query)
                                debug_print("_update_metadata - rating_values= ", rating_values)
                                cursor.execute(rating_change_query, rating_values)

                            updated_books += 1
                        except:
                            debug_print('    Database Exception:  Unable to set series info')
                            raise
                    else:
                        debug_print("_update_metadata - no match for title='%s' contentId='%s'" % (book.title, contentID))
                        not_on_device_books += 1
                    connection.commit()
            debug_print("Update summary: Books updated=%d, unchanged books=%d, not on device=%d, Total=%d" % (updated_books, unchanged_books, not_on_device_books, count_books))

            cursor.close()
        
        return (updated_books, unchanged_books, not_on_device_books, count_books)


    def _store_current_bookmark(self, books, options=None):
        
        if options:
            self.options = options

        books_with_bookmark    = 0
        books_without_bookmark = 0
        count_books            = 0
        clear_if_unread          = self.options[cfg.KEY_CLEAR_IF_UNREAD]
        store_if_more_recent     = self.options[cfg.KEY_STORE_IF_MORE_RECENT]
        do_not_store_if_reopened = self.options[cfg.KEY_DO_NOT_STORE_IF_REOPENED]
        
        import sqlite3 
        with closing(sqlite3.connect(self.device_database_path())) as connection:
            # return bytestrings if the content cannot the decoded as unicode
            connection.text_factory = lambda x: unicode(x, "utf-8", "ignore")

            library_db = self.gui.current_db
            library_config = cfg.get_library_config(library_db)
            sony_bookmark_column = library_config.get(cfg.KEY_CURRENT_LOCATION_CUSTOM_COLUMN, cfg.DEFAULT_LIBRARY_VALUES[cfg.KEY_CURRENT_LOCATION_CUSTOM_COLUMN])
            sony_percentRead_column         = library_config.get(cfg.KEY_PERCENT_READ_CUSTOM_COLUMN, cfg.DEFAULT_LIBRARY_VALUES[cfg.KEY_PERCENT_READ_CUSTOM_COLUMN])
            rating_column                   = library_config.get(cfg.KEY_RATING_CUSTOM_COLUMN, cfg.DEFAULT_LIBRARY_VALUES[cfg.KEY_RATING_CUSTOM_COLUMN])
            last_read_column                = library_config.get(cfg.KEY_LAST_READ_CUSTOM_COLUMN, cfg.DEFAULT_LIBRARY_VALUES[cfg.KEY_LAST_READ_CUSTOM_COLUMN])
            if sony_bookmark_column:
                debug_print("_store_current_bookmark - sony_bookmark_column=", sony_bookmark_column)
#                sony_bookmark_col = custom_cols[sony_bookmark_column]
#                debug_print("_store_current_bookmark - sony_bookmark_col=", sony_bookmark_col)
                sony_bookmark_col_label = library_db.field_metadata.key_to_label(sony_bookmark_column)
                debug_print("_store_current_bookmark - sony_bookmark_col_label=", sony_bookmark_col_label)
            if sony_percentRead_column:
#                sony_percentRead_col = custom_cols[sony_percentRead_column]
                sony_percentRead_col_label = library_db.field_metadata.key_to_label(sony_percentRead_column)

            rating_col_label = library_db.field_metadata.key_to_label(rating_column) if rating_column else ''
            if last_read_column:
#                sony_percentRead_col = custom_cols[sony_percentRead_column]
                last_read_col_label = library_db.field_metadata.key_to_label(last_read_column)

            debug_print("_store_current_bookmark - sony_bookmark_column=", sony_bookmark_column)
            debug_print("_store_current_bookmark - sony_percentRead_column=", sony_percentRead_column) 
            debug_print("_store_current_bookmark - rating_column=", rating_column) 
            debug_print("_store_current_bookmark - rating_col_label=", rating_col_label) 
            debug_print("_store_current_bookmark - last_read_column=", last_read_column) 

#            id_map = {}
            cursor = connection.cursor()
            for book in books:
                count_books += 1
#                mi = Metadata('Unknown')
                for contentID in book.contentIDs:
                    debug_print("_store_current_bookmark - contentId='%s'" % (contentID))
                    fetch_values = (contentID,)
                    fetch_query = EPUB_FETCH_QUERY
                    debug_print("_store_current_bookmark - fetch_query='%s'" % (fetch_query))
                    cursor.execute(fetch_query, fetch_values)
                    result = cursor.fetchone()
                    
                    sony_bookmark = None
                    sony_percentRead         = None
                    last_read                = None
                    update_library           = False
                    if result is not None: 
                        debug_print("_store_current_bookmark - result=", result)
                        books_with_bookmark += 1
                        if result[2] == 0 and clear_if_unread:
                            sony_bookmark = None
                            sony_percentRead         = None
                            last_read                = None
                            update_library           = True
                        else:
                            update_library = True
                            if result[7] == MIMETYPE_SONY:
                                sony_bookmark = result[0]
                            else:
                                sony_bookmark = result[0][len(contentID) + 1:] if result[0] else None
                    
                            if result[2] == 1: # or (result[2] == 0 and result[3] > 0):
                                sony_percentRead = result[3]
                            elif result[2] == 2:
                                sony_percentRead = 100

                            if result[8]:
                                sony_rating = result[8] * 2
                            else:
                                sony_rating = 0
                                
                            if result[5]:
                                debug_print("_store_current_bookmark - result[5]=", result[5])
                                last_read = convert_sony_date(result[5])
                                debug_print("_store_current_bookmark - last_read=", last_read)

                            if last_read_column and store_if_more_recent:
            #                    last_read_col_label['#value#'] = last_read
                                current_last_read = book.get_user_metadata(last_read_column, True)['#value#']
                                debug_print("_store_current_bookmark - book.get_user_metadata(last_read_column, True)['#value#']=", current_last_read)
                                debug_print("_store_current_bookmark - setting mi.last_read=", last_read)
                                debug_print("_store_current_bookmark - store_if_more_recent - current_last_read < last_read=", current_last_read < last_read)
                                if current_last_read and last_read:
                                    update_library &= current_last_read < last_read
                                elif last_read:
                                    update_library &= True

                            if sony_percentRead_column and do_not_store_if_reopened:
                                current_percentRead = book.get_user_metadata(sony_percentRead_column, True)['#value#']
                                debug_print("_store_current_bookmark - do_not_store_if_reopened - current_percentRead=", current_percentRead)
                                update_library &= current_percentRead < 100

                    elif self.options[cfg.KEY_CLEAR_IF_UNREAD]:
                        books_with_bookmark += 1
                        sony_bookmark        = None
                        sony_percentRead     = None
                        last_read            = None
                        update_library       = True
                    else:
                        books_without_bookmark += 1
                        continue
                    
                    if update_library:
                        debug_print("_store_current_bookmark - sony_bookmark='%s'" % (sony_bookmark))
                        debug_print("_store_current_bookmark - sony_percentRead=", sony_percentRead)
                        if sony_bookmark_column:
                            if sony_bookmark:
                                new_value = sony_bookmark
                            else:
        #                        sony_bookmark_col['#value#'] = None
                                new_value = None
                                debug_print("_store_current_bookmark - setting bookmark column to None")
        #                    mi.set_user_metadata(sony_bookmark_column, sony_bookmark_col)
                            debug_print("_store_current_bookmark - bookmark - on sony=", new_value)
                            debug_print("_store_current_bookmark - bookmark - in library=", book.get_user_metadata(sony_bookmark_column, True)['#value#'])
                            debug_print("_store_current_bookmark - bookmark - on sony==in library=", new_value == book.get_user_metadata(sony_bookmark_column, True)['#value#'])
                            old_value = book.get_user_metadata(sony_bookmark_column, True)['#value#']
                            if not old_value == new_value: 
                                library_db.set_custom(book.calibre_id, new_value, label=sony_bookmark_col_label, commit=False)
    
                        if sony_percentRead_column:
        #                    sony_percentRead_col['#value#'] = sony_percentRead
                            debug_print("_store_current_bookmark - setting mi.sony_percentRead=", sony_percentRead)
                            current_percentRead = book.get_user_metadata(sony_percentRead_column, True)['#value#']
                            debug_print("_store_current_bookmark - percent read - in book=", current_percentRead)
                            if not current_percentRead == sony_percentRead:
                                library_db.set_custom(book.calibre_id, sony_percentRead, label=sony_percentRead_col_label, commit=False)
        #                    mi.set_user_metadata(sony_percentRead_column, sony_percentRead_col)
    
                        if last_read_column:
        #                    last_read_col_label['#value#'] = last_read
                            current_last_read = book.get_user_metadata(last_read_column, True)['#value#']
                            debug_print("_store_current_bookmark - book.get_user_metadata(last_read_column, True)['#value#']=", current_last_read)
                            debug_print("_store_current_bookmark - setting mi.last_read=", last_read)
                            debug_print("_store_current_bookmark - current_last_read == last_read=", current_last_read == last_read)
                            if not current_last_read == last_read:
                                library_db.set_custom(book.calibre_id, last_read, label=last_read_col_label, commit=False)
        #                    mi.set_user_metadata(last_read_column, last_read_col_label)
    
        #                debug_print("_store_current_bookmark - mi=", mi)
        #                id_map[book.calibre_id] = mi
                    else:
                        books_with_bookmark    -= 1
                        books_without_bookmark += 1

            connection.commit()
            cursor.close()
            
#            edit_metadata_action = self.gui.iactions['Edit Metadata']
#            edit_metadata_action.apply_metadata_changes(id_map)
            library_db.commit()
        
        return (books_with_bookmark, books_without_bookmark, count_books)


    def _restore_current_bookmark(self, books):
        updated_books       = 0
        not_on_device_books = 0
        count_books         = 0

        library_db     = self.gui.current_db
        library_config = cfg.get_library_config(library_db)
        sony_bookmark_column = library_config.get(cfg.KEY_CURRENT_LOCATION_CUSTOM_COLUMN, cfg.DEFAULT_LIBRARY_VALUES[cfg.KEY_CURRENT_LOCATION_CUSTOM_COLUMN])
        sony_percentRead_column         = library_config.get(cfg.KEY_PERCENT_READ_CUSTOM_COLUMN, cfg.DEFAULT_LIBRARY_VALUES[cfg.KEY_PERCENT_READ_CUSTOM_COLUMN])
        rating_column                   = library_config.get(cfg.KEY_RATING_CUSTOM_COLUMN, cfg.DEFAULT_LIBRARY_VALUES[cfg.KEY_RATING_CUSTOM_COLUMN])
        last_read_column                = library_config.get(cfg.KEY_LAST_READ_CUSTOM_COLUMN, cfg.DEFAULT_LIBRARY_VALUES[cfg.KEY_LAST_READ_CUSTOM_COLUMN])

        chapter_query = 'SELECT c1.bookmark, ' \
                               'c1.ReadStatus, '          \
                               'c1.___PercentRead, '      \
                               'c1.Attribution, '         \
                               'c1.DateLastRead, '        \
                               'c1.Title, '               \
                               'c1.MimeType '
        chapter_query += 'FROM content c1 '
        chapter_query += 'WHERE c1.BookId IS NULL '  \
                      'AND c1.ContentId = ?'

        chapter_update  = 'UPDATE content '                \
                            'SET bookmark = ? ' \
                            '  , FirstTimeReading = ? '    \
                            '  , ReadStatus = ? '          \
                            '  , ___PercentRead = ? '      \
                            '  , DateLastRead = ? '        \
                            'WHERE BookID IS NULL '        \
                            'AND ContentID = ?'

        import sqlite3 
        with closing(sqlite3.connect(self.device_database_path()
            )) as connection:
            # return bytestrings if the content cannot the decoded as unicode
            connection.text_factory = lambda x: unicode(x, "utf-8", "ignore")
            connection.row_factory = sqlite3.Row

            cursor = connection.cursor()

            for book in books:
                count_books += 1
                for contentID in book.contentIDs:
                    chapter_values = (contentID,)
                    cursor.execute(chapter_query, chapter_values)
                    result = cursor.fetchone()
                    
                    if result is not None: # and not result[6] == MIMETYPE_SONY:
                        debug_print("_restore_current_bookmark - result= ", result)
                        chapter_update          = 'UPDATE content SET '
                        chapter_set_clause      = ''
                        chapter_values          = []
                        location_update         = 'UPDATE content SET '
                        location_set_clause     = ''
                        location_values         = []
                        
                        sony_bookmark           = None
                        sony_percentRead        = None
    
                        if sony_bookmark_column:
                            reading_location_string  = book.get_user_metadata(sony_bookmark_column, True)['#value#']
                            debug_print("_restore_current_bookmark - reading_location_string=", reading_location_string)
                            if reading_location_string:
                                if result['MimeType'] == MIMETYPE_SONY:
                                    sony_bookmark = reading_location_string
                                else:
                                    reading_location_parts   = reading_location_string.split(BOOKMARK_SEPARATOR)
                                    sony_bookmark = (contentID + "#" + reading_location_parts[0]) if len(reading_location_parts) > 0 else None
                            else:
                                sony_bookmark = None
                        
                            if reading_location_string:
                                chapter_values.append(sony_bookmark)
                                chapter_set_clause += ', bookmark  = ? '
                            else:
                                debug_print("_restore_current_bookmark - reading_location_string=", reading_location_string)

                        if sony_percentRead_column:
                            sony_percentRead = book.get_user_metadata(sony_percentRead_column, True)['#value#']
                            sony_percentRead = sony_percentRead if sony_percentRead else result['___PercentRead']
                            chapter_values.append(sony_percentRead)
                            chapter_set_clause += ', ___PercentRead  = ? '

                        if self.options[cfg.KEY_READING_STATUS]:
                            if sony_percentRead:
                                debug_print("_restore_current_bookmark - chapter_values= ", chapter_values)
                                if sony_percentRead == 100:
                                    chapter_values.append(2)
                                    debug_print("_restore_current_bookmark - chapter_values= ", chapter_values)
                                else:
                                    chapter_values.append(1)
                                    debug_print("_restore_current_bookmark - chapter_values= ", chapter_values)
                                chapter_set_clause += ', ReadStatus  = ? '
                                chapter_values.append('false')
                                chapter_set_clause += ', FirstTimeReading = ? '

                        last_read = None
                        if self.options[cfg.KEY_DATE_TO_NOW]:
                            chapter_values.append(strftime(self.device_timestamp_string(), time.gmtime()))
                            chapter_set_clause += ', DateLastRead  = ? '
                        elif last_read_column:
                            last_read = book.get_user_metadata(last_read_column, True)['#value#']
                            if last_read is not None:
                                chapter_values.append(last_read.strftime(self.device_timestamp_string()))
                                chapter_set_clause += ', DateLastRead  = ? '

                        debug_print("_restore_current_bookmark - found contentId='%s'" % (contentID))
                        debug_print("_restore_current_bookmark - sony_bookmark=", sony_bookmark)
                        debug_print("_restore_current_bookmark - sony_percentRead=", sony_percentRead)
                        debug_print("_restore_current_bookmark - last_read=", last_read)
#                        debug_print("    result=", result)
    
                        if len(chapter_set_clause) > 0:
                            chapter_update += chapter_set_clause[1:]
                            chapter_update += 'WHERE ContentID = ? AND BookID IS NULL'
                            chapter_values.append(contentID)
                        else:
                            debug_print("_restore_current_bookmark - no changes found to selected metadata. No changes being made.")
                            not_on_device_books += 1
                            continue
    
                        debug_print("_restore_current_bookmark - chapter_update=%s" % chapter_update)
                        debug_print("_restore_current_bookmark - chapter_values= ", chapter_values)
                        try:
                            cursor.execute(chapter_update, chapter_values)
                                
                            updated_books += 1
                        except:
                            debug_print('    Database Exception:  Unable to set bookmark info.')
                            raise
                    else:
                        debug_print("_restore_current_bookmark - no match for title='%s' contentId='%s'" % (book.title, book.contentID))
                        not_on_device_books += 1
                    connection.commit()
            debug_print("_restore_current_bookmark - Update summary: Books updated=%d, not on device=%d, Total=%d" % (updated_books, not_on_device_books, count_books))

            cursor.close()
        
        return (updated_books, not_on_device_books, count_books)



    def fetch_book_fonts(self):
        debug_print("fetch_book_fonts - start")
        import sqlite3 
        with closing(sqlite3.connect(self.device.normalize_path(
            self.device_path + DBPATH))) as connection:
            # return bytestrings if the content cannot the decoded as unicode
            connection.text_factory = lambda x: unicode(x, "utf-8", "ignore")

            book_options = {}
            
            fetch_query = 'SELECT  '                   \
                            '"ReadingFontFamily", '    \
                            '"ReadingFontSize", '      \
                            '"ReadingAlignment", '     \
                            '"ReadingLineHeight", '    \
                            '"ReadingLeftMargin", '    \
                            '"ReadingRightMargin"  '   \
                            'FROM content_settings '   \
                            'WHERE ContentId = ?'
            fetch_values = (self.single_contentID,)

            cursor = connection.cursor()
            cursor.execute(fetch_query, fetch_values)
            result = cursor.fetchone()
            if result is not None:
                book_options['readingFontFamily']   = result[0]
                book_options['readingFontSize']     = result[1]
                book_options['readingAlignment']    = result[2].title()
                book_options['readingLineHeight']   = result[3]
                book_options['readingLeftMargin']   = result[4]
                book_options['readingRightMargin']  = result[5]
            connection.commit()

            cursor.close()
        
        return book_options


    def device_timestamp_string(self):
        if not self.timestamp_string:
            if "TIMESTAMP_STRING" in dir(self.device):
                self.timestamp_string = self.device.TIMESTAMP_STRING
            else:
                self.timestamp_string = "%Y-%m-%dT%H:%M:%SZ"
        return self.timestamp_string


    def _set_reader_fonts(self, contentIDs, delete=False):
        debug_print("_set_reader_fonts - start")
        updated_fonts  = 0
        added_fonts    = 0
        deleted_fonts  = 0
        count_books    = 0

        import sqlite3 
        with closing(sqlite3.connect(self.device.normalize_path(
            self.device_path + DBPATH))) as connection:
            # return bytestrings if the content cannot the decoded as unicode
            connection.text_factory = lambda x: unicode(x, "utf-8", "ignore")

            test_query = 'SELECT 1 '                    \
                            'FROM content_settings '    \
                            'WHERE ContentId = ?'
            delete_query = 'DELETE FROM content_settings '    \
                            'WHERE ContentId = ?'

            if not delete:
                font_face       = self.options[cfg.KEY_READING_FONT_FAMILY]
                justification   = self.options[cfg.KEY_READING_ALIGNMENT].lower()
                justification   = '' if justification == 'off' else justification
                font_size       = self.options[cfg.KEY_READING_FONT_SIZE]
                line_spacing    = self.options[cfg.KEY_READING_LINE_HEIGHT]
                left_margins    = self.options[cfg.KEY_READING_LEFT_MARGIN]
                right_margins   = self.options[cfg.KEY_READING_RIGHT_MARGIN]
               
                add_query = 'INSERT INTO content_settings ( '   \
                                '"DateModified", '              \
                                '"ReadingFontFamily", '         \
                                '"ReadingFontSize", '           \
                                '"ReadingAlignment", '          \
                                '"ReadingLineHeight", '         \
                                '"ReadingLeftMargin", '         \
                                '"ReadingRightMargin", '        \
                                '"ContentID" '                  \
                                ') '                            \
                            'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)'
                add_values = (
                              time.strftime(self.device_timestamp_string(), time.gmtime()), 
                              font_face, 
                              font_size, 
                              justification, 
                              line_spacing, 
                              left_margins, 
                              right_margins, 
                              )
                update_query = 'UPDATE content_settings '    \
                                'SET "DateModified" = ?, '   \
                                '"ReadingFontFamily" = ?, '  \
                                '"ReadingFontSize" = ?, '    \
                                '"ReadingAlignment" = ?, '   \
                                '"ReadingLineHeight" = ?, '  \
                                '"ReadingLeftMargin" = ?, '  \
                                '"ReadingRightMargin" = ? '  \
                                'WHERE ContentId = ?'
                update_values = (
                                 time.strftime(self.device_timestamp_string(), time.gmtime()), 
                                 font_face, 
                                 font_size, 
                                 justification, 
                                 line_spacing, 
                                 left_margins, 
                                 right_margins, 
                                 )

            cursor = connection.cursor()

            for contentID in contentIDs:
                test_values = (contentID,)
                if delete:
                    cursor.execute(delete_query, test_values)
                    deleted_fonts += 1
                else:
                    cursor.execute(test_query, test_values)
                    result = cursor.fetchone()
                    if result is None:
                        cursor.execute(add_query, add_values + (contentID,))
                        added_fonts += 1
                    else:
                        cursor.execute(update_query, update_values + (contentID,))
                        updated_fonts += 1
                connection.commit()
                count_books += 1

            cursor.close()
        
        return updated_fonts, added_fonts, deleted_fonts, count_books


    def get_config_file(self):
        config_file_path = self.device.normalize_path(self.device._main_prefix + '.sony/Sony/Sony eReader.conf')
        sonyConfig = ConfigParser.SafeConfigParser(allow_no_value=True)
        sonyConfig.optionxform = str
        debug_print("_update_config_reader_settings - config_file_path=", config_file_path)
        sonyConfig.read(config_file_path)
        
        return sonyConfig, config_file_path

    def _update_config_reader_settings(self, options):
        sonyConfig, config_file_path = self.get_config_file()

        sonyConfig.set('Reading', cfg.KEY_READING_FONT_FAMILY,  options[cfg.KEY_READING_FONT_FAMILY])
        sonyConfig.set('Reading', cfg.KEY_READING_ALIGNMENT,    options[cfg.KEY_READING_ALIGNMENT])
        sonyConfig.set('Reading', cfg.KEY_READING_FONT_SIZE,    "%g" % options[cfg.KEY_READING_FONT_SIZE])
        sonyConfig.set('Reading', cfg.KEY_READING_LINE_HEIGHT,  "%g" % options[cfg.KEY_READING_LINE_HEIGHT])
        sonyConfig.set('Reading', cfg.KEY_READING_LEFT_MARGIN,  "%g" % options[cfg.KEY_READING_LEFT_MARGIN])
        sonyConfig.set('Reading', cfg.KEY_READING_RIGHT_MARGIN, "%g" % options[cfg.KEY_READING_RIGHT_MARGIN])
        
        with open(config_file_path, 'wb') as config_file:
            sonyConfig.write(config_file)


    def device_database_path(self, prefix=None):
        if not prefix:
            prefix = self.current_location['prefix']
        return self.device.normalize_path(prefix + DBPATH)


    def show_help1(self):
        self.show_help()

    def show_help(self, anchor=''):
        debug_print("show_help - anchor=", anchor)
        # Extract on demand the help file resource
        def get_help_file_resource():
            # We will write the help file out every time, in case the user upgrades the plugin zip
            # and there is a later help file contained within it.
            HELP_FILE = 'sonyutilities_Help.html'
            file_path = os.path.join(config_dir, 'plugins', HELP_FILE)
            file_data = self.load_resources(HELP_FILE)[HELP_FILE]
            with open(file_path,'w') as f:
                f.write(file_data)
            return file_path
        debug_print("show_help - anchor=", anchor)
        url = 'file:///' + get_help_file_resource()
        url = QUrl(url)
        if not (anchor or anchor == ''):
            url.setFragment(anchor)
        open_url(url)

    def convert_sony_date(self, sony_date):
        return convert_sony_date(sony_date)


def check_device_database(database_path):
    import sqlite3 
    with closing(sqlite3.connect(database_path)) as connection:
        # return bytestrings if the content cannot the decoded as unicode
        connection.text_factory = lambda x: unicode(x, "utf-8", "ignore")

        check_query = 'PRAGMA integrity_check'
        cursor = connection.cursor()

        check_result = ''
        cursor.execute(check_query)
        result = cursor.fetchall()
        if not result is None:
            for line in result:
                check_result += '\n' + line[0]
#                debug_print("_check_device_database - result line=", line[0])
        else:
            check_result = _("Execution of '%s' failed") % check_query

        connection.commit()

        cursor.close()

    return check_result


def convert_sony_date(sony_date):
    from calibre.utils.date import utc_tz
    if sony_date:
        converted_date = datetime.fromtimestamp(sony_date/1000).replace(tzinfo=utc_tz)
    else:
        converted_date = None
    return converted_date
