#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=4:sw=4:sta:et:sts=4:ai
from __future__ import (unicode_literals, division, absolute_import,
                        print_function)

__license__   = 'GPL v3'
__copyright__ = '2014, Derek Broughton <auspex@pointerstop.ca>'
__docformat__ = 'restructuredtext en'

import copy

try:
    from PyQt5.Qt import (Qt, QWidget, QGridLayout, QLabel, QPushButton, QVBoxLayout, QSpinBox,
                          QGroupBox, QCheckBox, QLineEdit)
    from PyQt5 import QtGui
except ImportError:
    from PyQt4.Qt import (Qt, QWidget, QGridLayout, QLabel, QPushButton, QVBoxLayout, QSpinBox,
                          QGroupBox, QCheckBox, QLineEdit)
    from PyQt4 import QtGui

from calibre.gui2 import open_url, choose_dir, error_dialog
from calibre.utils.config import JSONConfig

# from calibre.customize.zipplugin import load_translations
from calibre_plugins.sonyutilities.common_utils import (get_library_uuid, CustomColumnComboBox,
                                     debug_print, KeyboardConfigDialog, KeyComboBox, ImageTitleLayout)


PREFS_NAMESPACE = 'sonyutilitiesPlugin'
PREFS_KEY_SETTINGS = 'settings'

KEY_SCHEMA_VERSION = 'SchemaVersion'
DEFAULT_SCHEMA_VERSION = 0.1

STORE_LIBRARIES = 'libraries'
KEY_CURRENT_LOCATION_CUSTOM_COLUMN = 'currentReadingLocationColumn'
KEY_PERCENT_READ_CUSTOM_COLUMN     = 'precentReadColumn'
KEY_RATING_CUSTOM_COLUMN           = 'ratingColumn'
KEY_LAST_READ_CUSTOM_COLUMN        = 'lastReadColumn'
KEY_STORE_ON_CONNECT               = 'storeOnConnect'
KEY_PROMPT_TO_STORE                = 'promptToStore'
KEY_STORE_IF_MORE_RECENT           = 'storeIfMoreRecent'
KEY_DO_NOT_STORE_IF_REOPENED       = 'doNotStoreIfReopened'
KEY_DO_UPDATE_CHECK                = 'doFirmwareUpdateCheck'
KEY_LAST_FIRMWARE_CHECK_TIME       = 'firmwareUpdateCheckLastTime'
KEY_DO_EARLY_FIRMWARE_CHECK        = 'doEarlyFirmwareUpdate'
DEFAULT_LIBRARY_VALUES = {
                          KEY_CURRENT_LOCATION_CUSTOM_COLUMN: '',
                          KEY_PERCENT_READ_CUSTOM_COLUMN:     '',
                          KEY_RATING_CUSTOM_COLUMN:           None,
                          KEY_LAST_READ_CUSTOM_COLUMN:        None,
                         }

BOOKMARK_OPTIONS_STORE_NAME             = 'BookmarkOptions'
METADATA_OPTIONS_STORE_NAME             = 'MetadataOptions'
READING_OPTIONS_STORE_NAME              = 'ReadingOptions'
COMMON_OPTIONS_STORE_NAME               = 'commonOptionsStore'
DISMISSTILES_OPTIONS_STORE_NAME         = 'dismissTilesOptionsStore'
FIXDUPLICATESHELVES_OPTIONS_STORE_NAME  = 'fixDuplicatesOptionsStore'
ORDERSERIESSHELVES_OPTIONS_STORE_NAME   = 'orderSeriesShelvesOptionsStore'
UPDATE_OPTIONS_STORE_NAME               = 'updateOptionsStore'
BACKUP_OPTIONS_STORE_NAME               = 'backupOptionsStore'

