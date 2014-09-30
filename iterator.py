#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=4:sw=4:sta:et:sts=4:ai
from __future__ import (division, absolute_import, print_function)

__license__   = 'GPL v3'
__copyright__ = '2014, Derek Broughton <auspex@pointerstop.ca>'
__docformat__ = 'restructuredtext en'

from calibre.ebooks.oeb.iterator.book import EbookIterator as _iterator
import os

class EbookIterator(_iterator):
    def __init__(self, pathtoebook, log=None):
        super(EbookIterator, self).__init__(pathtoebook, log=log)
        self.__enter__(only_input_plugin=True, read_anchor_map=False)
        
    def convert_from_sony_bookmark(self, bookmark, title=''):
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
        prefix       = self._tdir.tdir+'/'
        filename    = self.spine[bm['spine']].rpartition(prefix)[2]
        pos         = bm['pos'].split('/')
        
        # ADE doesn't count the <HEAD> tag
        if pos[1] == '2':
            pos[1]  = '1'
                
        bookmark = "%s#point(%s)" % filename, '/'.join(pos)
        return bookmark
        