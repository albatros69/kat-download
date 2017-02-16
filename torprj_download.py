#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import (unicode_literals, absolute_import, print_function, division)

from feedparser import parse
from urllib import quote
#from requests import get
from cfscrape import create_scraper
from ssl import SSLError
from xml.sax._exceptions import SAXParseException as ParseException
from ConfigParser import RawConfigParser
from argparse import ArgumentParser
#from datetime import datetime, timedelta
import arrow
from time import sleep
import logging, logging.handlers
import re, glob, os


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.handlers.SysLogHandler(facility=logging.handlers.SysLogHandler.LOG_USER, address='/dev/log')
formatter = logging.Formatter('%(module)s: %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)


def search_for_available_download(number, config, num_forced=False):
    # Search for files recently downloaded and that match the file pattern
    filepattern = re.compile(config['filepattern'].decode('string-escape'), re.IGNORECASE)
    tmp_num = 0
    for f in glob.glob(config['filepath']):
        m = filepattern.search(os.path.basename(f))
        if not num_forced and m and int(m.group('number')) >= number:
            #print('Fichier "%s" déjà téléchargé...' % (f, ))
            logger.info('%s : Fichier "%s" déjà téléchargé %s...' % (config['title'], os.path.basename(f), arrow.get(os.path.getmtime(f)).humanize(locale='fr_FR'), ) )
            tmp_num = max(tmp_num, int(m.group('number')))

    if tmp_num:
        n = tmp_num+1
    else:
        n = number

    if 'last_download' in config and config['last_download']:
        #lastdownload = datetime.strptime(config['last_download'], "%Y-%m-%d %H:%M:%S.%f")
        lastdownload = arrow.get(config['last_download'])
    else:
        #lastdownload = datetime.now() + timedelta(days=-4)
        lastdownload = arrow.now().replace(days=-4)

    if not num_forced and lastdownload > arrow.now().replace(days=-2):
        logger.info('%s : dernier téléchargement trop récent %s...' % (config['title'], lastdownload.humanize(locale='fr_FR'), ) )
        return n

    retries = 0
    scraper = create_scraper()
    while True:
        keywords = config['searchkeywords'] % { 'number': n }
        feed = parse(scraper.get('https://torrentproject.se/rss/%s/' % (quote(keywords), )).content)
        if feed.bozo:
            if isinstance(feed.bozo_exception, SSLError):
                logger.info("Recherche de l'épisode #%d de %s : SSLError" % (n, config['title']))
                if retries < 10:
                    retries += 1
                    sleep(2)
                    continue
                else:
                    break
            elif isinstance(feed.bozo_exception, ParseException):
                logger.info("Recherche de l'épisode #%d de %s : pas disponible..." % (n, config['title']))
                #print("Recherche de l'épisode #%d de %s : pas disponible..." % (n, config['title']))
                break
            else:
                logger.info("Recherche de l'épisode #%d de %s : erreur inconnue..." % (n, config['title']))
                break

        #print(feed.entries)
        for e in feed.entries:
            m = filepattern.search(e['title'])
            if m and int(m.group('number')) == n:
                logger.info("Épisode #%d de %s : démarrage du téléchargement..." % (n, config['title']))
                print("Épisode #%d de %s : démarrage du téléchargement..." % (n, config['title']))
                for url in [ a['href'] for a in e['links'] if a['type'] == 'application/x-bittorrent' ]:
                    with open(os.path.abspath(os.path.join(config['torrentdest'], os.path.basename(url))), 'w') as torrent:
                        torrent.write(scraper.get(url, stream=True).content)
                retries = 0; n += 1
                break
        else:
            logger.info("Recherche de l'épisode #%d de %s : pas disponible..." % (n, config['title']))
            #print("Recherche de l'épisode #%d de %s : pas disponible..." % (n, config['title']))
            break

        if num_forced:
            break

    return n


if __name__ == '__main__':

    Parser = ArgumentParser()
    Parser.add_argument("-n", "--number", dest="number", type=int, default=0,
                        help="Episode number to look for. Overrides configuration file.")
    Parser.add_argument("-c", "--config", dest="config", action="store", default='torprj_download.cfg',
                        help="Load configuration from this file (default: torprj_download.cfg).")
    Parser.add_argument("what", nargs='+', metavar="CONFIG_SECTION",
                        help="Sections of the configuration file where to get the download details.")
    Args = Parser.parse_args()

    Config = RawConfigParser(defaults= { 'number': 1 })
    Config.read(Args.config)
    chgt = False

    for w in Args.what:

        EpisodeNumber = Args.number
        num_forced = True
        if EpisodeNumber == 0:
            EpisodeNumber = Config.getint(w, 'number')
            num_forced = False
        if EpisodeNumber == 0:
            EpisodeNumber = 1
            num_forced = False

        n = search_for_available_download(EpisodeNumber, dict(Config.items(w)), num_forced)
        if not num_forced and n:
            Config.set(w, 'number', n)
        if not num_forced and n > EpisodeNumber:
            chgt = True
            Config.set(w, 'last_download', str(arrow.now()))

    if chgt:
        with open(Args.config, 'wb') as configfile:
            Config.write(configfile)

