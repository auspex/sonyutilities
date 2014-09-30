#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=4:sw=4:sta:et:sts=4:ai
from __future__ import (unicode_literals, division, absolute_import,
                        print_function)

__license__   = 'GPL v3'
__copyright__ = '2012, Derek Broughton <auspex@pointerstop.ca>'
__docformat__ = 'restructuredtext en'

import os
import re
import sys
import shutil
from datetime import datetime

from contextlib import closing

from calibre.utils.ipc.server import Server
from calibre.utils.ipc.job import ParallelJob
from calibre.utils.logging import Log
from calibre_plugins.sonyutilities.action import (
                    EPUB_FETCH_QUERY, 
                    convert_sony_date, check_device_database)
import calibre_plugins.sonyutilities.config as cfg
from calibre_plugins.sonyutilities.common_utils import debug_print
from calibre_plugins.sonyutilities.iterator import EbookIterator
from calibre.ebooks.oeb.parse_utils import parse_html, xpath
from lxml import etree

def do_device_database_backup(backup_options, notification=lambda x,y:x):
#     from sqlite3 import DatabaseError
    
    debug_print("do_device_database_backup - start")
#     server = Server()
        
    notification(0.01, _("Backing up the Sony device database"))
    debug_print('do_device_database_backup - backup_options=', backup_options)
    device_name             = backup_options['device_name']
    uuid                    = backup_options['device_store_uuid']
    location                = backup_options['location_code']
    backup_template         = backup_options['backup_file_template'].format(device_name, location, uuid, '{0}')
    dest_dir                = backup_options[cfg.KEY_BACKUP_DEST_DIRECTORY]
    copies_to_keep          = backup_options[cfg.KEY_BACKUP_COPIES_TO_KEEP]
    debug_print('do_device_database_backup - copies_to_keep=', copies_to_keep)
    import glob
    
    backup_file_search = datetime.now().strftime(backup_template.format("%Y%m%d-"+'[0-9]'*6))
    debug_print('do_device_database_backup - backup_file_search=', backup_file_search)
    backup_file_search = os.path.join(dest_dir, backup_file_search)
    debug_print('do_device_database_backup - backup_file_search=', backup_file_search)
    backup_files = glob.glob(backup_file_search)
    debug_print('do_device_database_backup - backup_files=', backup_files)

    if len(backup_files) > 0:
        debug_print('auto_backup_device_database - Backup already done today')
        notification(1, _("Backup already done"))
        return False

    notification(0.1, _("Backing up databases"))
    database_file   = backup_options['database_file']
    database_dir    = os.path.dirname(database_file)
    backup_dir_name = datetime.now().strftime(backup_template.format("%Y%m%d-%H%M%S"))
    backup_file_path= os.path.join(dest_dir, backup_dir_name, '')
    debug_print('do_device_database_backup - backup_dir_name=%s' % backup_dir_name)
    debug_print('do_device_database_backup - backup_dir_path=%s' % backup_file_path)
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
                debug_print('do_device_database_backup - database is corrupt!')
                raise Exception(check_result)
        except Exception as e:
            debug_print('do_device_database_backup - backup is corrupt - renaming file.')
            filename, fileext = os.path.splitext(database_file)
            corrupt_filename = filename + "_CORRUPT" + fileext
            debug_print('do_device_database_backup - backup_file_name=%s' % database_file)
            debug_print('do_device_database_backup - corrupt_file_path=%s' % corrupt_filename)
            os.rename(database_file, corrupt_filename)
            raise

    if copies_to_keep > 0:
        notification(0.9, _("Removing old backups"))
        debug_print('do_device_database_backup - copies to keep:%s' % copies_to_keep)

        timestamp_filter = "{0}-{1}".format('[0-9]'*8, '[0-9]'*6)
#             backup_file_search = backup_template.format("*-*")
        backup_file_search = backup_template.format(timestamp_filter)
        debug_print('do_device_database_backup - backup_file_search=', backup_file_search)
        backup_file_search = os.path.join(dest_dir, backup_file_search)
        debug_print('do_device_database_backup - backup_file_search=', backup_file_search)
        backup_files = glob.glob(backup_file_search)
        debug_print('do_device_database_backup - backup_files=', backup_files)
        debug_print('do_device_database_backup - backup_files=', backup_files[:len(backup_files) - copies_to_keep])
        debug_print('do_device_database_backup - len(backup_files) - copies_to_keep=', len(backup_files) - copies_to_keep)

        if len(backup_files) - copies_to_keep > 0:
            for filename in sorted(backup_files)[:len(backup_files) - copies_to_keep]:
                debug_print('do_device_database_backup - removing backup files:', filename)
                shutil.rmtree(filename, ignore_errors=True)

        debug_print('do_device_database_backup - Removing old backups - finished')
    else:
        debug_print('do_device_database_backup - Manually managing backups')

    notification(1, _("Sony device database backup finished"))
    return False


