import praw
import regex
import logging
import requests
from bs4 import BeautifulSoup

USER_AGENT = "python-script:wertpapierbot:0.0.1 (by /u/SebRut)"
COMMAND_PATTERN = r'^(?:!WP: )'
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

# configure logging
handler = logging.StreamHandler()
handler.setLevel(logging.DEBUG)

# add praw logger
praw_logger = logging.getLogger('prawcore')
praw_logger.setLevel(logging.WARN)
praw_logger.addHandler(handler)

# add self logger
logger = logging.getLogger("wertpapierbot")
logger.setLevel(logging.DEBUG)
logger.addHandler(handler)

# authenticate against reddit api and obtain an Reddit instance and ref to finanzen subreddit
reddit = praw.Reddit("wertpapierbot", user_agent=USER_AGENT)
finanzen_sub = reddit.subreddit("finanzen")


# handle a single submission including all comments
def handle_stock_request(comment, matches):
    message = ""
    for match in matches:
        url = DATA_URL + match
        values = {}
        response = requests.get(url, headers={'Accept-Language ': 'de-DE', 'User-Agent': USER_AGENT},
                                cookies={'DisplayUniverse': 'DE-priv', 'Preferredlanguage': 'de'})
        if response.status_code != 200:
            logger.error("An error occured while fetching {}: {}".format(url, response.status_code))
            continue
        soup = BeautifulSoup(response.text, 'html.parser')
        values['name'] = \
            soup.select(
                "#product > div.grid-b.float-left > table:nth-of-type(2) > tr:nth-of-type(1) > td.value-cell > a")[0] \
                .text.strip()
        logger.debug("Fonds Name: {}".format(values['name']))
        values['isin'] = \
            soup.select("#product > div.grid-b.float-left > table:nth-of-type(2) > tr:nth-of-type(2) > td.value-cell")[
                0] \
                .text.strip()
        logger.debug("Fonds ISIN: {}".format(values['isin']))
        values['wkn'] = \
            soup.select("#product > div.grid-b.float-left > table:nth-of-type(2) > tr:nth-of-type(3) > td.value-cell")[
                0] \
                .text.strip()
        logger.debug("Fonds WKN: {}".format(values['wkn']))
        values['desc'] = soup.select("#product > div.grid-b.float-left > p:nth-of-type(1)")[0].text.strip()
        logger.debug("Fonds Description: {}".format(values['desc']))
        values['currency'] = \
            soup.select("#product > div.grid-b.float-left > table:nth-of-type(3) > tr:nth-of-type(3) > td.value-cell")[
                0] \
                .text.strip()
        logger.debug("Fonds Currency: {}".format(values['currency']))
        values['distributing'] = \
            soup.select("#product > div.grid-b.float-left > table:nth-of-type(3) > tr:nth-of-type(5) > td.value-cell")[
                0] \
                .text.strip()
        logger.debug("Distributing: {}".format(values['distributing']))
        values['ter_incl'] = \
            soup.select("#product > div.grid-b.float-left > table:nth-of-type(3) > tr:nth-of-type(11) > td.value-cell")[
                0] \
                .text.strip()
        logger.debug("TER including Performance Fee: {}".format(values['ter_incl']))
        values['domicile'] = \
            soup.select("#product > div.grid-b.float-left > table:nth-of-type(3) > tr:nth-of-type(14) > td.value-cell")[
                0] \
                .text.strip()
        logger.debug("Fonds Domicile: {}".format(values['domicile']))
        values['replication_status'] = \
            soup.select("#product > div.grid-b.float-left > table:nth-of-type(3) > tr:nth-of-type(15) > td.value-cell")[
                0] \
                .text.strip()
        logger.debug("Replication Status: {}".format(values['replication_status']))
        message = message + FUND_INFO_STRING.format(**values)
    # TODO: append bot disclaimer
    # TODO: post
    pass



def handle_submission(sub):
    submission = reddit.submission(id=sub)
    submission.comment_sort = "new"
    submission.comments.replace_more(limit=0)

    bot_replied = False
    comment_queue = submission.comments[:]
    matching_comments = list()
    while comment_queue:
        com = comment_queue.pop(0)
        logger.debug("Parsing comment {}".format(com.id))

        # add sub comments to queue
        comment_queue.extend(com.replies)

        # check if the comment is a top level comment and by the bot
        if not bot_replied and com.author.name == "WertpapierBot" and com.depth == 1:
            bot_replied = True

        com_body = com.body

        match_results = list()
        match_results.append("ETF110")
        match_results.extend(WKN_PATTERN.findall(com_body))
        match_results.extend(ISIN_PATTERN.findall(com_body))
        logger.debug("Stock ids found: {}".format(match_results))
        if match_results:
            # TODO: check for existing bot reply
            handle_stock_request(com, match_results)


def handle_finanzen():
    # parse the last 25 submissions in /r/finanzen
    for sub in finanzen_sub.new(limit=25):
        logger.debug("Parsing submission {}".format(sub))
        handle_submission(sub)


# handle_finanzen()
handle_stock_request("abc", ["ETF110"])
