#!/usr/bin/python
# -*- coding: UTF-8 -*-
from __future__ import (unicode_literals, division, absolute_import,
                        print_function)

__license__   = 'GPL v3'
__copyright__ = '2012, David Forrester <davidfor@internode.on.net>'
__docformat__ = 'restructuredtext en'

import re
import ConfigParser
from datetime import datetime
from contextlib import closing

from calibre_plugins.sonyutilities.common_utils import debug_print
try:
    from PyQt5.Qt import (QDialog, QVBoxLayout, QLabel, QCheckBox, QGridLayout, QRadioButton, QComboBox, QSpinBox,
                          QGroupBox, Qt, QDialogButtonBox, QHBoxLayout, QPixmap, QTableWidget, QAbstractItemView,
                          QProgressDialog, QTimer, QLineEdit, QPushButton, QDoubleSpinBox, QButtonGroup,
                          QSpacerItem, QToolButton, QTableWidgetItem, QAction, QApplication, QUrl)
    from PyQt5 import QtWidgets as QtGui
except ImportError as e:
    debug_print("Error loading QT5: ", e)
    from PyQt4.Qt import (QDialog, QVBoxLayout, QLabel, QCheckBox, QGridLayout, QRadioButton, QComboBox, QSpinBox,
                          QGroupBox, Qt, QDialogButtonBox, QHBoxLayout, QPixmap, QTableWidget, QAbstractItemView,
                          QProgressDialog, QTimer, QLineEdit, QPushButton, QDoubleSpinBox, QButtonGroup,
                          QSpacerItem, QToolButton, QTableWidgetItem, QAction, QApplication, QUrl)
    from PyQt4 import QtGui

from calibre.ebooks.metadata import authors_to_string
from calibre.gui2 import gprefs, warning_dialog, error_dialog, question_dialog, open_url, choose_dir

from functools import partial
from urllib import quote_plus

from calibre.gui2.complete2 import EditWithComplete
from calibre.utils.config import tweaks
from calibre.utils.date import qt_to_dt, utc_tz
from calibre.utils.icu import sort_key

try:
    from calibre.gui2 import QVariant
    del QVariant
except ImportError:
    is_qt4 = False
    convert_qvariant = lambda x: x
else:
    is_qt4 = True

    def convert_qvariant(x):
        vt = x.type()
        if vt == x.String:
            return unicode(x.toString())
        if vt == x.List:
            return [convert_qvariant(i) for i in x.toList()]
        return x.toPyObject()

from calibre_plugins.sonyutilities.common_utils import (SizePersistedDialog, ReadOnlyTableWidgetItem, ImageTitleLayout,
                     DateDelegate, DateTableWidgetItem, RatingTableWidgetItem, CheckableTableWidgetItem,
                     get_icon, SonyDB, convert_sony_date)
#                     debug_print, get_icon, get_library_uuid)
from calibre_plugins.sonyutilities.book import SeriesBook
import calibre_plugins.sonyutilities.config as cfg

# Checked with FW2.5.2
LINE_SPACINGS =     [1.3, 1.35, 1.4, 1.6, 1.775, 1.9, 2, 2.2, 3 ]
LINE_SPACINGS_291 = [1, 1.05, 1.07, 1.1, 1.2, 1.4,  1.5, 1.7, 1.8, 2, 2.2, 2.4, 2.6, 2.8, 3 ]
LINE_SPACINGS_320 = [1, 1.05, 1.07, 1.1, 1.2, 1.35, 1.5, 1.7, 1.8, 2, 2.2, 2.4, 2.6, 2.8, 3 ]
FONT_SIZES    = [12, 14, 16, 17, 18, 19, 20, 21, 22, 24, 25, 26, 28, 32, 36, 40, 44, 46, 48, 50, 52, 54, 56, 58 ]
SONY_FONTS    = { # Format is: Display name, setting name
                 'Document Default':  'default', 
                 'Amasis':            'Amasis', 
                 'Avenir':            'Avenir Next', 
                 'Caecilia':          'Caecilia',
                 'Georgia':           'Georgia', 
                 'Gill Sans':         'Gill Sans', 
                 'Sony Nickel':       'Sony Nickel', 
                 'Malabar':           'Malabar', 
                 'Rockwell':          'Rockwell', 
                 'Gothic MB101':      'A-OTF Gothic MB101 Pr6N', 
                 'Ryumin':            'A-OTF Ryumin Pr6N', 
                 'OpenDyslexic':      'OpenDyslexic', 
                 }

TILE_TYPES    = {   # Format is: Activity/Tile name, Display Name, tooltip
                 ("Award",           _("Awards"),               _("Displays each award when given.")),
                 ("Bookstore",       _("Bookstore"),            _("The Sony Bookstore.")),
                 ("CategoryFTE",     _("Browse by category"),   _("Lists several categories from the Sony Bookstore.")),
                 ("Extras",          _("Extras"),               _("A tile is displayed for each extra when used.")),
                 ("GlobalStats",     _("Global Stats"),         _("Displays the number of finished books in your library.")),
                 ("Library",         _("Library"),              _("Shows new books added to the library.")),
                 ("QuickTour",       _("Quick Tour"),           _("The device Quick Tour that is displayed when the device is first set-up.")),
                 ("RecentPocketArticle", _("Pocket Article"),   _("Pocket articles.")),
                 ("Recommendations", _("Recommendations"),      _("Sony's recommendations for you.")),
                 ("RelatedItems",    _("Related Items"),        _("After a sync, will show books related to any you are reading. There can be one tile for each of your books.")),
                 ("WhatsNew",        _("Release Notes"),        _("Shows that there was an update to the firmware with the new version number. You probably don't want to dismiss this.")),
                 ("Shelf",           _("Shelf"),                _("Can have a tile for each shelf.")),
                 ("Sync",            _("Sync"),                 _("Displays when a sync was last done. Does not have options to dismiss it.")),
                 ("Top50",           _("Top 50"),               _("The Top 50 books in the Sony store.")),
                }

DIALOG_NAME = 'Sony Utilities'

ORDER_SHELVES_TYPE = [
                    cfg.KEY_ORDER_SHELVES_SERIES, 
                    cfg.KEY_ORDER_SHELVES_AUTHORS, 
                    cfg.KEY_ORDER_SHELVES_OTHER,
                    cfg.KEY_ORDER_SHELVES_ALL
                    ]

ORDER_SHELVES_BY = [
                    cfg.KEY_ORDER_SHELVES_BY_SERIES, 
                    cfg.KEY_ORDER_SHELVES_PUBLISHED
                    ]
# This is where all preferences for this plugin will be stored
#plugin_prefs = JSONConfig('plugins/Sony Utilities')

# pulls in translation files for _() strings
try:
    debug_print("SonyUtilites::dialogs.py - loading translations")
    load_translations()
except NameError:
    debug_print("SonyUtilites::dialogs.py - exception when loading translations")
    pass # load_translations() added in calibre 1.9

def get_plugin_pref(store_name, option):
    return cfg.plugin_prefs.get(option, cfg.METADATA_OPTIONS_DEFAULTS[cfg.KEY_SET_TITLE]) 

class AuthorTableWidgetItem(ReadOnlyTableWidgetItem):
    def __init__(self, text, sort_key):
        ReadOnlyTableWidgetItem.__init__(self, text)
        self.sort_key = sort_key

    #Qt uses a simple < check for sorting items, override this to use the sortKey
    def __lt__(self, other):
        return self.sort_key < other.sort_key


class QueueProgressDialog(QProgressDialog):

    def __init__(self, gui, books, tdir, options, queue, db, plugin_action=None):
        QProgressDialog.__init__(self, '', '', 0, len(books), gui)
        debug_print("")
        self.setMinimumWidth(500)
        self.books, self.tdir, self.options, self.queue, self.db = \
            books, tdir, options, queue, db
        self.plugin_action = plugin_action
        self.gui = gui
        self.i, self.books_to_scan = 0, []

        self.options['count_selected_books'] = len(self.books) if self.books else 0
        self.setWindowTitle(_("Queuing books for storing reading position"))
        QTimer.singleShot(0, self.do_books)
        self.exec_()


    def do_books(self):
        debug_print("Start")
#        book = self.books[self.i]
        
        library_db              = self.db
        library_config          = cfg.get_library_config(library_db)
        sony_bookmark_column    = library_config.get(cfg.KEY_CURRENT_LOCATION_CUSTOM_COLUMN, cfg.DEFAULT_LIBRARY_VALUES[cfg.KEY_CURRENT_LOCATION_CUSTOM_COLUMN])
        sony_percentRead_column = library_config.get(cfg.KEY_PERCENT_READ_CUSTOM_COLUMN, cfg.DEFAULT_LIBRARY_VALUES[cfg.KEY_PERCENT_READ_CUSTOM_COLUMN])
        last_read_column        = library_config.get(cfg.KEY_LAST_READ_CUSTOM_COLUMN, cfg.DEFAULT_LIBRARY_VALUES[cfg.KEY_LAST_READ_CUSTOM_COLUMN])

        debug_print("sony_percentRead_column=", sony_percentRead_column)
        self.setLabelText(_('Preparing the list of books ...'))
        self.setValue(1)
        search_condition = ''
        if self.options[cfg.KEY_DO_NOT_STORE_IF_REOPENED]:
            search_condition = 'and ({0}:false or {0}:<100)'.format(sony_percentRead_column)
        if self.options['allOnDevice']:
            search_condition = 'ondevice:True {0}'.format(search_condition)
            debug_print("search_condition=", search_condition)
            onDeviceIds = set(library_db.search_getting_ids(search_condition, None, sort_results=False, use_virtual_library=False))
        else:
            onDeviceIds = self.plugin_action._get_selected_ids()

        self.books = self.plugin_action._convert_calibre_ids_to_books(library_db, onDeviceIds)
        self.setRange(0, len(self.books))
        import pydevd;pydevd.settrace()
        with closing(SonyDB(self.plugin_action.device_database_path)) as db:
            for book in self.books:
                self.i += 1
                device_book_paths = self.plugin_action.get_device_paths_from_id(book.calibre_id)
    #            debug_print("device_book_paths:", device_book_paths)
    #            book.paths = device_book_paths
                book.contentIDs = [self.plugin_action.get_contentID_from_path(path, db.cursors) 
                                   for path in device_book_paths]
                if len(book.contentIDs):
                    self.setLabelText(_('Queuing ') + book.title)
                    data = dict(
                        id          = book.calibre_id,
                        title       = book.title,
                        authors     = authors_to_string(book.authors),
                        contentIds  = book.contentIDs,
                        paths       = device_book_paths,
                        bookmark    = book.get_user_metadata(sony_bookmark_column, True)['#value#'] if sony_bookmark_column else None,
                        percentRead = book.get_user_metadata(sony_percentRead_column, True)['#value#'] if sony_percentRead_column else None,
                        last_read   = book.get_user_metadata(last_read_column, True)['#value#'] if last_read_column else None
                    )
                    self.books_to_scan.append(data)
                self.setValue(self.i)

        debug_print("Finish")
        return self.do_queue()


    def do_queue(self):
        debug_print("")
        if self.gui is None:
            # There is a nasty QT bug with the timers/logic above which can
            # result in the do_queue method being called twice
            return
        self.hide()

        # Queue a job to process these ePub books
        self.queue(self.tdir, self.options, self.books_to_scan)

    def _authors_to_list(self, db, book_id):
        authors = db.authors(book_id, index_is_id=True)
        if authors:
            return [a.strip().replace('|',',') for a in authors.split(',')]
        return []


class ReaderOptionsDialog(SizePersistedDialog):

    def __init__(self, parent, plugin_action):
        SizePersistedDialog.__init__(self, parent, 'sony utilities plugin:reader font settings dialog')
        self.plugin_action = plugin_action
        self.help_anchor   = "SetReaderFonts"

        debug_print("self.plugin_action.device_fwversion=", self.plugin_action.device_fwversion())
        self.line_spacings = LINE_SPACINGS
        if self.plugin_action.device_fwversion() >= (3, 2, 0):
            self.line_spacings = LINE_SPACINGS_320
        elif self.plugin_action.device_fwversion() >= (2, 9, 1):
            self.line_spacings = LINE_SPACINGS_291
        self.initialize_controls()