def do_store_locations(books_to_scan, options, notification=lambda x,y:x):
    '''
    Master job, to launch child jobs to modify each ePub
    '''
    debug_print("do_store_locations - start")
    server = Server()
    
    debug_print("do_store_locations - options=%s" % (options))
    # Queue all the jobs
#     args = ['calibre_plugins.sonyutilities.jobs', 'do_sonyutilities_all',
    args = ['calibre_plugins.sonyutilities.jobs', 'do_store_bookmarks',
            (books_to_scan, options)]
#    debug_print("do_store_locations - args=%s" % (args))
    debug_print("do_store_locations - len(books_to_scan)=%d" % (len(books_to_scan)))
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
            debug_print("do_store_locations - Job not finished")
            continue
#        debug_print("do_store_locations - Job finished")
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
    debug_print("do_store_locations - finished")
    # return the map as the job result
    return stored_locations, options

def do_store_current_bookmark(log, book_id, contentIDs, options):
    '''
    Child job, to store location for this book
    '''
    count_books = 0
    result      = None

    import sqlite3 
    with closing(sqlite3.connect(options["device_database_path"])) as connection:
        # return bytestrings if the content cannot be decoded as unicode
        connection.text_factory = lambda x: unicode(x, "utf-8", "ignore")

        cursor = connection.cursor()
        count_books += 1
        
        for contentID in contentIDs:
            log("store_current_bookmark - contentId='%s'" % (contentID))
            fetch_values = (contentID,)
            fetch_query = EPUB_FETCH_QUERY
            cursor.execute(fetch_query, fetch_values)
            result = cursor.fetchone()

        connection.commit()
        cursor.close()
    
    return result


def do_store_bookmarks(books, options):
    '''
    Child job, to store location for all the books
    '''
    CFI = re.compile(r'([\[\]:@~])')
    log = Log()

    func_name = sys._getframe().f_code.co_name
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
        
    def calculate_percent_read(book_path, bookmark):
        
        iterator     = EbookIterator(book_path)
        bookmark     = unicode(bookmark)
        bm           = iterator.convert_from_sony_bookmark(bookmark, title=u'calibre_current_page_bookmark')
        spine_num    = bm['spine']
        total_pages  = sum(iterator.pages)
        pages_before = sum(iterator.pages[:spine_num])
        
        import pydevd;pydevd.settrace()
        raw          = open(iterator.spine[spine_num]).read()
        html         = parse_html(raw, log=log)
        # we'll start from the <body> element, which is /2/4 in the EPUB CFI format
        pos          = bm['pos'].split('/')[3:]
        body         = xpath(html, '//h:body')[0]
        left,right   = walk_tree(body, pos)
        pages_before+= iterator.pages[spine_num] * left / (left+right)
        
        return 100.0 * pages_before / total_pages
    
    debug_print(func_name + " - start")
    count_books      = 0
    stored_locations = dict()
    clear_if_unread          = options[cfg.KEY_CLEAR_IF_UNREAD]
    store_if_more_recent     = options[cfg.KEY_STORE_IF_MORE_RECENT]
    do_not_store_if_reopened = options[cfg.KEY_DO_NOT_STORE_IF_REOPENED]

    import sqlite3
    with closing(sqlite3.connect(options["device_database_path"])) as connection:
        # return bytestrings if the content cannot be decoded as unicode
        connection.text_factory = lambda x: unicode(x, "utf-8", "ignore")
        connection.row_factory  = sqlite3.Row

        cursor = connection.cursor()
        count_books += 1

        debug_print(func_name + " - about to start book loop")
        for book in books:
            title   = book['title']
            authors = book['authors']
            contentIDs = book['contentIds']
            debug_print(func_name + " - Current book: %s - %s" %(title, authors))
            debug_print(func_name + " - contentIds='%s'" % (contentIDs))
            book_status = None
            for path_id,contentID in enumerate(contentIDs):