KEY_STORE_BOOKMARK          = 'storeBookmarks'
KEY_DATE_TO_NOW             = 'setDateToNow'
KEY_CLEAR_IF_UNREAD         = 'clearIfUnread'
KEY_BACKGROUND_JOB          = 'backgroundJob'
KEY_SET_TITLE               = 'title'
KEY_USE_TITLE_SORT          = 'titleSort'
KEY_SET_AUTHOR              = 'author'
KEY_USE_AUTHOR_SORT         = 'authourSort'
KEY_SET_DESCRIPTION         = 'description'
KEY_SET_PUBLISHER           = 'publisher'
KEY_SET_SERIES              = 'series'
KEY_SET_TAGS_IN_SUBTITLE    = 'tagsInSubtitle'
KEY_USE_PLUGBOARD           = 'usePlugboard'
KEY_SET_READING_STATUS      = 'setRreadingStatus'
KEY_READING_STATUS          = 'readingStatus'
KEY_SET_PUBLISHED_DATE      = 'published_date'
KEY_SET_ISBN                = 'isbn'
KEY_SET_NOT_INTERESTED      = 'mark_not_interested'
KEY_SET_LANGUAGE            = 'language'
KEY_RESET_POSITION          = 'resetPosition'
KEY_TILE_OPTIONS            = 'tileOptions'
KEY_CHANGE_DISMISS_TRIGGER  = 'changeDismissTrigger'
KEY_CREATE_DISMISS_TRIGGER  = 'createDismissTrigger'
KEY_DELETE_DISMISS_TRIGGER  = 'deleteDismissTrigger'
KEY_CREATE_ANALYTICSEVENTS_TRIGGER  = 'createAnalyticsEventsTrigger'
KEY_DELETE_ANALYTICSEVENTS_TRIGGER  = 'deleteAnalyticsEventsTrigger'
KEY_TILE_RECENT_NEW             = 'tileRecentBooksNew'
KEY_TILE_RECENT_FINISHED        = 'tileRecentBooksFinished'
KEY_TILE_RECENT_IN_THE_CLOUD    = 'tileRecentBooksInTheCLoud'

KEY_READING_FONT_FAMILY     = 'readingFontFamily'
KEY_READING_ALIGNMENT       = 'readingAlignment'
KEY_READING_FONT_SIZE       = 'readingFontSize'
KEY_READING_LINE_HEIGHT     = 'readingLineHeight'
KEY_READING_LEFT_MARGIN     = 'readingLeftMargin'
KEY_READING_RIGHT_MARGIN    = 'readingRightMargin'
KEY_READING_LOCK_MARGINS    = 'lockMargins'
KEY_UPDATE_CONFIG_FILE      = 'updateConfigFile'

KEY_BUTTON_ACTION_DEVICE    = 'buttonActionDevice'
KEY_BUTTON_ACTION_LIBRARY   = 'buttonActionLibrary'

KEY_KEEP_NEWEST_SHELF       = 'keepNewestShelf'
KEY_PURGE_SHELVES           = 'purgeShelves'

KEY_SORT_DESCENDING         = 'sortDescending'
KEY_SORT_UPDATE_CONFIG      = 'updateConfig'

KEY_ORDER_SHELVES_SERIES    = 0
KEY_ORDER_SHELVES_AUTHORS   = 1
KEY_ORDER_SHELVES_OTHER     = 2
KEY_ORDER_SHELVES_ALL       = 3
KEY_ORDER_SHELVES_TYPE      = 'orderShelvesType'

KEY_ORDER_SHELVES_BY_SERIES = 0
KEY_ORDER_SHELVES_PUBLISHED = 1
KEY_ORDER_SHELVES_BY        = 'orderShelvesBy'

KEY_DO_DAILY_BACKUP         = 'doDailyBackp'
KEY_BACKUP_COPIES_TO_KEEP   = 'backupCopiesToKeepSpin'
KEY_BACKUP_DEST_DIRECTORY   = 'backupDestDirectory'

BOOKMARK_OPTIONS_DEFAULTS = {
                KEY_STORE_BOOKMARK:             True,
                KEY_READING_STATUS:             True,
                KEY_DATE_TO_NOW:                True, 
                KEY_CLEAR_IF_UNREAD:            False, 
                KEY_BACKGROUND_JOB:             False, 
                KEY_STORE_IF_MORE_RECENT:       False,
                KEY_DO_NOT_STORE_IF_REOPENED:   False
                }
METADATA_OPTIONS_DEFAULTS = {
                KEY_SET_TITLE:          False,
                KEY_SET_AUTHOR:         False,
                KEY_SET_DESCRIPTION:    False,
                KEY_SET_PUBLISHER:      False,
                KEY_SET_SERIES:         False,
                KEY_SET_READING_STATUS: False,
                KEY_READING_STATUS:     -1,
                KEY_SET_PUBLISHED_DATE: False,
                KEY_SET_ISBN:           False,
                KEY_SET_NOT_INTERESTED: False,
                KEY_SET_LANGUAGE:       False,
                KEY_RESET_POSITION:     False,
                KEY_USE_PLUGBOARD:      False,
                KEY_USE_TITLE_SORT:     False,
                KEY_USE_AUTHOR_SORT:    False,
                KEY_SET_TAGS_IN_SUBTITLE: False
                }
