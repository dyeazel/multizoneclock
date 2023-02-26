# SPDX-FileCopyrightText: 2023 Dean A Yeazel
#
# SPDX-License-Identifier: MIT

# Big Board
# Runs on Airlift Metro M4 with 64x32 RGB Matrix display & shield

# general reference: https://learn.adafruit.com/adafruit-matrixportal-m4/matrixportal-library-overview

import json
import time
import board
import busio
import displayio
import re
import terminalio
from adafruit_display_shapes.rect import Rect
from adafruit_display_text.label import Label
from adafruit_bitmap_font import bitmap_font
from adafruit_matrixportal.network import Network
from adafruit_matrixportal.matrix import Matrix
import adafruit_requests as requests

BLINK = True
DEBUG = False
SHOW_AM_PM = False
next_update = 0

class ZoneInfo():
    def __init__(self):
        self.utc_offset_sec = 0
        self.is_utc = False
        self.tz_name = ""
        self.tz_abbr = ""
        self.latitude = 0.0
        self.longitude = 0.0
        self.sunrise = 0
        self.sunset = 0

class ClockLine():
    def __init__(self, clock_font):
        self.clock_label = Label(clock_font)
        self.zone_label = Label(terminalio.FONT)

clock_lines = []

zone_info = []
zone_info.append(ZoneInfo())
zone_info.append(ZoneInfo())

zone_info[0].tz_name = "America/Chicago"
zone_info[0].tz_abbr = "CST"
# Madison
zone_info[0].latitude = 43.073051
zone_info[0].longitude = -89.401230
zone_info[1].tz_name = "Europe/Madrid"
zone_info[1].tz_abbr = "CET"
# Algorta
zone_info[1].latitude = 43.348680
zone_info[1].longitude = -3.010120

# Get wifi details and more from a secrets.py file
try:
    from secrets import secrets
except ImportError:
    print("WiFi secrets are kept in secrets.py, please add them there!")
    raise
print("    Big Board")
print("Time will be set for {}".format(secrets["timezone"]))

# --- Display setup ---
matrix = Matrix()
display = matrix.display
network = Network(status_neopixel=board.NEOPIXEL, debug=False)

# --- Drawing setup ---
group = displayio.Group()  # Create a Group
bitmap = displayio.Bitmap(64, 32, 2)  # Create a bitmap object,width, height, bit depth
color = displayio.Palette(4)  # Create a color palette
color[0] = 0x000000  # black background
color[1] = 0xFF0000  # red
color[2] = 0xCC4000  # amber
color[3] = 0x85FF00  # greenish

# Create a TileGrid using the Bitmap and Palette
tile_grid = displayio.TileGrid(bitmap, pixel_shader=color)
group.append(tile_grid)  # Add the TileGrid to the Group
display.show(group)

# Fonts: https://learn.adafruit.com/custom-fonts-for-pyportal-circuitpython-display
if not DEBUG:
    font = bitmap_font.load_font("font/Monaco-numbers-14.bdf")
else:
    font = terminalio.FONT

clock_lines = [ ClockLine(font), ClockLine(font) ]

