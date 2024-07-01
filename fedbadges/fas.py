""" Utilities for fedbadges that don't quite fit anywhere else. """

# These are here just so they're available in globals()
# for compiling lambda expressions
import logging
import re
import sys
import traceback

import backoff
import fasjson_client


log = logging.getLogger(__name__)


def _fasjson_backoff_hdlr(details):
    log.warning(f"FASJSON call failed. Retrying. {traceback.format_tb(sys.exc_info()[2])}")


class FASProxy:

    def __init__(self, url: str):
        self._url = url
        self._client = self._build_client()

    def _build_client(self):
        return fasjson_client.Client(self._url)

    def user_exists(self, user: str):
        """Return true if the user exists in FAS."""
        return self.get_user(user) is not None

    @backoff.on_exception(
        backoff.expo,
        (ConnectionError, TimeoutError),
        max_tries=3,
        on_backoff=_fasjson_backoff_hdlr,
    )
    def get_user(self, username: str):
        """Return the user in FAS."""
        try:
            return self._client.get_user(username=username).result
        except fasjson_client.errors.APIError as e:
            if e.code == 404:
                return None
            raise

    @backoff.on_exception(
        backoff.expo,
        (ConnectionError, TimeoutError),
        max_tries=3,
        on_backoff=_fasjson_backoff_hdlr,
    )
    def search_user(self, **search_args):
        try:
            result = self._client.search(**search_args).result
        except fasjson_client.errors.APIError as e:
            if e.code == 404:
                return None
            raise
        if not result:
            return None
        return result[0]

    def search_ircnick(self, nick):
        """Return the username corresponding to the IRC/matrix nickname in FAS."""
        if ":/" in nick:
            possible_nicks = [nick]
        else:
            possible_nicks = [f"matrix:/{nick}", f"irc:/{nick}"]
        for pnick in possible_nicks:
            user = self.search_user(ircnick=pnick)
            if user is not None:
                return user["username"]
        # Not found, return None
        return None

    def search_email(self, email):
        """Return the user with the specified email in FAS."""
        if email.endswith("@fedoraproject.org"):
            return email.rsplit("@", 1)[0]

        result = self.search_user(email=email)
        if not result:
            return None
        return result[0]["username"]

    def search_github(self, uri):
        m = re.search(r"^https?://api.github.com/users/([a-z][a-z0-9-]+)$", uri)
        if not m:
            log.warning("Can't extract the username from %r", uri)
            return None
        github_username = m.group(1)
        result = self.search_user(github_username__exact=github_username)
        if not result:
            return None
        return result[0]["username"]


# Match OpenID agent strings, i.e. http://FAS.id.fedoraproject.org
def openid2fas(openid, config):
    id_provider_hostname = re.escape(config["id_provider_hostname"])
    m = re.search(f"^https?://([a-z][a-z0-9]+)\\.{id_provider_hostname}$", openid)
    if m:
        return m.group(1)
    return openid


def distgit2fas(uri, config):
    distgit_hostname = re.escape(config["distgit_hostname"])
    m = re.search(f"^https?://{distgit_hostname}/user/([a-z][a-z0-9]+)$", uri)
    if m:
        return m.group(1)
    return uri


def krb2fas(name):
    if "/" not in name:
        return name
    return name.split("/")[0]
