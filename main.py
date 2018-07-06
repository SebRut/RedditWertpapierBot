import logging
import os
from pathlib import Path

import praw
import regex
import requests
from bs4 import BeautifulSoup
from praw.models import MoreComments

__version__ = "0.2.0"
USER_AGENT = "python-script:wertpapierbot:%s (by /u/SebRut)" % __version__
COMMAND_PATTERN = r'^(?:!FUND: )'
WKN_PATTERN = regex.compile(COMMAND_PATTERN + r'((?:[A-Z]|\d){6})$', regex.MULTILINE)
ISIN_PATTERN = regex.compile(COMMAND_PATTERN + r'([A-Z]{2}\d{10})$', regex.MULTILINE)
DATA_URL = "https://www.etfinfo.com/de/product/"
FUND_INFO_STRING = """**{name}** ({isin} / {wkn})

{currency} - {distributing} - TER {ter_incl} (inkl. Performance Fee) - {replication_status}

[Fonds bei etfinfo.com]({etfinfourl})

[Fonds bei justETF]({justetfurl})
***
"""
BOT_DISCLAIMER = """
Ich bin WertpapierBot. Mithilfe von \"!FUND: {WKN|ISIN}\" kannst du mich aufrufen. |
 WertpapierBot %s |
 [Feedback geben](https://www.reddit.com/message/compose/?to=SebRut&subject=WertpapierBot)
""" % __version__

PROCESSING_INTERVAL = os.getenv("RWB_PROCESSING_INTERVAL", 300)
SUBMISSION_LIMIT = os.getenv("RWB_SUBMISSION_LIMIT", 25)
RWB_DESCRIPTION_LIMIT = os.getenv("RWB_DESCRIPTION_LIMIT", 500)
PRODUCTION = 'RWB_PRODUCTION' in os.environ

# configure logging
handler = logging.StreamHandler()
handler.setLevel(logging.DEBUG)

formatter = logging.Formatter("[%(asctime)s](%(levelname)s) %(message)s", "%Y-%m-%d %H:%M:%S")
handler.setFormatter(formatter)

# add praw logger
praw_logger = logging.getLogger('prawcore')
if PRODUCTION:
    praw_logger.setLevel(logging.WARN)
else:
    praw_logger.setLevel(logging.INFO)
praw_logger.addHandler(handler)

# add self logger
logger = logging.getLogger("wertpapierbot")
if PRODUCTION:
    logger.setLevel(logging.INFO)
else:
    logger.setLevel(logging.DEBUG)
logger.addHandler(handler)

# add logging to log.txt
if PRODUCTION:
    fileHandler = logging.FileHandler("log.txt")
    fileHandler.setFormatter(formatter)
    fileHandler.setLevel(logging.INFO)
    logger.addHandler(fileHandler)


def get_fund_data(identifier):
    url = DATA_URL + identifier
    values = {'etfinfourl': url}
    response = requests.get(url, headers={'Accept-Language ': 'de-DE', 'User-Agent': USER_AGENT},
                            cookies={'DisplayUniverse': 'DE-priv', 'PreferredLanguage': 'de',
                                     'PrivacyPolicy': 'true',
                                     'DisclaimerAccepted': 'true'})
    if response.status_code != 200:
        logger.error("An error occurred while fetching %s: %s", url, response.status_code)
        return
    if response.text.count("Keine Fonds gefunden") > 0:
        logger.error("Funds with identifier \"%s\" not found", identifier)
        return

    soup = BeautifulSoup(response.text, 'html.parser')

    # get general information table
    general_table_rows = soup.select("#product > div.grid-b.float-left > table:nth-of-type(2) > tr")
    if not general_table_rows:
        general_table_rows = soup.select("#product > div.grid-b.float-left > table:nth-of-type(1) > tr")
        if not general_table_rows:
            logger.warning("No general information found while fetching %s", identifier)
            return
    values['name'] = general_table_rows[0].select_one("td.value-cell > a").text.strip()
    values['isin'] = general_table_rows[1].select_one("td.value-cell").text.strip()
    values['wkn'] = general_table_rows[2].select_one("td.value-cell").text.strip()
    logger.debug("Fonds Name: %s", values['name'])
    logger.debug("Fonds ISIN: %s", values['isin'])
    logger.debug("Fonds WKN: %s", values['wkn'])

    values['justetfurl'] = "https://www.justetf.com/de/etf-profile.html?groupField=index&isin=%s" % values['isin']

    values['desc'] = soup.select("#product > div.grid-b.float-left > p:nth-of-type(1)")[0].text.strip()
    logger.debug("Fonds Description: %s", values['desc'])

    details_table_rows = soup.select("#product > div.grid-b.float-left > table:nth-of-type(3) > tr")
    if not details_table_rows:
        logger.warning("No details available while fetching %s", identifier)
        return values
    values['currency'] = details_table_rows[2].select_one("td.value-cell").text.strip()
    values['distributing'] = details_table_rows[4].select_one("td.value-cell").text.strip()
    values['ter_incl'] = details_table_rows[10].select_one("td.value-cell").text.strip()
    values['domicile'] = details_table_rows[13].select_one("td.value-cell").text.strip()
    values['replication_status'] = details_table_rows[14].select_one("td.value-cell").text.strip()
    logger.debug("Fonds Currency: %s", values['currency'])
    logger.debug("Distributing: %s", values['distributing'])
    logger.debug("TER including Performance Fee: %s", values['ter_incl'])
    logger.debug("Fonds Domicile: %s", values['domicile'])
    logger.debug("Replication Status: %s", values['replication_status'])
    return values


