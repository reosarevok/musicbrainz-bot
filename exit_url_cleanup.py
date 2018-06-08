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

exit_url_query_sites = [
    'vk.com/away.php',
    'exit.sc/',
    'facebook.com/(l|confirmemail|login).php',
    '(encrypted.|)google.(at|be|ca|ch|co.(bw|il|uk)|com(|.(ar|au|br|eg|tr|tw))|cl|de|dk|es|fr|nl|pl|se)/url',
    'l.instagram.com/',
    'youtube.com/redirect',
    'linkedin.com/authwall',
    'mora.jp/cart',
]

exit_url_query_params = [
    'to',  # used by vk.com/away.php
    'url',  # used by exit.sc/ and google.*/url
    'u',  # used by facebook.com/l.php and l.instagram.com/
    'next',  # used by facebook.com/(confirmemail|login).php
    'q',  # used by youtube.com/redirect
    'sessionRedirect',  # used by linkedin.com/authwall
    'returnUrl',  # used by mora.jp/cart
]

query_exit_urls = sqlalchemy.text('''
SELECT * FROM musicbrainz.url
WHERE edits_pending = 0
    AND url SIMILAR TO 'http(s|)://(www.|)({sites})\?%({params})=http(s|)%\%3A\%2F\%2F%'
'''.format(
    sites='|'.join(exit_url_query_sites),
    params='|'.join(exit_url_query_params),
))

browser = mechanize.Browser()
browser.set_handle_robots(False)
browser.set_debug_redirects(False)
browser.set_debug_http(False)


def get_target_url(url, verbose=False):
    """Get target URL from exit page parameters

    Should take an input like
    > https://exit.sc/?url=https%3A%2F%2Fopen.spotify.com%2Fartist%2F3tEV3J5gW5BDMrJqE3NaBy%3Fsi%3D1mLk6MZSRGuol8rgwCe_Cg
    and return something like
    > https://open.spotify.com/album/57t2ciLI9ACJQKi7LcbKxD
    """

    clean_urls = []
    for param in urlparse(url).query.split('&'):
        split_param = param.split('=')
        if len(split_param) == 2 and 'http' == split_param[1][:4]:
            clean_urls += [unquote(split_param[1])]
    if len(clean_urls) == 1:
        if verbose:
            print "Found one URL contained inside this URL:", clean_urls[0]
        return clean_urls[0]
    elif len(clean_urls) == 0:
        if verbose:
            print "Found no URLs contained inside this URL."
        return None
    else:
        if verbose:
            print "Found more than one URLs(!):", clean_urls
        return None


def main(verbose = False):
    edit_note = """Cleaning exit URL.

    Using `exit_url_cleanup.py`: https://github.com/Freso/musicbrainz-bot/blob/master/exit_url_cleanup.py"""
    if verbose:
        print 'Finding URLs using SQL query:', query_exit_urls
    urls = db.execute(query_exit_urls)
    if verbose:
        print u'Found %s URLs!' % (urls.rowcount)
    for url in urls:
        if verbose:
            print u'[!!!] Working on url: %s' % (cfg.MB_SITE + u'/url/' + unicode(url['gid']))
        new_url = get_target_url(url['url'], verbose)
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
    with PIDFile('/tmp/mbbot_clean_up_exit_urls.pid'):
        main(options.verbose)
