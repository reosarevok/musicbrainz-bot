# -*- coding: utf-8 -*-
from optparse import OptionParser
from urlparse import urlparse
from urllib import unquote

import sqlalchemy
import mechanize

from editing import MusicBrainzClient
from mbbot.utils.pidfile import PIDFile
import config as cfg

engine = sqlalchemy.create_engine(cfg.MB_DB)
db = engine.connect()
db.execute('SET search_path TO musicbrainz')

mb = MusicBrainzClient(cfg.MB_USERNAME, cfg.MB_PASSWORD, cfg.MB_SITE)

https_domains = [
    '%.bandcamp.com',
    'music.monstercat.com',
    'open.spotify.com',
    'secondhandsongs.com',
]

query_http_urls = sqlalchemy.text('''
SELECT gid, url FROM musicbrainz.url
WHERE edits_pending = 0
    AND url SIMILAR TO 'http://({sites})/%'
LIMIT 200
'''.format(
    sites='|'.join(https_domains),
))

browser = mechanize.Browser()
browser.set_handle_robots(False)
browser.set_debug_redirects(False)
browser.set_debug_http(False)


def main(verbose = False):
    edit_note = """Converting HTTP URL to HTTPS.

    Using `httpsify_the_world.py`: https://github.com/Freso/musicbrainz-bot/blob/master/httpsify_the_world.py"""
    if verbose:
        print 'Finding URLs using SQL query:', query_http_urls
    urls = db.execute(query_http_urls)
    if verbose:
        print u'Found %s URLs!' % (urls.rowcount)
    for url in urls:
        if verbose:
            print u'[!!!] Working on url: %s' % (cfg.MB_SITE + u'/url/' + unicode(url['gid']))
        new_url = url['url'].replace('http://', 'https://', 1)
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
    parser.add_option('-v', '--verbose', action='store_true', default=False,
            help='be more verbose')
    (options, args) = parser.parse_args()
    with PIDFile('/tmp/mbbot_httpsify_the_world.pid'):
        main(options.verbose)
