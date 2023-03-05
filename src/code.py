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

# ------------------------------------------------------------------------------------
# --    Classes
# ------------------------------------------------------------------------------------

class ZoneInfo():
    def __init__(self, config):
        self.utc_offset_sec = 0
        self.is_utc = False
        self.tz_abbr = config["tz_abbr"]
        self.latitude = config["latitude"]
        self.longitude = config["longitude"]
        self.sunrise = 0
        self.sunset = 0
        self.dst_start = 0
        self.dst_end = 0
        self.next_check = 0

class ClockLine():
    def __init__(self, clock_font):
        self.clock_label = Label(clock_font)
        self.zone_label = Label(terminalio.FONT)

# ------------------------------------------------------------------------------------

# ------------------------------------------------------------------------------------
# --    Constants
# ------------------------------------------------------------------------------------
BLINK = True
DEBUG = False
SHOW_AM_PM = False
FEED_LOG = "big-board.big-board-log"
FEED_DRIFT = "big-board.big-board-drift"
AUX_ZONE_TIME_S = 5
WARN_MINUTES = 55
# ------------------------------------------------------------------------------------

# ------------------------------------------------------------------------------------
# --    Module Level Variables
# ------------------------------------------------------------------------------------
next_update = 0
next_time_update = 0
# Start this at zero. It will be incremented before the first read.
aux_zone_index = 0
next_aux_zone_time = 0
clock_lines = []
zone_info = []
# ------------------------------------------------------------------------------------

from locations import locations
print("found {} locations:".format(len(locations)))
for idx in range(len(locations)):
    print(locations[idx]["tz_abbr"])
    zone_info.append(ZoneInfo(locations[idx]))

# Get wifi details and more from a secrets.py file
try:
    from secrets import secrets
except ImportError:
    print("WiFi secrets are kept in secrets.py, please add them there!")
    raise

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
    font = bitmap_font.load_font("font/mono-numbers-14.bdf")
else:
    font = terminalio.FONT

clock_lines = [ ClockLine(font), ClockLine(font) ]

