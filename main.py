import praw
import regex
import logging

USER_AGENT = "python-script:wertpapierbot:0.0.1 (by /u/SebRut)"
COMMAND_PATTERN = r'^(?:!WP: )'
WKN_PATTERN = regex.compile(COMMAND_PATTERN + r'((?:[A-Z]|\d){6})$', regex.MULTILINE)
ISIN_PATTERN = regex.compile(COMMAND_PATTERN + r'([A-Z]{2}\d{10})$', regex.MULTILINE)

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


# parse the last 25 submissions in /r/finanzen
for sub in finanzen_sub.new(limit=25):
    logger.debug("Parsing submission {}".format(sub))
    handle_submission(sub)
