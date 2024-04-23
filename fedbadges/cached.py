import logging
from contextlib import suppress

import datanommer.models
from dogpile.cache import make_region
from dogpile.cache.api import NO_VALUE
from dogpile.cache.util import kwarg_function_key_generator
from fedora_messaging.message import Message


log = logging.getLogger(__name__)
cache = make_region()


class CachedValue:

    def __init__(self):
        self._key_generator = kwarg_function_key_generator(None, self.compute)

    def _get_key(self, **kwargs):
        return self._key_generator(**kwargs).replace(" ", "|")

    def get(self, **kwargs):
        key = self._get_key(**kwargs)
        return cache.get_or_create(key, creator=self.compute, creator_args=((), kwargs))

    def set(self, *, value, **kwargs):
        key = self._get_key(**kwargs)
        log.debug("Updating cached value %s with key %s", self.__class__.__name__, key)
        cache.set(key, value)

    def compute(self, **kwargs):
        raise NotImplementedError

    def on_message(self, message: Message):
        raise NotImplementedError


class TopicUserCount(CachedValue):

    def compute(self, *, topic, username):
        total, pages, query = datanommer.models.Message.grep(
            topics=[topic], users=[username], defer=True
        )
        return total

    def on_message(self, message: Message):
        for username in message.usernames:
            current_value = self.get(topic=message.topic, username=username)
            if current_value == NO_VALUE:
                continue  # Don't update the value if no one has ever requested it
            self.set(topic=message.topic, username=username, value=current_value + 1)

    @classmethod
    def is_applicable(cls, search_kwargs):
        """Return whether we can use this cached value for this datanommer query"""
        query_keys = set(search_kwargs.keys())
        with suppress(KeyError):
            query_keys.remove("rows_per_page")
        if query_keys != {"topics", "users"}:
            return False
        return len(search_kwargs["topics"]) == 1 and len(search_kwargs["users"]) == 1


def on_message(message: Message):
    TopicUserCount().on_message(message)
