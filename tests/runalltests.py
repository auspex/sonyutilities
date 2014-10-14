#!/usr/bin/python
# -*- coding: UTF-8 -*-
from __future__ import (unicode_literals, division, absolute_import,
                        print_function)

__license__   = 'GPL v3'
__copyright__ = '2014, Derek Broughton <auspex@pointerstop.ca>'
__docformat__ = 'restructuredtext en'
'''
Created on Oct 3, 2014

@author: derek broughton <auspex@pointerstop.ca>
'''
import os
try:
    import init_calibre # must be imported to be able to import sonyutilities
    from calibre_plugins import sonyutilities
except ImportError:
    import sys
    if "pydoc" in sys.argv[0]:
        pass
    else:
        raise  
import doctest
import unittest
DEBUG = True

def load_tests(loader, tests, ignore):
    """
    this function is automatically found by the unittest finder
    
    Note, calibre uses i18n, and _() is used extensively.  Therefore, never display a result
    implicitly, always use print(). IE:
    >>> print(_)
    <bound method NullTranslations.ugettext ...

    Provided this test is still running last in the suite, this won't break anything, but will show 
    what happens when you use the implicit display:
    >>> str('this is a string')
    'this is a string'
    >>> print(_)
    this is a string
    
    And now _ is b0rked!
    """
    path   = os.path.dirname(sonyutilities.__file__)
    flist  = []
    for root, dirs, files in os.walk(path):
        # remove hidden directories from 'dirs', starting at end of list 
        ixs = reversed(range(len(dirs)))
        [dirs.pop(n) for n in ixs if dirs[n][0] == '.']
        
        # add python source files (.py) and text files ('.txt') to the file list 
        flist += [os.path.join(root,f) for f in files if f[0] != '.' and f.endswith((".py",".txt"))]
        
    suite  = doctest.DocFileSuite(*flist,
                                  module_relative=False,
#                                   setUp      = setUp,
#                                   tearDown   = tearDown,
#                                   globs      = {'DEBUG': True},
                                  optionflags= doctest.ELLIPSIS
                          )
    tests.addTests(suite)
    return tests

if __name__ == '__main__':
    pythonpath = ':'.join([x for x in sys.path if x ])
    print ('PYTHONPATH='+pythonpath)
    unittest.main()