#        self.options = gprefs.get(self.unique_pref_name+':settings', {})
        debug_print("ReaderOptionsDialog:__init__")

        # Set some default values from last time dialog was used.
        self.prefs = cfg.plugin_prefs[cfg.READING_OPTIONS_STORE_NAME]
        self.change_settings(self.prefs)
        debug_print(self.prefs)
        if self.prefs.get(cfg.KEY_READING_LOCK_MARGINS, False):
            self.lock_margins_checkbox.click()
        if self.prefs.get(cfg.KEY_UPDATE_CONFIG_FILE, False):
            self.update_config_file_checkbox.setCheckState(Qt.Checked)
        self.get_book_settings_pushbutton.setEnabled(self.plugin_action.singleSelected)

        # Cause our dialog size to be restored from prefs or created on first usage
        self.resize_dialog()

    def initialize_controls(self):
        self.setWindowTitle(DIALOG_NAME)
        layout = QVBoxLayout(self)
        self.setLayout(layout)
        title_layout = ImageTitleLayout(self, 'images/icon.png', 'Sony eReader Font Settings')
        layout.addLayout(title_layout)

        options_group = QGroupBox(_("Reader font settings"), self)
        layout.addWidget(options_group)
        options_layout = QGridLayout()
        options_group.setLayout(options_layout)
        
        options_layout.addWidget(QLabel(_("Font Face")), 0, 0, 1, 1)
        self.font_choice = FontChoiceComboBox(self)
        options_layout.addWidget(self.font_choice, 0, 1, 1, 4)
        options_layout.addWidget(QLabel(_("Font Size")), 1, 0, 1, 1)
        self.font_size_spin = QSpinBox(self)
        self.font_size_spin.setMinimum(12)
        self.font_size_spin.setMaximum(58)
        self.font_size_spin.setToolTip(_("Font size to use when reading. The device default is about 22."))
        options_layout.addWidget(self.font_size_spin, 1, 1, 1, 1)
        
        options_layout.addWidget(QLabel(_("Line Spacing")), 2, 0, 1, 1)
        self.line_spacing_spin = QSpinBox(self)
        self.line_spacing_spin.setMinimum(0)
        self.line_spacing_spin.setMaximum(len(self.line_spacings) - 1)
        options_layout.addWidget(self.line_spacing_spin, 2, 1, 1, 1)
        self.line_spacing_spin.setToolTip(_("The line spacing number is how many times the right arrow is pressed on the device."))
        self.line_spacing_spin.valueChanged.connect(self.line_spacing_spin_changed)

        self.custom_line_spacing_checkbox = QCheckBox(_("Custom setting"), self)
        options_layout.addWidget(self.custom_line_spacing_checkbox, 2, 2, 1, 1)
        self.custom_line_spacing_checkbox.setToolTip(_("If you want to try a line spacing other than the Sony specified, check this and enter a number."))
        self.custom_line_spacing_checkbox.clicked.connect(self.custom_line_spacing_checkbox_clicked)

        self.custom_line_spacing_edit = QLineEdit(self)
        self.custom_line_spacing_edit.setEnabled(False)
        options_layout.addWidget(self.custom_line_spacing_edit, 2, 3, 1, 2)
        self.custom_line_spacing_edit.setToolTip(_("Sony use from 1.3 to 4.0. Any number can be entered, but whether the device will use it, is another matter."))

        options_layout.addWidget(QLabel(_("Left margins")), 3, 0, 1, 1)
        self.left_margins_spin = QSpinBox(self)
        self.left_margins_spin.setMinimum(0)
        self.left_margins_spin.setMaximum(16)
        self.left_margins_spin.setToolTip(_("Margins on the device are set in multiples of two, but single steps work."))
        options_layout.addWidget(self.left_margins_spin, 3, 1, 1, 1)
        self.left_margins_spin.valueChanged.connect(self.left_margins_spin_changed)

        self.lock_margins_checkbox = QCheckBox(_("Lock margins"), self)
        options_layout.addWidget(self.lock_margins_checkbox, 3, 2, 1, 1)
        self.lock_margins_checkbox.setToolTip(_("Lock the left and right margins to the same value. Changing the left margin will also set the right margin."))
        self.lock_margins_checkbox.clicked.connect(self.lock_margins_checkbox_clicked)

        options_layout.addWidget(QLabel(_("Right margins")), 3, 3, 1, 1)
        self.right_margins_spin = QSpinBox(self)
        self.right_margins_spin.setMinimum(0)
        self.right_margins_spin.setMaximum(16)
        self.right_margins_spin.setToolTip(_("Margins on the device are set in multiples of three, but single steps work."))
        options_layout.addWidget(self.right_margins_spin, 3, 4, 1, 1)

        options_layout.addWidget(QLabel(_("Justification")), 5, 0, 1, 1)
        self.justification_choice = JustificationChoiceComboBox(self)
        options_layout.addWidget(self.justification_choice, 5, 1, 1, 1)

        self.update_config_file_checkbox = QCheckBox(_("Update config file"), self)
        options_layout.addWidget(self.update_config_file_checkbox, 5, 3, 1, 1)
        self.update_config_file_checkbox.setToolTip(_("Update the 'Sony eReader.conf' file with the new settings. These will be used when opening new books or books that do not have stored settings."))

        button_layout = QHBoxLayout(self)
        layout.addLayout(button_layout)
        self.get_device_settings_pushbutton = QPushButton(_("&Get configuration from device"), self)
        button_layout.addWidget(self.get_device_settings_pushbutton)
        self.get_device_settings_pushbutton.setToolTip(_("Read the device configuration file to get the current default settings."))
        self.get_device_settings_pushbutton.clicked.connect(self.get_device_settings)
        
        self.get_book_settings_pushbutton = QPushButton(_("&Get settings from device"), self)
        button_layout.addWidget(self.get_book_settings_pushbutton)
        self.get_book_settings_pushbutton.setToolTip(_("Fetches the current for the selected book from the device."))
        self.get_book_settings_pushbutton.clicked.connect(self.get_book_settings)
        
        # Dialog buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.ok_clicked)
        button_box.rejected.connect(self.reject)
        button_layout.addWidget(button_box)


    def ok_clicked(self):

        self.prefs = cfg.READING_OPTIONS_DEFAULTS
        self.prefs[cfg.KEY_READING_FONT_FAMILY] = SONY_FONTS[unicode(self.font_choice.currentText()).strip()]
        self.prefs[cfg.KEY_READING_ALIGNMENT]   = unicode(self.justification_choice.currentText()).strip()
        self.prefs[cfg.KEY_READING_FONT_SIZE]   = int(unicode(self.font_size_spin.value()))
        if self.custom_line_spacing_is_checked():
            self.prefs[cfg.KEY_READING_LINE_HEIGHT] = float(unicode(self.custom_line_spacing_edit.text()))
            debug_print("custom -self.prefs[cfg.KEY_READING_LINE_HEIGHT]=", self.prefs[cfg.KEY_READING_LINE_HEIGHT])
        else:
            self.prefs[cfg.KEY_READING_LINE_HEIGHT] = self.line_spacings[int(unicode(self.line_spacing_spin.value()))]
            debug_print("spin - self.prefs[cfg.KEY_READING_LINE_HEIGHT]=", self.prefs[cfg.KEY_READING_LINE_HEIGHT])
        self.prefs[cfg.KEY_READING_LEFT_MARGIN]  = int(unicode(self.left_margins_spin.value()))
        self.prefs[cfg.KEY_READING_RIGHT_MARGIN] = int(unicode(self.right_margins_spin.value()))
        self.prefs[cfg.KEY_READING_LOCK_MARGINS] = self.lock_margins_checkbox_is_checked()
        self.prefs[cfg.KEY_UPDATE_CONFIG_FILE]   = self.update_config_file_checkbox.checkState() == Qt.Checked

        gprefs.set(self.unique_pref_name+':settings', self.prefs)
        self.accept()

    def custom_line_spacing_checkbox_clicked(self, checked):
        self.line_spacing_spin.setEnabled(not checked)
        self.custom_line_spacing_edit.setEnabled(checked)
        if not self.custom_line_spacing_is_checked():
            self.line_spacing_spin_changed(None)

    def lock_margins_checkbox_clicked(self, checked):
        self.right_margins_spin.setEnabled(not checked)
        if checked: #not self.custom_line_spacing_is_checked():
            self.right_margins_spin.setProperty('value', int(unicode(self.left_margins_spin.value())))

    def line_spacing_spin_changed(self, checked):
        self.custom_line_spacing_edit.setText(unicode(self.line_spacings[int(unicode(self.line_spacing_spin.value()))]))

    def left_margins_spin_changed(self, checked):
        if self.lock_margins_checkbox_is_checked():
            self.right_margins_spin.setProperty('value', int(unicode(self.left_margins_spin.value())))

    def custom_line_spacing_is_checked(self):
        return self.custom_line_spacing_checkbox.checkState() == Qt.Checked

    def lock_margins_checkbox_is_checked(self):
        return self.lock_margins_checkbox.checkState() == Qt.Checked

    def get_device_settings(self):
        sonyConfig = ConfigParser.SafeConfigParser(allow_no_value=True)
        device = self.parent().device_manager.connected_device
        device_path = self.parent().device_manager.connected_device._main_prefix
        debug_print("device_path=", device_path)
        sonyConfig.read(device.normalize_path(device_path + '.sony/Sony/Sony eReader.conf'))
        
        device_settings = {}
        device_settings[cfg.KEY_READING_FONT_FAMILY] = sonyConfig.get('Reading', cfg.KEY_READING_FONT_FAMILY) \
                                                    if sonyConfig.has_option('Reading', cfg.KEY_READING_FONT_FAMILY) \
                                                    else cfg.READING_OPTIONS_DEFAULTS[cfg.KEY_READING_FONT_FAMILY]
        device_settings[cfg.KEY_READING_ALIGNMENT]  = sonyConfig.get('Reading', cfg.KEY_READING_ALIGNMENT) \
                                                    if sonyConfig.has_option('Reading', cfg.KEY_READING_ALIGNMENT)  \
                                                    else cfg.READING_OPTIONS_DEFAULTS[cfg.KEY_READING_ALIGNMENT]
        device_settings[cfg.KEY_READING_FONT_SIZE]   = sonyConfig.get('Reading', cfg.KEY_READING_FONT_SIZE) \
                                                    if sonyConfig.has_option('Reading', cfg.KEY_READING_FONT_SIZE) \
                                                    else cfg.READING_OPTIONS_DEFAULTS[cfg.KEY_READING_FONT_SIZE]
        device_settings[cfg.KEY_READING_LINE_HEIGHT] = float(sonyConfig.get('Reading', cfg.KEY_READING_LINE_HEIGHT)) \
                                                    if sonyConfig.has_option('Reading', cfg.KEY_READING_LINE_HEIGHT) \
                                                    else cfg.READING_OPTIONS_DEFAULTS[cfg.KEY_READING_LINE_HEIGHT]
        device_settings[cfg.KEY_READING_LEFT_MARGIN] = sonyConfig.get('Reading', cfg.KEY_READING_LEFT_MARGIN) \
                                                    if sonyConfig.has_option('Reading', cfg.KEY_READING_LEFT_MARGIN) \
                                                    else cfg.READING_OPTIONS_DEFAULTS[cfg.KEY_READING_LEFT_MARGIN]
        device_settings[cfg.KEY_READING_RIGHT_MARGIN] = sonyConfig.get('Reading', cfg.KEY_READING_RIGHT_MARGIN) \
                                                    if sonyConfig.has_option('Reading', cfg.KEY_READING_RIGHT_MARGIN) \
                                                    else cfg.READING_OPTIONS_DEFAULTS[cfg.KEY_READING_RIGHT_MARGIN]

        self.change_settings(device_settings)

    def change_settings(self, reader_settings):
        font_face = reader_settings.get(cfg.KEY_READING_FONT_FAMILY, cfg.READING_OPTIONS_DEFAULTS[cfg.KEY_READING_FONT_FAMILY])
        debug_print("font_face=", font_face)
        self.font_choice.select_text(font_face)
        
        justification = reader_settings.get(cfg.KEY_READING_ALIGNMENT, cfg.READING_OPTIONS_DEFAULTS[cfg.KEY_READING_ALIGNMENT])
        self.justification_choice.select_text(justification)
        
        font_size = reader_settings.get(cfg.KEY_READING_FONT_SIZE, cfg.READING_OPTIONS_DEFAULTS[cfg.KEY_READING_FONT_SIZE])
        self.font_size_spin.setProperty('value', font_size)
        
        line_spacing = reader_settings.get(cfg.KEY_READING_LINE_HEIGHT, cfg.READING_OPTIONS_DEFAULTS[cfg.KEY_READING_LINE_HEIGHT])
        debug_print("line_spacing='%s'" % line_spacing)
        if line_spacing in self.line_spacings:
            line_spacing_index = self.line_spacings.index(line_spacing)
            debug_print("line_spacing_index=", line_spacing_index)
            self.custom_line_spacing_checkbox.setCheckState(Qt.Checked)
        else:
            self.custom_line_spacing_checkbox.setCheckState(Qt.Unchecked)
            debug_print("line_spacing_index not found")
            line_spacing_index = 0
        self.custom_line_spacing_checkbox.click()
        self.custom_line_spacing_edit.setText(unicode(line_spacing))
        self.line_spacing_spin.setProperty('value', line_spacing_index)
        
        left_margins = reader_settings.get(cfg.KEY_READING_LEFT_MARGIN, cfg.READING_OPTIONS_DEFAULTS[cfg.KEY_READING_LEFT_MARGIN])
        self.left_margins_spin.setProperty('value', left_margins)
        right_margins = reader_settings.get(cfg.KEY_READING_RIGHT_MARGIN, cfg.READING_OPTIONS_DEFAULTS[cfg.KEY_READING_RIGHT_MARGIN])
        self.right_margins_spin.setProperty('value', right_margins)

    def get_book_settings(self):
        book_options = self.plugin_action.fetch_book_fonts()
        
        if len(book_options) > 0:
            self.change_settings(book_options)


class UpdateMetadataOptionsDialog(SizePersistedDialog):

    def __init__(self, parent, plugin_action):
        SizePersistedDialog.__init__(self, parent, 'sony utilities plugin:update metadata settings dialog')
        self.plugin_action = plugin_action
        self.help_anchor   = "UpdateMetadata"

        self.initialize_controls()

#        self.options = gprefs.get(self.unique_pref_name+':settings', {})

        # Set some default values from last time dialog was used.
        title = cfg.get_plugin_pref(cfg.METADATA_OPTIONS_STORE_NAME, cfg.KEY_SET_TITLE)
        self.title_checkbox.setCheckState(Qt.Checked if title else Qt.Unchecked)
        
        title_sort = cfg.get_plugin_pref(cfg.METADATA_OPTIONS_STORE_NAME, cfg.KEY_USE_TITLE_SORT)
        self.title_sort_checkbox.setCheckState(Qt.Checked if title_sort else Qt.Unchecked)
        self.title_checkbox_clicked(title)
        
        author = cfg.get_plugin_pref(cfg.METADATA_OPTIONS_STORE_NAME, cfg.KEY_SET_AUTHOR)
        self.author_checkbox.setCheckState(Qt.Checked if author else Qt.Unchecked)

        author_sort = cfg.get_plugin_pref(cfg.METADATA_OPTIONS_STORE_NAME, cfg.KEY_USE_AUTHOR_SORT)
        self.author_sort_checkbox.setCheckState(Qt.Checked if author_sort else Qt.Unchecked)
        self.author_checkbox_clicked(author)
        
        description = cfg.get_plugin_pref(cfg.METADATA_OPTIONS_STORE_NAME, cfg.KEY_SET_DESCRIPTION)
        self.description_checkbox.setCheckState(Qt.Checked if description else Qt.Unchecked)
        
        publisher = cfg.get_plugin_pref(cfg.METADATA_OPTIONS_STORE_NAME, cfg.KEY_SET_PUBLISHER)
        self.publisher_checkbox.setCheckState(Qt.Checked if publisher else Qt.Unchecked)
        
        published = cfg.get_plugin_pref(cfg.METADATA_OPTIONS_STORE_NAME, cfg.KEY_SET_PUBLISHED_DATE)
        self.published_checkbox.setCheckState(Qt.Checked if published else Qt.Unchecked)
        
        isbn = cfg.get_plugin_pref(cfg.METADATA_OPTIONS_STORE_NAME, cfg.KEY_SET_ISBN)
        self.isbn_checkbox.setCheckState(Qt.Checked if isbn and self.plugin_action.supports_ratings else Qt.Unchecked)
        self.isbn_checkbox.setEnabled(self.plugin_action.supports_ratings)

        series = cfg.get_plugin_pref(cfg.METADATA_OPTIONS_STORE_NAME, cfg.KEY_SET_SERIES)
        self.series_checkbox.setCheckState(Qt.Checked if series and self.plugin_action.supports_series else Qt.Unchecked)
        self.series_checkbox.setEnabled(self.plugin_action.supports_series)

        tags_in_subtitle = cfg.get_plugin_pref(cfg.METADATA_OPTIONS_STORE_NAME, cfg.KEY_SET_TAGS_IN_SUBTITLE)
        self.tags_in_subtitle_checkbox.setCheckState(Qt.Checked if tags_in_subtitle and self.plugin_action.supports_series else Qt.Unchecked)