class RedditWertpapierBot:
    def __init__(self):
        self.__reddit = None
        self.__subreddit = None

    def __setup_reddit(self):
        # authenticate against reddit api and obtain an Reddit instance and ref to finanzen subreddit
        # get configuration from praw.INI if existing else try getting data from env vars

        if not {"praw_client_id", "praw_client_secret", "praw_password", "praw_username"}.difference(os.environ):
            logger.info("Getting new reddit instance using data from environment variables")
            praw.Reddit(user_agent=USER_AGENT)
        elif Path("praw.ini").is_file():
            logger.info("Getting new reddit instance using data from praw.ini")
            self.__reddit = praw.Reddit("wertpapierbot", user_agent=USER_AGENT)
        else:
            logger.error("No configuration found")
            exit(-1)
        # basic reddit instance checks
        if not self.__reddit:
            logger.error("Reddit instance is not initialized")
            exit(-1)
        if self.__reddit.read_only:
            logger.error("Reddit instance is read only")
            exit(-1)
        # get subreddit for processing
        self.__subreddit = self.__reddit.subreddit("finanzen")
        if not self.__subreddit:
            logger.error("Subreddit instance is not initialized")
            exit(-1)

        self.__fullname = self.__reddit.user.me().fullname

    # handle a single submission including all comments
    def __handle_stock_requests(self, comment, matches):
        message = ""
        for match in matches:
            try:
                values = get_fund_data(match)
                if values:
                    message = message + FUND_INFO_STRING.format(**values)
            except Exception as e:
                logger.error(
                    "An error occurred while gathering funds data for \"%s\": %s", match, repr(e))
        if message:
            message = message + BOT_DISCLAIMER
            reply = self.__reddit.comment(comment).reply(message)
            logger.info("Replied to %s, reply id: %s", comment, reply.id)

    def __handle_comment(self, comment):
        if not comment.author:
            return

        com_body = comment.body

        match_results = list()
        match_results.extend(WKN_PATTERN.findall(com_body))
        match_results.extend(ISIN_PATTERN.findall(com_body))
        if match_results:
            logger.debug("Stock ids found: %s", match_results)
            responded = False
            comment.refresh()
            for rep in comment.replies:
                if isinstance(rep, MoreComments):
                    continue
                if rep.author.fullname == self.__fullname:
                    responded = True
                    break
            if not responded:
                self.__handle_stock_requests(comment, match_results)

    def __main_loop(self):
        logger.info("Main loop started")

        for comment in self.__subreddit.stream.comments():
            logger.debug("Parsing comment \"%s\"", comment)
            self.__handle_comment(comment)

    def start(self):
        self.__setup_reddit()
        self.__main_loop()


if __name__ == "__main__":
    if PRODUCTION:
        logger.info("Running in Production Mode...")
    else:
        logger.info("Running in Development Mode...")
    bot = RedditWertpapierBot()
    bot.start()
