#!/usr/bin/python
# -*- coding: UTF-8 -*-
from __future__ import (unicode_literals, division, absolute_import,
                        print_function)

__license__   = 'GPL v3'
__copyright__ = '2012, David Forrester <davidfor@internode.on.net>'\
                '2014, Derek Broughton <auspex@pointerstop.ca>'
__docformat__ = 'restructuredtext en'

import os
import re
import shutil
from datetime import datetime

from contextlib import closing

from calibre.utils.ipc.server import Server
from calibre.utils.ipc.job import ParallelJob
from calibre.utils.logging import Log
from calibre_plugins.sonyutilities.action import (
                    EPUB_FETCH_QUERY, 
                    check_device_database)
import calibre_plugins.sonyutilities.config as cfg
from calibre_plugins.sonyutilities.common_utils import debug_print, convert_sony_date, SonyDB
from calibre_plugins.sonyutilities.book import EbookIterator

def do_device_database_backup(backup_options, notification=lambda x,y:x):
    """
    Sony keeps independent databases on both the internal memory and any external SD cards
    
    This job will be started once for each memory location, copying every file from the 
    database directory with a ".db" extension, to a folder in the user-configured destination
    directory.
    
    This automatic backup will only be performed once a day, so the job will exit without 
    backups if run a second time.
    
    >>> import os
    
    Make a database directory, with a number of files
    >>> source_dir = os.tempnam()
    >>> os.mkdir(source_dir)
    >>> import subprocess
    >>> print(subprocess.check_output("cd %s;touch books.db notepads.db textfile.txt" % source_dir, shell=True))
    <BLANKLINE>
    
    >>> backup_options = {
    ...     'device_name': 'Sony Reader',
    ...     'device_store_uuid': 'abcdef',
    ...     'location_code': 'main',
    ...     'dest': os.tempnam(),
    ...     'database_file': source_dir+"/books.db",
    ...     'copies': 2
    ... }
    >>> #from calibre_plugins.sonyutilities.jobs import do_device_database_backup
    >>> ret=do_device_database_backup(backup_options)
    >>> print(subprocess.check_output("ls %(dest)s" % backup_options, stderr=subprocess.STDOUT, shell=True))
    books.db  notepads.db
    >>> print(subprocess.call("rm -rf "+source_dir, shell=True))
    0
    >>> print(subprocess.call("rm -rf %(dest)s" % backup_options, shell=True))
    0
    
    """
    debug_print("start")
       
    BACKUP_FILE_TEMPLATE = '{0}-{1}-{2}-{3}'

    notification(0.01, _("Backing up the Sony device database"))
    debug_print('backup_options=', backup_options)
    device_name             = backup_options['device_name']
    uuid                    = backup_options['device_store_uuid']
    location                = backup_options['location_code']
    # Backup file names will be devicename-location-uuid-timestamp
    backup_template         = BACKUP_FILE_TEMPLATE.format(device_name, location, uuid, '{0}')
    dest_dir                = backup_options['dest']
    copies_to_keep          = backup_options['copies']
    debug_print('copies_to_keep=', copies_to_keep)
    
    database_file           = backup_options['database_file']
    import glob
    
    backup_file_search = datetime.now().strftime(backup_template.format("%Y%m%d-"+'[0-9]'*6))
    debug_print('backup_file_search=', backup_file_search)
    backup_file_search = os.path.join(dest_dir, backup_file_search)
    debug_print('backup_file_search=', backup_file_search)
    backup_files = glob.glob(backup_file_search)
    debug_print('backup_files=', backup_files)

    if len(backup_files) > 0:
        debug_print('Backup already done today')
        notification(1, _("Backup already done"))
        return False

    notification(0.1, _("Backing up databases"))
    database_dir    = os.path.dirname(database_file)
    backup_dir_name = datetime.now().strftime(backup_template.format("%Y%m%d-%H%M%S"))
    backup_file_path= os.path.join(dest_dir, backup_dir_name, '')
    debug_print('backup_dir_name=%s' % backup_dir_name)
    debug_print('backup_dir_path=%s' % backup_file_path)
    shutil.copytree(database_dir, 
                    backup_file_path, 
                    ignore=lambda src,names: [x for x in names if not x.endswith('.db')])
    
    files_backedup  = glob.glob(backup_file_path+'/*.db')
    num_backups     = float(len(files_backedup))
    
    progress = 0.4
    progress_inc = 0.4/num_backups
    for database_file in files_backedup:
        progress += progress_inc
        notification(progress, _("Performing check on the database")+ "=%s" % database_file)
        try:
            check_result = check_device_database(database_file)
            if not check_result.split()[0] == 'ok':
                debug_print('database is corrupt!')
                raise Exception(check_result)
        except Exception as e:
            debug_print('backup is corrupt - renaming file.')
            filename, fileext = os.path.splitext(database_file)
            corrupt_filename = filename + "_CORRUPT" + fileext
            debug_print('backup_file_name=%s' % database_file)
            debug_print('corrupt_file_path=%s' % corrupt_filename)
            os.rename(database_file, corrupt_filename)
            raise

    if copies_to_keep > 0:
        notification(0.9, _("Removing old backups"))
        debug_print('copies to keep:%s' % copies_to_keep)

        timestamp_filter = "{0}-{1}".format('[0-9]'*8, '[0-9]'*6)