#        self.tags_in_subtitle_checkbox.setEnabled(self.plugin_action.supports_series)
        self.tags_in_subtitle_checkbox.setVisible(False)

        use_plugboard = cfg.get_plugin_pref(cfg.METADATA_OPTIONS_STORE_NAME, cfg.KEY_USE_PLUGBOARD)
        self.use_plugboard_checkbox.setCheckState(Qt.Checked if use_plugboard else Qt.Unchecked)
        self.use_plugboard_checkbox_clicked(use_plugboard)

        language = cfg.get_plugin_pref(cfg.METADATA_OPTIONS_STORE_NAME, cfg.KEY_SET_LANGUAGE)
        self.language_checkbox.setCheckState(Qt.Checked if language else Qt.Unchecked)

        # Cause our dialog size to be restored from prefs or created on first usage
        self.resize_dialog()

    def initialize_controls(self):
        self.setWindowTitle(DIALOG_NAME)
        layout = QVBoxLayout(self)
        self.setLayout(layout)
        title_layout = ImageTitleLayout(self, 'images/icon.png', 'Update metadata in Device Library')
        layout.addLayout(title_layout)

        options_group = QGroupBox(_("Metadata to update"), self)
        layout.addWidget(options_group)
        options_layout = QGridLayout()
        options_group.setLayout(options_layout)

        self.title_checkbox = QCheckBox(_("Title"), self)
        options_layout.addWidget(self.title_checkbox, 0, 0, 1, 1)
        self.title_checkbox.clicked.connect(self.title_checkbox_clicked)
        self.title_sort_checkbox = QCheckBox(_("Use 'Title Sort'"), self)
        options_layout.addWidget(self.title_sort_checkbox, 0, 1, 1, 1)
        
        self.author_checkbox = QCheckBox(_("Author"), self)
        options_layout.addWidget(self.author_checkbox, 0, 2, 1, 1)
        self.author_checkbox.clicked.connect(self.author_checkbox_clicked)
        self.author_sort_checkbox = QCheckBox(_("Use 'Author Sort'"), self)
        options_layout.addWidget(self.author_sort_checkbox, 0, 3, 1, 1)
        
        self.series_checkbox = QCheckBox(_("Series and Index"), self)
        options_layout.addWidget(self.series_checkbox, 1, 0, 1, 2)
        
        self.description_checkbox = QCheckBox(_("Comments/Synopsis"), self)
        options_layout.addWidget(self.description_checkbox, 1, 2, 1, 2)
        
        self.publisher_checkbox = QCheckBox(_("Publisher"), self)
        options_layout.addWidget(self.publisher_checkbox, 2, 0, 1, 2)
        
        self.published_checkbox = QCheckBox(_("Published Date"), self)
        options_layout.addWidget(self.published_checkbox, 2, 2, 1, 2)
        
        self.isbn_checkbox = QCheckBox(_("ISBN"), self)
        options_layout.addWidget(self.isbn_checkbox, 4, 0, 1, 2)
        
        self.language_checkbox = QCheckBox(_("Language"), self)
        options_layout.addWidget(self.language_checkbox, 4, 2, 1, 2)
        
        self.tags_in_subtitle_checkbox = QCheckBox(_("Tags in subtitle"), self)
        options_layout.addWidget(self.tags_in_subtitle_checkbox, 5, 2, 1, 2)

        self.use_plugboard_checkbox = QCheckBox(_("Use Plugboard"), self)
        self.use_plugboard_checkbox.setToolTip(_("Set the metadata on the device using the plugboard for the device and book format."))
        self.use_plugboard_checkbox.clicked.connect(self.use_plugboard_checkbox_clicked)
        options_layout.addWidget(self.use_plugboard_checkbox, 6, 0, 1, 2)

        self.readingStatusGroupBox = ReadingStatusGroupBox(self.parent())
        layout.addWidget(self.readingStatusGroupBox)

        # Dialog buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.ok_clicked)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def ok_clicked(self):

        self.new_prefs = {}
        self.new_prefs = cfg.METADATA_OPTIONS_DEFAULTS
        self.new_prefs[cfg.KEY_SET_TITLE]          = self.title_checkbox.checkState() == Qt.Checked
        self.new_prefs[cfg.KEY_USE_TITLE_SORT]     = self.title_sort_checkbox.checkState() == Qt.Checked
        self.new_prefs[cfg.KEY_SET_AUTHOR]         = self.author_checkbox.checkState() == Qt.Checked
        self.new_prefs[cfg.KEY_USE_AUTHOR_SORT]    = self.author_sort_checkbox.checkState() == Qt.Checked
        self.new_prefs[cfg.KEY_SET_DESCRIPTION]    = self.description_checkbox.checkState() == Qt.Checked
        self.new_prefs[cfg.KEY_SET_PUBLISHER]      = self.publisher_checkbox.checkState() == Qt.Checked
        self.new_prefs[cfg.KEY_SET_PUBLISHED_DATE] = self.published_checkbox.checkState() == Qt.Checked
        self.new_prefs[cfg.KEY_SET_ISBN]           = self.isbn_checkbox.checkState() == Qt.Checked
        self.new_prefs[cfg.KEY_SET_SERIES]         = self.series_checkbox.checkState() == Qt.Checked
        self.new_prefs[cfg.KEY_USE_PLUGBOARD]      = self.use_plugboard_checkbox.checkState() == Qt.Checked
        self.new_prefs[cfg.KEY_SET_LANGUAGE]       = self.language_checkbox.checkState() == Qt.Checked
        self.new_prefs[cfg.KEY_SET_TAGS_IN_SUBTITLE] = False#self.tags_in_subtitle_checkbox.checkState() == Qt.Checked
        cfg.plugin_prefs[cfg.METADATA_OPTIONS_STORE_NAME] = self.new_prefs


#        gprefs.set(self.unique_pref_name+':settings', self.options)

        self.new_prefs[cfg.KEY_SET_READING_STATUS] = self.readingStatusGroupBox.readingStatusIsChecked()
        if self.readingStatusGroupBox.readingStatusIsChecked():
            self.new_prefs[cfg.KEY_READING_STATUS] = self.readingStatusGroupBox.readingStatus()
            if self.new_prefs['readingStatus'] < 0:
                return error_dialog(self, 'No reading status option selected',
                            'If you are changing the reading status, you must select an option to continue',
                            show=True, show_copy_button=False)
            self.new_prefs[cfg.KEY_RESET_POSITION] = self.readingStatusGroupBox.reset_position_checkbox.checkState() == Qt.Checked

        # Only if the user has checked at least one option will we continue
        for key in self.new_prefs:
            debug_print("key='%s' self.new_prefs[key]=%s" % (key, self.new_prefs[key]))
            if self.new_prefs[key] and not key == cfg.KEY_READING_STATUS:
                self.accept()
                return
        return error_dialog(self, 'No options selected',
                            'You must select at least one option to continue.',
                            show=True, show_copy_button=False)

    def title_checkbox_clicked(self, checked):
        self.title_sort_checkbox.setEnabled(checked and not self.use_plugboard_checkbox.checkState() == Qt.Checked)

    def author_checkbox_clicked(self, checked):
        self.author_sort_checkbox.setEnabled(checked and not self.use_plugboard_checkbox.checkState() == Qt.Checked)

    def use_plugboard_checkbox_clicked(self, checked):
        self.title_sort_checkbox.setEnabled(not checked and self.title_checkbox.checkState() == Qt.Checked)
        self.author_sort_checkbox.setEnabled(not checked and self.author_checkbox.checkState() == Qt.Checked)


class DismissTilesOptionsDialog(SizePersistedDialog):

    def __init__(self, parent, plugin_action):
        SizePersistedDialog.__init__(self, parent, 'sony utilities plugin:dismiss tiles settings dialog')
        self.plugin_action = plugin_action
        self.help_anchor   = "DismissTiles"

#        self.options = gprefs.get(self.unique_pref_name+':settings', {})
        self.options = cfg.get_plugin_prefs(cfg.DISMISSTILES_OPTIONS_STORE_NAME)
        self.initialize_controls()

        self.tiles_new_checkbox.setCheckState(Qt.Checked if self.options.get(cfg.KEY_TILE_RECENT_NEW, False) else Qt.Unchecked)
        self.tiles_finished_checkbox.setCheckState(Qt.Checked if self.options.get(cfg.KEY_TILE_RECENT_FINISHED, False) else Qt.Unchecked)
        self.tiles_inthecloud_checkbox.setCheckState(Qt.Checked if self.options.get(cfg.KEY_TILE_RECENT_IN_THE_CLOUD, False) else Qt.Unchecked)

        # Cause our dialog size to be restored from prefs or created on first usage
        self.resize_dialog()

    def initialize_controls(self):
        self.setWindowTitle(DIALOG_NAME)
        layout = QVBoxLayout(self)
        self.setLayout(layout)
        title_layout = ImageTitleLayout(self, 'images/icon.png', 'Dismiss Tiles from Home Screen', )
        layout.addLayout(title_layout)

        main_layout = QHBoxLayout()
        layout.addLayout(main_layout, 1)
        col2_layout = QVBoxLayout()
        main_layout.addLayout(col2_layout)

        self._add_groupbox(col2_layout, 'Tile Types:', TILE_TYPES, self.options.get(cfg.KEY_TILE_OPTIONS, {}))
        col2_layout.addSpacing(5)

        options_group = QGroupBox(_("Book Tiles"), self)
        options_group.setToolTip(_("For books, you can dismiss the 'Finished' and 'New' tiles."))
        layout.addWidget(options_group)
        options_layout = QGridLayout()
        options_group.setLayout(options_layout)

        self.tiles_new_checkbox = QCheckBox(_("New"), self)
        self.tiles_new_checkbox.setToolTip(_("Select this option if you want to dismiss new books. This will act on all tiles of this type."))
        options_layout.addWidget(self.tiles_new_checkbox, 0, 0, 1, 1)
        self.tiles_finished_checkbox = QCheckBox(_("Finished"), self)
        self.tiles_finished_checkbox.setToolTip(_("Select this option if you want to dismiss finished books."))
        options_layout.addWidget(self.tiles_finished_checkbox, 0, 1, 1, 1)
        self.tiles_inthecloud_checkbox = QCheckBox(_("In the Cloud"), self)
        self.tiles_inthecloud_checkbox.setToolTip(_("Select this option if you want to dismiss books that are 'In the Cloud'."))
        options_layout.addWidget(self.tiles_inthecloud_checkbox, 0, 2, 1, 1)

        options_group = QGroupBox(_("Database Trigger"), self)
        options_group.setToolTip(_("When a tile is added or changed, the database trigger will automatically set them to be dismissed. This will be done for the tile types selected above."))
        layout.addWidget(options_group)
        options_layout = QGridLayout()
        options_group.setLayout(options_layout)

        self.database_trigger_checkbox = QCheckBox(_("Change database trigger"), self)
        self.database_trigger_checkbox.setToolTip(_("Select this option if you want to change the current database trigger."))
        options_layout.addWidget(self.database_trigger_checkbox, 0, 0, 1, 2)
        self.database_trigger_checkbox.clicked.connect(self.database_trigger_checkbox_clicked)

        self.create_trigger_radiobutton = QRadioButton(_("Create or change trigger"), self)
        self.create_trigger_radiobutton.setToolTip(_("To create or change the trigger, select this option."))
        options_layout.addWidget(self.create_trigger_radiobutton, 1, 0, 1, 1)
        self.create_trigger_radiobutton.setEnabled(False)

        self.delete_trigger_radiobutton = QRadioButton(_("Delete trigger"), self)
        self.delete_trigger_radiobutton.setToolTip(_("This will remove the existing trigger and let the device work as Sony intended it."))
        options_layout.addWidget(self.delete_trigger_radiobutton, 1, 1, 1, 1)
        self.delete_trigger_radiobutton.setEnabled(False)

        # Dialog buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self._ok_clicked)
        button_box.rejected.connect(self.reject)
        self.select_none_button = button_box.addButton(_("Clear all"), QDialogButtonBox.ResetRole)
        self.select_none_button.setToolTip(_("Clear all selections"))
        self.select_none_button.clicked.connect(self._select_none_clicked)
        layout.addWidget(button_box)

    def _add_groupbox(self, layout, title, option_info, options):
        groupbox = QGroupBox(title)
        groupbox.setToolTip(_("This is the list of Tile types that can be dismissed. Select the one you want to dismiss."))

        layout.addWidget(groupbox)
        groupbox_layout = QGridLayout()
        groupbox.setLayout(groupbox_layout)
        
        xpos = 0
        ypos = 0
        i    = 0

        for key, text, tooltip in sorted(option_info):
            checkbox = QCheckBox(_(text), self)
            checkbox.setToolTip(_(tooltip))
            checkbox.setCheckState(Qt.Checked if options.get(key, False) else Qt.Unchecked)
            setattr(self, key, checkbox)
            groupbox_layout.addWidget(checkbox, ypos, xpos, 1, 1)
            i += 1
            if i % 2 == 0:
                xpos = 0
                ypos += 1
            else:
                xpos = 1

    def database_trigger_checkbox_clicked(self, checked):
        self.create_trigger_radiobutton.setEnabled(checked)
        self.delete_trigger_radiobutton.setEnabled(checked)

    def _ok_clicked(self):
        self.options = {}
        self.options[cfg.KEY_TILE_OPTIONS] = {}
        for option_name, _t, _tt in TILE_TYPES:
            self.options[cfg.KEY_TILE_OPTIONS][option_name] = getattr(self, option_name).checkState() == Qt.Checked

        self.options[cfg.KEY_TILE_RECENT_NEW]          = self.tiles_new_checkbox.checkState() == Qt.Checked
        self.options[cfg.KEY_TILE_RECENT_FINISHED]     = self.tiles_finished_checkbox.checkState() == Qt.Checked
        self.options[cfg.KEY_TILE_RECENT_IN_THE_CLOUD] = self.tiles_inthecloud_checkbox.checkState() == Qt.Checked

        cfg.plugin_prefs[cfg.DISMISSTILES_OPTIONS_STORE_NAME] = self.options

        self.options[cfg.KEY_CHANGE_DISMISS_TRIGGER] = self.database_trigger_checkbox.checkState() == Qt.Checked
        self.options[cfg.KEY_CREATE_DISMISS_TRIGGER] = self.create_trigger_radiobutton.isChecked()
        self.options[cfg.KEY_DELETE_DISMISS_TRIGGER] = self.delete_trigger_radiobutton.isChecked()

        have_options = False
        # Only if the user has checked at least one option will we continue
        for key in self.options[cfg.KEY_TILE_OPTIONS]:
            have_options = have_options or self.options[cfg.KEY_TILE_OPTIONS][key]

        if have_options or self.options[cfg.KEY_TILE_RECENT_FINISHED] or self.options[cfg.KEY_TILE_RECENT_NEW] or self.options[cfg.KEY_DELETE_DISMISS_TRIGGER] or self.options[cfg.KEY_TILE_RECENT_IN_THE_CLOUD]:
            self.accept()
            return
        return error_dialog(self, 'No options selected',
                            'You must select at least one option to continue.',
                            show=True, show_copy_button=False)

    def _select_none_clicked(self):
        for option_name, _t, _tt in TILE_TYPES:
            getattr(self, option_name).setCheckState(Qt.Unchecked)
        self.tiles_new_checkbox.setCheckState(Qt.Unchecked)
        self.tiles_finished_checkbox.setCheckState(Qt.Unchecked)


class BookmarkOptionsDialog(SizePersistedDialog):

    def __init__(self, parent, plugin_action):
        SizePersistedDialog.__init__(self, parent, 'sony utilities plugin:bookmark options dialog')
        self.plugin_action = plugin_action
        self.help_anchor   = "StoreCurrentBookmark"

