#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=4:sw=4:sta:et:sts=4:ai
from __future__ import (unicode_literals, division, absolute_import,
                        print_function)

__license__   = 'GPL v3'
__copyright__ = '2011, Grant Drake <grant.drake@gmail.com>'
__docformat__ = 'restructuredtext en'

import re
import os
try:
    import init_calibre # must be imported for nosetests
except ImportError:
    pass

from calibre_plugins.sonyutilities.common_utils import debug_print
from calibre.utils.date import format_date
from calibre.ebooks.metadata import fmt_sidx
from calibre.ebooks.metadata.book.base import Metadata
from calibre.ebooks.oeb.iterator.book import EbookIterator as _iterator
from calibre.ebooks.oeb.parse_utils import parse_html, xpath
from lxml import etree

def get_indent_for_index(series_index):
    if not series_index:
        return 0
    return len(str(series_index).split('.')[1].rstrip('0'))

class SeriesBook(object):
    series_column = 'Series'


    def __init__(self, mi, series_columns):
        debug_print("SeriesBook:__init__ - mi.series_index=", mi.series_index)
        self._orig_mi      = Metadata(_('Unknown'), other=mi)
        self._mi           = mi
        self._orig_title   = mi.title
        self._orig_pubdate = self._mi.pubdate
        self._orig_series  = self._mi.sony_series
        self.get_series_index()
        self._series_columns     = series_columns
        self._assigned_indexes   = { 'Series': None }
        self._series_indents     = { 'Series': get_indent_for_index(mi.series_index) }
        self._is_valid_index     = True
        self._orig_custom_series = {}

        for key in self._series_columns:
            self._orig_custom_series[key] = mi.get_user_metadata(key, True)
            self._series_indents[key] = get_indent_for_index(self.series_index(column=key))
            self._assigned_indexes[key] = None

    def get_series_index(self):
        self._orig_series_index_string = None
        self._series_index_format      = None
        try:
            debug_print("SeriesBook:get_series_index - self._mi.sony_series_number=%s" % self._mi.sony_series_number)
            self._orig_series_index = float(self._mi.sony_series_number) if self._mi.sony_series_number is not None else None
        except:
            debug_print("SeriesBook:get_series_index - non numeric series - self._mi.sony_series_number=%s" % self._mi.sony_series_number)
            numbers = re.findall(r"\d*\.?\d+", self._mi.sony_series_number)
            if len(numbers) > 0:
                self._orig_series_index        = float(numbers[0])
                self._orig_series_index_string = self._mi.sony_series_number
                self._series_index_format      = self._mi.sony_series_number.replace(numbers[0], "%g", 1)
#            self._orig_series_index = re.findall(r"\d*", self._mi.sony_series_number)
            debug_print("SeriesBook:get_series_index - self._orig_series_index=", self._orig_series_index)

    def get_mi_to_persist(self):
        # self._mi will be potentially polluted with changes applied to multiple series columns
        # Instead return a Metadata object with only changes relevant to the last series column selected.
        debug_print("SeriesBook:get_mi_to_persist")
        self._orig_title = self._mi.title
        if hasattr(self._mi, 'pubdate'):
            self._orig_pubdate = self._mi.pubdate
        self._orig_series = self._mi.series
        self._orig_series_index = self._mi.series_index

        return self._orig_mi

    def revert_changes(self):
        debug_print("SeriesBook:revert_changes")
        self._mi.title = self._orig_title
        if hasattr(self._mi, 'pubdate'):
            self._mi.pubdate = self._orig_pubdate
        self._mi.series = self._mi.sony_series
        self._mi.series_index = self._orig_series_index

        return


    def id(self):
        if hasattr(self._mi, 'id'):
            return self._mi.id

    def authors(self):
        return self._mi.authors

    def title(self):
        return self._mi.title

    def set_title(self, title):
        self._mi.title = title

    def is_title_changed(self):
        return self._mi.title != self._orig_title

    def pubdate(self):
        if hasattr(self._mi, 'pubdate'):
            return self._mi.pubdate

    def set_pubdate(self, pubdate):
        self._mi.pubdate = pubdate

    def is_pubdate_changed(self):
        if hasattr(self._mi, 'pubdate') and hasattr(self._orig_mi, 'pubdate'):
            return self._mi.pubdate != self._orig_pubdate
        return False

    def is_series_changed(self):
        if self._mi.series != self._orig_series:
            return True
        if self._mi.series_index != self._orig_series_index:
            return True
        
        return False

    def orig_series_name(self):
        return self._orig_series

    def orig_series_index(self):
        debug_print("SeriesBook:orig_series_index - self._orig_series_index=", self._orig_series_index)
        debug_print("SeriesBook:orig_series_index - self._orig_series_index.__class__=", self._orig_series_index.__class__)
        return self._orig_series_index

    def orig_series_index_string(self):
