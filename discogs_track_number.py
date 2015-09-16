#!/usr/bin/python

import re
import sqlalchemy
from editing import MusicBrainzWebdriverClient
import discogs_client
import time
import Levenshtein
from utils import mangle_name, join_names, out, colored_out, bcolors, durationToMS, msToDuration, unaccent
import config as cfg

engine = sqlalchemy.create_engine(cfg.MB_DB)
db = engine.connect()
db.execute("SET search_path TO musicbrainz, %s" % cfg.BOT_SCHEMA_DB)

mb = MusicBrainzWebdriverClient(cfg.MB_USERNAME, cfg.MB_PASSWORD, cfg.MB_SITE)

discogs = discogs_client.Client('MusicBrainzBot/0.1 +https://github.com/murdos/musicbrainz-bot')

"""
CREATE TABLE bot_discogs_track_number (
    gid uuid NOT NULL,
    processed timestamp with time zone DEFAULT now(),
    CONSTRAINT bot_discogs_track_number_pkey PRIMARY KEY (gid)
);
"""

query = """
WITH
    vinyl_releases AS (
        SELECT DISTINCT r.id, u.url AS discogs_url
        FROM release r
            JOIN medium m ON m.release = r.id
            JOIN l_release_url l ON l.entity0 = r.id AND l.link IN (SELECT id FROM link WHERE link_type = 76)
            JOIN url u ON u.id = l.entity1
        WHERE m.format IN (7,8,29,30,31)
            /* Discogs link should only be linked to this release */
            AND NOT EXISTS (SELECT 1 FROM l_release_url WHERE l_release_url.entity1 = u.id AND l_release_url.entity0 <> r.id)
            /* this release should not have another Discogs link attached */
            AND NOT EXISTS (SELECT 1 FROM l_release_url WHERE l_release_url.entity0 = r.id AND l_release_url.entity1 <> u.id
                                    AND l_release_url.link IN (SELECT id FROM link WHERE link_type = 76))
            AND EXISTS (SELECT 1 FROM track t WHERE t.medium = m.id AND t.number ~ '^\d+$')
            AND l.edits_pending = 0
            AND r.edits_pending = 0
            AND m.edits_pending = 0
    )
SELECT r.id, r.gid, r.name, ra.discogs_url, ac.name AS ac_name, b.processed, SUM(m.track_count) AS track_count
FROM vinyl_releases ra
JOIN release r ON ra.id = r.id
JOIN medium m ON r.id = m.release
JOIN artist_credit ac ON r.artist_credit=ac.id
LEFT JOIN bot_discogs_track_number b ON r.gid = b.gid
GROUP BY r.artist_credit, r.id, r.gid, r.name, ra.discogs_url, ac.name, b.processed
ORDER BY b.processed NULLS FIRST, r.artist_credit, r.id
LIMIT 1000
"""

query_release_tracks = """
SELECT t.id, t.position, t.number, t.name, t.length, m.position AS medium_position
FROM track t
    JOIN medium m ON t.medium = m.id
WHERE m.release = %s
ORDER by m.position, t.position
"""

def are_similar(name1, name2):
    name1, name2 = (mangle_name(s) for s in (name1, name2))
    ratio = Levenshtein.jaro_winkler(name1, name2)
    # TODO: remove this debug print
    threshold = 0.75
    if ratio < threshold:
        print " * ratio = %s => name1 = '%s' vs name2 = '%s'" % (ratio, name1, name2)
    return ratio >= threshold

def discogs_get_tracklist(release_url):
    m = re.match(r'http://www.discogs.com/release/([0-9]+)', release_url)
    if m:
        release_id = int(m.group(1))
        release = discogs.release(release_id)
        return [track for track in release.tracklist if track.position != '']
    return None

for release in db.execute(query):
    colored_out(bcolors.OKBLUE, 'Looking up release "%s" by "%s" http://musicbrainz.org/release/%s' % (release['name'], release['ac_name'], release['gid']))

    discogs_tracks = discogs_get_tracklist(release['discogs_url'])
    if (len(discogs_tracks) != release['track_count']):
        colored_out(bcolors.FAIL, ' * number of tracks mismatches (Discogs: %s vs MB: %s)' % (len(discogs_tracks), release['track_count']))
    else:
        changed = False
        new_mediums = []
        position = 0
        for mb_track in db.execute(query_release_tracks, (release['id'],)):
            new_track = {'id': mb_track['id']}
            if len(new_mediums) < mb_track['medium_position']:
                new_mediums.append({'tracklist': []})
            new_mediums[-1]['tracklist'].append(new_track)

            discogs_track = discogs_tracks[position]
            if not are_similar(discogs_track.title, mb_track['name']):
                colored_out(bcolors.FAIL, ' * track #%s not similar enough' % discogs_track.position)
                changed = False
                break

            if discogs_track.position != mb_track['number'] \
                and re.match(r'^(AA\d?|[A-Z]+|[A-Z][\.-]?\d*)$', discogs_track.position) \
                and re.match(r'^\d+$', mb_track['number']):
                new_track['number'] = discogs_track.position
                changed = True

            # Also set length if it's not defined on MB
            if discogs_track.duration != "" and mb_track['length'] is None:
                new_track['length'] = discogs_track.duration
                changed = True
            position += 1

        if not changed:
            colored_out(bcolors.HEADER, ' * no changes found from %s' % release['discogs_url'])
        else:
            edit_note = 'Tracks number and/or length from attached Discogs link (%s)' % release['discogs_url']
            out(' * edit note: %s' % (edit_note,))
            mb.edit_release_tracklisting(release['gid'], new_mediums, edit_note, True)

    if release['processed'] is None:
        db.execute("INSERT INTO bot_discogs_track_number (gid) VALUES (%s)", (release['gid'],))
    else:
        db.execute("UPDATE bot_discogs_track_number SET processed = now() WHERE gid = %s", (release['gid'],))