#        self.options = gprefs.get(self.unique_pref_name+':settings', {})

        # Set some default values from last time dialog was used.
        c = cfg.plugin_prefs[cfg.BOOKMARK_OPTIONS_STORE_NAME]
        store_bookmarks             = c.get(cfg.KEY_STORE_BOOKMARK,  cfg.BOOKMARK_OPTIONS_DEFAULTS[cfg.KEY_STORE_BOOKMARK])
        set_status_to_reading       = c.get(cfg.KEY_READING_STATUS,  cfg.BOOKMARK_OPTIONS_DEFAULTS[cfg.KEY_READING_STATUS])
        set_date_to_now             = c.get(cfg.KEY_DATE_TO_NOW,     cfg.BOOKMARK_OPTIONS_DEFAULTS[cfg.KEY_DATE_TO_NOW])
        clear_if_unread             = c.get(cfg.KEY_CLEAR_IF_UNREAD, cfg.BOOKMARK_OPTIONS_DEFAULTS[cfg.KEY_CLEAR_IF_UNREAD])
        store_if_more_recent        = c.get(cfg.KEY_STORE_IF_MORE_RECENT,     cfg.BOOKMARK_OPTIONS_DEFAULTS[cfg.KEY_STORE_IF_MORE_RECENT])
        do_not_store_if_reopened    = c.get(cfg.KEY_DO_NOT_STORE_IF_REOPENED, cfg.BOOKMARK_OPTIONS_DEFAULTS[cfg.KEY_DO_NOT_STORE_IF_REOPENED])
        background_job              = c.get(cfg.KEY_BACKGROUND_JOB,  cfg.BOOKMARK_OPTIONS_DEFAULTS[cfg.KEY_BACKGROUND_JOB])

        self.initialize_controls()

        if store_bookmarks:
            self.store_radiobutton.click()
        else:
            self.restore_radiobutton.click()
        self.status_to_reading_checkbox.setCheckState(Qt.Checked if set_status_to_reading else Qt.Unchecked)
        self.date_to_now_checkbox.setCheckState(Qt.Checked if set_date_to_now else Qt.Unchecked)

        self.clear_if_unread_checkbox.setCheckState(Qt.Checked if clear_if_unread else Qt.Unchecked)
        self.store_if_more_recent_checkbox.setCheckState(Qt.Checked if store_if_more_recent else Qt.Unchecked)
        self.do_not_store_if_reopened_checkbox.setCheckState(Qt.Checked if do_not_store_if_reopened else Qt.Unchecked)
        self.background_checkbox.setCheckState(Qt.Checked if background_job else Qt.Unchecked)

        # Cause our dialog size to be restored from prefs or created on first usage
        self.resize_dialog()

    def initialize_controls(self):
        self.setWindowTitle(DIALOG_NAME)
        layout = QVBoxLayout(self)
        self.setLayout(layout)
        title_layout = ImageTitleLayout(self, 'images/icon.png', 'Store or Restore Bookmark')
        layout.addLayout(title_layout)

        options_column_group = QGroupBox(_("Options"), self)
        layout.addWidget(options_column_group)
        options_layout = QGridLayout()
        options_column_group.setLayout(options_layout)

        self.store_radiobutton = QRadioButton(_("Store"), self)
        self.store_radiobutton.setToolTip(_("Store the current reading position in the calibre library."))
        options_layout.addWidget(self.store_radiobutton, 1, 0, 1, 1)
        self.store_radiobutton.clicked.connect(self.store_radiobutton_clicked)

        self.clear_if_unread_checkbox = QCheckBox(_("Clear if unread"), self)
        self.clear_if_unread_checkbox.setToolTip(_("If the book on the device is shown as unread, clear the reading position stored in the library."))
        options_layout.addWidget(self.clear_if_unread_checkbox, 2, 0, 1, 1)

        self.store_if_more_recent_checkbox = QCheckBox(_("Only if more recent"), self)
        self.store_if_more_recent_checkbox.setToolTip(_("Only store the reading position if the last read timestamp on the device is more recent than in the library."))
        options_layout.addWidget(self.store_if_more_recent_checkbox, 3, 0, 1, 1)

        self.do_not_store_if_reopened_checkbox = QCheckBox(_("Not if finished in library"), self)
        self.do_not_store_if_reopened_checkbox.setToolTip(_("Do not store the reading position if the library has the book as finished. This is if the percent read is 100%."))
        options_layout.addWidget(self.do_not_store_if_reopened_checkbox, 4, 0, 1, 1)


        self.restore_radiobutton = QRadioButton(_("Restore"), self)
        self.restore_radiobutton.setToolTip(_("Copy the current reading position back to the device."))
        options_layout.addWidget(self.restore_radiobutton, 1, 1, 1, 1)
        self.restore_radiobutton.clicked.connect(self.restore_radiobutton_clicked)
        
        self.status_to_reading_checkbox = QCheckBox(_("Set reading status"), self)
        self.status_to_reading_checkbox.setToolTip(_("If this is not set, when the current reading position is on the device, the reading status will not be changes. If the percent read is 100%, the book will be marked as finished. Otherwise, it will be in progress."))
        options_layout.addWidget(self.status_to_reading_checkbox, 2, 1, 1, 1)
        
        self.date_to_now_checkbox = QCheckBox(_("Set date to now"), self)
        self.date_to_now_checkbox.setToolTip(_("Setting the date to now will put the book at the top of the \"Recent reads\" list."))
        options_layout.addWidget(self.date_to_now_checkbox, 3, 1, 1, 1)
        
        self.background_checkbox = QCheckBox(_("Run in background"), self)
        self.background_checkbox.setToolTip(_("Do store or restore as background job."))
        options_layout.addWidget(self.background_checkbox, 5, 0, 1, 2)

        # Dialog buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.ok_clicked)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def ok_clicked(self):
#        gprefs.set(self.unique_pref_name+':settings', self.options)
        new_prefs = {}
        new_prefs[cfg.KEY_STORE_BOOKMARK]       = self.store_radiobutton.isChecked()
        new_prefs[cfg.KEY_READING_STATUS]       = self.status_to_reading_checkbox.checkState() == Qt.Checked
        new_prefs[cfg.KEY_DATE_TO_NOW]          = self.date_to_now_checkbox.checkState() == Qt.Checked
        new_prefs[cfg.KEY_CLEAR_IF_UNREAD]      = self.clear_if_unread_checkbox.checkState() == Qt.Checked
        new_prefs[cfg.KEY_STORE_IF_MORE_RECENT] = self.store_if_more_recent_checkbox.checkState() == Qt.Checked
        new_prefs[cfg.KEY_DO_NOT_STORE_IF_REOPENED] = self.do_not_store_if_reopened_checkbox.checkState() == Qt.Checked
        new_prefs[cfg.KEY_BACKGROUND_JOB]       = self.background_checkbox.checkState() == Qt.Checked
        cfg.plugin_prefs[cfg.BOOKMARK_OPTIONS_STORE_NAME]  = new_prefs
        self.options = new_prefs
        self.accept()

    def restore_radiobutton_clicked(self, checked):
        self.status_to_reading_checkbox.setEnabled(checked)
        self.date_to_now_checkbox.setEnabled(checked)
        self.clear_if_unread_checkbox.setEnabled(not checked)
        self.store_if_more_recent_checkbox.setEnabled(not checked)
        self.do_not_store_if_reopened_checkbox.setEnabled(not checked)
        self.background_checkbox.setEnabled(not checked)

    def store_radiobutton_clicked(self, checked):
        self.status_to_reading_checkbox.setEnabled(not checked)
        self.date_to_now_checkbox.setEnabled(not checked)
        self.clear_if_unread_checkbox.setEnabled(checked)
        self.store_if_more_recent_checkbox.setEnabled(checked)
        self.do_not_store_if_reopened_checkbox.setEnabled(checked)
        self.background_checkbox.setEnabled(checked)



class ChangeReadingStatusOptionsDialog(SizePersistedDialog):

    def __init__(self, parent, plugin_action):
        SizePersistedDialog.__init__(self, parent, 'sony utilities plugin:change reading status settings dialog')
        self.plugin_action = plugin_action
        self.help_anchor   = "ChangeReadingStatus"

        self.options = gprefs.get(self.unique_pref_name+':settings', {})
        
        self.initialize_controls()

        # Cause our dialog size to be restored from prefs or created on first usage
        self.resize_dialog()

    def initialize_controls(self):
        self.setWindowTitle(DIALOG_NAME)
        layout = QVBoxLayout(self)
        self.setLayout(layout)
        title_layout = ImageTitleLayout(self, 'images/icon.png', 'Change Reading Status in Device Library')
        layout.addLayout(title_layout)

        self.readingStatusGroupBox = ReadingStatusGroupBox(self.parent())
        layout.addWidget(self.readingStatusGroupBox)

        # Dialog buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.ok_clicked)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def ok_clicked(self):

        self.options = self.plugin_action.default_options()

        self.options['setRreadingStatus'] = self.readingStatusGroupBox.readingStatusIsChecked()
        if self.options['setRreadingStatus']:
            self.options['readingStatus'] = self.readingStatusGroupBox.readingStatus()
            if self.options['readingStatus'] < 0:
                return error_dialog(self, 'No reading status option selected',
                           'If you are changing the reading status, you must select an option to continue',
                            show=True, show_copy_button=False)
            self.options['resetPosition'] = self.readingStatusGroupBox.reset_position_checkbox.checkState() == Qt.Checked

        # Only if the user has checked at least one option will we continue
        for key in self.options:
            if self.options[key]:
                self.accept()
                return
        return error_dialog(self,'No options selected',
                           'You must select at least one option to continue',
                            show=True, show_copy_button=False)


class BackupAnnotationsOptionsDialog(SizePersistedDialog):

    def __init__(self, parent, plugin_action):
        SizePersistedDialog.__init__(self, parent, 'sony utilities plugin:backup annotation files settings dialog')
        self.plugin_action = plugin_action
        self.help_anchor   = "BackupAnnotations"

        self.options = gprefs.get(self.unique_pref_name+':settings', {})
        
        self.initialize_controls()

        self.dest_directory_edit.setText(self.options.get('dest_directory', ''))
        # Cause our dialog size to be restored from prefs or created on first usage
        self.resize_dialog()

    def initialize_controls(self):
        self.setWindowTitle(DIALOG_NAME)
        layout = QVBoxLayout(self)
        self.setLayout(layout)
        title_layout = ImageTitleLayout(self, 'images/icon.png', 'Backup Annotations Files')
        layout.addLayout(title_layout)
        options_layout = QGridLayout()
        layout.addLayout(options_layout)

        dest_directory_label = QLabel(_("Destination:"), self)
        dest_directory_label.setToolTip(_("Select the destination the annotations files are to be backed up in."))
        self.dest_directory_edit = QLineEdit(self)
        self.dest_directory_edit.setMinimumSize(200, 0)
        dest_directory_label.setBuddy(self.dest_directory_edit)
        dest_pick_button = QPushButton(_("..."), self)
        dest_pick_button.setMaximumSize(24, 20)
        dest_pick_button.clicked.connect(self._get_dest_directory_name)
        options_layout.addWidget(dest_directory_label, 0, 0, 1, 1)
        options_layout.addWidget(self.dest_directory_edit, 0, 1, 1, 1)
        options_layout.addWidget(dest_pick_button, 0, 2, 1, 1)

        # Dialog buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.ok_clicked)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def ok_clicked(self):

        if len(self.dest_directory_edit.text()) == 0:
            return error_dialog(self,'No destination',
                               'You must enter a destination directory to save the annotation files in',
                                show=True, show_copy_button=False)

        self.options['dest_directory'] = unicode(self.dest_directory_edit.text())
        gprefs.set(self.unique_pref_name+':settings', self.options)
        self.accept()

    def dest_path(self):
        return self.dest_directory_edit.text()

    def _get_dest_directory_name(self):
        path = choose_dir(self, 'backup annotations destination dialog','Choose destination directory')
        self.dest_directory_edit.setText(path)


class CoverUploadOptionsDialog(SizePersistedDialog):

    def __init__(self, parent, plugin_action):
        SizePersistedDialog.__init__(self, parent, 'sony utilities plugin:cover upload settings dialog')
        self.plugin_action = plugin_action
        self.help_anchor   = "UploadCovers"

        self.initialize_controls()

        self.options = gprefs.get(self.unique_pref_name+':settings', {})

        # Set some default values from last time dialog was used.
        blackandwhite = self.options.get('blackandwhite', False)
        self.blackandwhite_checkbox.setCheckState(Qt.Checked if blackandwhite else Qt.Unchecked)
        keep_cover_aspect = self.options.get('keep_cover_aspect', False)
        self.keep_cover_aspect_checkbox.setCheckState(Qt.Checked if keep_cover_aspect else Qt.Unchecked)
#         kepub_covers = self.options.get('kepub_covers', False)
#         self.kepub_covers_checkbox.setCheckState(Qt.Checked if kepub_covers else Qt.Unchecked)

        # Cause our dialog size to be restored from prefs or created on first usage
        self.resize_dialog()

    def initialize_controls(self):
        self.setWindowTitle(DIALOG_NAME)
        layout = QVBoxLayout(self)
        self.setLayout(layout)
        title_layout = ImageTitleLayout(self, 'images/icon.png', 'Upload Covers')
        layout.addLayout(title_layout)

        options_group = QGroupBox(_("Upload Covers"), self)
        layout.addWidget(options_group)
        options_layout = QGridLayout()
        options_group.setLayout(options_layout)
        self.blackandwhite_checkbox = QCheckBox(_("Black and White Covers"), self)
        options_layout.addWidget(self.blackandwhite_checkbox, 0, 0, 1, 1)
        self.keep_cover_aspect_checkbox = QCheckBox(_("Keep cover aspect ratio"), self)
        options_layout.addWidget(self.keep_cover_aspect_checkbox, 0, 1, 1, 1)
#         self.kepub_covers_checkbox = QCheckBox(_("Upload covers for Sony epubs"), self)
#         options_layout.addWidget(self.kepub_covers_checkbox, 1, 0, 1, 1)

        # Dialog buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.ok_clicked)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def ok_clicked(self):

        self.options['blackandwhite']     = self.blackandwhite_checkbox.checkState() == Qt.Checked
        self.options['keep_cover_aspect'] = self.keep_cover_aspect_checkbox.checkState() == Qt.Checked
#         self.options['kepub_covers']      = self.kepub_covers_checkbox.checkState() == Qt.Checked

        gprefs.set(self.unique_pref_name+':settings', self.options)
        self.accept()


class RemoveCoverOptionsDialog(SizePersistedDialog):

    def __init__(self, parent, plugin_action):
        SizePersistedDialog.__init__(self, parent, 'sony utilities plugin:remove cover settings dialog')
        self.plugin_action = plugin_action
        self.help_anchor   = "RemoveCovers"

        self.initialize_controls()

        self.options = gprefs.get(self.unique_pref_name+':settings', {})

#         kepub_covers = self.options.get('kepub_covers', False)
#         self.kepub_covers_checkbox.setCheckState(Qt.Checked if kepub_covers else Qt.Unchecked)

        # Cause our dialog size to be restored from prefs or created on first usage
        self.resize_dialog()

    def initialize_controls(self):
        self.setWindowTitle(DIALOG_NAME)
        layout = QVBoxLayout(self)
        self.setLayout(layout)
        title_layout = ImageTitleLayout(self, 'images/icon.png', 'Remove Covers')
        layout.addLayout(title_layout)

        options_group = QGroupBox(_("Remove Covers"), self)
        layout.addWidget(options_group)
        options_layout = QGridLayout()
        options_group.setLayout(options_layout)
#         self.kepub_covers_checkbox = QCheckBox(_("Remove covers for Sony epubs"), self)
#         self.kepub_covers_checkbox.setToolTip(_("Check this if you want to remove covers for any Sony epubs synced from the Sony server."))
#         options_layout.addWidget(self.kepub_covers_checkbox, 0, 0, 1, 1)

        # Dialog buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.ok_clicked)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def ok_clicked(self):

#         self.options['kepub_covers'] = self.kepub_covers_checkbox.checkState() == Qt.Checked

        gprefs.set(self.unique_pref_name+':settings', self.options)
        self.accept()


class BlockAnalyticsOptionsDialog(SizePersistedDialog):

    def __init__(self, parent, plugin_action):
        SizePersistedDialog.__init__(self, parent, 'sony utilities plugin:block analytics settings dialog')
        self.plugin_action = plugin_action
        self.help_anchor   = "BlockAnalyticsEvents"

        self.initialize_controls()

        # Cause our dialog size to be restored from prefs or created on first usage
        self.resize_dialog()

    def initialize_controls(self):
        self.setWindowTitle(DIALOG_NAME)
        layout = QVBoxLayout(self)
        self.setLayout(layout)
        title_layout = ImageTitleLayout(self, 'images/icon.png', 'Block Analytics')
        layout.addLayout(title_layout)

        options_group = QGroupBox(_("AnalyticsEvents Database Trigger"), self)
        options_group.setToolTip(_("When an entry is added to the AnalyticsEvents, it will be removed."))
        layout.addWidget(options_group)
        options_layout = QGridLayout()
        options_group.setLayout(options_layout)

        self.create_trigger_radiobutton = QRadioButton(_("Create or change trigger"), self)
        self.create_trigger_radiobutton.setToolTip(_("To create or change the trigger, select this option."))
        options_layout.addWidget(self.create_trigger_radiobutton, 1, 0, 1, 1)

        self.delete_trigger_radiobutton = QRadioButton(_("Delete trigger"), self)
        self.delete_trigger_radiobutton.setToolTip(_("This will remove the existing trigger and let the device work as Sony intended it."))
        options_layout.addWidget(self.delete_trigger_radiobutton, 1, 1, 1, 1)

        # Dialog buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.ok_clicked)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def ok_clicked(self):
        self.options = {}
        self.options[cfg.KEY_CREATE_ANALYTICSEVENTS_TRIGGER] = self.create_trigger_radiobutton.isChecked()
        self.options[cfg.KEY_DELETE_ANALYTICSEVENTS_TRIGGER] = self.delete_trigger_radiobutton.isChecked()

        # Only if the user has checked at least one option will we continue
        for key in self.options:
            if self.options[key]:
                self.accept()
                return
        return error_dialog(self, 'No options selected',
                            'You must select at least one option to continue',
                            show=True, show_copy_button=False)