READING_OPTIONS_DEFAULTS = {
                KEY_READING_FONT_FAMILY:  'Georgia',
                KEY_READING_ALIGNMENT:    'Off',
                KEY_READING_FONT_SIZE:    22,
                KEY_READING_LINE_HEIGHT:  1.3,
                KEY_READING_LEFT_MARGIN:  3,
                KEY_READING_RIGHT_MARGIN: 3,
                KEY_READING_LOCK_MARGINS: False,
                KEY_UPDATE_CONFIG_FILE:   False,
                }
COMMON_OPTIONS_DEFAULTS = {
                KEY_STORE_ON_CONNECT:           False,
                KEY_PROMPT_TO_STORE:            True,
                KEY_STORE_IF_MORE_RECENT:       False,
                KEY_DO_NOT_STORE_IF_REOPENED:   False,
                KEY_BUTTON_ACTION_DEVICE:       '',
                KEY_BUTTON_ACTION_LIBRARY:      '',
                }
DISMISSTILES_OPTIONS_DEFAULTS = {
                KEY_TILE_OPTIONS:               {},
                KEY_TILE_RECENT_NEW:            False,
                KEY_TILE_RECENT_FINISHED:       False,
                KEY_TILE_RECENT_IN_THE_CLOUD:   False
                }

FIXDUPLICATESHELVES_OPTIONS_DEFAULTS = {
                KEY_KEEP_NEWEST_SHELF:  True,
                KEY_PURGE_SHELVES:      False
                }

ORDERSERIESSHELVES_OPTIONS_DEFAULTS = {
                KEY_SORT_DESCENDING:    False,
                KEY_SORT_UPDATE_CONFIG: True,
                KEY_ORDER_SHELVES_TYPE: KEY_ORDER_SHELVES_SERIES,
                KEY_ORDER_SHELVES_BY:   KEY_ORDER_SHELVES_BY_SERIES
                }

UPDATE_OPTIONS_DEFAULTS = {
                KEY_DO_UPDATE_CHECK: False,
                KEY_LAST_FIRMWARE_CHECK_TIME: 0,
                KEY_DO_EARLY_FIRMWARE_CHECK: False
                }

BACKUP_OPTIONS_DEFAULTS = {
                KEY_DO_DAILY_BACKUP:        False,
                KEY_BACKUP_COPIES_TO_KEEP:  5,
                KEY_BACKUP_DEST_DIRECTORY:  ''
                }

# This is where all preferences for this plugin will be stored
plugin_prefs = JSONConfig('plugins/Sony Utilities')

# Set defaults
plugin_prefs.defaults[BOOKMARK_OPTIONS_STORE_NAME]      = BOOKMARK_OPTIONS_DEFAULTS
plugin_prefs.defaults[METADATA_OPTIONS_STORE_NAME]      = METADATA_OPTIONS_DEFAULTS
plugin_prefs.defaults[READING_OPTIONS_STORE_NAME]       = READING_OPTIONS_DEFAULTS
plugin_prefs.defaults[COMMON_OPTIONS_STORE_NAME]        = COMMON_OPTIONS_DEFAULTS
plugin_prefs.defaults[DISMISSTILES_OPTIONS_STORE_NAME]  = DISMISSTILES_OPTIONS_DEFAULTS
plugin_prefs.defaults[FIXDUPLICATESHELVES_OPTIONS_STORE_NAME]  = FIXDUPLICATESHELVES_OPTIONS_DEFAULTS
plugin_prefs.defaults[ORDERSERIESSHELVES_OPTIONS_STORE_NAME]   = ORDERSERIESSHELVES_OPTIONS_DEFAULTS
plugin_prefs.defaults[STORE_LIBRARIES]                  = {}
plugin_prefs.defaults[UPDATE_OPTIONS_STORE_NAME]        = UPDATE_OPTIONS_DEFAULTS
plugin_prefs.defaults[BACKUP_OPTIONS_STORE_NAME]        = BACKUP_OPTIONS_DEFAULTS


