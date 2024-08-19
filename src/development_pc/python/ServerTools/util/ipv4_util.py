from ipaddress import (
    ip_address, summarize_address_range,
    IPv4Address, IPv4Network
)
import typing
from typing import List, Iterator, Optional, Tuple

"""
IPv4アドレス操作関数ユーティリティ
"""


@typing.no_type_check
# Suppress: Incompatible types in assignment (expression has type
#  "IPv4Address | IPv6Address", variable has type "IPv4Address")  [assignment]
#  See: https://mypy.readthedocs.io/en/stable/
#     type_inference_and_annotations.html#type-ignore-error-codes
def get_cidr_cc_list(ip_start: str,
                     ip_count: int,
                     country_code: str) -> List[Tuple[IPv4Network, str]]:
    # mypy check error IPv?Address to Any.
    # IP address: IPv6Address | IPv4Address
    addr_first: IPv4Address = ip_address(ip_start)
    # Broadcast address
    addr_last: IPv4Address = addr_first + ip_count - 1
    cidr_ite: Iterator[IPv4Network] = summarize_address_range(addr_first, addr_last)
    return [(cidr, country_code) for cidr in cidr_ite]


@typing.no_type_check
def detect_cc_in_cidr_cc_list(
        target_ip: str,
        cidr_cc_list: List[Tuple[IPv4Network, str]]
        ) -> Tuple[Optional[str], Optional[str]]:
    target_ip_addr: IPv4Address = ip_address(target_ip)
    match_network: Optional[str] = None
    match_cc: Optional[str] = None
    for cidr_cc in cidr_cc_list:
        if target_ip_addr in cidr_cc[0]:
            match_network = str(cidr_cc[0])
            match_cc = cidr_cc[1]
            break

    return match_network, match_cc
