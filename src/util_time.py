import re
import time


# Adds a specified number of seconds to a time_tuple
def add_seconds(value, seconds):
    return time.localtime(time.mktime(value) + seconds)


# Formats a time_tuple as a string.
def format_time(value):
    return "{year}-{month:02d}-{day:02d} {hours}:{minutes:02d}:{seconds:02d}".format(year=value[0], month=value[1], day=value[2], hours=value[3], minutes=value[4], seconds=value[5])


# Converts an ISO formatted date/time string like 2023-02-17T14:35:27 to a time in seconds.
def parse_time(value):
    result = 0

    m = re.search("(\d*)-(\d*)-(\d*)T(\d*):(\d*):(\d*)", value)
    if m:
        t = (
            int(m.group(1)), int(m.group(2)), int(m.group(3)),
            int(m.group(4)), int(m.group(5)), int(m.group(6)),
            -1, -1, -1,
        )

        result = time.mktime(t)

    return result