class CleanImagesDirOptionsDialog(SizePersistedDialog):

    def __init__(self, parent, plugin_action):
        SizePersistedDialog.__init__(self, parent, 'sony utilities plugin:clean images dir settings dialog')
        self.plugin_action = plugin_action
        self.help_anchor   = "CleanImagesDir"

        self.initialize_controls()

        self.options = gprefs.get(self.unique_pref_name+':settings', {})

        delete_extra_covers = self.options.get('delete_extra_covers', False)
        self.delete_extra_covers_checkbox.setCheckState(Qt.Checked if delete_extra_covers else Qt.Unchecked)

        # Cause our dialog size to be restored from prefs or created on first usage
        self.resize_dialog()

    def initialize_controls(self):
        self.setWindowTitle(DIALOG_NAME)
        layout = QVBoxLayout(self)
        self.setLayout(layout)
        title_layout = ImageTitleLayout(self, 'images/icon.png', 'Clean Images Directory')
        layout.addLayout(title_layout)

        options_group = QGroupBox(_("Clean Images"), self)
        layout.addWidget(options_group)
        options_layout = QGridLayout()
        options_group.setLayout(options_layout)
        self.delete_extra_covers_checkbox = QCheckBox(_("Delete extra cover image files"), self)
        self.delete_extra_covers_checkbox.setToolTip(_("Check this if you want to delete the extra cover image files from the images directory on the device."))
        options_layout.addWidget(self.delete_extra_covers_checkbox, 0, 0, 1, 1)

        # Dialog buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.ok_clicked)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def ok_clicked(self):

        self.options['delete_extra_covers'] = self.delete_extra_covers_checkbox.checkState() == Qt.Checked

        gprefs.set(self.unique_pref_name+':settings', self.options)
        self.accept()


class LockSeriesDialog(SizePersistedDialog):

    def __init__(self, parent, title, initial_value):
        SizePersistedDialog.__init__(self, parent, 'Manage Series plugin:lock series dialog')
        self.initialize_controls(title, initial_value)

        # Cause our dialog size to be restored from prefs or created on first usage
        self.resize_dialog()

    def initialize_controls(self, title, initial_value):
        self.setWindowTitle(_("Lock Series Index"))
        layout = QVBoxLayout(self)
        self.setLayout(layout)
        title_layout = ImageTitleLayout(self, 'images/lock32.png', 'Lock Series Index')
        layout.addLayout(title_layout)

        layout.addSpacing(10)
        self.title_label = QLabel('Series index for book: \'%s\''%title, self)
        layout.addWidget(self.title_label)

        hlayout = QHBoxLayout()
        layout.addLayout(hlayout)

        self.value_spinbox = QDoubleSpinBox(self)
        self.value_spinbox.setRange(0, 99000000)
        self.value_spinbox.setDecimals(2)
        self.value_spinbox.setValue(initial_value)
        self.value_spinbox.selectAll()
        hlayout.addWidget(self.value_spinbox, 0)
        hlayout.addStretch(1)

        self.assign_same_checkbox = QCheckBox(_("&Assign this index value to all remaining books"), self)
        layout.addWidget(self.assign_same_checkbox)
        layout.addStretch(1)

        # Dialog buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def get_value(self):
        return float(unicode(self.value_spinbox.value()))

    def assign_same_value(self):
        return self.assign_same_checkbox.isChecked()

class TitleWidgetItem(QTableWidgetItem):

    def __init__(self, book):
        if isinstance(book, SeriesBook):
            QTableWidgetItem.__init__(self, book.title())
            self.title_sort = book.title()
            if not book.is_valid():
                self.setIcon(get_icon('dialog_warning.png'))
                self.setToolTip(_("You have conflicting or out of sequence series indexes"))
            elif book.id() is None:
                self.setIcon(get_icon('add_book.png'))
                self.setToolTip(_("Empty book added to series"))
            elif book.is_title_changed() or book.is_pubdate_changed() or book.is_series_changed():
                self.setIcon(get_icon('format-list-ordered.png'))
                self.setToolTip(_("The book data has been changed"))
            else:
                self.setIcon(get_icon('ok.png'))
                self.setToolTip(_("The series data is unchanged"))
        else:
            QTableWidgetItem.__init__(self, book.title)
            self.title_sort = book.title_sort

    def __lt__(self, other):
        return (self.title_sort < other.title_sort)


class AuthorsTableWidgetItem(ReadOnlyTableWidgetItem):

    def __init__(self, authors, author_sort=None):
        text = ' & '.join(authors)
        ReadOnlyTableWidgetItem.__init__(self, text)
#        self.setTextColor(Qt.darkGray)
        self.setForeground(Qt.darkGray)
        self.author_sort = author_sort

    def __lt__(self, other):
        return (self.author_sort < other.author_sort)


class SeriesTableWidgetItem(ReadOnlyTableWidgetItem):

    def __init__(self, series_name, series_index, is_original=False, assigned_index=None):
        if series_name:
            text = '%s [%s]' % (series_name, series_index)
            text = '%s - %s' % (series_name, series_index)
#            text = '%s [%s]' % (series_name, fmt_sidx(series_index))
#            text = '%s - %s' % (series_name, fmt_sidx(series_index))
        else:
            text = ''
        ReadOnlyTableWidgetItem.__init__(self, text)
        if assigned_index is not None:
            self.setIcon(get_icon('images/lock.png'))
            self.setToolTip(_("Value assigned by user"))
        if is_original:
            self.setForeground(Qt.darkGray)


class SeriesColumnComboBox(QComboBox):

    def __init__(self, parent, series_columns):
        QComboBox.__init__(self, parent)
        self.series_columns = series_columns
        for key, column in series_columns.iteritems():
            self.addItem('%s (%s)'% (key, column['name']))
        self.insertItem(0, 'Series')

    def select_text(self, selected_key):
        if selected_key == 'Series':
            self.setCurrentIndex(0)
        else:
            for idx, key in enumerate(self.seriesColumns.keys()):
                if key == selected_key:
                    self.setCurrentIndex(idx)
                    return

    def selected_value(self):
        if self.currentIndex() == 0:
            return 'Series'
        return self.series_columns.keys()[self.currentIndex() - 1]


class SeriesTableWidget(QTableWidget):

    def __init__(self, parent):
        QTableWidget.__init__(self, parent)
        self.create_context_menu()
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setDropIndicatorShown(True)
        self.fmt = tweaks['gui_pubdate_display_format']
        if self.fmt is None:
            self.fmt = 'MMM yyyy'

    def create_context_menu(self):
        self.setContextMenuPolicy(Qt.ActionsContextMenu)
        self.assign_original_index_action = QAction(_("Lock original series index"), self)
        self.assign_original_index_action.setIcon(get_icon('images/lock.png'))
        self.assign_original_index_action.triggered.connect(self.parent().assign_original_index)
        self.addAction(self.assign_original_index_action)
        self.assign_index_action = QAction(_("Lock series index..."), self)
        self.assign_index_action.setIcon(get_icon('images/lock.png'))
        self.assign_index_action.triggered.connect(self.parent().assign_index)
        self.addAction(self.assign_index_action)
        self.clear_index_action = QAction(_("Unlock series index"), self)
        self.clear_index_action.setIcon(get_icon('images/lock_delete.png'))
        self.clear_index_action.triggered.connect(partial(self.parent().clear_index, all_rows=False))
        self.addAction(self.clear_index_action)
        self.clear_all_index_action = QAction(_("Unlock all series index"), self)
        self.clear_all_index_action.setIcon(get_icon('images/lock_open.png'))
        self.clear_all_index_action.triggered.connect(partial(self.parent().clear_index, all_rows=True))
        self.addAction(self.clear_all_index_action)
        sep2 = QAction(self)
        sep2.setSeparator(True)
        self.addAction(sep2)
        for name in ['PubDate', 'Original Series Index', 'Original Series Name']:
            sort_action = QAction('Sort by '+name, self)
            sort_action.setIcon(get_icon('images/sort.png'))
            sort_action.triggered.connect(partial(self.parent().sort_by, name))
            self.addAction(sort_action)
        sep3 = QAction(self)
        sep3.setSeparator(True)
        self.addAction(sep3)
        for name, icon in [('FantasticFiction', 'images/ms_ff.png'),
                           ('Goodreads', 'images/ms_goodreads.png'),
                           ('Google', 'images/ms_google.png'),
                           ('Wikipedia', 'images/ms_wikipedia.png')]:
            menu_action = QAction('Search %s' % name, self)
            menu_action.setIcon(get_icon(icon))
            menu_action.triggered.connect(partial(self.parent().search_web, name))
            self.addAction(menu_action)

    def populate_table(self, books):
        self.clear()
        self.setAlternatingRowColors(True)
        self.setRowCount(len(books))
        header_labels = ['Title', 'Author(s)', 'PubDate', 'Series', 'New Series']
        self.setColumnCount(len(header_labels))
        self.setHorizontalHeaderLabels(header_labels)
        self.verticalHeader().setDefaultSectionSize(24)
        self.horizontalHeader().setStretchLastSection(True)

        for row, book in enumerate(books):
            self.populate_table_row(row, book)

        self.resizeColumnToContents(0)
        self.setMinimumColumnWidth(0, 150)
        self.setColumnWidth(1, 100)
        self.resizeColumnToContents(2)
        self.setMinimumColumnWidth(2, 60)
        self.resizeColumnToContents(3)
        self.setMinimumColumnWidth(3, 120)
        self.setSortingEnabled(False)
        self.setMinimumSize(550, 0)
        self.selectRow(0)
        delegate = DateDelegate(self, self.fmt, default_to_today=False)
        self.setItemDelegateForColumn(2, delegate)

    def setMinimumColumnWidth(self, col, minimum):
        if self.columnWidth(col) < minimum:
            self.setColumnWidth(col, minimum)

    def populate_table_row(self, row, book):
        self.blockSignals(True)
        self.setItem(row, 0, TitleWidgetItem(book))
        self.setItem(row, 1, AuthorsTableWidgetItem(book.authors()))
        self.setItem(row, 2, DateTableWidgetItem(book.pubdate(), is_read_only=False,
                                                 default_to_today=False, fmt=self.fmt))
        self.setItem(row, 3, SeriesTableWidgetItem(book.orig_series_name(),
#                                                   book.orig_series_index(),
                                                   book.orig_series_index_string(),
                                                   is_original=True))
        self.setItem(row, 4, SeriesTableWidgetItem(book.series_name(),
                                                   book.series_index_string(),
                                                   assigned_index=book.assigned_index()))
        self.blockSignals(False)

    def swap_row_widgets(self, src_row, dest_row):
        self.blockSignals(True)
        self.insertRow(dest_row)
        for col in range(self.columnCount()):
            self.setItem(dest_row, col, self.takeItem(src_row, col))
        self.removeRow(src_row)
        self.blockSignals(False)

    def select_and_scroll_to_row(self, row):
        self.selectRow(row)
        self.scrollToItem(self.currentItem())

    def event_has_mods(self, event=None):
        mods = event.modifiers() if event is not None else \
                QApplication.keyboardModifiers()
        return mods & Qt.ControlModifier or mods & Qt.ShiftModifier

    def mousePressEvent(self, event):
        ep = event.pos()
        if self.indexAt(ep) not in self.selectionModel().selectedIndexes() and \
                event.button() == Qt.LeftButton and not self.event_has_mods():
            self.setDragEnabled(False)
        else:
            self.setDragEnabled(True)
        return QTableWidget.mousePressEvent(self, event)

    def dropEvent(self, event):
        rows = self.selectionModel().selectedRows()
        selrows = []
        for row in rows:
            selrows.append(row.row())
        selrows.sort()
        drop_row = self.rowAt(event.pos().y())
        if drop_row == -1:
            drop_row = self.rowCount() - 1
        rows_before_drop = [idx for idx in selrows if idx < drop_row]
        rows_after_drop = [idx for idx in selrows if idx >= drop_row]

        dest_row = drop_row
        for selrow in rows_after_drop:
            dest_row += 1
            self.swap_row_widgets(selrow + 1, dest_row)
            book = self.parent().books.pop(selrow)
            self.parent().books.insert(dest_row, book)

        dest_row = drop_row + 1
        for selrow in reversed(rows_before_drop):
            self.swap_row_widgets(selrow, dest_row)
            book = self.parent().books.pop(selrow)
            self.parent().books.insert(dest_row - 1, book)
            dest_row = dest_row - 1

        event.setDropAction(Qt.CopyAction)
        # Determine the new row selection
        self.selectRow(drop_row)
        self.parent().renumber_series()

    def set_series_column_headers(self, text):
        item = self.horizontalHeaderItem(3)
        if item is not None:
            item.setText('Original '+text)
        item = self.horizontalHeaderItem(4)
        if item is not None:
            item.setText('New '+text)


