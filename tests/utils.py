""" Utilities for tests """


def get_rule(rules, name):
    for rule in rules:
        if rule["name"] == name:
            return rule