#             backup_file_search = backup_template.format("*-*")
        backup_file_search = backup_template.format(timestamp_filter)
        debug_print('backup_file_search=', backup_file_search)
        backup_file_search = os.path.join(dest_dir, backup_file_search)
        debug_print('backup_file_search=', backup_file_search)
        backup_files = glob.glob(backup_file_search)
        debug_print('backup_files=', backup_files)
        debug_print('backup_files=', backup_files[:len(backup_files) - copies_to_keep])
        debug_print('len(backup_files) - copies_to_keep=', len(backup_files) - copies_to_keep)

        if len(backup_files) - copies_to_keep > 0:
            for filename in sorted(backup_files)[:len(backup_files) - copies_to_keep]:
                debug_print('removing backup files:', filename)
                shutil.rmtree(filename, ignore_errors=True)

        debug_print('Removing old backups - finished')
    else:
        debug_print('Manually managing backups')

    notification(1, _("Sony device database backup finished"))
    return False


def do_store_locations(books_to_scan, options, notification=lambda x,y:x):
    '''
    Master job, to launch child jobs to modify each ePub
    '''
    debug_print("start")
    server = Server()
    
    debug_print("options=%s" % (options))
    # Queue all the jobs
#     args = ['calibre_plugins.sonyutilities.jobs', 'do_sonyutilities_all',
    args = ['calibre_plugins.sonyutilities.jobs', 'do_store_bookmarks',
            (books_to_scan, options)]
#    debug_print("args=%s" % (args))
    debug_print("len(books_to_scan)=%d" % (len(books_to_scan)))
    job = ParallelJob('arbitrary', "Store locations", done=None, args=args)
    server.add_job(job)

    # This server is an arbitrary_n job, so there is a notifier available.
    # Set the % complete to a small number to avoid the 'unavailable' indicator
    notification(0.01, 'Reading device database')

    # dequeue the job results as they arrive, saving the results
    total = 1
    count = 0
    stored_locations = dict()
    while True:
        job = server.changed_jobs_queue.get()
        # A job can 'change' when it is not finished, for example if it
        # produces a notification. Ignore these.
        job.update()
        if not job.is_finished:
            debug_print("Job not finished")
            continue
#        debug_print("Job finished")
        # A job really finished. Get the information.
        stored_locations = job.result
        import pydevd;pydevd.settrace()
#        book_id = job._book_id
#        stored_locations[book_id] = stored_location
        count += 1
        notification(float(count)/total, 'Storing locations')
        # Add this job's output to the current log
        #debug_print("Stored_location=", stored_locations)
        number_bookmarks = len(stored_locations) if stored_locations else 0
        debug_print("Stored_location count=%d" % number_bookmarks)
        debug_print(job.details)
        if count >= total:
            # All done!
            break

    server.close()
    debug_print("finished")
    # return the map as the job result
    return stored_locations, options

def do_store_bookmarks(books, options):
    '''
    Child job, to store location for all the books
    '''
    
    debug_print("start")
    count_books      = 0
    stored_locations = dict()
    clear_if_unread          = options[cfg.KEY_CLEAR_IF_UNREAD]
    store_if_more_recent     = options[cfg.KEY_STORE_IF_MORE_RECENT]
    do_not_store_if_reopened = options[cfg.KEY_DO_NOT_STORE_IF_REOPENED]
    device                   = options['action'].device
    import pydevd;pydevd.settrace() # debug

    with closing(SonyDB(options['databases'])) as cursors:
        count_books += 1
    
        debug_print("about to start book loop")
        for book in books:
            title   = book['title']
            authors = book['authors']
            contentIDs = book['contentIds']
            debug_print("Current book: %s - %s" %(title, authors))
            debug_print("contentIds='%s'" % (contentIDs))
            book_status = None
            for path_id,contentID in enumerate(contentIDs):
    #                log("_store_bookmarks - contentId='%s'" % (contentID))
                debug_print("contentId='%s'" % (contentID))
                if book['paths'][path_id].startswith(device._main_prefix):
                    cursor = cursors[device._main_prefix]
                else:
                    cursor = cursors[device._card_a_prefix]
                cursor.execute(EPUB_FETCH_QUERY, (contentID,))
                
                # Take the status from the version that is farthest along
                for row in cursor:
                    if not book_status \
                    or row[b'reading_time'] > book_status[b'reading_time'] \
                    or row[b'percent'] > book_status[b'percent']:
                        book_status = dict(row)
                        if not row[b'percent']:
                            book_status[b'percent'] = EbookIterator(book['paths'][path_id],
                                                                    log=Log()).calculate_percent_read(row[b'mark'])
            if not book_status:
                continue
    
            debug_print("book_status=", book_status)
            book_status['reading_time'] = convert_sony_date(book_status['reading_time'])
    #             debug_print("last_read=", last_read)
    
            reading_position_changed = False
            if book_status['mark'] is None and clear_if_unread:
                reading_position_changed    = True
                book_status['mark']         = None
                book_status['percent']      = 0
                book_status['reading_time'] = None
            else:
                reading_position_changed = book['bookmark'] != book_status['mark']
                reading_position_changed |= book['percentRead'] != book_status['percent']
                reading_position_changed |= book['last_read'] != book_status['reading_time']
                debug_print("reading_position_changed=", reading_position_changed)
                if store_if_more_recent:
                    if book['last_read'] and book_status['reading_time']:
                        debug_print("current_last_read < last_read=", book['last_read'] < book_status['reading_time'])
                        reading_position_changed &= book['last_read'] < book_status['reading_time']
                    elif book_status['reading_time']:
                        reading_position_changed &= True
                if do_not_store_if_reopened:
                    debug_print("book.percentRead=", book['percentRead'])
                    reading_position_changed &= book['percentRead'] < 100
    
            if reading_position_changed:
                debug_print("position changed for: %s - %s" %(title, authors))
                stored_locations[book['id']] = book_status

    debug_print("finished book loop")
    
    # clean up
    for cursor in cursor.values():
        cursor.connection.close()
    
    debug_print("finished")
    return stored_locations