class ManageSeriesDeviceDialog(SizePersistedDialog):

    def __init__(self, parent, plugin_action, books, all_series, series_columns):
        SizePersistedDialog.__init__(self, parent, 'sony utilities plugin:series dialog')
        self.plugin_action = plugin_action
        self.db = self.parent().library_view.model().db
        self.books = books
        self.all_series = all_series
        self.series_columns = series_columns
        self.block_events = True

        self.initialize_controls()

        # Books will have been sorted by the Calibre series column
        # Choose the appropriate series column to be editing
        initial_series_column = 'Series'
        self.series_column_combo.select_text(initial_series_column)
        if len(series_columns) == 0:
            # Will not have fired the series_column_changed event
            self.series_column_changed()
        # Renumber the books using the assigned series name/index in combos/spinbox
        self.renumber_series(display_in_table=False)

        # Display the books in the table
        self.block_events = False
        self.series_table.populate_table(books)
        if len(unicode(self.series_combo.text()).strip()) > 0:
            self.series_table.setFocus()
        else:
            self.series_combo.setFocus()
        self.update_series_headers(initial_series_column)

        # Cause our dialog size to be restored from prefs or created on first usage
        self.resize_dialog()

    def initialize_controls(self):
        self.setWindowTitle(_("Manage Series"))
        layout = QVBoxLayout(self)
        self.setLayout(layout)
        title_layout = ImageTitleLayout(self, 'images/manage_series.png', 'Manage Series on Device')
        layout.addLayout(title_layout)

        # Series name and start index layout
        series_name_layout = QHBoxLayout()
        layout.addLayout(series_name_layout)

        series_column_label = QLabel(_("Series &Column:"), self)
        series_name_layout.addWidget(series_column_label)
        self.series_column_combo = SeriesColumnComboBox(self, self.series_columns)
        self.series_column_combo.currentIndexChanged[int].connect(self.series_column_changed)
        series_name_layout.addWidget(self.series_column_combo)
        series_column_label.setBuddy(self.series_column_combo)
        series_name_layout.addSpacing(20)

        series_label = QLabel(_("Series &Name:"), self)
        series_name_layout.addWidget(series_label)
        self.series_combo = EditWithComplete(self)
        self.series_combo.setEditable(True)
        self.series_combo.setInsertPolicy(QComboBox.InsertAlphabetically)
        self.series_combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.series_combo.setMinimumContentsLength(25)
        self.series_combo.currentIndexChanged[int].connect(self.series_changed)
        self.series_combo.editTextChanged.connect(self.series_changed)
        self.series_combo.set_separator(None)
        series_label.setBuddy(self.series_combo)
        series_name_layout.addWidget(self.series_combo)
        series_name_layout.addSpacing(20)
        series_start_label = QLabel(_("&Start At:"), self)
        series_name_layout.addWidget(series_start_label)
        self.series_start_number = QSpinBox(self)
        self.series_start_number.setRange(0, 99000000)
        self.series_start_number.valueChanged[int].connect(self.series_start_changed)
        series_name_layout.addWidget(self.series_start_number)
        series_start_label.setBuddy(self.series_start_number)
        series_name_layout.insertStretch(-1)

        # Series name and start index layout
        formatting_layout = QHBoxLayout()
        layout.addLayout(formatting_layout)

        self.clean_title_checkbox = QCheckBox(_("Clean titles of Sony books"), self)
        formatting_layout.addWidget(self.clean_title_checkbox)
        self.clean_title_checkbox.setToolTip(_("Removes series information from the titles. For Sony books, this is '(Series Name - #1)'"))
        self.clean_title_checkbox.clicked.connect(self.clean_title_checkbox_clicked)

        # Main series table layout
        table_layout = QHBoxLayout()
        layout.addLayout(table_layout)

        self.series_table = SeriesTableWidget(self)
        self.series_table.itemSelectionChanged.connect(self.item_selection_changed)
        self.series_table.cellChanged[int,int].connect(self.cell_changed)

        table_layout.addWidget(self.series_table)
        table_button_layout = QVBoxLayout()
        table_layout.addLayout(table_button_layout)
        move_up_button = QToolButton(self)
        move_up_button.setToolTip(_("Move book up in series (Alt+Up)"))
        move_up_button.setIcon(get_icon('arrow-up.png'))
        move_up_button.setShortcut(_('Alt+Up'))
        move_up_button.clicked.connect(self.move_rows_up)
        table_button_layout.addWidget(move_up_button)
        move_down_button = QToolButton(self)
        move_down_button.setToolTip(_("Move book down in series (Alt+Down)"))
        move_down_button.setIcon(get_icon('arrow-down.png'))
        move_down_button.setShortcut(_('Alt+Down'))
        move_down_button.clicked.connect(self.move_rows_down)
        table_button_layout.addWidget(move_down_button)
        spacerItem1 = QSpacerItem(20, 40, QtGui.QSizePolicy.Minimum, QtGui.QSizePolicy.Expanding)
        table_button_layout.addItem(spacerItem1)
        assign_index_button = QToolButton(self)
        assign_index_button.setToolTip(_("Lock to index value..."))
        assign_index_button.setIcon(get_icon('images/lock.png'))
        assign_index_button.clicked.connect(self.assign_index)
        table_button_layout.addWidget(assign_index_button)
        clear_index_button = QToolButton(self)
        clear_index_button.setToolTip(_("Unlock series index"))
        clear_index_button.setIcon(get_icon('images/lock_delete.png'))
        clear_index_button.clicked.connect(self.clear_index)
        table_button_layout.addWidget(clear_index_button)
        spacerItem2 = QSpacerItem(20, 40, QtGui.QSizePolicy.Minimum, QtGui.QSizePolicy.Expanding)
        table_button_layout.addItem(spacerItem2)
        delete_button = QToolButton(self)
        delete_button.setToolTip(_("Remove book from the series list"))
        delete_button.setIcon(get_icon('trash.png'))
        delete_button.clicked.connect(self.remove_book)
        table_button_layout.addWidget(delete_button)
        spacerItem3 = QSpacerItem(20, 40, QtGui.QSizePolicy.Minimum, QtGui.QSizePolicy.Expanding)
        table_button_layout.addItem(spacerItem3)
        move_left_button = QToolButton(self)
        move_left_button.setToolTip(_("Move series index to left of decimal point (Alt+Left)"))
        move_left_button.setIcon(get_icon('back.png'))
        move_left_button.setShortcut(_('Alt+Left'))
        move_left_button.clicked.connect(partial(self.series_indent_change, -1))
        table_button_layout.addWidget(move_left_button)
        move_right_button = QToolButton(self)
        move_right_button.setToolTip(_("Move series index to right of decimal point (Alt+Right)"))
        move_right_button.setIcon(get_icon('forward.png'))
        move_right_button.setShortcut(_('Alt+Right'))
        move_right_button.clicked.connect(partial(self.series_indent_change, 1))
        table_button_layout.addWidget(move_right_button)

        # Dialog buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        keep_button = button_box.addButton(_(" &Restore Original Series "), QDialogButtonBox.ResetRole)
        keep_button.clicked.connect(self.restore_original_series)

    def reject(self):
        debug_print("ManageSeriesDeviceDialog:reject")
        for book in self.books:
            book.revert_changes()
        super(ManageSeriesDeviceDialog, self).reject()

    def series_column_changed(self):
        debug_print("start")
        series_column = self.series_column_combo.selected_value()
        SeriesBook.series_column = series_column
        # Choose a series name and series index from the first book in the list
        initial_series_name = ''
        initial_series_index = 1
        if len(self.books) > 0:
            first_book = self.books[0]
            initial_series_name = first_book.series_name()
            debug_print("initial_series_name", initial_series_name)
            if initial_series_name:
                debug_print("series_column_changed first_book.series_index()=", first_book.series_index())
                initial_series_index = int(first_book.series_index())
        # Populate the series name combo as appropriate for that column
        self.initialize_series_name_combo(series_column, initial_series_name)
        # Populate the series index spinbox with the initial value
        self.series_start_number.setProperty('value', initial_series_index)
        self.update_series_headers(series_column)
        if self.block_events:
            return
        self.renumber_series()

    def update_series_headers(self, series_column):
        if series_column == 'Series':
            self.series_table.set_series_column_headers(series_column)
        else:
            header_text = self.series_columns[series_column]['name']
            self.series_table.set_series_column_headers(header_text)

    def initialize_series_name_combo(self, series_column, series_name):
        self.series_combo.clear()
        if series_name is None:
            series_name = ''
        values = self.all_series
        if series_column == 'Series':
            self.series_combo.update_items_cache([x[1] for x in values])
            for i in values:
                _id, name = i
                self.series_combo.addItem(name)
        else:
            label = self.db.field_metadata.key_to_label(series_column)
            values = list(self.db.all_custom(label=label))
            values.sort(key=sort_key)
            self.series_combo.update_items_cache(values)
            for name in values:
                self.series_combo.addItem(name)
        self.series_combo.setEditText(series_name)

    def series_changed(self):
        if self.block_events:
            return
        self.renumber_series()

    def series_start_changed(self):
        if self.block_events:
            return
        self.renumber_series()

    def restore_original_series(self):
        # Go through the books and overwrite the indexes with the originals, fixing in place
        for book in self.books:
            if book.orig_series_index():
                book.set_assigned_index(book.orig_series_index())
                book.set_series_name(book.orig_series_name())
                book.set_series_index(book.orig_series_index())
        # Now renumber the whole series so that anything in between gets changed
        self.renumber_series()

    def clean_title(self, remove_series):
        # Go through the books and clean the Sony series from the title
        for book in self.books:
            if remove_series:
                series_in_title = re.findall(r"\(.*\)", book._orig_title)
                if len(series_in_title) > 0:
                    book._mi.title = book._orig_title.replace(series_in_title[len(series_in_title) - 1], "")
            else:
                book._mi.title = book._orig_title
        # Now renumber the whole series so that anything in between gets changed
        self.renumber_series()

    def clean_title_checkbox_clicked(self, checked):
#        self.clean_title = checked
        self.clean_title(checked)

    def renumber_series(self, display_in_table=True):
        if len(self.books) == 0:
            return
        series_name = unicode(self.series_combo.currentText()).strip()
        series_index = float(unicode(self.series_start_number.value()))
        last_series_indent = 0
        for row, book in enumerate(self.books):
            book.set_series_name(series_name)
            series_indent = book.series_indent()
            if book.assigned_index() is not None:
                series_index = book.assigned_index()
            else:
                if series_indent >= last_series_indent:
                    if series_indent == 0:
                        if row > 0:
                            series_index += 1.
                    elif series_indent == 1:
                        series_index += 0.1
                    else:
                        series_index += 0.01
                else:
                    # When series indent decreases, need to round to next
                    if series_indent == 1:
                        series_index = round(series_index + 0.05, 1)
                    else: # series_indent == 0:
                        series_index = round(series_index + 0.5, 0)
            book.set_series_index(series_index)
            last_series_indent = series_indent
        # Now determine whether books have a valid index or not
        self.books[0].set_is_valid(True)
        for row in range(len(self.books)-1, 0, -1):
            book = self.books[row]
            previous_book = self.books[row-1]
            if book.series_index() <= previous_book.series_index():
                book.set_is_valid(False)
            else:
                book.set_is_valid(True)
        if display_in_table:
            for row, book in enumerate(self.books):
                self.series_table.populate_table_row(row, book)

    def assign_original_index(self):
        if len(self.books) == 0:
            return
        for row in self.series_table.selectionModel().selectedRows():
            book = self.books[row.row()]
            book.set_assigned_index(book.orig_series_index())
        self.renumber_series()
        self.item_selection_changed()

    def assign_index(self):
        if len(self.books) == 0:
            return
        auto_assign_value = None
        for row in self.series_table.selectionModel().selectedRows():
            book = self.books[row.row()]
            if auto_assign_value is not None:
                book.set_assigned_index(auto_assign_value)
                continue

            d = LockSeriesDialog(self, book.title(), book.series_index())
            d.exec_()
            if d.result() != d.Accepted:
                break
            if d.assign_same_value():
                auto_assign_value = d.get_value()
                book.set_assigned_index(auto_assign_value)
            else:
                book.set_assigned_index(d.get_value())

        self.renumber_series()
        self.item_selection_changed()

    def clear_index(self, all_rows=False):
        if len(self.books) == 0:
            return
        if all_rows:
            for book in self.books:
                book.set_assigned_index(None)
        else:
            for row in self.series_table.selectionModel().selectedRows():
                book = self.books[row.row()]
                book.set_assigned_index(None)
        self.renumber_series()

    def remove_book(self):
        if not question_dialog(self, _("Are you sure?"), '<p>'+
                _("Remove the selected book(s) from the series list?"), show_copy_button=False):
            return
        rows = self.series_table.selectionModel().selectedRows()
        if len(rows) == 0:
            return
        selrows = []
        for row in rows:
            selrows.append(row.row())
        selrows.sort()
        first_sel_row = self.series_table.currentRow()
        for row in reversed(selrows):
            self.books.pop(row)
            self.series_table.removeRow(row)
        if first_sel_row < self.series_table.rowCount():
            self.series_table.select_and_scroll_to_row(first_sel_row)
        elif self.series_table.rowCount() > 0:
            self.series_table.select_and_scroll_to_row(first_sel_row - 1)
        self.renumber_series()

    def move_rows_up(self):
        self.series_table.setFocus()
        rows = self.series_table.selectionModel().selectedRows()
        if len(rows) == 0:
            return
        first_sel_row = rows[0].row()
        if first_sel_row <= 0:
            return
        # Workaround for strange selection bug in Qt which "alters" the selection
        # in certain circumstances which meant move down only worked properly "once"
        selrows = []
        for row in rows:
            selrows.append(row.row())
        selrows.sort()
        for selrow in selrows:
            self.series_table.swap_row_widgets(selrow - 1, selrow + 1)
            self.books[selrow-1], self.books[selrow] = self.books[selrow], self.books[selrow-1]

        scroll_to_row = first_sel_row - 1
        if scroll_to_row > 0:
            scroll_to_row = scroll_to_row - 1
        self.series_table.scrollToItem(self.series_table.item(scroll_to_row, 0))
        self.renumber_series()

    def move_rows_down(self):
        self.series_table.setFocus()
        rows = self.series_table.selectionModel().selectedRows()
        if len(rows) == 0:
            return
        last_sel_row = rows[-1].row()
        if last_sel_row == self.series_table.rowCount() - 1:
            return
        # Workaround for strange selection bug in Qt which "alters" the selection
        # in certain circumstances which meant move down only worked properly "once"
        selrows = []
        for row in rows:
            selrows.append(row.row())
        selrows.sort()
        for selrow in reversed(selrows):
            self.series_table.swap_row_widgets(selrow + 2, selrow)
            self.books[selrow+1], self.books[selrow] = self.books[selrow], self.books[selrow+1]

        scroll_to_row = last_sel_row + 1
        if scroll_to_row < self.series_table.rowCount() - 1:
            scroll_to_row = scroll_to_row + 1
        self.series_table.scrollToItem(self.series_table.item(scroll_to_row, 0))
        self.renumber_series()

    def series_indent_change(self, delta):
        for row in self.series_table.selectionModel().selectedRows():
            book = self.books[row.row()]
            series_indent = book.series_indent()
            if delta > 0:
                if series_indent < 2:
                    book.set_series_indent(series_indent+1)
            else:
                if series_indent > 0:
                    book.set_series_indent(series_indent-1)
            book.set_assigned_index(None)
        self.renumber_series()

    def sort_by(self, name):
        if name == 'PubDate':
            self.books = sorted(self.books, key=lambda k: k.sort_key(sort_by_pubdate=True))
        elif name == 'Original Series Name':
            self.books = sorted(self.books, key=lambda k: k.sort_key(sort_by_name=True))
        else:
            self.books = sorted(self.books, key=lambda k: k.sort_key())
        self.renumber_series()

    def search_web(self, name):
        URLS =  {
                'FantasticFiction': 'http://www.fantasticfiction.co.uk/search/?searchfor=author&keywords={author}',
                'Goodreads': 'http://www.goodreads.com/search/search?q={author}&search_type=books',
                'Google': 'http://www.google.com/#sclient=psy&q=%22{author}%22+%22{title}%22',
                'Wikipedia': 'http://en.wikipedia.org/w/index.php?title=Special%3ASearch&search={author}'
                }
        for row in self.series_table.selectionModel().selectedRows():
            book = self.books[row.row()]
            safe_title = self.convert_to_search_text(book.title())
            safe_author = self.convert_author_to_search_text(book.authors()[0])
            url = URLS[name].replace('{title}', safe_title).replace('{author}', safe_author)
            open_url(QUrl.fromEncoded(url))

    def convert_to_search_text(self, text, encoding='utf-8'):
        # First we strip characters we will definitely not want to pass through.
        # Periods from author initials etc do not need to be supplied
        text = text.replace('.', '')
        # Now encode the text using Python function with chosen encoding
        text = quote_plus(text.encode(encoding, 'ignore'))
        # If we ended up with double spaces as plus signs (++) replace them
        text = text.replace('++','+')
        return text

    def convert_author_to_search_text(self, author, encoding='utf-8'):
        # We want to convert the author name to FN LN format if it is stored LN, FN
        # We do this because some websites (Sony) have crappy search engines that
        # will not match Adams+Douglas but will match Douglas+Adams
        # Not really sure of the best way of determining if the user is using LN, FN
        # Approach will be to check the tweak and see if a comma is in the name

        # Comma separated author will be pipe delimited in Calibre database
        fn_ln_author = author
        if author.find(',') > -1:
            # This might be because of a FN LN,Jr - check the tweak
            sort_copy_method = tweaks['author_sort_copy_method']
            if sort_copy_method == 'invert':
                # Calibre default. Hence "probably" using FN LN format.
                fn_ln_author = author
            else:
                # We will assume that we need to switch the names from LN,FN to FN LN
                parts = author.split(',')
                surname = parts.pop(0)
                parts.append(surname)
                fn_ln_author = ' '.join(parts).strip()
        return self.convert_to_search_text(fn_ln_author, encoding)

    def cell_changed(self, row, column):
        book = self.books[row]
        if column == 0:
            book.set_title(unicode(self.series_table.item(row, column).text()).strip())
        elif column == 2:
            qtdate = convert_qvariant(self.series_table.item(row, column).data(Qt.DisplayRole))
            book.set_pubdate(qt_to_dt(qtdate, as_utc=False))

    def item_selection_changed(self):
        row = self.series_table.currentRow()
        if row == -1:
            return
        has_assigned_index = False
        for row in self.series_table.selectionModel().selectedRows():
            book = self.books[row.row()]
            if book.assigned_index():
                has_assigned_index = True
        self.series_table.clear_index_action.setEnabled(has_assigned_index)
        if not has_assigned_index:
            for book in self.books:
                if book.assigned_index():
                    has_assigned_index = True
        self.series_table.clear_all_index_action.setEnabled(has_assigned_index)

