#!/usr/bin/python
# -*- coding: UTF-8 -*-
from __future__ import (unicode_literals, division, absolute_import,
                        print_function)

__license__   = 'GPL v3'
__copyright__ = '2012, David Forrester <davidfor@internode.on.net>'\
                '2014, Derek Broughton <auspex@pointerstop.ca>'
__docformat__ = 'restructuredtext en'

import os, time
try:
    from PyQt5.Qt import Qt
    from PyQt5.Qt import (QIcon, QPixmap, QLabel, QDialog, QHBoxLayout, QProgressBar,
                          QTableWidgetItem, QFont, QLineEdit, QComboBox,
                          QVBoxLayout, QDialogButtonBox, QStyledItemDelegate, QDateTime,
                          QRegExpValidator, QRegExp, )
except ImportError:
    from PyQt4.Qt import Qt
    from PyQt4.Qt import (QIcon, QPixmap, QLabel, QDialog, QHBoxLayout, QProgressBar,
                          QTableWidgetItem, QFont, QLineEdit, QComboBox,
                          QVBoxLayout, QDialogButtonBox, QStyledItemDelegate, QDateTime,
                          QRegExpValidator, QRegExp)

from calibre.constants import iswindows, DEBUG
from calibre.gui2 import gprefs, error_dialog, UNDEFINED_QDATETIME, Application
from calibre.gui2.actions import menu_action_unique_name
from calibre.gui2.keyboard import ShortcutConfig
from calibre.utils.config import config_dir
from calibre.utils.date import now, format_date, UNDEFINED_DATE
from calibre import prints
import sys
import sqlite3

# Global definition of our plugin name. Used for common functions that require this.
plugin_name = None
# Global definition of our plugin resources. Used to share between the xxxAction and xxxBase
# classes if you need any zip images to be displayed on the configuration dialog.
plugin_icon_resources = {}

BASE_TIME = None
def debug_print(*args):
    """
    Print all args, prefixed by a time stamp and the module/method from which it was called
    
    >>> from calibre_plugins.sonyutilities.common_utils import debug_print
    >>> global DEBUG
    >>> DEBUG=True
    
    Unfortunately, that doesn't seem to actually set DEBUG, and we get nothing...
    >>> debug_print("test", "message")
    
    """
    #TODO: figure out how to set DEBUG=True in tests
    if DEBUG:
        code = sys._getframe(1).f_code
        method_name = code.co_filename+'::'+code.co_name
        del code
    
        global BASE_TIME
        if BASE_TIME is None:
            BASE_TIME = time.time()
        prints('DEBUG: %6.1f'%(time.time()-BASE_TIME), method_name, '-', *args)



def set_plugin_icon_resources(name, resources):
    '''
    Set our global store of plugin name and icon resources for sharing between
    the InterfaceAction class which reads them and the ConfigWidget
    if needed for use on the customization dialog for this plugin.
    '''
    global plugin_icon_resources, plugin_name
    plugin_name = name
    plugin_icon_resources = resources

def get_icon(icon_name):
    '''
    Retrieve a QIcon for the named image from the zip file if it exists,
    or if not then from Calibre's image cache.
    '''
    if icon_name:
        pixmap = get_pixmap(icon_name)
        if pixmap is None:
            # Look in Calibre's cache for the icon
            return QIcon(I(icon_name))
        else:
            return QIcon(pixmap)
    return QIcon()


