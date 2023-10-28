import time
import util_time


def log(message):
    print("{time}: {msg}".format(time=util_time.format_time(time.localtime()), msg=message))
