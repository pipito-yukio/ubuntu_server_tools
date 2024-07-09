import os
from pathlib import Path
from datetime import datetime
import logging
import logging.config
import json

my_home = os.environ.get("HOME")
log_home = os.environ.get("PATH_SERVER_TOOLS_LOGS", "logs/servertools")

instance = None


def get_logger(name):
    global instance
    if instance is None:
        init()
        instance = object()
    return logging.getLogger(name)


def init():
    base_path = os.path.abspath(os.path.dirname(__file__))
    # print(base_path)
    logfile = os.path.join(base_path, "logconf_main.json")
    with open(logfile, "r") as fp:
        logconf = json.load(fp)
    # print(logconf)
    fmt_filename = logconf['handlers']['fileHandler']['filename']
    webapp_log_home = os.path.join(my_home, log_home)
    filename = fmt_filename.format(webapp_log_home)
    fullpath = os.path.expanduser(filename)
    logdir = Path(os.path.dirname(fullpath))
    if not logdir.exists():
        logdir.mkdir(parents=True)

    base, extention = os.path.splitext(fullpath)
    datepart = datetime.now().strftime("%Y%m%d%H%M")
    filename = "{}_{}{}".format(base, datepart, extention)
    # Override
    logconf['handlers']['fileHandler']['filename'] = filename
    logging.config.dictConfig(logconf)