try:
    debug_print("SonyUtilites::action.py - loading translations")
    load_translations()
except NameError:
    debug_print("SonyUtilites::action.py - exception when loading translations")
    pass # load_translations() added in calibre 1.9


def get_plugin_pref(store_name, option):
    c = plugin_prefs[store_name]
    default_value = plugin_prefs.defaults[store_name][option]
    return c.get(option, default_value)

def get_plugin_prefs(store_name):
    c = plugin_prefs[store_name]
    return c

def migrate_library_config_if_required(db, library_config):
    schema_version = library_config.get(KEY_SCHEMA_VERSION, 0)
    if schema_version == DEFAULT_SCHEMA_VERSION:
        return
    # We have changes to be made - mark schema as updated
    library_config[KEY_SCHEMA_VERSION] = DEFAULT_SCHEMA_VERSION

    # Any migration code in future will exist in here.
    if schema_version < 0.1:
        pass

    set_library_config(db, library_config)


def get_library_config(db):
    library_id = get_library_uuid(db)
    library_config = None
    # Check whether this is a configuration needing to be migrated from json into database
    if 'libraries' in plugin_prefs:
        libraries = plugin_prefs['libraries']
        if library_id in libraries:
            # We will migrate this below
            library_config = libraries[library_id]
            # Cleanup from json file so we don't ever do this again
            del libraries[library_id]
            if len(libraries) == 0:
                # We have migrated the last library for this user
                del plugin_prefs['libraries']
            else:
                plugin_prefs['libraries'] = libraries

    if library_config is None:
        library_config = db.prefs.get_namespaced(PREFS_NAMESPACE, PREFS_KEY_SETTINGS,
                                                 copy.deepcopy(DEFAULT_LIBRARY_VALUES))
#    migrate_library_config_if_required(db, library_config)
    return library_config


def set_library_config(db, library_config):
    db.prefs.set_namespaced(PREFS_NAMESPACE, PREFS_KEY_SETTINGS, library_config)


class ConfigWidget(QWidget):

    def __init__(self, plugin_action):
        QWidget.__init__(self)
        self.plugin_action = plugin_action
        layout = QVBoxLayout(self)
        self.setLayout(layout)
        self.help_anchor = "configuration"
        
        title_layout = ImageTitleLayout(self, 'images/icon.png', 'Sony Utilities Options')
        layout.addLayout(title_layout)

#        c = plugin_prefs[STORE_NAME]
        library_config = get_library_config(self.plugin_action.gui.current_db)

        custom_column_group = QGroupBox(_('Custom Columns'), self)
        layout.addWidget(custom_column_group )
        options_layout = QGridLayout()
        custom_column_group.setLayout(options_layout)

        avail_text_columns   = self.get_text_custom_columns()
        avail_number_columns = self.get_number_custom_columns()
        avail_rating_columns = self.get_rating_custom_columns()
        avail_date_columns   = self.get_date_custom_columns()
#        debug_print("avail_rating_columns=", avail_rating_columns)
#        debug_print("default columns=", self.plugin_action.gui.library_view.model().orig_headers)
        current_Location_column  = library_config.get(KEY_CURRENT_LOCATION_CUSTOM_COLUMN, DEFAULT_LIBRARY_VALUES[KEY_CURRENT_LOCATION_CUSTOM_COLUMN])
        precent_read_column      = library_config.get(KEY_PERCENT_READ_CUSTOM_COLUMN, DEFAULT_LIBRARY_VALUES[KEY_PERCENT_READ_CUSTOM_COLUMN])
        rating_column            = library_config.get(KEY_RATING_CUSTOM_COLUMN, DEFAULT_LIBRARY_VALUES[KEY_RATING_CUSTOM_COLUMN])
        last_read_column         = library_config.get(KEY_LAST_READ_CUSTOM_COLUMN, DEFAULT_LIBRARY_VALUES[KEY_LAST_READ_CUSTOM_COLUMN])

        store_on_connect         = get_plugin_pref(COMMON_OPTIONS_STORE_NAME, KEY_STORE_ON_CONNECT)
        prompt_to_store          = get_plugin_pref(COMMON_OPTIONS_STORE_NAME, KEY_PROMPT_TO_STORE)
        store_if_more_recent     = get_plugin_pref(COMMON_OPTIONS_STORE_NAME, KEY_STORE_IF_MORE_RECENT)
        do_not_store_if_reopened = get_plugin_pref(COMMON_OPTIONS_STORE_NAME, KEY_DO_NOT_STORE_IF_REOPENED)

