import json
import logging
import socket
from typing import Optional
import psycopg2
from psycopg2.extensions import connection

"""
PostgreSQL Database接続生成クラス
"""


class PgDatabase(object):
    def __init__(self, configfile,
                 hostname: Optional[str] = None,
                 logger: Optional[logging.Logger] = None):
        self.logger = logger
        with open(configfile, 'r') as fp:
            db_conf = json.load(fp)
            if hostname is None:
                hostname = socket.gethostname()
            db_conf["host"] = db_conf["host"].format(hostname=hostname)
        # default connection is itarable curosr
        self.conn = psycopg2.connect(**db_conf)
        # Dictinaly-like cursor connection.
        # self.conn = psycopg2.connect(**dbconf, cursor_factory=psycopg2.extras.DictCursor)
        if self.logger is not None:
            self.logger.debug(self.conn)

    def get_connection(self) -> connection:
        return self.conn

    def rollback(self) -> None:
        if self.conn is not None:
            self.conn.rollback()

    def commit(self) -> None:
        if self.conn is not None:
            self.conn.commit()

    def close(self) -> None:
        if self.conn is not None:
            if self.logger is not None:
                self.logger.debug(f"Close {self.conn}")
            self.conn.close()
