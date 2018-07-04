import logging
import time
from pathlib import Path

import praw
import regex
import requests
from bs4 import BeautifulSoup
from praw.models import MoreComments

USER_AGENT = "python-script:wertpapierbot:0.0.1 (by /u/SebRut)"
COMMAND_PATTERN = r'^(?:!FUND: )'
WKN_PATTERN = regex.compile(COMMAND_PATTERN + r'((?:[A-Z]|\d){6})$', regex.MULTILINE)
ISIN_PATTERN = regex.compile(COMMAND_PATTERN + r'([A-Z]{2}\d{10})$', regex.MULTILINE)
DATA_URL = "https://www.etfinfo.com/de/product/"
FUND_INFO_STRING = """**{name}**

|||
---|----
ISIN | {isin}
WKN | {wkn}
Fondswährung | {currency}
Ausschüttend | {distributing}
TER inklusive Performance Fee | {ter_incl}
Fondsdomizil | {domicile}
Replikationsmethode | {replication_status}

> {desc}

***
"""
BOT_DISCLAIMER = """
"""

# TODO: load dynamically
PROCESSING_INTERVAL = 30
SUBMISSION_LIMIT = 25
PRODUCTION = False

# configure logging
handler = logging.StreamHandler()
handler.setLevel(logging.DEBUG)

formatter = logging.Formatter("[%(asctime)s](%(levelname)s) %(message)s", "%Y-%m-%d %H:%M:%S")
handler.setFormatter(formatter)

# add praw logger
praw_logger = logging.getLogger('prawcore')
praw_logger.setLevel(logging.WARN)
praw_logger.addHandler(handler)

# add self logger
logger = logging.getLogger("wertpapierbot")
if PRODUCTION:
    logger.setLevel(logging.INFO)
else:
    logger.setLevel(logging.DEBUG)
logger.addHandler(handler)

reddit = None
subreddit = None


def setup_reddit():
    global reddit
    global subreddit
    # authenticate against reddit api and obtain an Reddit instance and ref to finanzen subreddit
    # get configuration from praw.INI if existing else try getting data from env vars
    if Path("praw.INI").is_file():
        logger.info("Getting new reddit instance using data from praw.INI")
        reddit = praw.Reddit("wertpapierbot", user_agent=USER_AGENT)
    else:
        # TODO: read env vars
        if False:
            logger.info("Getting new reddit instance using data from environment variables")
            # TODO: set up reddit instance
            pass
        else:
            logger.error("No configuration found")
            exit(-1)
    # basic reddit instance checks
    if not reddit:
        logger.error("Reddit instance is not initialized")
        exit(-1)
    if reddit.read_only:
        logger.error("Reddit instance is read only")
        exit(-1)
    # get subreddit for processing
    subreddit = reddit.subreddit("finanzen")
    if not subreddit:
        logger.error("Subreddit instance is not initialized")
        exit(-1)


def get_fund_data(identifier):
    url = DATA_URL + identifier
    values = {}
    response = requests.get(url, headers={'Accept-Language ': 'de-DE', 'User-Agent': USER_AGENT},
                            cookies={'DisplayUniverse': 'DE-priv', 'PreferredLanguage': 'de', 'PrivacyPolicy': 'true',
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
    values['desc'] = soup.select("#product > div.grid-b.float-left > p:nth-of-type(1)")[0].text.strip()
    logger.debug("Fonds Description: %s", values['desc'])

    details_table_rows = soup.select("#product > div.grid-b.float-left > table:nth-of-type(3) > tr")
    if not details_table_rows:
        logger.warning("No details available while fetching %s", identifier)
        return
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


# handle a single submission including all comments
def handle_stock_requests(comment, matches):
    message = ""
    for match in matches:
        try:
            values = get_fund_data(match)
            if values:
                message = message + FUND_INFO_STRING.format(**values)
        except Exception as e:
            logger.error(
                "An error occurred while gathering funds data for \"%s\": %s", match, repr(e))
    message = message + BOT_DISCLAIMER
    # reply = reddit.comment(comment).reply(message)
    # logger.info("Replied to %s, reply id: %s", comment, reply.id)
    pass


def handle_submission(sub):
    submission = reddit.submission(id=sub)
    submission.comment_sort = "new"
    submission.comments.replace_more(limit=0)

    bot_replied = False
    comment_queue = submission.comments[:]

    while comment_queue:
        com = comment_queue.pop(0)
        logger.debug("Parsing comment %s", com.id)

        if not com.author:
            continue

        # add sub comments to queue
        comment_queue.extend(com.replies)

        # check if the comment is a top level comment and by the bot
        if not bot_replied and com.depth == 0 and com.author.name == "WertpapierBot":
            bot_replied = True

        com_body = com.body

        match_results = list()
        match_results.extend(WKN_PATTERN.findall(com_body))
        match_results.extend(ISIN_PATTERN.findall(com_body))
        if len(match_results) > 0:
            logger.debug("Stock ids found: %s", match_results)
            # TODO: check for existing bot reply
            responded = False
            for rep in com.replies:
                if isinstance(rep, MoreComments):
                    continue
                if rep.author.name == "WertpapierBot":
                    responded = True
                    break
            if not responded:
                handle_stock_requests(com, match_results)


def main_loop():
    logger.info("Main loop started")
    while True:
        # parse the last 25 submissions in /r/finanzen
        for sub in subreddit.new(limit=SUBMISSION_LIMIT):
            logger.debug("Parsing submission %s", sub)
            handle_submission(sub)
        time.sleep(PROCESSING_INTERVAL)


if __name__ == "__main__":
    setup_reddit()
    main_loop()
    # handle_stock_requests("abc", ["ETF110", "FR0010315770", "LU0468897110"])