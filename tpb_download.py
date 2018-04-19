#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import (unicode_literals, absolute_import, print_function, division)

from bs4 import BeautifulSoup
from urllib import quote
from client import DelugeClient
from cfscrape import create_scraper
from ConfigParser import RawConfigParser
from argparse import ArgumentParser
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

    client = DelugeClient()
    client.connect('localhost', 58846, '<name>', '<key>')

    retries = 0
    scraper = create_scraper()
    while True:
        keywords = config['searchkeywords'] % { 'number': n }
        try:
            page = scraper.get('https://thepiratebay.org/search/%s/0/99/0' % (quote(keywords), ))
        except Exception as e:
            logger.exception(e)
            break

        torrent_table = BeautifulSoup(page.text, 'lxml').find("table", id="searchResult")
        torrent_rows = torrent_table("tr") if torrent_table else []

        if len(torrent_rows)<2:
            logger.info("Recherche de l'épisode #%d de %s : pas disponible..." % (n, config['title']))
            #print("Recherche de l'épisode #%d de %s : pas disponible..." % (n, config['title']))
            break

        for r in torrent_rows[1:]:
            title = ' '.join(r.find(class_="detLink").stripped_strings)
            download_url = r.find(title="Download this torrent using magnet")["href"]
            m = filepattern.search(title)
            if m and int(m.group('number')) == n:
                logger.info("Épisode #%d de %s : démarrage du téléchargement..." % (n, config['title']))
                print("Épisode #%d de %s : démarrage du téléchargement..." % (n, config['title']))
                try:
                    client.core.add_torrent_magnet(download_url, {})
                except:
                    logger.info("Épisode #%d de %s : échec du téléchargement..." % (n, config['title']))
                    print("Épisode #%d de %s : échec du téléchargement..." % (n, config['title']))
                retries = 0; n += 1
                break
        else:
            logger.info("Recherche de l'épisode #%d de %s : pas disponible..." % (n, config['title']))
            #print("Recherche de l'épisode #%d de %s : pas disponible..." % (n, config['title']))
            break

        if num_forced:
            break

    client.disconnect()
    return n


if __name__ == '__main__':

    Parser = ArgumentParser()
    Parser.add_argument("-n", "--number", dest="number", type=int, default=0,
                        help="Episode number to look for. Overrides configuration file.")
    Parser.add_argument("-c", "--config", dest="config", action="store", default='tpb_download.cfg',
                        help="Load configuration from this file (default: tpb_download.cfg).")
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