def get_pixmap(icon_name):
    '''
    Retrieve a QPixmap for the named image
    Any icons belonging to the plugin must be prefixed with 'images/'
    '''
    global plugin_icon_resources, plugin_name

    if not icon_name.startswith('images/'):
        # We know this is definitely not an icon belonging to this plugin
        pixmap = QPixmap()
        pixmap.load(I(icon_name))
        return pixmap

    # Check to see whether the icon exists as a Calibre resource
    # This will enable skinning if the user stores icons within a folder like:
    # ...\AppData\Roaming\calibre\resources\images\Plugin Name\
    if plugin_name:
        local_images_dir = get_local_images_dir(plugin_name)
        local_image_path = os.path.join(local_images_dir, icon_name.replace('images/', ''))
        if os.path.exists(local_image_path):
            pixmap = QPixmap()
            pixmap.load(local_image_path)
            return pixmap

    # As we did not find an icon elsewhere, look within our zip resources
    if icon_name in plugin_icon_resources:
        pixmap = QPixmap()
        pixmap.loadFromData(plugin_icon_resources[icon_name])
        return pixmap
    return None


def get_local_images_dir(subfolder=None):
    '''
    Returns a path to the user's local resources/images folder
    If a subfolder name parameter is specified, appends this to the path
    '''
    images_dir = os.path.join(config_dir, 'resources/images')
    if subfolder:
        images_dir = os.path.join(images_dir, subfolder)
    if iswindows:
        images_dir = os.path.normpath(images_dir)
    return images_dir


def create_menu_item(ia, parent_menu, menu_text, image=None, tooltip=None,
                     shortcut=(), triggered=None, is_checked=None):
    '''
    Create a menu action with the specified criteria and action
    Note that if no shortcut is specified, will not appear in Preferences->Keyboard
    This method should only be used for actions which either have no shortcuts,
    or register their menus only once. Use create_menu_action_unique for all else.
    '''
    if shortcut is not None:
        if len(shortcut) == 0:
            shortcut = ()
        else:
            shortcut = _(shortcut)
    ac = ia.create_action(spec=(menu_text, None, tooltip, shortcut),
        attr=menu_text)
    if image:
        ac.setIcon(get_icon(image))
    if triggered is not None:
        ac.triggered.connect(triggered)
    if is_checked is not None:
        ac.setCheckable(True)
        if is_checked:
            ac.setChecked(True)

    parent_menu.addAction(ac)
    return ac


def create_menu_action_unique(ia, parent_menu, menu_text, image=None, tooltip=None,
                       shortcut=None, triggered=None, is_checked=None, shortcut_name=None,
                       unique_name=None):
    '''
    Create a menu action with the specified criteria and action, using the new
    InterfaceAction.create_menu_action() function which ensures that regardless of
    whether a shortcut is specified it will appear in Preferences->Keyboard
    '''
    orig_shortcut = shortcut
    kb = ia.gui.keyboard
    if unique_name is None:
        unique_name = menu_text
    if not shortcut == False:
        full_unique_name = menu_action_unique_name(ia, unique_name)
        if full_unique_name in kb.shortcuts:
            shortcut = False
        else:
            if shortcut is not None and not shortcut == False:
                if len(shortcut) == 0:
                    shortcut = None
                else:
                    shortcut = _(shortcut)

    if shortcut_name is None:
        shortcut_name = menu_text.replace('&','')

    ac = ia.create_menu_action(parent_menu, unique_name, menu_text, icon=None, shortcut=shortcut,
        description=tooltip, triggered=triggered, shortcut_name=shortcut_name)
    if shortcut == False and not orig_shortcut == False:
        if ac.calibre_shortcut_unique_name in ia.gui.keyboard.shortcuts:
            kb.replace_action(ac.calibre_shortcut_unique_name, ac)
    if image:
        ac.setIcon(get_icon(image))
    if is_checked is not None:
        ac.setCheckable(True)
        if is_checked:
            ac.setChecked(True)
    return ac


def get_library_uuid(db):
    try:
        library_uuid = db.library_id
    except:
        library_uuid = ''
    return library_uuid


class ImageLabel(QLabel):

    def __init__(self, parent, icon_name, size=16):
        super(QLabel,self).__init__(self, parent)
        pixmap = get_pixmap(icon_name)
        self.setPixmap(pixmap)
        self.setMaximumSize(size, size)
        self.setScaledContents(True)


