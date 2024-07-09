from dataclasses import dataclass

"""
テーブル用データクラス
"""


@dataclass(frozen=True)
class RegUnauthIpAddr:
    ip_addr: str
    reg_date: str


@dataclass(frozen=True)
class UnauthIpAddr:
    id: int
    ip_addr: str
    reg_date: str
    country_code: str
    dropped_date: str


@dataclass(frozen=True)
class SshAuthError:
    log_date: str
    ip_id: int
    appear_count: int
