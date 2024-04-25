import datetime
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


class CachedDatanommerMessage:
    def __init__(self, message: Message):
        self.msg_id = (message.id,)
        self.topic = (message.topic,)
        self.timestamp = (datetime.datetime.now(tz=datetime.timezone.utc),)
        self.msg = (message.body,)
        self.headers = (message._properties.headers,)
        self.users = message.usernames
        self.packages = message.packages


class CachedDatanommerQuery:
    def __init__(self, result):
        self._result = result

    def all(self):
        return self._result


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

    def is_applicable(self, *args, **kwargs):
        raise NotImplementedError


class CachedDatanommerValue(CachedValue):

    def cache_kwargs(self):
        raise NotImplementedError

    def get(self, search_kwargs):
        return super().get(**self.cache_kwargs(search_kwargs))


class TopicAndUserQuery(CachedDatanommerValue):

    def cache_kwargs(self, search_kwargs):
        return dict(topic=search_kwargs["topics"][0], username=search_kwargs["users"][0])

    def compute(self, *, topic, username):
        total, _pages, messages = datanommer.models.Message.grep(topics=[topic], users=[username])
        return total, messages

    def is_applicable(self, search_kwargs, badge_dict):
        """Return whether we can use this cached value for this datanommer query"""
        return _query_has_single_arg(search_kwargs, ["topics", "users"])

    def on_message(self, message: Message):
        def _append_message(result):
            total, messages = result
            messages.append(CachedDatanommerMessage(message))
            return total + 1, messages

        for username in message.usernames:
            self._update_if_exists({"topic": message.topic, "username": username}, _append_message)


class TopicCount(TopicAndUserQuery):

    def compute(self, *, topic, username):
        total, pages, query = datanommer.models.Message.grep(
            topics=[topic], users=[username], defer=True
        )
        return total, None

    def is_applicable(self, search_kwargs, badge_dict):
        """Return whether we can use this cached value for this datanommer query"""
        if not super().is_applicable(search_kwargs, badge_dict):
            return False
        return badge_dict.get("operation") == "count"

    def on_message(self, message: Message):
        for username in message.usernames:
            self._update_if_exists(
                {"topic": message.topic, "username": username}, lambda v: (v[0] + 1, None)
            )


# class CachedBuildState(TopicAndUserQuery):
#
#     STATE = None
#
#     def compute(self, *, topic, username):
#         _total, _pages, messages = datanommer.models.Message.grep(
#             topics=[topic], users=[username]
#         )
#         return sum(1 for msg in messages if msg.msg["new"] == self.STATE)
#
#     def is_applicable(self, search_kwargs, badge_dict):
#         """Return whether we can use this cached value for this datanommer query"""
#         if not super().is_applicable(search_kwargs, badge_dict):
#             return False
#         topic = search_kwargs["topics"][0]
#         if not topic.endswith("buildsys.build.state.change"):
#             return False
#         if (
#             badge_dict.get("operation", {}).get("lambda")
#             != f"sum(1 for msg in query.all() if msg.msg['new'] == {self.STATE})"
#         ):
#             return False
#         return True
#
#     def on_message(self, message: Message):
#         if message.body["new"] != self.STATE:
#             return
#         for username in message.usernames:
#             self._update_if_exists(
#                 {"topic": message.topic, "username": username}, lambda v: v + 1
#             )
#         self._update_if_exists(self.cache_kwargs, lambda v: v + 1)
#
#
# class SuccessfulBuilds(CachedBuildState):
#
#     STATE = 1
#
#
# class FailedBuilds(CachedBuildState):
#
#     STATE = 3


# Most specific to less specific
DATANOMMER_CACHED_VALUES = (TopicCount, TopicAndUserQuery)
# All the cached values, datanommer and others (ok there aren't any others yet)
CACHED_VALUES = DATANOMMER_CACHED_VALUES


def on_message(msg: Message):
    for CachedValue in CACHED_VALUES:
        cached_value = CachedValue()
        cached_value.on_message(msg)
