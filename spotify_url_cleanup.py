# -*- coding: utf-8 -*-
import re
from optparse import OptionParser
from urlparse import urlparse

import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
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

sp = spotipy.Spotify(client_credentials_manager=SpotifyClientCredentials(
    client_id=cfg.SPOTIFY_CLIENT_ID,
    client_secret=cfg.SPOTIFY_CLIENT_SECRET))

query_bad_spotify_urls = '''
SELECT * FROM musicbrainz.url
WHERE edits_pending = 0 AND (
        url LIKE 'http://open.spotify.com/%%/%%'
     OR url LIKE 'http://play.spotify.com/%%/%%'
     OR url LIKE 'https://play.spotify.com/%%/%%'
)
ORDER BY id ASC
'''

browser = mechanize.Browser()
browser.set_handle_robots(False)
browser.set_debug_redirects(False)
browser.set_debug_http(False)


def get_spotify_url(url, verbose = False):
    """Clean up Spotify URL.

    Should take an input like
    > http://play.spotify.com/album/57t2ciLI9ACJQKi7LcbKxD?play=true&utm_source=open.spotify.com&utm_medium=open
    and return something like
    > https://open.spotify.com/album/57t2ciLI9ACJQKi7LcbKxD
    """

    parsed_url = urlparse(url)
    entity_type = parsed_url.path.split('/')[1]
    if verbose:
        print "parsed_url is", parsed_url
        print "entity_type is", entity_type
    try:
        entity = getattr(sp, entity_type)(url)
    except AttributeError:
        print '%s is not a valid Spotify entity type.' % (entity_type)
        return None
    except spotipy.client.SpotifyException as e:
        print 'Error looking up entity at Spotify: %s (for %s)' % (e, url)
        return None
    return entity['external_urls']['spotify']


def main(verbose = False):
    urls = db.execute(query_bad_spotify_urls)
    for url in urls:
        new_url = get_spotify_url(url['url'], verbose)
        if new_url is None:
            print 'Skipping %s.' % (url['url'])
            continue
        edit_note = """Fixing Spotify URL.

Using `spotify_url_cleanup.py`: https://github.com/Freso/musicbrainz-bot/blob/master/spotify_url_cleanup.py"""
        if verbose:
            print u'Working on url: %s' % (u'https://musicbrainz.org/url/' + url['gid'])
            print u'→ Changing %s to %s' % (url['url'], new_url)
        try:
            mb.edit_url(url['gid'], url['url'], new_url, edit_note, auto=False)
        except:
            continue


if __name__ == '__main__':
    parser = OptionParser()
    parser.add_option('-v', '--verbose', action='store_true', default=False,
            help='be more verbose')
    (options, args) = parser.parse_args()
    with PIDFile('/tmp/mbbot_clean_up_spotify_links.pid'):
        main(options.verbose)