#        debug_print("SeriesBook:orig_series_index - self._orig_series_index=", self._orig_series_index)
#        debug_print("SeriesBook:orig_series_index - self._orig_series_index.__class__=", self._orig_series_index.__class__)
        if self._orig_series_index_string is not None:
            return self._orig_series_index_string
        
        return fmt_sidx(self._orig_series_index)

    def series_name(self):
        return self._mi.series

    def set_series_name(self, series_name):
        self._mi.series = series_name

    def series_index(self, column=None):
        return self._mi.series_index

    def series_index_string(self, column=None):
        if self._series_index_format is not None:
            return self._series_index_format % self._mi.series_index
        return fmt_sidx(self._mi.series_index)

    def set_series_index(self, series_index):
        self._mi.series_index = series_index
        self.set_series_indent(get_indent_for_index(series_index))

    def series_indent(self):
        return self._series_indents[self.series_column]

    def set_series_indent(self, index):
        self._series_indents[self.series_column] = index

    def assigned_index(self):
        return self._assigned_indexes[self.series_column]

    def set_assigned_index(self, index):
        self._assigned_indexes[self.series_column] = index

    def is_valid(self):
        return self._is_valid_index

    def set_is_valid(self, is_valid_index):
        self._is_valid_index = is_valid_index

    def sort_key(self, sort_by_pubdate=False, sort_by_name=False):
        if sort_by_pubdate:
            pub_date = self.pubdate()
            if pub_date is not None and pub_date.year > 101:
                return format_date(pub_date, 'yyyyMMdd')
        else:
            series = self.orig_series_name()
            series_number = self.orig_series_index() if self.orig_series_index() is not None else -1
            debug_print("sort_key - series_number=", series_number)
            debug_print("sort_key - series_number.__class__=", series_number.__class__)
            if series:
                if sort_by_name:
                    return '%s%06.2f'% (series, series_number)
                else:
                    return '%06.2f%s'% (series_number, series)
        return ''

