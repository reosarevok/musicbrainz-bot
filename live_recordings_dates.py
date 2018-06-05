#!/usr/bin/python

import re
import sqlalchemy
from editing import MusicBrainzClient
import time
from utils import out, colored_out, bcolors
import config as cfg

engine = sqlalchemy.create_engine(cfg.MB_DB)
db = engine.connect()
db.execute("SET search_path TO musicbrainz, %s" % cfg.BOT_SCHEMA_DB)

mb = MusicBrainzClient(cfg.MB_USERNAME, cfg.MB_PASSWORD, cfg.MB_SITE)

"""
CREATE TABLE mbbot.bot_live_recordings_dates (
    gid uuid NOT NULL,
    processed timestamp with time zone DEFAULT now(),
    CONSTRAINT bot_live_recordings_dates_pkey PRIMARY KEY (gid)
);
"""

query = """
    SELECT DISTINCT r.id, r.gid AS r_gid, w.gid AS w_gid, r.name, r.comment, lrw.id AS rel_id, lt.id AS link_type, r.artist_credit, b.processed
    FROM recording r
        JOIN l_recording_work lrw ON lrw.entity0 = r.id
        JOIN link l ON l.id = lrw.link
        JOIN link_type lt ON l.link_type = lt.id
        JOIN link_attribute la ON la.link = l.id
        JOIN link_attribute_type lat ON la.attribute_type = lat.id AND lat.name = 'live'
        JOIN work w ON lrw.entity1 = w.id
        LEFT JOIN bot_live_recordings_dates b ON r.gid = b.gid
    WHERE r.comment ~ E'live, \\\\d{4}(-\\\\d{2})?(-\\\\d{2})?:?'
        AND l.begin_date_year IS NULL
        AND l.end_date_year IS NULL
        AND lt.name = 'performance'
        AND r.edits_pending = 0 AND lrw.edits_pending = 0
        /* Only one linked work */
        AND NOT EXISTS (SELECT 1 FROM l_recording_work lrw2 WHERE lrw2.entity0 = r.id AND lrw2.entity1 <> lrw.entity1)
    ORDER BY b.processed NULLS FIRST, r.artist_credit, r.id
    LIMIT 750
"""

date_re = re.compile(r'live, (\d{4})(?!-\d{4})(?:-(\d{2}))?(?:-(\d{2}))?:?', re.I)
for recording in db.execute(query):

    m = re.match(date_re, recording['comment'])
    if m is None:
        colored_out(bcolors.WARNING, 'Skipping https://musicbrainz.org/recording/%s "%s (%s)": not matching regexp' % (recording['r_gid'], recording['name'], recording['comment']))
    else:
        date = {'year': int(m.group(1))}

        if m.group(2) is not None:
            date['month'] = int(m.group(2))
        if m.group(3) is not None:
            date['day'] = int(m.group(3))

        colored_out(bcolors.OKBLUE, 'Setting performance relationships dates of https://musicbrainz.org/recording/%s "%s (%s)"' % (recording['r_gid'], recording['name'], recording['comment']))

        attributes = {}
        edit_note = 'Setting relationship dates from recording comment: "%s"' % recording['comment']
        colored_out(bcolors.NONE, " * new date:", date)

        entity0 = {'type': 'recording', 'gid': recording['r_gid']}
        entity1 = {'type': 'work', 'gid': recording['w_gid']}

        time.sleep(2)
        mb.edit_relationship(recording['rel_id'], entity0, entity1, recording['link_type'], attributes, date, date, edit_note, True)

    if recording['processed'] is None:
        db.execute("INSERT INTO bot_live_recordings_dates (gid) VALUES (%s)", (recording['r_gid'],))
    else:
        db.execute("UPDATE bot_live_recordings_dates SET processed = now() WHERE gid = %s", (recording['r_gid'],))
