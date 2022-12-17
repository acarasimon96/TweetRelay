from typing import Tuple

from tweepy import __version__ as _tweepy_ver

_TWEEPY_VER_TUPLE: Tuple[int] = tuple(int(n) for n in _tweepy_ver.split(".", 3))


def tweepy_ver_before(required_version: str):
    major, minor, patch = (int(n) for n in required_version.split(".", 3))
    return _TWEEPY_VER_TUPLE[0] < major or (
        _TWEEPY_VER_TUPLE[0] == major
        and (
            _TWEEPY_VER_TUPLE[1] < minor
            or (_TWEEPY_VER_TUPLE[1] == minor and _TWEEPY_VER_TUPLE[2] < patch)
        )
    )