#         do_check_for_firmware_updates = get_plugin_pref(UPDATE_OPTIONS_STORE_NAME, KEY_DO_UPDATE_CHECK)
#         do_early_firmware_updates     = get_plugin_pref(UPDATE_OPTIONS_STORE_NAME, KEY_DO_EARLY_FIRMWARE_CHECK)
#         self.update_check_last_time   = get_plugin_pref(UPDATE_OPTIONS_STORE_NAME, KEY_LAST_FIRMWARE_CHECK_TIME)

        do_daily_backup          = get_plugin_pref(BACKUP_OPTIONS_STORE_NAME, KEY_DO_DAILY_BACKUP)
        dest_directory           = get_plugin_pref(BACKUP_OPTIONS_STORE_NAME, KEY_BACKUP_DEST_DIRECTORY)
        copies_to_keep           = get_plugin_pref(BACKUP_OPTIONS_STORE_NAME, KEY_BACKUP_COPIES_TO_KEEP)
#        debug_print("current_Location_column=%s, precent_read_column=%s, rating_column=%s" % (current_Location_column, precent_read_column, rating_column))

        current_Location_label = QLabel(_('Current Reading Location Column:'), self)
        current_Location_label.setToolTip(_("Select a custom column to store the current reading location. The column type must be 'text'. Leave this blank if you do not want to store or restore the current reading location."))
        self.current_Location_combo = CustomColumnComboBox(self, avail_text_columns, current_Location_column)
        current_Location_label.setBuddy(self.current_Location_combo)
        options_layout.addWidget(current_Location_label, 0, 0, 1, 1)
        options_layout.addWidget(self.current_Location_combo, 0, 1, 1, 1)
        
        percent_read_label = QLabel(_('Percent Read Column:'), self)
        percent_read_label.setToolTip(_("Column used to store the current percent read. The column type must be a 'integer'. Leave this blank if you do not want to store or restore the percentage read."))
        self.percent_read_combo = CustomColumnComboBox(self, avail_number_columns, precent_read_column)
        percent_read_label.setBuddy(self.percent_read_combo)
        options_layout.addWidget(percent_read_label, 2, 0, 1, 1)
        options_layout.addWidget(self.percent_read_combo, 2, 1, 1, 1)

        rating_label = QLabel(_('Rating Column:'), self)
        rating_label.setToolTip(_("Column used to store the rating. The column type must be a 'integer'. Leave this blank if you do not want to store or restore the rating."))
        self.rating_combo = CustomColumnComboBox(self, avail_rating_columns, rating_column)
        rating_label.setBuddy(self.rating_combo)
        options_layout.addWidget(rating_label, 3, 0, 1, 1)
        options_layout.addWidget(self.rating_combo, 3, 1, 1, 1)

        last_read_label = QLabel(_('Last Read Column:'), self)
        last_read_label.setToolTip(_("Column used to store when the book was last read. The column type must be a 'Date'. Leave this blank if you do not want to store the last read timestamp."))
        self.last_read_combo = CustomColumnComboBox(self, avail_date_columns, last_read_column)
        last_read_label.setBuddy(self.last_read_combo)
        options_layout.addWidget(last_read_label, 4, 0, 1, 1)
        options_layout.addWidget(self.last_read_combo, 4, 1, 1, 1)

        auto_store_group = QGroupBox(_('Store on connect'), self)
        layout.addWidget(auto_store_group )
        options_layout = QGridLayout()
        auto_store_group.setLayout(options_layout)

        self.store_on_connect_checkbox = QCheckBox(_("Store current bookmarks on connect"), self)
        self.store_on_connect_checkbox.setToolTip(_("When this is checked, the library will be updated with the current bookmark for all books on the device."))
        self.store_on_connect_checkbox.setCheckState(Qt.Checked if store_on_connect else Qt.Unchecked)
        self.store_on_connect_checkbox.clicked.connect(self.store_on_connect_checkbox_clicked)
        options_layout.addWidget(self.store_on_connect_checkbox, 0, 0, 1, 3)

        self.prompt_to_store_checkbox = QCheckBox(_("Prompt to store any changes"), self)
        self.prompt_to_store_checkbox.setToolTip(_("Enable this to be prompted to save the changed bookmarks after an automatic store is done."))
        self.prompt_to_store_checkbox.setCheckState(Qt.Checked if prompt_to_store else Qt.Unchecked)
        self.prompt_to_store_checkbox.setEnabled(store_on_connect)
        options_layout.addWidget(self.prompt_to_store_checkbox, 1, 0, 1, 1)

        self.store_if_more_recent_checkbox = QCheckBox(_("Only if more recent"), self)
        self.store_if_more_recent_checkbox.setToolTip(_("Only store the reading position if the last read timestamp on the device is more recent than in the library."))
        self.store_if_more_recent_checkbox.setCheckState(Qt.Checked if store_if_more_recent else Qt.Unchecked)
        self.store_if_more_recent_checkbox.setEnabled(store_on_connect)
        options_layout.addWidget(self.store_if_more_recent_checkbox, 1, 1, 1, 1)

        self.do_not_store_if_reopened_checkbox = QCheckBox(_("Not if finished in library"), self)
        self.do_not_store_if_reopened_checkbox.setToolTip(_("Do not store the reading position if the library has the book as finished. This is if the percent read is 100%."))
        self.do_not_store_if_reopened_checkbox.setCheckState(Qt.Checked if do_not_store_if_reopened else Qt.Unchecked)
        self.do_not_store_if_reopened_checkbox.setEnabled(store_on_connect)
        options_layout.addWidget(self.do_not_store_if_reopened_checkbox, 1, 2, 1, 1)

