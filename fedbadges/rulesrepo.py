import datetime
import logging
import os

import yaml

import fedbadges.rules


log = logging.getLogger(__name__)


class RulesRepo:

    def __init__(self, config, directory):
        self.config = config
        self.directory = os.path.abspath(self.config["badges_directory"])
        self._last_load = None
        self.rules = []

    def load_all(self, tahrir_client, force=False):
        if force or self._needs_update():
            self.rules = self._load_all(tahrir_client)
        return self.rules

    def _load_all(self, tahrir_client):
        # badges indexed by trigger
        badges = []
        log.info("Looking in %r to load badge definitions" % self.directory)
        for root, _dirs, files in os.walk(self.directory):
            for partial_fname in files:
                fname = root + "/" + partial_fname
                badge = self._load_badge_from_yaml(fname)

                if not badge:
                    continue

                try:
                    badge_rule = fedbadges.rules.BadgeRule(
                        badge, tahrir_client, self.issuer_id, self.config, self.fasjson
                    )
                    badge_rule.setup()
                    badges.append(badge_rule)
                except ValueError as e:
                    log.error("Initializing rule for %r failed with %r", fname, e)

        log.info("Loaded %i total badge definitions" % len(badges))
        self._last_rules_load = datetime.datetime.now()
        return badges

    def _load_badge_from_yaml(self, fname):
        log.debug("Loading %r" % fname)
        try:
            with open(fname) as f:
                return yaml.safe_load(f.read())
        except Exception as e:
            log.error("Loading %r failed with %r", fname, e)
            return None

    def _needs_update(self):
        # Run "git -C directory log -1 --pretty=format:%aI"
        # Deserialize it with datetime.datetime.fromisoformat()
        # Compare with self._last_rules_load
        pass
