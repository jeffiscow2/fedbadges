#!/usr/bin/env python3

import json
import logging
from pathlib import Path

import click
import requests
from fedora_messaging import config as fm_config
from fedora_messaging import message as fm_message

from fedbadges.consumer import FedoraBadgesConsumer


class TestingConsumer(FedoraBadgesConsumer):
    def award_badge(self, username, badge_rule, link=None):
        print(f"Would award badge {badge_rule.badge_id} to {username} for {link or '?'}")


def _get_message_from_datagrepper(message_id, datagrepper_url):
    """Fetch a message by ID from Datagreeper"""
    url = f"{datagrepper_url}/v2/id?id={message_id}&is_raw=true"
    response = requests.get(url, timeout=5)
    try:
        response.raise_for_status()
    except requests.HTTPError as e:
        raise click.ClickException(f"Failed to retrieve message from Datagrepper: {e}") from e
    return response.json()


@click.command()
@click.option(
    "-c", "--config", type=click.Path(exists=True), help="Fedora Messaging configuration file"
)
@click.argument("message")
def main(config, message):
    fm_config.conf.load_config(config)
    fm_config.conf.setup_logging()
    logger = logging.getLogger("fedbadges")
    logger.setLevel(logging.DEBUG)
    consumer = TestingConsumer()
    consumer.loop.run_until_complete(consumer._refresh_badges_task.stop())
    consumer._reload_rules()

    if Path(message).exists():
        with open(message) as f:
            message_data = json.load(f)
    else:
        datagrepper_url = consumer.config["datagrepper_url"]
        message_data = _get_message_from_datagrepper(message, datagrepper_url)

    # Disable the topic prefix, the loaded message already has everything.
    fm_config.conf["topic_prefix"] = ""
    message = fm_message.load_message(message_data)
    consumer(message)


if __name__ == "__main__":
    main()
