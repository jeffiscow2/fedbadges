import logging
from contextlib import suppress

import datanommer.models
from dogpile.cache import make_region
from dogpile.cache.api import NO_VALUE
from dogpile.cache.util import kwarg_function_key_generator
from fedora_messaging.message import Message


log = logging.getLogger(__name__)
cache = make_region()


def _query_has_single_arg(search_kwargs, required_kwargs):
    query_keys = set(search_kwargs.keys())
    with suppress(KeyError):
        query_keys.remove("rows_per_page")
    if query_keys != set(required_kwargs):
        return False
    return all(len(search_kwargs[arg]) == 1 for arg in required_kwargs)


class CachedValue:

    def __init__(self):
        self._key_generator = kwarg_function_key_generator(self.__class__.__name__, self.compute)

    def _get_key(self, **kwargs):
        return self._key_generator(**kwargs).replace(" ", "|")

    def get(self, **kwargs):
        key = self._get_key(**kwargs)
        return cache.get_or_create(key, creator=self.compute, creator_args=((), kwargs))

    def compute(self, **kwargs):
        raise NotImplementedError

    def on_message(self, message: Message):
        raise NotImplementedError

    def _update_if_exists(self, cache_kwargs: dict, update_fn):
        key = self._get_key(**cache_kwargs)
        current_value = cache.get(key)
        if current_value == NO_VALUE:
            return  # Don't update the value if no one has ever requested it
        cache.set(key, update_fn(current_value))

    def is_applicable(cls, *args, **kwargs):
        raise NotImplementedError


class CachedDatanommerQuery(CachedValue):
    def __init__(self, search_kwargs):
        super().__init__()
        self._search_kwargs = search_kwargs

    @property
    def cache_kwargs(self):
        raise NotImplementedError

    def get(self):
        return super().get(**self.cache_kwargs)


class TopicCount(CachedDatanommerQuery):

    @property
    def cache_kwargs(self):
        return dict(
            topic=self._search_kwargs["topics"][0], username=self._search_kwargs["users"][0]
        )

    def compute(self, *, topic, username):
        total, pages, query = datanommer.models.Message.grep(
            topics=[topic], users=[username], defer=True
        )
        return total

    def is_applicable(self, badge_dict):
        """Return whether we can use this cached value for this datanommer query"""
        if badge_dict.get("operation") != "count":
            return False
        return _query_has_single_arg(self._search_kwargs, ["topics", "users"])

    def on_message(self, message: Message):
        self._update_if_exists(self.cache_kwargs, lambda v: v + 1)


class CachedBuildState(CachedDatanommerQuery):

    STATE = None

    @property
    def cache_kwargs(self):
        return dict(
            topic=self._search_kwargs["topics"][0], username=self._search_kwargs["users"][0]
        )

    def compute(self, *, topic, username):
        _total, _pages, messages = datanommer.models.Message.grep(topics=[topic], users=[username])
        return sum(1 for msg in messages if msg.msg["new"] == self.STATE)

    def is_applicable(self, badge_dict):
        """Return whether we can use this cached value for this datanommer query"""
        try:
            topic = self._search_kwargs["topics"][0]
        except (KeyError, IndexError):
            return False
        if not topic.endswith("buildsys.build.state.change"):
            return False
        if (
            badge_dict.get("operation", {}).get("lambda")
            != f"sum(1 for msg in query.all() if msg.msg['new'] == {self.STATE})"
        ):
            return False
        return _query_has_single_arg(self._search_kwargs, ["topics", "users"])

    def on_message(self, message: Message):
        if message.body["new"] != self.STATE:
            return
        self._update_if_exists(self.cache_kwargs, lambda v: v + 1)


class SuccessfulBuilds(CachedBuildState):

    STATE = 1


class FailedBuilds(CachedBuildState):

    STATE = 3