class EbookIterator(_iterator):
    def __init__(self, pathtoebook, log=None):
        """
        The superclass is not a true "iterator". This makes it a little closer
        by combining the __init__() and __enter__() methods
        
        """
        super(EbookIterator, self).__init__(pathtoebook, log=log)
        self.__enter__(only_input_plugin=True, read_anchor_map=False)

    def __iter__(self):
        """ make it a proper iterable, by exposing the spine as the iterator 
        """ 
        return iter(self.spine)
    
            
    def convert_from_sony_bookmark(self, bookmark, title=''):
        """
        Convert Sony bookmarks to Calibre format
        
        A sony bookmark looks like:
        >>> sony_bookmark = "titlepage.xhtml#point(/1/4/2/2:0)"
        
        Create a dummy book class that doesn't actually have to open a file
        >>> from calibre_plugins.sonyutilities.book import EbookIterator 
        >>> class Tempdir():
        ...     tdir='/tmp'
        ... 
        >>> class DummyBook(EbookIterator):
        ...     def __init__(self):
        ...         self.spine = ['/tmp/dummy1.xhtml', '/tmp/titlepage.xhtml', '/tmp/dummy1.xhtml',]
        ...         self._tdir = Tempdir()
        ... 
        >>> book = DummyBook()
        >>> print(book.convert_from_sony_bookmark(sony_bookmark,u'my bookmark'))
        {'spine': 1, 'type': u'cfi', 'pos': u'/2/4/2/2:0', 'title': u'my bookmark'}
        
        """
        filename,pos = bookmark.split('#point')
        pos          = pos.strip(u'(\x00)').split('/')
        # Adobe Digital Editions doesn't count the tags correctly
        if pos[1] == '1':
            pos[1] = '2'
        pos = '/'.join(pos)
        prefix       = self._tdir.tdir
        path         = os.path.join(prefix,filename)
        spine_num    = self.spine.index(path)
        
        bm = dict(title=title, type='cfi', spine=spine_num, pos=pos)
        return bm
    
    def convert_to_sony_bookmark(self, bm):
        """
        Convert Calibre bookmarks to Sony format
        
        A sony bookmark looks like:
        >>> sony_bookmark = "titlepage.xhtml#point(/1/4/2/2:0)"
        
        The (internal) Calibre bookmark is a dictionary:
        >>> calibre_bm = {'spine': 1, 'type': 'cfi', 'pos': u'/2/4/2/2:0', 'title': 'my bookmark'}
        
        >>> class Tempdir():
        ...     tdir='/tmp'
        ... 
        >>> class DummyBook(EbookIterator):
        ...     def __init__(self):
        ...         self.spine = ['/tmp/dummy1.xhtml', '/tmp/titlepage.xhtml', '/tmp/dummy1.xhtml',]
        ...         self._tdir = Tempdir()
        ... 
        >>> book = DummyBook()
        >>> print(book.convert_to_sony_bookmark(calibre_bm)==sony_bookmark)
        True
        
        """
        prefix      = self._tdir.tdir+'/'
        filename    = self.spine[bm['spine']].rpartition(prefix)[2]
        pos         = bm['pos'].split('/')
        
        # ADE doesn't count the <HEAD> tag
        if pos[1] == '2':
            pos[1]  = '1'
        
        bookmark = "%s#point(%s)" % (filename, '/'.join(pos))
        return bookmark


    def calculate_percent_read(self,bookmark):
        """
        Open a book and figure out how far into it we are from the bookmark
        
        Sony store a current page number, and total number of pages, for books downloaded 
        from their store (now Kobo), but doesn't store it for sideloaded books.
        
        >>> 
        """
        CFI = re.compile(r'([\[\]:@~])')
        node_len  = lambda x: len(x) if x is not None else 0

        def walk_tree(parent, pos):
            # find the tag number we're looking for
            tag_parts = CFI.split(pos.pop(0))
            tag_id = ''
            offset = 0
    
            if len(tag_parts) > 1:
                if tag_parts[1] == '[':
                    tag_id = tag_parts[2]
                elif tag_parts[1] == ':':
                    try:
                        offset = int(tag_parts[2])
                    except Exception, e:
                        debug_print(e)
                    
            tag_num = int(tag_parts[0])
    
            if tag_num > 1:
                left_char_cnt  = node_len(parent.text)
            else:
                left_char_cnt  = 0
            right_char_cnt     = node_len(parent.tail)
            
            if tag_id:
                tag_node   = parent.find(".//*[id='%s']" % tag_id)
                if tag_node:
                    tag_num= parent.index(tag_node)
                
            # if it's an odd numbered node, it's text
            text_node = (tag_num % 2 == 1)
            # actual tags are even indexes (odd numbers indicate the text between tags)
            # so pos: 2->0, 4->1, 6->2, etc
            idx       = (tag_num-1)//2
            # find all the text to the left of our pointer
            left_char_cnt += sum([len(etree.tostring(node,method="text"))+node_len(node.tail)
                                  for node in parent[:idx]])
            # now, if it's a text node, we counted too far
            # subtract the tail of the last node, and add any offset
            if text_node:
                left_char_cnt += offset - node_len(node.tail)
            # if it's a tag node, drill down, if there's anything left to drill 
            elif pos:
                l,r  = walk_tree(parent[idx], pos)
                left_char_cnt += l
                right_char_cnt+= r
            else:
                left_char_cnt += offset
                right_char_cnt+= len(etree.tostring(parent[idx],method="text"))+node_len(parent[idx].tail)-offset
            # and find the characters to the right of our pointer
            right_char_cnt += sum([len(etree.tostring(node,method="text"))+node_len(node.tail)
                                  for node in parent[idx+1:]])
                
            return left_char_cnt, right_char_cnt
            
        
        bookmark     = unicode(bookmark)
        bm           = self.convert_from_sony_bookmark(bookmark, title=u'calibre_current_page_bookmark')
        spine_num    = bm['spine']
        total_pages  = sum(self.pages)
        pages_before = sum(self.pages[:spine_num])
        
        raw          = open(self.spine[spine_num]).read()
        html         = parse_html(raw, self.log)
        # we'll start from the <body> element, which is /2/4 in the EPUB CFI format
        pos          = bm['pos'].split('/')[3:]
        body         = xpath(html, '//h:body')[0]
        left,right   = walk_tree(body, pos)
        pages_before+= self.pages[spine_num] * left / (left+right)
        
        return 100.0 * pages_before / total_pages
