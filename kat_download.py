#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import (unicode_literals, absolute_import, print_function, division)

from feedparser import parse
from urllib import quote
from ssl import SSLError
from xml.sax._exceptions import SAXParseException as ParseException
from ConfigParser import RawConfigParser
from argparse import ArgumentParser
from datetime import datetime, timedelta
from time import sleep
import logging, logging.handlers
import re, glob, os


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.handlers.SysLogHandler(facility=logging.handlers.SysLogHandler.LOG_USER, address='/dev/log')
formatter = logging.Formatter('%(module)s: %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)


def search_for_available_download(number, config):
    filepattern = re.compile(config['filepattern'].decode('string-escape'))

    # Search for files recently downloaded and that match the file pattern
    for f in glob.glob(config['filepath']):
        m = filepattern.search(os.path.basename(f))
        if m and int(m.group('number'))+1 >= number and \
           datetime.fromtimestamp(os.path.getmtime(f)) > datetime.now() + timedelta(days=-2):
            #print('File "%s" too recent...' % (f, ))
            logger.info('File "%s" too recent...' % (os.path.basename(f), ))
            return number

    n = number
    retries = 0
    while True:
        keywords = config['searchkeywords'] % { 'number': n }
        feed = parse('https://kat.cr/usearch/%s/?rss=1' % (quote(keywords), ))
        if feed.bozo:
            if isinstance(feed.bozo_exception, SSLError):
                logger.info("Searching for episode #%d of %s: SSLError" % (n, config['title']))
                if retries < 10:
                    retries += 1
                    sleep(2)
                    continue
                else:
                    break
            elif isinstance(feed.bozo_exception, ParseException):
                logger.info("Searching for episode #%d of %s: not available..." % (n, config['title']))
                #print("Recherche de l'épisode #%d de %s : pas disponible..." % (n, config['title']))
                break
            else:
                logger.info("Searching for episode #%d of %s: unknown error..." % (n, config['title']))
                break

        #print(feed.entries)
        for e in feed.entries:
            m = filepattern.search(e['title'])
            if m and int(m.group('number')) == n:
                logger.info("Searching for episode #%d of %s : download starting..." % (n, config['title']))
                print("Searching for episode #%d of %s : download starting..." % (n, config['title']))
                with open(os.path.abspath(os.path.join(config['torrentdest'], os.path.basename(e['torrent_filename']))), 'w') as torrent:
                    torrent.write("d10:magnet-uri%d:%se" % (len(e['torrent_magneturi']), e['torrent_magneturi']))
                retries = 0; n += 1
                break
        else:
            logger.info("Searching episode #%d of %s : not available..." % (n, config['title']))
            #print("Recherche de l'épisode #%d de %s : pas disponible..." % (n, config['title']))
            break

    return n


if __name__ == '__main__':

    Parser = ArgumentParser()
    Parser.add_argument("-n", "--number", dest="number", type=int, default=0,
                        help="Episode number to look for. Overrides configuration file.")
    Parser.add_argument("-c", "--config", dest="config", action="store", default='kat_download.cfg',
                        help="Load configuration from this file (default: kat_download.cfg).")
    Parser.add_argument("what", nargs='+', metavar="CONFIG_SECTION",
                        help="Sections of the configuration file where to get the download details.")
    Args = Parser.parse_args()

    Config = RawConfigParser(defaults= { 'number': 1 })
    Config.read(Args.config)

    for w in Args.what:

        EpisodeNumber = Args.number
        if EpisodeNumber == 0:
            EpisodeNumber = Config.getint(w, 'number')
        if EpisodeNumber == 0:
            EpisodeNumber = 1

        n = search_for_available_download(EpisodeNumber, dict(Config.items(w)))
        if n:
            Config.set(w, 'number', n)

    with open(Args.config, 'wb') as configfile:
        Config.write(configfile)



