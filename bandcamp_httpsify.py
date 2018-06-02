# -*- coding: utf-8 -*-
import re
from optparse import OptionParser
from collections import defaultdict

import sqlalchemy
import mechanize

import editing
from editing import MusicBrainzClient
from utils import out
from mbbot.utils.pidfile import PIDFile
import config as cfg

engine = sqlalchemy.create_engine(cfg.MB_DB)
db = engine.connect()
db.execute('SET search_path TO musicbrainz')

mb = MusicBrainzClient(cfg.MB_USERNAME, cfg.MB_PASSWORD, cfg.MB_SITE)

query_bandcamp_urls_using_http = '''
SELECT * FROM musicbrainz.url
WHERE url LIKE 'http://%%bandcamp.com%%'
ORDER BY id ASC LIMIT 100
'''

browser = mechanize.Browser()
browser.set_handle_robots(False)
browser.set_debug_redirects(False)
browser.set_debug_http(False)


def main(verbose = False):
    urls = db.execute(query_bandcamp_urls_using_http)
    for url in urls:
        new_url = u'https' + url['url'][4:]
        edit_note = """Updating HTTP URL to HTTPS.

Using `bandcamp_httpsify.py`;
Source available at https://github.com/Freso/musicbrainz-bot/blob/master/bandcamp_httpsify.py"""
        if verbose:
            print u'Working on url: %s' % (url)
            print u'→ Changing %s to %s' % (url['url'], new_url)
        try:
            mb.edit_url(url['gid'], url['url'], new_url, edit_note, auto=True)
        except:
            continue


if __name__ == '__main__':
    parser = OptionParser()
    parser.add_option('-v', '--verbose', action='store_true', default=False,
            help='be more verbose')
    (options, args) = parser.parse_args()
    with PIDFile('/tmp/mbbot_httpsify_bandcamp_links.pid'):
        main(options.verbose)