#                log("_store_bookmarks - contentId='%s'" % (contentID))
                debug_print(func_name + " - contentId='%s'" % (contentID))
                fetch_values = (contentID,)
                fetch_query = EPUB_FETCH_QUERY
                cursor.execute(fetch_query, fetch_values)
                
                # Take the status from the version that is farthest along
                for row in cursor:
                    if not book_status \
                    or row[b'reading_time'] > book_status[b'reading_time'] \
                    or row[b'percent'] > book_status[b'percent']:
                        book_status = dict(row)
                        if not row[b'percent']:
                            book_status[b'percent'] = calculate_percent_read(book['paths'][path_id],row[b'mark'])
            if not book_status:
                continue

            debug_print(func_name + " - book_status=", book_status)
            book_status['reading_time'] = convert_sony_date(book_status['reading_time'])
#             debug_print(func_name + " - last_read=", last_read)

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
                debug_print(func_name + " - reading_position_changed=", reading_position_changed)
                if store_if_more_recent:
                    if book['last_read'] and book_status['reading_time']:
                        debug_print(func_name + " - store_if_more_recent - current_last_read < last_read=", book['last_read'] < book_status['reading_time'])
                        reading_position_changed &= book['last_read'] < book_status['reading_time']
                    elif book_status['reading_time']:
                        reading_position_changed &= True
                if do_not_store_if_reopened:
                    debug_print(func_name + " - do_not_store_if_reopened - book.percentRead=", book['percentRead'])
                    reading_position_changed &= book['percentRead'] < 100

            if reading_position_changed:
                debug_print(func_name + " - position changed for: %s - %s" %(title, authors))
                stored_locations[book['id']] = book_status

        debug_print(func_name + " - finished book loop")
        connection.commit()
        cursor.close()
    
    debug_print(func_name + " - finished")
    return stored_locations


def _get_file_imageIds(image_path):
    imageids_files = {}
    if image_path:
        for path, dirs, files in os.walk(image_path):
#            debug_print("_get_file_imageIds - path=%s, dirs=%s" % (path, dirs))
#            debug_print("_get_file_imageIds - files=", files)
#            debug_print("_get_file_imageIds - len(files)=", len(files))
            for filename in files:
#                debug_print("_get_file_imageIds - filename=", filename)
                if filename.find(" - N3_") > 0:
#                    debug_print("check_covers - filename=%s" % (filename))
                    imageid = filename.split(" - N3_")[0]
                    imageids_files[imageid] = path
                    continue
                elif filename.find(" - AndroidBookLoadTablet_Aspect") > 0:
#                    debug_print("check_covers - filename=%s" % (filename))
                    imageid = filename.split(" - AndroidBookLoadTablet_Aspect")[0]
                    imageids_files[imageid] = path
                    continue
                else:
                    debug_print("_get_file_imageIds - path=%s" % (path))
                    debug_print("check_covers: not 'N3' file - filename=%s" % (filename))

#    imageids_files = set(imageids_files)
    return imageids_files

def _remove_extra_files(extra_imageids_files, imageids_files, delete_extra_covers, image_path, images_tree=False):
    extra_image_files = []
    from glob import glob
#    debug_print("_remove_extra_files - images_tree=%s" % (images_tree))
    for imageId in extra_imageids_files:
        image_path = imageids_files[imageId]
#        debug_print("_remove_extra_files - image_path=%s" % (image_path))
#        debug_print("_remove_extra_files - imageId=%s" % (imageId))
        for filename in glob(os.path.join(image_path, imageId + '*')):
#            debug_print("_remove_extra_files - filename=%s" % (filename))
            extra_image_files.append(os.path.basename(filename))
            if delete_extra_covers:
                os.unlink(filename)
        if images_tree and delete_extra_covers:
#            debug_print("_remove_extra_files - about to remove directory: image_path=%s" % image_path)
            try:
                os.removedirs(image_path)
                debug_print("_remove_extra_files - removed path=%s" % (image_path))
            except Exception as e:
                debug_print("_remove_extra_files - removed path exception=", e)

    return extra_image_files

def _get_imageId_set(device_database_path):
    import sqlite3 
    with closing(sqlite3.connect(device_database_path)) as connection:
        connection.text_factory = lambda x: unicode(x, "utf-8", "ignore")

        imageId_query = """SELECT DISTINCT ImageId
                        FROM content
                        """
        cursor = connection.cursor()

        imageIDs = []
        cursor.execute(imageId_query)
        for row in cursor:
            imageIDs.append(row[0])
#            debug_print("_get_imageid_set - row[0]='%s'" % (row[0]))
        connection.commit()

        cursor.close()

    return set(imageIDs)