class ImageTitleLayout(QHBoxLayout):
    '''
    A reusable layout widget displaying an image followed by a title
    '''
    def __init__(self, parent, icon_name, title):
        super(QHBoxLayout,self).__init__(self)
        self.title_image_label = QLabel(parent)
        self.update_title_icon(icon_name)
        self.addWidget(self.title_image_label)

        title_font = QFont()
        title_font.setPointSize(16)
        shelf_label = QLabel(title, parent)
        shelf_label.setFont(title_font)
        self.addWidget(shelf_label)
        self.insertStretch(-1)
        
        # Add hyperlink to a help file at the right. We will replace the correct name when it is clicked.
        help_label = QLabel(('<a href="http://www.foo.com/">{0}</a>').format(_("Help")), parent)
        help_label.setTextInteractionFlags(Qt.LinksAccessibleByMouse | Qt.LinksAccessibleByKeyboard)
        help_label.setAlignment(Qt.AlignRight)
        help_label.linkActivated.connect(parent.help_link_activated)
        self.addWidget(help_label)

    def update_title_icon(self, icon_name):
        pixmap = get_pixmap(icon_name)
        if pixmap is None:
            error_dialog(self.parent(),  _("Restart required"),
                          _("Title image not found - you must restart Calibre before using this plugin!"), show=True)
        else:
            self.title_image_label.setPixmap(pixmap)
        self.title_image_label.setMaximumSize(32, 32)
        self.title_image_label.setScaledContents(True)


class SizePersistedDialog(QDialog):
    '''
    This dialog is a base class for any dialogs that want their size/position
    restored when they are next opened.
    '''
    def __init__(self, parent, unique_pref_name):
        super(QDialog,self).__init__(self, parent)
        self.unique_pref_name = unique_pref_name
        self.geom = gprefs.get(unique_pref_name, None)
        self.finished.connect(self.dialog_closing)
        self.help_anchor = ''

    def resize_dialog(self):
        if self.geom is None:
            self.resize(self.sizeHint())
        else:
            self.restoreGeometry(self.geom)

    def dialog_closing(self, result):
        geom = bytearray(self.saveGeometry())
        gprefs[self.unique_pref_name] = geom

    def help_link_activated(self, url):
        self.plugin_action.show_help(anchor=self.help_anchor)


class ReadOnlyTableWidgetItem(QTableWidgetItem):

    def __init__(self, text):
        if text is None:
            text = ''
        super(QTableWidgetItem,self).__init__(self, text, QTableWidgetItem.UserType)
        self.setFlags(Qt.ItemIsSelectable|Qt.ItemIsEnabled)

class RatingTableWidgetItem(QTableWidgetItem):

    def __init__(self, rating, is_read_only=False):
        super(QTableWidgetItem,self).__init__(self, '', QTableWidgetItem.UserType)
        self.setData(Qt.DisplayRole, rating)
        if is_read_only:
            self.setFlags(Qt.ItemIsSelectable|Qt.ItemIsEnabled)


class DateTableWidgetItem(QTableWidgetItem):

    def __init__(self, date_read, is_read_only=False, default_to_today=False, fmt=None):
#        debug_print("date_read=", date_read)
        if date_read is None or date_read == UNDEFINED_DATE and default_to_today:
            date_read = now()
        if is_read_only:
            super(QTableWidgetItem,self).__init__(self, format_date(date_read, fmt), QTableWidgetItem.UserType)
            self.setFlags(Qt.ItemIsSelectable|Qt.ItemIsEnabled)
            self.setData(Qt.DisplayRole, QDateTime(date_read))
        else:
            super(QTableWidgetItem,self).__init__(self, '', QTableWidgetItem.UserType)
            self.setData(Qt.DisplayRole, QDateTime(date_read))

