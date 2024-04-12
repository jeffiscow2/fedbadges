from unittest.mock import patch

import pytest
from fedora_messaging.message import Message

import fedbadges.rules


class MockQuery:
    def __init__(self, returned_count):
        self.returned_count = returned_count

    def count(self):
        return self.returned_count


def test_malformed_criteria():
    """Test that an error is raised when nonsense is provided."""
    with pytest.raises(KeyError):
        fedbadges.rules.Criteria(
            dict(
                watwat="does not exist",
            )
        )


def test_underspecified_criteria():
    """Test that an error is raised when condition is missing."""
    with pytest.raises(ValueError):
        fedbadges.rules.Criteria(
            dict(
                datanommer={
                    "filter": {"topics": ["%(topic)s"], "wat": "baz"},
                    "operation": "count",
                }
            )
        )


def test_malformed_filter():
    """Test that an error is raised for malformed filters"""
    with pytest.raises(KeyError):
        fedbadges.rules.Criteria(
            dict(
                datanommer={
                    "filter": {"topics": ["%(topic)s"], "wat": "baz"},
                    "operation": "count",
                    "condition": {
                        "greater than or equal to": 500,
                    },
                }
            )
        )


@pytest.mark.parametrize(
    ["returned_count", "expectation"],
    [
        (499, False),
        (500, True),
        (501, True),
    ],
)
def test_basic_datanommer(returned_count, expectation):
    criteria = fedbadges.rules.Criteria(
        dict(
            datanommer={
                "filter": {
                    "topics": ["%(topic)s"],
                },
                "operation": "count",
                "condition": {
                    "greater than or equal to": 500,
                },
            }
        )
    )
    message = Message(
        topic="org.fedoraproject.dev.something.sometopic",
    )
    with patch("datanommer.models.Message.grep") as grep:
        grep.return_value = returned_count, 1, MockQuery(returned_count)
        result = criteria.matches(message)
        assert result == expectation
        grep.assert_called_once_with(
            topics=["org.fedoraproject.dev.something.sometopic"],
            defer=True,
        )


@pytest.mark.parametrize(
    ["returned_count", "expectation"],
    [
        (499, False),
        (500, True),
        (501, True),
    ],
)
def test_datanommer_with_lambda_condition(returned_count, expectation):
    criteria = fedbadges.rules.Criteria(
        dict(
            datanommer={
                "filter": {
                    "topics": ["%(topic)s"],
                },
                "operation": "count",
                "condition": {
                    "lambda": "value >= 500",
                },
            }
        )
    )
    message = Message(
        topic="org.fedoraproject.dev.something.sometopic",
    )
    with patch("datanommer.models.Message.grep") as f:
        f.return_value = returned_count, 1, MockQuery(returned_count)
        result = criteria.matches(message)
        assert result == expectation


@pytest.mark.parametrize(
    ["returned_count", "expectation"],
    [
        (4, False),
        (5, True),
        (6, False),
    ],
)
def test_datanommer_formatted_operations(returned_count, expectation):
    criteria = fedbadges.rules.Criteria(
        dict(
            datanommer={
                "filter": {
                    "topics": ["%(topic)s"],
                },
                "operation": {
                    "lambda": "query.count() == %(msg.some_value)s",
                },
                "condition": {
                    "lambda": "value",
                },
            }
        )
    )
    message = Message(
        topic="org.fedoraproject.dev.something.sometopic",
        body=dict(
            some_value=5,
        ),
    )
    with patch("datanommer.models.Message.grep") as grep:
        grep.return_value = returned_count, 1, MockQuery(returned_count)
        result = criteria.matches(message)
        assert result == expectation


@pytest.mark.parametrize(
    ["returned_count", "expectation"],
    [
        (499, False),
        (500, True),
        (501, True),
    ],
)
def test_datanommer_with_lambda_operation(returned_count, expectation):
    criteria = fedbadges.rules.Criteria(
        dict(
            datanommer={
                "filter": {
                    "topics": ["%(topic)s"],
                },
                "operation": {
                    "lambda": "query.count() - 5",
                },
                "condition": {
                    "lambda": "value >= 495",
                },
            }
        )
    )
    message = Message(
        topic="org.fedoraproject.dev.something.sometopic",
    )
    with patch("datanommer.models.Message.grep") as grep:
        grep.return_value = returned_count, 1, MockQuery(returned_count)
        result = criteria.matches(message)
        assert result == expectation


def test_datanommer_with_lambda_filter():
    criteria = fedbadges.rules.Criteria(
        dict(
            datanommer={
                "filter": {
                    "users": {
                        "lambda": "[u for u in set(['%(msg.commit.username)s', '%(msg.commit.agent)s'])"
                        " if not u in ['bodhi', 'oscar']]",
                    }
                },
                "operation": "count",
                "condition": {
                    "greater than or equal to": 0,
                },
            }
        )
    )

    # Here we use a real message so we can test fedmsg.meta integration
    message = Message(
        topic="org.fedoraproject.prod.trac.git.receive",
        body={
            "commit": {
                "username": "ralph",
                "stats": {
                    "files": {"README.rst": {"deletions": 0, "lines": 1, "insertions": 1}},
                    "total": {"deletions": 0, "files": 1, "insertions": 1, "lines": 1},
                },
                "name": "Ralph Bean",
                "rev": "24bcd20d08a68320f82951ce20959bc6a1a6e79c",
                "agent": "ralph",
                "summary": "Another commit to test fedorahosted fedmsg.",
                "repo": "moksha",
                "branch": "dev",
                "message": "Another commit to test fedorahosted fedmsg.\n",
                "email": "rbean@redhat.com",
            }
        },
    )
    returned_count = 0

    with patch("datanommer.models.Message.grep") as grep:
        grep.return_value = returned_count, 1, MockQuery(returned_count)
        result = criteria.matches(message)
        assert result is True
        grep.assert_called_once_with(users=["ralph"], defer=True)


def test_datanommer_with_dotted_filter():
    criteria = fedbadges.rules.Criteria(
        dict(
            datanommer={
                "filter": {
                    "users": [
                        "%(msg.commit.username)s",
                    ]
                },
                "operation": "count",
                "condition": {
                    "greater than or equal to": 0,
                },
            }
        )
    )

    # Here we use a real message so we can test fedmsg.meta integration
    message = Message(
        topic="org.fedoraproject.prod.trac.git.receive",
        body={
            "commit": {
                "username": "ralph",
                "stats": {
                    "files": {"README.rst": {"deletions": 0, "lines": 1, "insertions": 1}},
                    "total": {"deletions": 0, "files": 1, "insertions": 1, "lines": 1},
                },
                "name": "Ralph Bean",
                "rev": "24bcd20d08a68320f82951ce20959bc6a1a6e79c",
                "agent": "ralph",
                "summary": "Another commit to test fedorahosted fedmsg.",
                "repo": "moksha",
                "branch": "dev",
                "message": "Another commit to test fedorahosted fedmsg.\n",
                "email": "rbean@redhat.com",
            }
        },
    )
    returned_count = 0

    with patch("datanommer.models.Message.grep") as grep:
        grep.return_value = returned_count, 1, MockQuery(returned_count)
        result = criteria.matches(message)
        assert result is True
        grep.assert_called_once_with(users=["ralph"], defer=True)