class BooksNotInDeviceDatabaseTableWidget(QTableWidget):

    def __init__(self, parent):
        QTableWidget.__init__(self, parent)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.fmt = tweaks['gui_pubdate_display_format']
        if self.fmt is None:
            self.fmt = 'MMM yyyy'

    def populate_table(self, books):
        self.clear()
        self.setAlternatingRowColors(True)
        self.setRowCount(len(books))
        header_labels = ['Title', 'Author(s)', 'File Path', 'PubDate', 'File Timestamp']
        self.setColumnCount(len(header_labels))
        self.setHorizontalHeaderLabels(header_labels)
        self.verticalHeader().setDefaultSectionSize(24)
        self.horizontalHeader().setStretchLastSection(True)

        for row, book in enumerate(books):
            self.populate_table_row(row, book)

        self.resizeColumnToContents(0)
        self.setMinimumColumnWidth(0, 150)
        self.setColumnWidth(1, 100)
        self.resizeColumnToContents(2)
        self.setMinimumColumnWidth(2, 200)
        self.setSortingEnabled(True)
        self.setMinimumSize(550, 0)
        self.selectRow(0)
        delegate = DateDelegate(self, self.fmt, default_to_today=False)
        self.setItemDelegateForColumn(3, delegate)


    def setMinimumColumnWidth(self, col, minimum):
        if self.columnWidth(col) < minimum:
            self.setColumnWidth(col, minimum)

    def populate_table_row(self, row, book):
        self.blockSignals(True)
        titleColumn = TitleWidgetItem(book)
        titleColumn.setFlags(Qt.ItemIsSelectable|Qt.ItemIsEnabled)
        self.setItem(row, 0, titleColumn)
        authorColumn = AuthorsTableWidgetItem(book.authors, book.author_sort)
        self.setItem(row, 1, authorColumn)
        pathColumn = QTableWidgetItem(book.path)
        pathColumn.setFlags(Qt.ItemIsSelectable|Qt.ItemIsEnabled)
        self.setItem(row, 2, pathColumn)
        self.setItem(row, 3, DateTableWidgetItem(book.pubdate, is_read_only=True,
                                                 default_to_today=False, fmt=self.fmt))
        self.setItem(row, 4, DateTableWidgetItem(datetime(book.datetime[0], book.datetime[1], book.datetime[2], book.datetime[3], book.datetime[4], book.datetime[5], book.datetime[6], utc_tz), 
                                                 is_read_only=True, default_to_today=False))
        self.blockSignals(False)


class ShowBooksNotInDeviceDatabaseDialog(SizePersistedDialog):

    def __init__(self, parent, books):
        SizePersistedDialog.__init__(self, parent, 'sony utilities plugin:not in device database dialog')
        self.db = self.parent().library_view.model().db
        self.books = books
        self.block_events = True

        self.initialize_controls()

        # Display the books in the table
        self.block_events = False
        self.books_table.populate_table(books)

        # Cause our dialog size to be restored from prefs or created on first usage
        self.resize_dialog()

    def initialize_controls(self):
        self.setWindowTitle(_("Books not in Device Database"))
        layout = QVBoxLayout(self)
        self.setLayout(layout)
        title_layout = ImageTitleLayout(self, 'images/manage_series.png', 'Books not in Device Database')
        layout.addLayout(title_layout)

        # Main series table layout
        table_layout = QHBoxLayout()
        layout.addLayout(table_layout)

        self.books_table = BooksNotInDeviceDatabaseTableWidget(self)
        table_layout.addWidget(self.books_table)

        # Dialog buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok)
        button_box.accepted.connect(self.accept)
        layout.addWidget(button_box)

    def sort_by(self, name):
        if name == 'PubDate':
            self.books = sorted(self.books, key=lambda k: k.sort_key(sort_by_pubdate=True))


class ShowReadingPositionChangesDialog(SizePersistedDialog):

    def __init__(self, parent, plugin_action, reading_locations, db):
        SizePersistedDialog.__init__(self, parent, 'sony utilities plugin:show reading position changes dialog')
        self.plugin_action      = plugin_action
        self.reading_locations, self.options  = reading_locations
        self.block_events       = True
        self.help_anchor        = "ShowReadingPositionChanges"
        self.db                 = db

        self.initialize_controls()

        # Display the books in the table
        self.block_events = False
        self.reading_locations_table.populate_table(self.reading_locations)

        # Cause our dialog size to be restored from prefs or created on first usage
        self.resize_dialog()

    def initialize_controls(self):
        self.setWindowTitle(_("Show Reading Position Changes"))
        layout = QVBoxLayout(self)
        self.setLayout(layout)
        title_layout = ImageTitleLayout(self, 'images/manage_series.png', 'Show Reading Position Changes')
        layout.addLayout(title_layout)

        # Main series table layout
        table_layout = QHBoxLayout()
        layout.addLayout(table_layout)

        self.reading_locations_table = ShowReadingPositionChangesTableWidget(self, self.db)
        table_layout.addWidget(self.reading_locations_table)

        # Dialog buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self._ok_clicked)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _ok_clicked(self):
        self.options = {}

        for i in range(len(self.reading_locations)):
            self.reading_locations_table.selectRow(i)
            enabled = bool(self.reading_locations_table.item(i, 0).checkState())
            debug_print("row=%d, enabled=%s", i, enabled)
            if not enabled:
                book_id = convert_qvariant(self.reading_locations_table.item(i, 7).data(Qt.DisplayRole))
                debug_print("row=%d, book_id=%s", i, book_id)
                del self.reading_locations[book_id]
        self.accept()
        return

    def sort_by(self, name):
        if name == 'PubDate':
            self.shelves = sorted(self.shelves, key=lambda k: k.sort_key(sort_by_pubdate=True))


class ShowReadingPositionChangesTableWidget(QTableWidget):

    def __init__(self, parent, db):
        QTableWidget.__init__(self, parent)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.db = db
#        self.fmt = tweaks['gui_pubdate_display_format']
#        if self.fmt is None:
#            self.fmt = 'MMM yyyy'

        library_db     = self.db #self.gui.current_db
        library_config = cfg.get_library_config(library_db)
        self.sony_bookmark_column = library_config.get(cfg.KEY_CURRENT_LOCATION_CUSTOM_COLUMN, cfg.DEFAULT_LIBRARY_VALUES[cfg.KEY_CURRENT_LOCATION_CUSTOM_COLUMN])
        self.sony_percentRead_column         = library_config.get(cfg.KEY_PERCENT_READ_CUSTOM_COLUMN, cfg.DEFAULT_LIBRARY_VALUES[cfg.KEY_PERCENT_READ_CUSTOM_COLUMN])
        self.rating_column                   = library_config.get(cfg.KEY_RATING_CUSTOM_COLUMN, cfg.DEFAULT_LIBRARY_VALUES[cfg.KEY_RATING_CUSTOM_COLUMN])
        self.last_read_column                = library_config.get(cfg.KEY_LAST_READ_CUSTOM_COLUMN, cfg.DEFAULT_LIBRARY_VALUES[cfg.KEY_LAST_READ_CUSTOM_COLUMN])

    def populate_table(self, reading_positions):
        self.clear()
        self.setAlternatingRowColors(True)
        self.setRowCount(len(reading_positions))
        header_labels = ['', 'Title', 'Authors(s)', 'Current %', 'New %', 'Current Date', 'New Date', "Book ID"]
        self.setColumnCount(len(header_labels))
        self.setHorizontalHeaderLabels(header_labels)
        self.verticalHeader().setDefaultSectionSize(24)
        self.horizontalHeader().setStretchLastSection(True)

        debug_print("reading_positions=", reading_positions)
        row = 0
        for book_id, reading_position in reading_positions.iteritems():
#            debug_print("reading_position=", reading_position)
            self.populate_table_row(row, book_id, reading_position)
            row += 1

        self.resizeColumnToContents(0)
        self.resizeColumnToContents(1)
        self.setMinimumColumnWidth(1, 150)
        self.setColumnWidth(2, 100)
        self.resizeColumnToContents(3)
        self.resizeColumnToContents(4)
        self.resizeColumnToContents(5)
        self.resizeColumnToContents(6)
        self.hideColumn(7)
        self.setSortingEnabled(True)
#        self.setMinimumSize(550, 0)
        self.selectRow(0)
        delegate = DateDelegate(self, default_to_today=False)
        self.setItemDelegateForColumn(5, delegate)
        self.setItemDelegateForColumn(6, delegate)


    def setMinimumColumnWidth(self, col, minimum):
        if self.columnWidth(col) < minimum:
            self.setColumnWidth(col, minimum)

    def populate_table_row(self, row, book_id, reading_position):
#        debug_print("shelf:", row, shelf[0], shelf[1], shelf[2], shelf[3])
        self.blockSignals(True)

        book = self.db.get_metadata(book_id, index_is_id=True, get_cover=False)
#        debug_print("book_id:", book_id)
#        debug_print("book:", book)
#        debug_print("reading_position:", reading_position)

        self.setItem(row, 0, CheckableTableWidgetItem(True))

        titleColumn = QTableWidgetItem(reading_position[6])
        titleColumn.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
        self.setItem(row, 1, titleColumn)

        authorColumn = AuthorsTableWidgetItem(book.authors, book.author_sort)
        self.setItem(row, 2, authorColumn)

        current_percentRead = book.get_user_metadata(self.sony_percentRead_column, True)['#value#'] if self.sony_percentRead_column else None
        current_percent = RatingTableWidgetItem(current_percentRead, is_read_only=True)
        current_percent.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.setItem(row, 3, current_percent)
        
#        debug_print("reading_position[4]:", reading_position[4])
        new_percentRead = 0 
        if reading_position[2] == 1:
            new_percentRead = reading_position[3]
        elif reading_position[2] == 2:
            new_percentRead = 100
        new_percent = RatingTableWidgetItem(new_percentRead, is_read_only=True)
        new_percent.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.setItem(row, 4, new_percent)
        
        current_last_read = book.get_user_metadata(self.last_read_column, True)['#value#'] if self.last_read_column else None
        if current_last_read:
            self.setItem(row, 5, DateTableWidgetItem(current_last_read,
                                                     is_read_only=True,
                                                     default_to_today=False))
        self.setItem(row, 6, DateTableWidgetItem(convert_sony_date(reading_position[5]), 
                                                 is_read_only=True,
                                                 default_to_today=False))
        book_idColumn = RatingTableWidgetItem(book_id)
        self.setItem(row, 7, book_idColumn)
#        titleColumn.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
        self.blockSignals(False)


class FixDuplicateShelvesDialog(SizePersistedDialog):

    def __init__(self, parent, plugin_action, shelves):
        SizePersistedDialog.__init__(self, parent, 'sony utilities plugin:duplicate shelves in device database dialog')
        self.plugin_action = plugin_action
        self.shelves       = shelves
        self.block_events  = True
        self.help_anchor   = "FixDuplicateShelves"
        self.options = {}

        self.initialize_controls()

        # Display the books in the table
        self.block_events = False
        self.shelves_table.populate_table(self.shelves)

        # Cause our dialog size to be restored from prefs or created on first usage
        self.resize_dialog()

    def initialize_controls(self):
        self.setWindowTitle(_("Duplicate Shelves in Device Database"))
        layout = QVBoxLayout(self)
        self.setLayout(layout)
        title_layout = ImageTitleLayout(self, 'images/manage_series.png', 'Duplicate Shelves in Device Database')
        layout.addLayout(title_layout)

        # Main series table layout
        table_layout = QHBoxLayout()
        layout.addLayout(table_layout)

        self.shelves_table = DuplicateShelvesInDeviceDatabaseTableWidget(self)
        table_layout.addWidget(self.shelves_table)

        options_group = QGroupBox(_("Options"), self)
#        options_group.setToolTip(_("When a tile is added or changed, the database trigger will automatically set them to be dismissed. This will be done for the tile types selected above."))
        layout.addWidget(options_group)
        options_layout = QGridLayout()
        options_group.setLayout(options_layout)

        options_layout.addWidget(QLabel(_("Shelf to Keep")), 0, 0, 1, 1)
        self.keep_oldest_radiobutton = QRadioButton(_("Oldest"), self)
#        self.create_trigger_radiobutton.setToolTip(_("To create or change the trigger, select this option."))
        options_layout.addWidget(self.keep_oldest_radiobutton, 0, 1, 1, 1)
        self.keep_oldest_radiobutton.setEnabled(True)

        self.keep_newest_radiobutton = QRadioButton(_("Newest"), self)
#        self.delete_trigger_radiobutton.setToolTip(_("This will remove the existing trigger and let the device work as Sony intended it."))
        options_layout.addWidget(self.keep_newest_radiobutton, 0, 2, 1, 1)
        self.keep_newest_radiobutton.setEnabled(True)
        self.keep_newest_radiobutton.click()

        self.purge_checkbox = QCheckBox(_("Purge duplicate shelves"), self)
        self.purge_checkbox.setToolTip(_(
                    "When this option is selected, the duplicated rows are deleted from the database. "
                    "If this is done, they might be restore during the next sync to the Sony server."
                    ))
        options_layout.addWidget(self.purge_checkbox, 0, 3, 1, 1)

        # Dialog buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self._ok_clicked)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _ok_clicked(self):
        self.options = {}

        self.options[cfg.KEY_KEEP_NEWEST_SHELF] = self.keep_newest_radiobutton.isChecked()
        self.options[cfg.KEY_PURGE_SHELVES]     = self.purge_checkbox.checkState() == Qt.Checked

        have_options = self.keep_newest_radiobutton.isChecked() \
                    or self.keep_oldest_radiobutton.isChecked() \
                    or self.purge_checkbox.checkState() == Qt.Checked
        # Only if the user has checked at least one option will we continue
        if have_options:
            debug_print("- options=%s" % self.options)
            self.accept()
            return
        return error_dialog(self, 'No options selected',
                            'You must select at least one option to continue.',
                            show=True, show_copy_button=False)

    def sort_by(self, name):
        if name == 'PubDate':
            self.shelves = sorted(self.shelves, key=lambda k: k.sort_key(sort_by_pubdate=True))


class DuplicateShelvesInDeviceDatabaseTableWidget(QTableWidget):

    def __init__(self, parent):
        QTableWidget.__init__(self, parent)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
#        self.fmt = tweaks['gui_pubdate_display_format']
#        if self.fmt is None:
#            self.fmt = 'MMM yyyy'

    def populate_table(self, shelves):
        self.clear()
        self.setAlternatingRowColors(True)
        self.setRowCount(len(shelves))
        header_labels = ['Shelf Name', 'Oldest', 'Newest', 'Number']
        self.setColumnCount(len(header_labels))
        self.setHorizontalHeaderLabels(header_labels)
        self.verticalHeader().setDefaultSectionSize(24)
        self.horizontalHeader().setStretchLastSection(True)

        for row, shelf in enumerate(shelves):
            self.populate_table_row(row, shelf)

        self.resizeColumnToContents(0)
        self.setMinimumColumnWidth(0, 150)
        self.setColumnWidth(1, 150)
        self.resizeColumnToContents(2)
        self.setMinimumColumnWidth(2, 150)
        self.setSortingEnabled(True)
#        self.setMinimumSize(550, 0)
        self.selectRow(0)
        delegate = DateDelegate(self, default_to_today=False)
        self.setItemDelegateForColumn(1, delegate)
        self.setItemDelegateForColumn(2, delegate)


    def setMinimumColumnWidth(self, col, minimum):
        if self.columnWidth(col) < minimum:
            self.setColumnWidth(col, minimum)

    def populate_table_row(self, row, shelf):
#        debug_print("shelf:", row, shelf[0], shelf[1], shelf[2], shelf[3])
        self.blockSignals(True)
        shelf_name = shelf[0] if shelf[0] else _("(Unnamed shelf)")
        titleColumn = QTableWidgetItem(shelf_name)
        titleColumn.setFlags(Qt.ItemIsSelectable|Qt.ItemIsEnabled)
        self.setItem(row, 0, titleColumn)
