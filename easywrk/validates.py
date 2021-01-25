# coding: utf8

import string

# 文件路径字符要禁用这些字符
BAN_CHAR_LIST = ('\\', '/', ':', '*', '?', '"', '<', '>', '|')

NAME_ALLOW_LIST = []

NAME_ALLOW_LIST.extend(string.ascii_letters)
NAME_ALLOW_LIST.extend(string.digits)
NAME_ALLOW_LIST.extend(('-', '_', '=', '(', ')', '[', ']', '.'))

def validate_name(name):
    for n in name:
        if n not in NAME_ALLOW_LIST:
            return False

    return True