tz_label = {}
for idx in range(len(clock_lines)):
    clock_lines[idx].clock_label.x = 0
    clock_lines[idx].clock_label.y = 8 + ((display.height // 2) + 1) * idx
    group.append(clock_lines[idx].clock_label)

    clock_lines[idx].zone_label.x = 46
    clock_lines[idx].zone_label.y = 7 + ((display.height // 2) + 1) * idx
    clock_lines[idx].zone_label.color = 0x0000FF
    group.append(clock_lines[idx].zone_label)

    clock_lines[idx].zone_label.text = zone_info[idx].tz_abbr

status_label = Label(terminalio.FONT)
status_label.x = 0
status_label.y = clock_lines[1].zone_label.y
group.append(status_label)


def parse_time(value):
    result = 0

    m = re.search("(\d*)-(\d*)-(\d*)T(\d*):(\d*):(\d*)", value)
    if m:
        t = (
            int(m.group(1)),
            int(m.group(2)),
            int(m.group(3)),
            int(m.group(4)),
            int(m.group(5)),
            int(m.group(6)),
            -1,
            -1,
            -1,
        )

        result = time.mktime(t)

    return result


def update_time(*, index=0, hours=None, minutes=None, show_colon=False):
    now_utc_s = time.mktime(time.localtime())
    now_s = now_utc_s + zone_info[index].utc_offset_sec
    now = time.localtime(now_s)

    if now_s < 86400:
        clock_lines[index].zone_label.text = "???"
    elif int(round(zone_info[index].utc_offset_sec, 0)) == 0:
        clock_lines[index].zone_label.text = "UTC"
    else:
        clock_lines[index].zone_label.text = zone_info[index].tz_abbr

    if hours is None:
        hours = now[3]

    if zone_info[index].sunrise == zone_info[index].sunset:
        clock_lines[index].clock_label.color = color[2]
    elif (zone_info[index].sunrise < now_utc_s) and (now_utc_s < zone_info[index].sunset):
        # sunrise/sunset stored in UTC
        # daylight
        clock_lines[index].clock_label.color = color[3]
    else:
        # night
        clock_lines[index].clock_label.color = color[1]

    if SHOW_AM_PM:
        if hours > 12:  # Handle times later than 12:59
            hours -= 12
        elif not hours:  # Handle times between 0:00 and 0:59
            hours = 12

    if hours < 10:
        hours = " {hours}".format(hours=hours)
    else:
        hours = "{hours}".format(hours=hours)

    if minutes is None:
        minutes = now[4]

    if BLINK:
        colon = ":" if show_colon or now[5] % 2 else " "
    else:
        colon = ":"

    clock_lines[index].clock_label.text = "{hours}{colon}{minutes:02d}".format(
        hours=hours, minutes=minutes, colon=colon
    )
    bbx, bby, bbwidth, bbh = clock_lines[index].clock_label.bounding_box

    if DEBUG:
        print("Label bounding box: {},{},{},{}".format(bbx, bby, bbwidth, bbh))
        print("Label x: {} y: {}".format(clock_lines[index].clock_label.x, clock_lines[index].clock_label.y))

next_check = 0

# shapes: https://learn.adafruit.com/circuitpython-display-support-using-displayio/ui-quickstart
rect = Rect(0, (display.height // 2) - 1, display.width, 1, fill=0x000055)
group.append(rect)

update_time(show_colon=True)  # Display whatever time is on the board
clock_lines[idx].clock_label.text = "  :  "

while True:
    # new logic for checking time
    # - check every hour
    # - check if no DST offset for at least one of the zones
    # - check after DST changes. Need to look at ["dstInterval"]["dstStart"] and ["dstInterval"]["dstEnd"]
    #   which are both in UTC

    if next_check <= time.monotonic():
        try:
            update_time(
                show_colon=True
            )  # Make sure a colon is displayed while updating

	        # reference: https://docs.circuitpython.org/projects/matrixportal/en/latest/api.html#adafruit_matrixportal.network.Network

	        # reference: https://docs.circuitpython.org/projects/portalbase/en/latest/api.html#adafruit_portalbase.network.NetworkBase

            clock_lines[1].zone_label.color = 0xFF0000

            if not network.is_connected:
                print("connecting")
                clock_lines[1].zone_label.text = "net"
                network.connect(2)

                # Get UTC time. All future use of time will be relative to UTC.
                network.get_local_time("Etc/UTC")

            for idx in range(len(zone_info)):
                # Get the time zone data
                clock_lines[1].zone_label.text = "TZ"
                start_time = time.monotonic()
                response = network.fetch_data("https://www.timeapi.io/api/timezone/coordinate?latitude={lat}&longitude={lng}".format(lat=zone_info[idx].latitude, lng=zone_info[idx].longitude))
                print("-" * 40)
                print("response in {sec}".format(sec=time.monotonic() - start_time))
                print(response)
                print("-" * 40)

                response = json.loads(response)
                print(idx)
                print(response["currentUtcOffset"]["seconds"])
                zone_info[idx].utc_offset_sec = int(response["currentUtcOffset"]["seconds"])
                zone_info[idx].tz_name = response["timeZone"]

                print("{name} ({abbr}): {offset} s".format(name=zone_info[idx].tz_name, abbr=zone_info[idx].tz_abbr, offset=zone_info[idx].utc_offset_sec))

                # Get the almanac (sunrise/sunset) data
                clock_lines[1].zone_label.text = "alm"
                start_time = time.monotonic()
                response = network.fetch_data("https://api.sunrise-sunset.org/json?formatted=0&lat={lat}&lng={lng}".format(lat=zone_info[idx].latitude, lng=zone_info[idx].longitude))
                zone_info[idx].almanac = json.loads(response)["results"]

                zone_info[idx].sunrise = parse_time(zone_info[idx].almanac["sunrise"])
                zone_info[idx].sunset = parse_time(zone_info[idx].almanac["sunset"])

                print("-" * 40)
                print("response in {sec}".format(sec=time.monotonic() - start_time))
                print(response)
                print("-" * 40)

            clock_lines[1].zone_label.text = ":-)"
            next_check = time.monotonic() + 60 * 60
        except BrokenPipeError as e:
            print("BrokenPipeError")
            print(e)
            clock_lines[1].zone_label.text = "bpe"

        except ConnectionError as e:
            print("ConnectionError")
            print(e)
            clock_lines[1].zone_label.text = "c.e"

        except OSError as e:
            print("OSError")
            print(e)
            clock_lines[1].zone_label.text = "ose"

        except RuntimeError as e:
            print(e)
            print("An error occured, will retry")
            next_check = time.monotonic() + 10 * 60

        status_label.text = ""
        clock_lines[1].zone_label.color = 0x0000FF

    if next_update < time.monotonic():
        next_update = time.monotonic() + 1
        update_time()
        update_time(index = 1)