#        self.setItem(row, 1, QTableWidgetItem(shelf[1]))
#        self.setItem(row, 2, QTableWidgetItem(shelf[2]))
        self.setItem(row, 1, DateTableWidgetItem(shelf[1], is_read_only=True,
                                                 default_to_today=False))
        self.setItem(row, 2, DateTableWidgetItem(shelf[2], 
                                                 is_read_only=True, default_to_today=False))
        shelf_count = RatingTableWidgetItem(shelf[3], is_read_only=True)
        shelf_count.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.setItem(row, 3, shelf_count)
        self.blockSignals(False)


class OrderSeriesShelvesDialog(SizePersistedDialog):

    def __init__(self, parent, plugin_action, shelves):
        SizePersistedDialog.__init__(self, parent, 'sony utilities plugin:order series shelves dialog')
        self.plugin_action = plugin_action
        self.shelves       = shelves
        self.block_events  = True
        self.help_anchor   = "OrderSeriesShelves"

        self.options = cfg.get_plugin_prefs(cfg.ORDERSERIESSHELVES_OPTIONS_STORE_NAME)
        self.initialize_controls()
        self.order_shelves_in = self.options[cfg.KEY_SORT_DESCENDING]
        if self.order_shelves_in:
#            self.descending_radiobutton.click()
            self.order_shelves_in_button_group.button(1).setChecked(True)
        else:
#            self.ascending_radiobutton.click()
            self.order_shelves_in_button_group.button(0).setChecked(True)

        if self.options.get(cfg.KEY_SORT_UPDATE_CONFIG, cfg.ORDERSERIESSHELVES_OPTIONS_DEFAULTS[cfg.KEY_SORT_UPDATE_CONFIG]):
            self.update_config_checkbox.setCheckState(Qt.Checked)

        self.order_shelves_type = self.options.get(cfg.KEY_ORDER_SHELVES_TYPE, cfg.ORDERSERIESSHELVES_OPTIONS_DEFAULTS[cfg.KEY_ORDER_SHELVES_TYPE])
        self.order_shelves_type_button_group.button(self.order_shelves_type).setChecked(True)

        self.order_shelves_by = self.options.get(cfg.KEY_ORDER_SHELVES_BY, cfg.ORDERSERIESSHELVES_OPTIONS_DEFAULTS[cfg.KEY_ORDER_SHELVES_BY])
        self.order_shelves_by_button_group.button(self.order_shelves_by).setChecked(True)

        # Display the books in the table
        self.block_events = False
        self.shelves_table.populate_table(self.shelves)

        # Cause our dialog size to be restored from prefs or created on first usage
        self.resize_dialog()

    def initialize_controls(self):
        self.setWindowTitle(_("Order Series Shelves"))
        layout = QVBoxLayout(self)
        self.setLayout(layout)
        title_layout = ImageTitleLayout(self, 'images/manage_series.png', 'Order Series Shelves')
        layout.addLayout(title_layout)

        order_shelves_type_toolTip = [
                                    _("Order the shelves with series names."),
                                    _("Order the shelves with author names."),
                                    _("Order the shelves that do not have series or author names."),
                                    _("Order all shelves.")
                                    ]

        order_shelves_type_group_box = QGroupBox(_("Shelves to order"), self)
        layout.addWidget(order_shelves_type_group_box)
        order_shelves_type_group_box_layout = QHBoxLayout()
        order_shelves_type_group_box.setLayout(order_shelves_type_group_box_layout)
        self.order_shelves_type_button_group = QButtonGroup(self)
        self.order_shelves_type_button_group.buttonClicked[int].connect(self._order_shelves_type_radio_clicked)
        for row, text in enumerate([_('Series'), _('Authors'), _('Other'), _('All')]):
            rdo = QRadioButton(text, self)
            rdo.setToolTip(order_shelves_type_toolTip[row])
            self.order_shelves_type_button_group.addButton(rdo)
            self.order_shelves_type_button_group.setId(rdo, row)
            order_shelves_type_group_box_layout.addWidget(rdo)
        layout.addSpacing(5)

        self.fetch_button = QPushButton(_('Get shelves'), self)
        self.fetch_button.setToolTip(_('Edit the keyboard shortcuts associated with this plugin'))
        self.fetch_button.clicked.connect(self.fetch_button_clicked)
        order_shelves_type_group_box_layout.addWidget(self.fetch_button)

        # Main series table layout
        table_layout = QHBoxLayout()
        layout.addLayout(table_layout)

        self.shelves_table = OrderSeriesShelvesTableWidget(self)
        table_layout.addWidget(self.shelves_table)

        options_group = QGroupBox(_("Options"), self)
        options_tooltip = "The options are to set whether the shelf lists the books in series order or reverse order."
        options_group.setToolTip(options_tooltip)
        layout.addWidget(options_group)
        options_layout = QGridLayout()
        options_group.setLayout(options_layout)

        order_shelves_by_toolTip = [
                                    _("Order by series name and index and title."),
                                    _("Order by the published date.")
                                    ]

        order_shelves_by_group_box = QGroupBox(_("Order by"), self)
        options_layout.addWidget(order_shelves_by_group_box, 0, 0, 1, 1)
        order_shelves_by_group_box_layout = QVBoxLayout()
        order_shelves_by_group_box.setLayout(order_shelves_by_group_box_layout)
        self.order_shelves_by_button_group = QButtonGroup(self)
        self.order_shelves_by_button_group.buttonClicked[int].connect(self._order_shelves_by_radio_clicked)
        for row, text in enumerate([_('Series'), _('Published date')]):
            rdo = QRadioButton(text, self)
            rdo.setToolTip(order_shelves_by_toolTip[row])
            self.order_shelves_by_button_group.addButton(rdo)
            self.order_shelves_by_button_group.setId(rdo, row)
            order_shelves_by_group_box_layout.addWidget(rdo)

        order_shelves_in_toolTip = [
                                    _("Selecting ascending will sort the shelf in series order."),
                                    _("Selecting descending will sort the shelf in reverse series order.")
                                    ]

        order_shelves_in_group_box = QGroupBox(_("Order in"), self)
        options_layout.addWidget(order_shelves_in_group_box, 0, 1, 1, 1)
        order_shelves_in_group_box_layout = QVBoxLayout()
        order_shelves_in_group_box.setLayout(order_shelves_in_group_box_layout)
        self.order_shelves_in_button_group = QButtonGroup(self)
        self.order_shelves_in_button_group.buttonClicked[int].connect(self._order_shelves_in_radio_clicked)
        for row, text in enumerate([_('Ascending'), _('Descending')]):
            rdo = QRadioButton(text, self)
            rdo.setToolTip(order_shelves_in_toolTip[row])
            self.order_shelves_in_button_group.addButton(rdo)
            self.order_shelves_in_button_group.setId(rdo, row)
            order_shelves_in_group_box_layout.addWidget(rdo)


#        options_layout.addWidget(QLabel(_("Order in")), 0, 0, 1, 1)
#        self.ascending_radiobutton = QRadioButton(_("Ascending"), self)
#        self.ascending_radiobutton.setToolTip(_("Selecting ascending will sort the shelf in series order."))
#        options_layout.addWidget(self.ascending_radiobutton, 0, 1, 1, 1)
#
#        self.descending_radiobutton = QRadioButton(_("Descending"), self)
#        options_layout.addWidget(self.descending_radiobutton, 0, 2, 1, 1)
#        self.descending_radiobutton.setToolTip(_("Selecting descending will sort the shelf in reverse series order."))

        self.update_config_checkbox = QCheckBox(_("Update config file"), self)
        options_layout.addWidget(self.update_config_checkbox, 0, 2, 1, 1)
        self.update_config_checkbox.setToolTip(_("If this is selected, the configuration file is updated to set the selected sort for the shelves to 'Date Added'."))

        # Dialog buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self._ok_clicked)
        button_box.rejected.connect(self.reject)
        self.remove_seleced_button = button_box.addButton(_("Remove"), QDialogButtonBox.ResetRole)
        self.remove_seleced_button.setToolTip(_("Remove the selected shelves from the list. This will mean the ordering for these shelves will not be changed."))
        self.remove_seleced_button.clicked.connect(self._remove_selected_clicked)
        layout.addWidget(button_box)

    def _ok_clicked(self):
        self.options = {}

        self.options[cfg.KEY_SORT_DESCENDING]    = self.order_shelves_in #self.descending_radiobutton.isChecked()
        self.options[cfg.KEY_SORT_UPDATE_CONFIG] = self.update_config_checkbox.isChecked()
        self.options[cfg.KEY_ORDER_SHELVES_TYPE] = self.order_shelves_type
        self.options[cfg.KEY_ORDER_SHELVES_BY]   = self.order_shelves_by
        cfg.plugin_prefs[cfg.ORDERSERIESSHELVES_OPTIONS_STORE_NAME]  = self.options
        self.accept()
        return

    def _order_shelves_type_radio_clicked(self, idx):
        self.order_shelves_type = ORDER_SHELVES_TYPE[idx]

    def _order_shelves_by_radio_clicked(self, idx):
        self.order_shelves_by = ORDER_SHELVES_BY[idx]

    def _order_shelves_in_radio_clicked(self, idx):
        self.order_shelves_in = idx == 1

    def _remove_selected_clicked(self):
        self.shelves_table.remove_selected_rows()

    def fetch_button_clicked(self):
        self.shelves = self.plugin_action._get_series_shelf_count(self.order_shelves_type)
        self.shelves_table.populate_table(self.shelves)
        return
        
    def get_shelves(self):
        return self.shelves_table.get_shelves()


class OrderSeriesShelvesTableWidget(QTableWidget):

    def __init__(self, parent):
        QTableWidget.__init__(self, parent)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)

    def populate_table(self, shelves):
        self.clear()
        self.setAlternatingRowColors(True)
        self.setRowCount(len(shelves))
        header_labels = ['Shelf/Series Name', 'Books on Shelf']
        self.setColumnCount(len(header_labels))
        self.setHorizontalHeaderLabels(header_labels)
        self.verticalHeader().setDefaultSectionSize(24)
        self.horizontalHeader().setStretchLastSection(True)

        self.shelves = {}
        for row, shelf in enumerate(shelves):
            self.populate_table_row(row, shelf)
            self.shelves[row] = shelf

        self.resizeColumnToContents(0)
        self.setMinimumColumnWidth(0, 150)
        self.setColumnWidth(1, 150)
        self.setSortingEnabled(True)
#        self.setMinimumSize(550, 0)
        self.selectRow(0)


    def setMinimumColumnWidth(self, col, minimum):
        if self.columnWidth(col) < minimum:
            self.setColumnWidth(col, minimum)

    def populate_table_row(self, row, shelf):
#        debug_print("shelf:", row, shelf)
        self.blockSignals(True)
        nameColumn = QTableWidgetItem(shelf['name'])
        nameColumn.setFlags(Qt.ItemIsSelectable|Qt.ItemIsEnabled)
#        nameColumn.setData(Qt.UserRole, QVariant(row))
        nameColumn.setData(Qt.UserRole, row)
        self.setItem(row, 0, nameColumn)
        shelf_count = RatingTableWidgetItem(shelf['count'], is_read_only=True)
        shelf_count.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.setItem(row, 1, shelf_count)
        self.blockSignals(False)

    def get_shelves(self):
#        debug_print("self.shelves:", self.shelves)
        shelves = []
        for row in range(self.rowCount()):
            rnum = convert_qvariant(self.item(row, 0).data(Qt.UserRole))
            shelf = self.shelves[rnum]
            shelves.append(shelf)
        return shelves

    def remove_selected_rows(self):
        self.setFocus()
        rows = self.selectionModel().selectedRows()
        if len(rows) == 0:
            return
        first_sel_row = self.currentRow()
        for selrow in reversed(rows):
            self.removeRow(selrow.row())
        if first_sel_row < self.rowCount():
            self.select_and_scroll_to_row(first_sel_row)
        elif self.rowCount() > 0:
            self.select_and_scroll_to_row(first_sel_row - 1)

    def select_and_scroll_to_row(self, row):
        self.selectRow(row)
        self.scrollToItem(self.currentItem())


class FontChoiceComboBox(QComboBox):

    def __init__(self, parent):
        QComboBox.__init__(self, parent)
        for name, font in sorted(SONY_FONTS.items()):
            self.addItem(name, font)

    def select_text(self, selected_text):
        idx = self.findData(selected_text)
        if idx != -1:
            self.setCurrentIndex(idx)
        else:
            self.setCurrentIndex(0)

class JustificationChoiceComboBox(QComboBox):

    def __init__(self, parent):
        QComboBox.__init__(self, parent)
        self.addItems(['Off', 'Left', 'Justify'])

    def select_text(self, selected_text):
        idx = self.findText(selected_text)
        if idx != -1:
            self.setCurrentIndex(idx)
        else:
            self.setCurrentIndex(0)

class ReadingStatusGroupBox(QGroupBox):

    def __init__(self, parent):
        QGroupBox.__init__(self, parent)

        self.setTitle(_("Reading status"))
        options_layout = QGridLayout()
        self.setLayout(options_layout)

        self.reading_status_checkbox = QCheckBox(_("Change reading status"), self)
        options_layout.addWidget(self.reading_status_checkbox, 0, 0, 1, 2)
        self.reading_status_checkbox.clicked.connect(self.reading_status_checkbox_clicked)

        self.unread_radiobutton = QRadioButton(_("Unread"), self)
        options_layout.addWidget(self.unread_radiobutton, 1, 0, 1, 1)
        self.unread_radiobutton.setEnabled(False)

        self.reading_radiobutton = QRadioButton(_("Reading"), self)
        options_layout.addWidget(self.reading_radiobutton, 1, 1, 1, 1)
        self.reading_radiobutton.setEnabled(False)

        self.finished_radiobutton = QRadioButton(_("Finished"), self)
        options_layout.addWidget(self.finished_radiobutton, 1, 2, 1, 1)
        self.finished_radiobutton.setEnabled(False)

        self.reset_position_checkbox = QCheckBox(_("Reset reading position"), self)
        options_layout.addWidget(self.reset_position_checkbox, 2, 0, 1, 3)
        self.reset_position_checkbox.setToolTip(_("If this option is checked, the current position and last reading date will be reset."))

    def reading_status_checkbox_clicked(self, checked):
        self.unread_radiobutton.setEnabled(checked)
        self.reading_radiobutton.setEnabled(checked)
        self.finished_radiobutton.setEnabled(checked)
        self.reset_position_checkbox.setEnabled(checked)

    def readingStatusIsChecked(self):
        return self.reading_status_checkbox.checkState() == Qt.Checked

    def readingStatus(self):
        readingStatus = -1
        if self.unread_radiobutton.isChecked():
            readingStatus = 0
        elif self.reading_radiobutton.isChecked():
            readingStatus = 1
        elif self.finished_radiobutton.isChecked():
            readingStatus = 2
        
        return readingStatus


class AboutDialog(QDialog):

    def __init__(self, parent, icon, text):
        QDialog.__init__(self, parent)
        self.resize(400, 250)
        self.l = QGridLayout()
        self.setLayout(self.l)
        self.logo = QLabel()
        self.logo.setMaximumWidth(110)
        self.logo.setPixmap(QPixmap(icon.pixmap(100,100)))
        self.label = QLabel(text)
        self.label.setOpenExternalLinks(True)
        self.label.setWordWrap(True)
        self.setWindowTitle(_('About ' + DIALOG_NAME))
        self.setWindowIcon(icon)
        self.l.addWidget(self.logo, 0, 0)
        self.l.addWidget(self.label, 0, 1)
        self.bb = QDialogButtonBox(self)
        b = self.bb.addButton(_(_("OK")), self.bb.AcceptRole)
        b.setDefault(True)
        self.l.addWidget(self.bb, 2, 0, 1, -1)
        self.bb.accepted.connect(self.accept)