from calibre.gui2.library.delegates import DateDelegate as _DateDelegate
class DateDelegate(_DateDelegate):
    '''
    Delegate for dates. Because this delegate stores the
    format as an instance variable, a new instance must be created for each
    column. This differs from all the other delegates.
    '''
    def __init__(self, parent, fmt='dd MMM yyyy', default_to_today=True):
        _DateDelegate.__init__(self, parent)
        self.format = fmt
        self.default_to_today = default_to_today

#    def displayText(self, val, locale):
#        d = val.toDateTime()
#        if d <= UNDEFINED_QDATETIME:
#            return ''
#        return format_date(qt_to_dt(d, as_utc=False), self.format)

    def createEditor(self, parent, option, index):
        qde = QStyledItemDelegate.createEditor(self, parent, option, index)
        qde.setDisplayFormat(self.format)
        qde.setMinimumDateTime(UNDEFINED_QDATETIME)
        qde.setSpecialValueText(_('Undefined'))
        qde.setCalendarPopup(True)
        return qde

    def setEditorData(self, editor, index):
        val = index.model().data(index, Qt.DisplayRole).toDateTime()
        if val is None or val == UNDEFINED_QDATETIME:
            if self.default_to_today:
                val = self.default_date
            else:
                val = UNDEFINED_QDATETIME
        editor.setDateTime(val)

    def setModelData(self, editor, model, index):
        val = editor.dateTime()
        if val <= UNDEFINED_QDATETIME:
            model.setData(index, UNDEFINED_QDATETIME, Qt.EditRole)
        else:
            model.setData(index, QDateTime(val), Qt.EditRole)


class NoWheelComboBox(QComboBox):

    def wheelEvent (self, event):
        # Disable the mouse wheel on top of the combo box changing selection as plays havoc in a grid
        event.ignore()


class CheckableTableWidgetItem(QTableWidgetItem):

    def __init__(self, checked=False, is_tristate=False):
        super(QTableWidgetItem,self).__init__(self, '')
        self.setFlags(Qt.ItemFlags(Qt.ItemIsSelectable | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled ))
        if is_tristate:
            self.setFlags(self.flags() | Qt.ItemIsTristate)
        if checked:
            self.setCheckState(Qt.Checked)
        else:
            if is_tristate and checked is None:
                self.setCheckState(Qt.PartiallyChecked)
            else:
                self.setCheckState(Qt.Unchecked)

    def get_boolean_value(self):
        '''
        Return a boolean value indicating whether checkbox is checked
        If this is a tristate checkbox, a partially checked value is returned as None
        '''
        if self.checkState() == Qt.PartiallyChecked:
            return None
        else:
            return self.checkState() == Qt.Checked


class TextIconWidgetItem(QTableWidgetItem):

    def __init__(self, text, icon):
        super(QTableWidgetItem,self).__init__(self, text)
        if icon:
            self.setIcon(icon)


class ReadOnlyTextIconWidgetItem(ReadOnlyTableWidgetItem):

    def __init__(self, text, icon):
        ReadOnlyTableWidgetItem.__init__(self, text)
        if icon:
            self.setIcon(icon)


class ReadOnlyLineEdit(QLineEdit):

    def __init__(self, text, parent):
        if text is None:
            text = ''
        super(QLineEdit,self).__init__(self, text, parent)
        self.setEnabled(False)


class NumericLineEdit(QLineEdit):
    '''
    Allows a numeric value up to two decimal places, or an integer
    '''
    def __init__(self, *args):
        super(QLineEdit,self).__init__(self, *args)
        self.setValidator(QRegExpValidator(QRegExp(r'(^\d*\.[\d]{1,2}$)|(^[1-9]\d*[\.]$)'), self))


class KeyValueComboBox(QComboBox):

    def __init__(self, parent, values, selected_key):
        super(QComboBox,self).__init__(self, parent)
        self.values = values
        self.populate_combo(selected_key)

    def populate_combo(self, selected_key):
        self.clear()
        selected_idx = idx = -1
        for key, value in self.values.iteritems():
            idx = idx + 1
            self.addItem(value)
            if key == selected_key:
                selected_idx = idx
        self.setCurrentIndex(selected_idx)

    def selected_key(self):
        for key, value in self.values.iteritems():
            if value == unicode(self.currentText()).strip():
                return key