#         update_options_group = QGroupBox(_('Firmware Update Options'), self)
#         layout.addWidget(update_options_group)
#         options_layout = QGridLayout()
#         update_options_group.setLayout(options_layout)
# 
#         self.do_update_check = QCheckBox(_('Check for Sony firmware updates daily?'), self)
#         self.do_update_check.setToolTip(_('If this is selected the plugin will check for Sony firmware updates when your Sony device is plugged in, once per 24-hour period.'))
#         self.do_update_check.setCheckState(Qt.Checked if do_check_for_firmware_updates else Qt.Unchecked)
#         options_layout.addWidget(self.do_update_check, 0, 0, 1, 1)
# 
#         self.do_early_firmware_check = QCheckBox(_('Use early firmware adopter affiliate?'), self)
#         self.do_early_firmware_check.setToolTip(_('WARNING: THIS OPTION RISKS DOWNLOADING THE WRONG FIRMWARE FOR YOUR DEVICE! YOUR DEVICE MAY NOT FUNCTION PROPERLY IF THIS HAPPENS! Choose this option to attempt to download Sony firmware updates before they are officially available for your device.'))
#         self.do_early_firmware_check.setCheckState(Qt.Checked if do_early_firmware_updates else Qt.Unchecked)
#         options_layout.addWidget(self.do_early_firmware_check, 0, 1, 1, 1)

        backup_options_group = QGroupBox(_('Device Database Backup'), self)
        layout.addWidget(backup_options_group)
        options_layout = QGridLayout()
        backup_options_group.setLayout(options_layout)

        self.do_daily_backp_checkbox = QCheckBox(_('Backup the device database daily'), self)
        self.do_daily_backp_checkbox.setToolTip(_('If this is selected the plugin will backup the device database the first time it is connected each day.'))
        self.do_daily_backp_checkbox.setCheckState(Qt.Checked if do_daily_backup else Qt.Unchecked)
        self.do_daily_backp_checkbox.clicked.connect(self.do_daily_backp_checkbox_clicked)
        options_layout.addWidget(self.do_daily_backp_checkbox, 0, 0, 1, 3)

        self.dest_directory_label = QLabel(_("Destination:"), self)
        self.dest_directory_label.setToolTip(_("Select the destination the annotations files are to be backed up in."))
        self.dest_directory_edit = QLineEdit(self)
        self.dest_directory_edit.setMinimumSize(150, 0)
        self.dest_directory_edit.setText(dest_directory)
        self.dest_directory_label.setBuddy(self.dest_directory_edit)
        self.dest_pick_button = QPushButton(_("..."), self)
        self.dest_pick_button.setMaximumSize(24, 20)
        self.dest_pick_button.clicked.connect(self._get_dest_directory_name)
        options_layout.addWidget(self.dest_directory_label, 1, 0, 1, 1)
        options_layout.addWidget(self.dest_directory_edit, 1, 1, 1, 1)
        options_layout.addWidget(self.dest_pick_button, 1, 2, 1, 1)

        self.copies_to_keep_checkbox = QCheckBox(_('Copies to keep'), self)
        self.copies_to_keep_checkbox.setToolTip(_("Select this to limit the number of backup kept. If not set, the backup files must be manually deleted."))
        self.copies_to_keep_spin = QSpinBox(self)
        self.copies_to_keep_spin.setMinimum(2)
        self.copies_to_keep_spin.setToolTip(_("The number of backup copies of the database to keep. The minimum is 2."))
        options_layout.addWidget(self.copies_to_keep_checkbox, 1, 3, 1, 1)
        options_layout.addWidget(self.copies_to_keep_spin, 1, 4, 1, 1)
        self.copies_to_keep_checkbox.clicked.connect(self.copies_to_keep_checkbox_clicked)
        if copies_to_keep == -1:
            self.copies_to_keep_checkbox.setCheckState(not Qt.Checked)
        else:
            self.copies_to_keep_checkbox.setCheckState(Qt.Checked)
            self.copies_to_keep_spin.setProperty('value', copies_to_keep)

        self.do_daily_backp_checkbox_clicked(do_daily_backup)

        other_options_group = QGroupBox(_('Other Options'), self)
        layout.addWidget(other_options_group )
        options_layout = QGridLayout()
        other_options_group.setLayout(options_layout)

        library_default_label = QLabel(_('&Library Button default:'), self)
        library_default_label.setToolTip(_('If plugin is placed as a toolbar button, choose a default action when clicked on'))
        self.library_default_combo = KeyComboBox(self, self.plugin_action.library_actions_map, unicode(get_plugin_pref(COMMON_OPTIONS_STORE_NAME, KEY_BUTTON_ACTION_LIBRARY)))
        library_default_label.setBuddy(self.library_default_combo)
        options_layout.addWidget(library_default_label, 0, 0, 1, 1)
        options_layout.addWidget(self.library_default_combo, 0, 1, 1, 2)

        device_default_label = QLabel(_('&Device Button default:'), self)
        device_default_label.setToolTip(_('If plugin is placed as a toolbar button, choose a default action when clicked on'))
        self.device_default_combo = KeyComboBox(self, self.plugin_action.device_actions_map, unicode(get_plugin_pref(COMMON_OPTIONS_STORE_NAME, KEY_BUTTON_ACTION_DEVICE)))
        device_default_label.setBuddy(self.device_default_combo)
        options_layout.addWidget(device_default_label, 1, 0, 1, 1)
        options_layout.addWidget(self.device_default_combo, 1, 1, 1, 2)

        keyboard_shortcuts_button = QPushButton(_('Keyboard shortcuts...'), self)
        keyboard_shortcuts_button.setToolTip(_('Edit the keyboard shortcuts associated with this plugin'))
        keyboard_shortcuts_button.clicked.connect(self.edit_shortcuts)
        layout.addWidget(keyboard_shortcuts_button)
        layout.addStretch(1)

    def store_on_connect_checkbox_clicked(self, checked):
        self.prompt_to_store_checkbox.setEnabled(checked)
        self.store_if_more_recent_checkbox.setEnabled(checked)
        self.do_not_store_if_reopened_checkbox.setEnabled(checked)

    def do_daily_backp_checkbox_clicked(self, checked):
        self.dest_directory_edit.setEnabled(checked)
        self.dest_pick_button.setEnabled(checked)
        self.dest_directory_label.setEnabled(checked)
        self.copies_to_keep_checkbox.setEnabled(checked)
        self.copies_to_keep_checkbox_clicked(checked and self.copies_to_keep_checkbox.checkState() == Qt.Checked)

    def copies_to_keep_checkbox_clicked(self, checked):
        self.copies_to_keep_spin.setEnabled(checked)

    # Called by Calibre before save_settings 
    def validate(self):
