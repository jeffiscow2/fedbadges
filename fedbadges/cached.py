import logging

import pymemcache
import redis
from dogpile.cache import make_region
from dogpile.cache.proxy import ProxyBackend


log = logging.getLogger(__name__)
cache = make_region()

VERY_LONG_EXPIRATION_TIME = 86400 * 365  # a year


def configure(**kwargs):
    if not cache.is_configured:
        kwargs["wrap"] = [ErrorLoggingProxy]
        cache.configure(**kwargs)


class ErrorLoggingProxy(ProxyBackend):
    def set(self, key, value):
        try:
            self.proxied.set(key, value)
        except pymemcache.exceptions.MemcacheServerError:
            length = len(value)
            if length == 2:
                length = len(value[1])
            log.exception("Could not set the value in the cache (len=%s)", length)


def get_cached_messages_count(badge_id: str, candidate: str, get_previous_fn):
    key = f"messages_count|{badge_id}|{candidate}"
    try:
        current_value = cache.get_or_create(
            key,
            creator=lambda c: get_previous_fn(c) - 1,
            creator_args=((candidate,), {}),
            expiration_time=VERY_LONG_EXPIRATION_TIME,
        )
    except redis.exceptions.LockNotOwnedError:
        # This happens when the get_previous_fn() call lasted longer that the maximum redis lock
        # time. In this case, the value has been computed and stored in Redis, but dogpile just
        # failed to release the lock. Just try again, the value should be there already.
        log.debug(
            "Oops, getting the cached messages count of rule %s for user %s took too long for the "
            "cache lock. Retrying. It should be fast now.",
            badge_id,
            candidate,
        )
        return get_cached_messages_count(badge_id, candidate, get_previous_fn)

    # Add one (the current message), store it, return it
    new_value = current_value + 1
    cache.set(key, new_value)
    return new_value