class KeyComboBox(QComboBox):

    def __init__(self, parent, values, selected_key):
        super(QComboBox,self).__init__(self, parent)
        self.values = values
        self.populate_combo(selected_key)

    def populate_combo(self, selected_key):
        self.clear()
        selected_idx = -1
        for idx,key in enumerate(sorted(self.values.keys())):
            self.addItem(key)
            if key == selected_key:
                selected_idx = idx
        self.setCurrentIndex(selected_idx)

    def selected_key(self):
        for key in self.values:
            if key == unicode(self.currentText()).strip():
                return key


class CustomColumnComboBox(QComboBox):

    def __init__(self, parent, custom_columns={}, selected_column='', initial_items=['']):
        super(QComboBox,self).__init__(self, parent)
        self.populate_combo(custom_columns, selected_column, initial_items)

    def populate_combo(self, custom_columns, selected_column, initial_items=['']):
        self.clear()
        self.column_names = list(initial_items)
        if len(initial_items) > 0:
            self.addItems(initial_items)
        selected_idx = 0
        for idx, value in enumerate(initial_items):
            if value == selected_column:
                selected_idx = idx
        for key in sorted(custom_columns.keys()):
            self.column_names.append(key)
            self.addItem('%s (%s)'%(key, custom_columns[key]['name']))
            if key == selected_column:
                selected_idx = len(self.column_names) - 1
        self.setCurrentIndex(selected_idx)

    def get_selected_column(self):
        return self.column_names[self.currentIndex()]


class KeyboardConfigDialog(SizePersistedDialog):
    '''
    This dialog is used to allow editing of keyboard shortcuts.
    '''
    def __init__(self, gui, group_name):
        SizePersistedDialog.__init__(self, gui, 'Keyboard shortcut dialog')
        self.gui = gui
        self.setWindowTitle('Keyboard shortcuts')
        layout = QVBoxLayout(self)
        self.setLayout(layout)

        self.keyboard_widget = ShortcutConfig(self)
        layout.addWidget(self.keyboard_widget)
        self.group_name = group_name

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.commit)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        # Cause our dialog size to be restored from prefs or created on first usage
        self.resize_dialog()
        self.initialize()

    def initialize(self):
        self.keyboard_widget.initialize(self.gui.keyboard)
        self.keyboard_widget.highlight_group(self.group_name)

    def commit(self):
        self.keyboard_widget.commit()
        self.accept()


class ProgressBar(QDialog):
    def __init__(self, parent=None, max_items=100, window_title='Progress Bar',
                 label='Label goes here', on_top=False):
        if on_top:
            super(QDialog,self).__init__(self, parent=parent, flags=Qt.WindowStaysOnTopHint)
        else:
            super(QDialog,self).__init__(self, parent=parent)
        self.application = Application
        self.setWindowTitle(window_title)
        self.l = QVBoxLayout(self)
        self.setLayout(self.l)

        self.label = QLabel(label)
        self.label.setAlignment(Qt.AlignHCenter)
        self.l.addWidget(self.label)

        self.progressBar = QProgressBar(self)
        self.progressBar.setRange(0, max_items)
        self.progressBar.setValue(0)
        self.l.addWidget(self.progressBar)

    def increment(self):
        self.progressBar.setValue(self.progressBar.value() + 1)
        self.refresh()

    def refresh(self):
        self.application.processEvents()

    def set_label(self, value):
        self.label.setText(value)
        self.refresh()

    def set_maximum(self, value):
        self.progressBar.setMaximum(value)
        self.refresh()

    def set_value(self, value):
        self.progressBar.setValue(value)
        self.refresh()