#        import traceback
#        traceback.print_stack()
        
        debug_print('BEGIN Validate')
        valid = True
        # Only save if we were able to get data to avoid corrupting stored data
#        if self.do_daily_backp_checkbox.checkState() == Qt.Checked and not len(self.dest_directory_edit.text()):
#            error_dialog(self, 'No destination directory',
#                            'If the automatic device backup is set, there must be a destination directory.',
#                            show=True, show_copy_button=False)
#            valid = False

        debug_print('END Validate, status = %s' % valid)
        return valid

    def save_settings(self):

        new_prefs = {}
        new_prefs[KEY_BUTTON_ACTION_DEVICE]     = unicode(self.device_default_combo.currentText())
        new_prefs[KEY_BUTTON_ACTION_LIBRARY]    = unicode(self.library_default_combo.currentText())
        new_prefs[KEY_STORE_ON_CONNECT]         = self.store_on_connect_checkbox.checkState() == Qt.Checked
        new_prefs[KEY_PROMPT_TO_STORE]          = self.prompt_to_store_checkbox.checkState() == Qt.Checked
        new_prefs[KEY_STORE_IF_MORE_RECENT]     = self.store_if_more_recent_checkbox.checkState() == Qt.Checked
        new_prefs[KEY_DO_NOT_STORE_IF_REOPENED] = self.do_not_store_if_reopened_checkbox.checkState() == Qt.Checked
        plugin_prefs[COMMON_OPTIONS_STORE_NAME] = new_prefs

        new_update_prefs = {}
