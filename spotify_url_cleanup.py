# -*- coding: utf-8 -*-
import re
from optparse import OptionParser
from urlparse import urlparse, urlunparse

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
SELECT gid, url FROM musicbrainz.url
WHERE edits_pending = 0 AND (
    -- Badly formatted URLs 👎
    url SIMILAR TO 'http(s|)://(www.|)((open|play(|er)).|)spotify.com/(artist|album|track)/[a-zA-Z0-9]*%%'
    -- Well formatted URLs 👍
    AND url NOT SIMILAR TO 'https://open.spotify.com/(artist|album|track)/[a-zA-Z0-9]*'
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
    if entity_type == 'album' and len(parsed_url.path.split('/')) == 4:
        # E.g., "https://open.spotify.com/album/6P2k1pf9FrUjPqgiyPB6X1/2pIYXQg6z2ktVJPeyB74b1"
        url = urlunparse((
            parsed_url.scheme,
            parsed_url.netloc,
            '/'.join(parsed_url.path.split('/')[:3]),
            None, None, None
        ))
    try:
        entity = getattr(sp, entity_type)(url)
    except AttributeError:
        print '%s is not a valid Spotify entity type.' % (entity_type)
        return None
    except spotipy.client.SpotifyException as e:
        print 'Error looking up entity at Spotify: %s (for %s)' % (e, url)
        return None
    except Exception as e:
        print 'Some other error caught: %s' % (e)
        return None
    return entity['external_urls']['spotify']


def main(verbose = False):
    edit_note = """Fixing Spotify URL.

    Using `spotify_url_cleanup.py`: https://github.com/Freso/musicbrainz-bot/blob/master/spotify_url_cleanup.py"""
    urls = db.execute(query_bad_spotify_urls)
    if verbose:
        print u'Found %s URLs!' % (urls.rowcount)
    for url in urls:
        if verbose:
            print u'Working on url: %s' % (cfg.MB_SITE + u'/url/' + unicode(url['gid']))
        new_url = get_spotify_url(url['url'], verbose)
        if new_url is None:
            print 'Skipping %s.' % (url['url'])
            continue
        if verbose:
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
