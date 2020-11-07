# -*- coding: utf-8 -*-
from optparse import OptionParser

import sqlalchemy
import mechanize

from editing import MusicBrainzClient
from mbbot.utils.pidfile import PIDFile
import config as cfg

engine = sqlalchemy.create_engine(cfg.MB_DB)
db = engine.connect()
db.execute('SET search_path TO musicbrainz')

mb = MusicBrainzClient(cfg.MB_USERNAME, cfg.MB_PASSWORD, cfg.MB_SITE)

query_http_urls = sqlalchemy.text('''
SELECT gid, url FROM musicbrainz.url
WHERE edits_pending = 0
    AND url LIKE 'http://www.secondhandsongs.com/%'
LIMIT 1000
''')

browser = mechanize.Browser()
browser.set_handle_robots(False)
browser.set_debug_redirects(False)
browser.set_debug_http(False)


def main(verbose = False):
    edit_note = """Updating SecondHandSongs HTTP URLs to HTTPS and dropping "www", as per SecondHandSongs' own redirects. See https://tickets.metabrainz.org/browse/MBBE-6"""
    if verbose:
        print 'Finding URLs using SQL query:', query_http_urls
    urls = db.execute(query_http_urls)
    if verbose:
        print u'Found %s URLs!' % (urls.rowcount)
    for url in urls:
        if verbose:
            print u'[!!!] Working on url: %s' % (cfg.MB_SITE + u'/url/' + unicode(url['gid']))
        new_url = url['url'].replace('http://www.', 'https://', 1)
        if new_url is None:
            print 'Skipping %s.' % (url['url'])
            continue
        if verbose:
            print u'Changing %s to %s' % (url['url'], new_url)
        try:
            mb.edit_url(url['gid'], url['url'], new_url, edit_note, auto=False)
        except:
            continue


if __name__ == '__main__':
    parser = OptionParser()
    parser.add_option('-v', '--verbose', action='store_true', default=True,
            help='be more verbose')
    (options, args) = parser.parse_args()
    with PIDFile('/tmp/mbbot_httpsify_secondhandsongs.pid'):
        main(options.verbose)