class Cursor():
    """
    Given a path to a SQLite database, return an object containing the path and 
    an open cursor into the database
    >>> import os
    >>> from calibre_plugins.sonyutilities.common_utils import Cursor 
    >>> path1 = os.tempnam() 
    >>> x = Cursor(path1)
    >>> print (x.path == path1)
    True
    >>> print (x.cursor)
    <sqlite3.Cursor object at ...
    
    Clean up:
    >>> import subprocess
    >>> print(subprocess.call("rm -rvf "+path1, shell=True))
    0
       
    """
    def __init__(self,path):
        self.path  = path
        connection = sqlite3.connect(path)
        # return bytestrings if the content cannot be decoded as unicode
        connection.text_factory = lambda x: unicode(x, "utf-8", "ignore")
        connection.row_factory  = sqlite3.Row
        self.cursor = connection.cursor()
        del connection
         
class SonyDB(dict):
    """
    Given a dictionary of database paths indexed by database prefix,
    open cursors for each, and return a dictionary of Cursor objects, indexed by prefix
      
    The structure is suitable for using within a "with closing(...) as ..." structure
    and all cursors will be automatically closed when the end of the "with" block is reached.
      
    >>> import subprocess
    
    Create a SonyDB object (using empty databases), and check that it has correct structure
    >>> from calibre_plugins.sonyutilities.common_utils import SonyDB
    >>> path1 = os.tempnam()
    >>> path2 = os.tempnam()
    >>> testdict = {'a': path1, 'b' : path2}
    >>> obj = SonyDB(testdict)
    >>> print(obj['a'].path == path1)
    True
    >>> print(obj['b'].path == path2)
    True
    >>> print(obj['a'].cursor)
    <sqlite3.Cursor object ...
      
    Try opening the SonyDB and executing queries:
      
    >>> from contextlib import closing
    >>> with closing(SonyDB(testdict)) as db:
    ...     for prefix in db:
    ...         print(db[prefix].cursor.execute('PRAGMA integrity_check'))
    <sqlite3.Cursor object...
    <sqlite3.Cursor object...

    Since the 'with' block is closed, the cursors will be too
    >>> db['a'].cursor.execute('PRAGMA integrity_check')
    Traceback (most recent call last):
        ...
    ProgrammingError: Cannot operate on a closed database.
  
    Finally write some garbage into one of the 'db' files and execute the queries:
      
    >>> with (open(path1,'w')) as stream:
    ...     stream.write('test')
    >>> with closing(SonyDB(testdict)) as db:
    ...     for prefix in db:
    ...         db[prefix].cursor.execute('PRAGMA integrity_check')
    Traceback (most recent call last):
        ...
    DatabaseError: file is encrypted or is not a database
          
    Clean up:
    >>> print(subprocess.call("rm -rvf %s %s" % (path1, path2), shell=True))
    0
       
    """

    def __init__(self, db):
        cursors = {}
        for key in db:
            cursors[key]= Cursor(db[key]) 
        super(SonyDB, self).__init__(cursors)
       
            
    def close(self):
        for key in self.keys():
            self[key].cursor.connection.commit()
            self[key].cursor.connection.close()


def convert_sony_date(sony_date):
    """
    Convert an input sony date to a python Datetime

    Sony's dates are unix timestamps multiplied by 1000 
    - somebody must have felt it was necessary to save those few characters per date

    Create a timestamp for "2000-11-30"
    >>> from calibre_plugins.sonyutilities.common_utils import convert_sony_date
    >>> import time
    >>> from datetime import datetime
    >>> tm = time.mktime(time.strptime("2000-11-30 UTC", "%Y-%m-%d %Z"))
    >>> print(tm)
    975556800.0
    >>> print(convert_sony_date(int(tm*1000)))
    2000-11-30 00:00:00+00:00

    """
    from calibre.utils.date import utc_tz
    from datetime import datetime
    if sony_date:
        converted_date = datetime.fromtimestamp(sony_date/1000).replace(tzinfo=utc_tz)
    else:
        converted_date = None
    return converted_date
            