#         new_update_prefs[KEY_DO_UPDATE_CHECK]          = self.do_update_check.checkState() == Qt.Checked
#         new_update_prefs[KEY_DO_EARLY_FIRMWARE_CHECK]  = self.do_early_firmware_check.checkState() == Qt.Checked
#         new_update_prefs[KEY_LAST_FIRMWARE_CHECK_TIME] = self.update_check_last_time
        plugin_prefs[UPDATE_OPTIONS_STORE_NAME]        = new_update_prefs

        backup_prefs = {}
        backup_prefs[KEY_DO_DAILY_BACKUP]       = self.do_daily_backp_checkbox.checkState() == Qt.Checked
        backup_prefs[KEY_BACKUP_DEST_DIRECTORY] = unicode(self.dest_directory_edit.text())
        backup_prefs[KEY_BACKUP_COPIES_TO_KEEP] = int(unicode(self.copies_to_keep_spin.value())) if self.copies_to_keep_checkbox.checkState() == Qt.Checked else -1 
        plugin_prefs[BACKUP_OPTIONS_STORE_NAME] = backup_prefs

        db = self.plugin_action.gui.current_db
        library_config = get_library_config(db)
        library_config[KEY_CURRENT_LOCATION_CUSTOM_COLUMN] = self.current_Location_combo.get_selected_column()
        library_config[KEY_PERCENT_READ_CUSTOM_COLUMN]     = self.percent_read_combo.get_selected_column()
        library_config[KEY_RATING_CUSTOM_COLUMN]           = self.rating_combo.get_selected_column()
        library_config[KEY_LAST_READ_CUSTOM_COLUMN]        = self.last_read_combo.get_selected_column()
        set_library_config(db, library_config)

    def get_number_custom_columns(self):
        column_types = ['float','int']
        return self.get_custom_columns(column_types)

    def get_rating_custom_columns(self):
        column_types = ['rating','int']
        custom_columns = self.get_custom_columns(column_types)
        ratings_column_name = self.plugin_action.gui.library_view.model().orig_headers['rating']
        custom_columns['rating'] = {'name': ratings_column_name}
        return custom_columns

    def get_text_custom_columns(self):
        column_types = ['text']
        return self.get_custom_columns(column_types)

    def get_date_custom_columns(self):
        column_types = ['datetime']
        return self.get_custom_columns(column_types)

    def get_custom_columns(self, column_types):
        custom_columns = self.plugin_action.gui.library_view.model().custom_columns
        available_columns = {}
        for key, column in custom_columns.iteritems():
            typ = column['datatype']
            if typ in column_types and not column['is_multiple']:
                available_columns[key] = column
        return available_columns

    def help_link_activated(self, url):
        self.plugin_action.show_help(anchor="configuration")

    def edit_shortcuts(self):
        d = KeyboardConfigDialog(self.plugin_action.gui, self.plugin_action.action_spec[0])
        if d.exec_() == d.Accepted:
            self.plugin_action.gui.keyboard.finalize()

    def _get_dest_directory_name(self):
        path = choose_dir(self, 'backup annotations destination dialog','Choose destination directory')
        if path:
            self.dest_directory_edit.setText(path)
