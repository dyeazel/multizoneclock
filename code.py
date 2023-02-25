# SPDX-FileCopyrightText: 2023 Dean A Yeazel
#
# SPDX-License-Identifier: MIT

# Big Board
# Runs on Airlift Metro M4 with 64x32 RGB Matrix display & shield

import time
import board
import busio
import displayio
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

clock_label = {}
clock_label[0] = Label(font)
clock_label[1] = Label(font)

tz_label = {}
for idx in range(len(clock_label)):
    clock_label[idx].x = 1 #round(display.width / 2 - bbwidth / 2)
    clock_label[idx].y = 8 + ((display.height // 2) + 1) * idx
    group.append(clock_label[idx])

    tz_label[idx] = Label(terminalio.FONT)
    tz_label[idx].x = 43
    tz_label[idx].y = 7 + ((display.height // 2) + 1) * idx
    group.append(tz_label[idx])

tz_label[0].text = "LCL"
tz_label[1].text = "???"

status_label = Label(terminalio.FONT)
status_label.x = 0
status_label.y = tz_label[1].y
group.append(status_label)

def update_time(*, index=0, hours=None, minutes=None, show_colon=False):
    now = time.localtime()  # Get the time values we need
    if hours is None:
        hours = now[3]
    if hours >= 18 or hours < 6:  # evening hours to morning
        clock_label[index].color = color[1]
    else:
        clock_label[index].color = color[3]  # daylight hours

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

    clock_label[index].text = "{hours}{colon}{minutes:02d}".format(
        hours=hours, minutes=minutes, colon=colon
    )
    bbx, bby, bbwidth, bbh = clock_label[index].bounding_box

    if DEBUG:
        print("Label bounding box: {},{},{},{}".format(bbx, bby, bbwidth, bbh))
        print("Label x: {} y: {}".format(clock_label[index].x, clock_label[index].y))

next_check = 0

# shapes: https://learn.adafruit.com/circuitpython-display-support-using-displayio/ui-quickstart
rect = Rect(0, (display.height // 2) - 1, display.width, 2, fill=0xBBBBBB)
group.append(rect)

update_time(show_colon=True)  # Display whatever time is on the board

while True:
    if next_check <= time.monotonic():
        try:
            update_time(
                show_colon=True
            )  # Make sure a colon is displayed while updating

	        # reference: https://docs.circuitpython.org/projects/matrixportal/en/latest/api.html#adafruit_matrixportal.network.Network

	        # reference: https://docs.circuitpython.org/projects/portalbase/en/latest/api.html#adafruit_portalbase.network.NetworkBase

            clock_label[1].text = ""

            if not network.is_connected:
                print("connecting")
                status_label.text = "net"
                network.connect()

                network.get_local_time()  # Synchronize Board's clock to Internet

                print("fetch test")
                status_label.text = "test"
                response = network.fetch_data("https://api.sunrise-sunset.org/json?lat=36.7201600&lng=-4.4203400")
                print("-" * 40)
                print(response)
                print("-" * 40)

            print("fetch time")
            TIME_URL = "https://www.yeazel2.net/api/v1/util/gettime/Central%20Standard%20Time,W.%20Europe%20Standard%20Time"
            TIME_URL = "https://yeazel2.net/"

            status_label.text = "time"
            response = network.fetch(TIME_URL, timeout = 5)
            print("-" * 40)
            print(response)
            print("-" * 40)
            # https://www.yeazel2.net/api/v1/util/gettime/Central%20Standard%20Time,W.%20Europe%20Standard%20Time
            # capture time.monotonic() when response received
            # json.loads(response)
            # current time = server value + (time.monotonic() - last_check)

            next_check = time.monotonic() + 60 * 60
        except BrokenPipeError as e:
            print("BrokenPipeError")
            print(e)
            raise

        except RuntimeError as e:
            print("Some error occured, retrying!")
            print(e)
            next_check = time.monotonic() + 5

        status_label.text = ""

    if next_update < time.monotonic():
        next_update = time.monotonic() + 1
        update_time()
        update_time(index = 1)