for idx in range(len(clock_lines)):
    top = 8 + ((display.height // 2) + 1) * idx

    clock_lines[idx].clock_label.x = 0
    clock_lines[idx].clock_label.y = top
    group.append(clock_lines[idx].clock_label)

    clock_lines[idx].zone_label.x = 41
    clock_lines[idx].zone_label.y = top - 1
    group.append(clock_lines[idx].zone_label)

    clock_lines[idx].zone_label.color = 0x0000FF
    clock_lines[idx].zone_label.text = zone_info[idx].tz_abbr

# Solid blue line separating the two times.
rect = Rect(0, (display.height // 2) - 1, display.width, 1, fill=0x000055)
group.append(rect)
# Cyan bar to show the seconds.
seconds_rect = Rect(0, (display.height // 2), 5, 1, fill=0x005555)
group.append(seconds_rect)
# Red box within 5 minutes of the hour.
warn_rect = Rect(display.width, (display.height // 2) - 1 - 3, 5, 3, fill=0x550000)
group.append(warn_rect)


# Adds a specified number of seconds to a time_tuple
def add_seconds(value, seconds):
    return time.localtime(time.mktime(value) + seconds)


# Formats a time_tuple as a string.
def format_time(value):
    return "{year}-{month:02d}-{day:02d} {hours}:{minutes:02d}:{seconds:02d}".format(year=value[0], month=value[1], day=value[2], hours=value[3], minutes=value[4], seconds=value[5])


def log(message):
    print("{time}: {msg}".format(time=format_time(time.localtime()), msg=message))


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


# Shows a short status message in red in the time zone name area.
def set_status(message):
    clock_lines[1].zone_label.color = 0xFF0000
    clock_lines[1].zone_label.text = message


# Updates the UTC offset, DST start and end, and sunrise/sunset for a location.
# zone: the ZoneInfo to display.
# idx:  the line number where zone will be displayed.
def update_time_zone(zone, idx):
    if zone.next_check < time.mktime(time.localtime()):
        # Time to refresh the zone info.

        if not network.is_connected:
            # Need a connection to update the information.
            log("connecting")
            set_status("net")
            network.connect(2)

        # ------------------------------------------------------------
        # --    Time zone info from lat/long.
        # ------------------------------------------------------------
        log("getting timezone {zone} info".format(zone=zone.tz_abbr))
        set_status("api")
        network.push_to_io(FEED_LOG,
            "getting timezone {zone} info".format(zone=zone.tz_abbr))
        # Get the time zone data
        set_status("TZ{idx}".format(idx=idx))
        start_time = time.monotonic()
        response = network.fetch_data("https://www.timeapi.io/api/timezone/coordinate?latitude={lat}&longitude={lng}".format(lat=zone.latitude, lng=zone.longitude))
        print("response in {sec}".format(sec=time.monotonic() - start_time))

        # Parse the JSON response into a dictionary.
        response = json.loads(response)
        zone.utc_offset_sec = int(response["currentUtcOffset"]["seconds"])
        zone.tz_name = response["timeZone"]
        # Get the DST start and end in UTC, in seconds.
        zone.dst_start = parse_time(response["dstInterval"]["dstStart"])
        zone.dst_end = parse_time(response["dstInterval"]["dstEnd"])
        # ------------------------------------------------------------

        # ------------------------------------------------------------
        # Get the almanac (sunrise/sunset) info.
        # ------------------------------------------------------------
        log("getting almanac {zone} info".format(zone=idx))
        # Get the almanac (sunrise/sunset) data
        set_status("ss{idx}".format(idx=idx))
        start_time = time.monotonic()
        response = network.fetch_data("https://api.sunrise-sunset.org/json?formatted=0&lat={lat}&lng={lng}".format(lat=zone.latitude, lng=zone.longitude))
        print("response in {sec}".format(sec=time.monotonic() - start_time))
        # Parse the JSON response into a dictionary.
        zone.almanac = json.loads(response)["results"]
        # Get the sunrise and sunset in UTC, in seconds.
        zone.sunrise = parse_time(zone.almanac["sunrise"])
        zone.sunset = parse_time(zone.almanac["sunset"])
        # ------------------------------------------------------------

        # Check again a minute after sunset and DST changes to get the
        # sunrise/sunset for the next day and new DST values.
        # NOTES
        #   1) sunrise doesn't appear to update until after sunset has passed.
        #   2) we don't use dst_start and dst_end to change the UTC offset. They're
        #       just used to determine when to call the API again. So if DST ends,
        #       we'll call the API a minute after and it will return the new UTC offset.
        zone.next_check = min(zone.sunset, zone.dst_start, zone.dst_end) + 60
        # In case something weird happens, make sure we don't update too soon.
        if zone.next_check < now_s:
            zone.next_check = now_s + 60 * 60 * 1

        s = "({sunrise}, {sunset}), ({dst_start}, {dst_end}) => {nextcheck}".format(
            sunrise=format_time(time.localtime(zone.sunrise)),
            sunset=format_time(time.localtime(zone.sunset)),
            dst_start=format_time(time.localtime(zone.dst_start)),
            dst_end=format_time(time.localtime(zone.dst_end)),
            nextcheck=format_time(time.localtime(zone.next_check)))
        log(s)
        set_status("api")
        network.push_to_io(FEED_LOG,
            "zone {zone} almanac: {almanac}".format(zone=idx, almanac=s))


# Updates the time displayed
def update_time(*, zone=None, index=0, hours=None, minutes=None, show_colon=False):
    # Current UTC time from our clock, in seconds.
    now_utc_s = time.mktime(time.localtime())
    # Current time in zone, in seconds.
    now_s = now_utc_s + zone.utc_offset_sec
    # Current time in zone, in time_tuple.
    now = time.localtime(now_s)

    if now[0] == 2000:
        # Should only get this before the RTC has been set.
        clock_lines[index].zone_label.text = "???"
    elif int(round(zone.utc_offset_sec, 0)) == 0:
        clock_lines[index].zone_label.text = "UTC"
    else:
        clock_lines[index].zone_label.text = zone.tz_abbr

    if hours is None:
        hours = now[3]

    if zone.sunrise == zone.sunset:
        # No almanac informat yet. Show in red.
        clock_lines[index].clock_label.color = color[2]
    elif (zone.sunrise < now_utc_s) and (now_utc_s < zone.sunset):
        # sunrise/sunset stored in UTC
        # daylight = green
        clock_lines[index].clock_label.color = color[3]
    else:
        # night = red
        clock_lines[index].clock_label.color = color[1]

    if SHOW_AM_PM:
        if hours > 12:  # Handle times later than 12:59
            hours -= 12
        elif not hours:  # Handle times between 0:00 and 0:59
            hours = 12

    if hours < 10:
        # Pad with a space
        hours = " {hours}".format(hours=hours)
    else:
        hours = "{hours}".format(hours=hours)

    if minutes is None:
        minutes = now[4]

    if BLINK:
        # Colon on for even seconds.
        colon = ":" if show_colon or now[5] % 2 else " "
    else:
        colon = ":"

    clock_lines[index].clock_label.text = "{hours}{colon}{minutes:02d}".format(
        hours=hours, minutes=minutes, colon=colon
    )

    # This is a red rectangle that shows within five minutes of the hour.
    global warn_rect
    if minutes >= WARN_MINUTES:
        warn_rect.x = display.width - (60 - minutes) * warn_rect.width
    else:
        # Shove it off the right of the display.
        warn_rect.x = display.width

    # Move the seconds indicator each time.
    global seconds_rect
    seconds_rect.x = now[5]

    # Bounding box for the clock text, of you need it.
    bbx, bby, bbwidth, bbh = clock_lines[index].clock_label.bounding_box
    if DEBUG:
        print("Label bounding box: {},{},{},{}".format(bbx, bby, bbwidth, bbh))
        print("Label x: {} y: {}".format(clock_lines[index].clock_label.x, clock_lines[index].clock_label.y))

update_time(zone=zone_info[0], show_colon=True)  # Display whatever time is on the board
clock_lines[1].clock_label.text = "  :  "

while True:
    # Get the earliest next check.
    next_check = next_time_update
    for idx in range(len(zone_info)):
        next_check = min(next_check, zone_info[idx].next_check)

    try:
        now_s = time.mktime(time.localtime())
        if next_check < now_s:
            update_time(zone=zone_info[0],
                show_colon=True
            )  # Make sure a colon is displayed while updating

            if not network.is_connected:
                log("connecting")
                set_status("net")
                network.connect(2)

            if next_time_update < now_s:
                msg = "Updating clock from {time}".format(time=format_time(time.localtime()))
                set_status("api")
                network.push_to_io(FEED_LOG, msg)
                log(msg)
                set_status("RTC")
                network.get_local_time("Etc/UTC")
                # Check time again in an hour
                next_time_update = time.mktime(time.localtime()) + 60 * 60

                log("next clock update at {nextcheck}".format(nextcheck=format_time(time.localtime(next_time_update))))

        # We can always call this. It will only do the update if needed.
        update_time_zone(zone_info[0], 0)

        if next_aux_zone_time <= time.mktime(time.localtime()):
            # Time to switch to the next zone
            aux_zone_index += 1
            if aux_zone_index >= len(zone_info):
                # Rollover
                aux_zone_index = 1

            # We can always call this. It will only do the update if needed.
            update_time_zone(zone_info[aux_zone_index], aux_zone_index)
            # Set this after we update the timezone info, because the update is expensive
            next_aux_zone_time = time.mktime(time.localtime()) + AUX_ZONE_TIME_S

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

    clock_lines[1].zone_label.color = 0x0000FF

    if next_update < time.monotonic():
        # Only update the display once per second.
        next_update = time.monotonic() + 1
        # Always update the first line with zone_info[0]
        update_time(zone=zone_info[0])
        # Update the second line with the current auxilliary zone.
        update_time(zone=zone_info[aux_zone_index], index = 1)

    # Short nap to save power
    time.sleep(0.1)
