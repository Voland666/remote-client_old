#!/usr/bin/env python
# -*- coding: utf-8 -*-


class BaseObject(object):
    """
    Define basic behavior for all classes
    """

    def get(self, attribute_name, default_value=None):
        return getattr(self, attribute_name, default_value)

    def get_value(self, value, default_value):
        return value if value is not None else default_value

    def is_non_zero(self, value):
        return value is not None and len(value) > 0

    def escape_chars(self, chars, value):
        for char in chars:
            value = value.replace(char, '\\{}'.format(char))
        return value
