#!/usr/bin/python
# Based on miniterm sample in pyserial

import sys
import os
import serial
import threading
import traceback
import time
import re
import signal

class Color(object):
    def __init__(self):
        self.total = 1
        self.codes = [""]
        self.reset = ""
    def setup(self, total):
        self.total = total
        # Initialize colorama, if needed for the total number of devices
        # we have.  We avoid even loading colorama unless we need it.
        if total > 1:
            import colorama
            colorama.init()
            self.codes = [
                colorama.Fore.CYAN + colorama.Style.BRIGHT,
                colorama.Fore.YELLOW + colorama.Style.BRIGHT,
                colorama.Fore.MAGENTA + colorama.Style.BRIGHT,
                colorama.Fore.RED + colorama.Style.BRIGHT,
                colorama.Fore.GREEN + colorama.Style.BRIGHT,
                colorama.Fore.BLUE + colorama.Style.BRIGHT,
                colorama.Fore.WHITE + colorama.Style.BRIGHT,
                ]
            self.reset = colorama.Style.RESET_ALL
    def code(self, n):
        return self.codes[n % self.total]
g_color = Color()

if os.name == 'nt':
    import msvcrt
    class Console:
        def __init__(self):
            pass
        def cleanup(self):
            pass
        def getkey(self):
            while 1:
                z = msvcrt.getch()
                if z == '\0' or z == '\xe0': # function keys
                    msvcrt.getch()
                else:
                    if z == '\r':
                        return '\n'
                    return z
elif os.name == 'posix':
    import termios, select
    class Console:
        def __init__(self):
            self.fd = sys.stdin.fileno()
            try:
                self.old = termios.tcgetattr(self.fd)
                new = termios.tcgetattr(self.fd)
                new[3] = new[3] & ~termios.ICANON & ~termios.ECHO & ~termios.ISIG
                new[6][termios.VMIN] = 1
                new[6][termios.VTIME] = 0
                termios.tcsetattr(self.fd, termios.TCSANOW, new)
            except termios.error:
                # ignore errors, so we can pipe stuff to this script
                pass
        def cleanup(self):
            try:
                termios.tcsetattr(self.fd, termios.TCSAFLUSH, self.old)
            except:
                # ignore errors, so we can pipe stuff to this script
                pass
        def getkey(self):
            # Return -1 if we don't get input in 0.1 seconds, so that
            # the main code can check the "alive" flag and respond to SIGINT.
            [r, w, x] = select.select([self.fd], [], [self.fd], 0.1)
            if r:
                return os.read(self.fd, 1)
            elif x:
                return ''
            else:
                return -1
else:
    raise ("Sorry, no terminal implementation for your platform (%s) "
           "available." % sys.platform)

class Miniterm:
    """Normal interactive terminal"""

    def __init__(self,
                 serials,
                 suppress_bytes = None,
                 transmit_all = False):
        self.serials = serials
        self.suppress_bytes = suppress_bytes or ""
        self.last_color = ""
        self.threads = []
        self.transmit_all = transmit_all

    def start(self):
        self.alive = True

        # serial->console, all devices
        for (n, serial) in enumerate(self.serials):
            self.threads.append(threading.Thread(
                target = self.reader,
                args = (serial, g_color.code(n))
                ))

        # console->serial
        self.console = Console()
        self.threads.append(threading.Thread(target = self.writer))

        # start all threads
        for thread in self.threads:
            thread.daemon = True
            thread.start()

    def stop(self):
        self.alive = False

    def join(self):
        for thread in self.threads:
            while thread.isAlive():
                thread.join(0.1)

    def reader(self, serial, color):
        """loop and copy serial->console"""
        try:
            while self.alive:
                data = serial.read(1)
                if not data:
                    continue
                if color != self.last_color:
                    self.last_color = color
                    sys.stdout.write(color)
                if ((ord(data) >= 32 and ord(data) < 128) or
                    data == '\r' or data == '\n' or data == '\t'):
                    sys.stdout.write(data)
                else:
                    sys.stdout.write('\\x'+("0"+hex(ord(data))[2:])[-2:])
                sys.stdout.flush()
        except Exception as e:
            traceback.print_exc()
            self.console.cleanup()
            os._exit(1)

    def writer(self):
        """loop and copy console->serial until ^C"""
        try:
            while self.alive:
                try:
                    c = self.console.getkey()
                except KeyboardInterrupt:
                    c = '\x03'
                if c == '\x03':
                    self.stop()
                    return
                elif c == -1:
                    # No input, try again
                    continue
                elif c == '':
                    # EOF on input.  Wait a tiny bit so we can
                    # flush the remaining input, then stop.
                    time.sleep(0.25)
                    self.stop()
                    return
                elif c in self.suppress_bytes:
                    # Don't send these bytes
                    continue
                else:
                    # send character
                    if self.transmit_all:
                        for serial in self.serials:
                            serial.write(c)
                    else:
                        self.serials[0].write(c)
        except Exception as e:
            traceback.print_exc()
            self.console.cleanup()
            os._exit(1)

    def run(self):
        # Set all serial port timeouts to 0.1 sec
        saved_timeouts = []
        for (n, serial) in enumerate(self.serials):
            saved_timeouts.append(serial.timeout)
            serial.timeout = 0.1

        # Handle SIGINT gracefully
        signal.signal(signal.SIGINT, lambda *args: self.stop())

        # Go
        self.start()
        self.join()

        # Restore serial port timeouts
        for (n, serial) in enumerate(self.serials):
            serial.timeout = saved_timeouts[n]

        # Cleanup
        print ""
        self.console.cleanup()

if __name__ == "__main__":
    import argparse

    formatter = argparse.ArgumentDefaultsHelpFormatter
    description = ("Simple serial terminal that supports multiple devices.  "
                   "If more than one device is specified, device output is "
                   "shown in varying colors.  All input goes to the "
                   "first device.")
    parser = argparse.ArgumentParser(description = description,
                                     formatter_class = formatter)

    parser.add_argument("device", metavar="DEVICE", nargs="+",
                        help="serial device.  Specify DEVICE@BAUD for "
                        "per-device baudrates.")

    parser.add_argument("--all", "-a", action="store_true",
                        help="Send keystrokes to all devices, not just "
                        "the first one")
    parser.add_argument("--baudrate", "-b", metavar="BAUD", type=int,
                        help="baudrate for all devices", default=115200)
    parser.add_argument("--quiet", "-q", action="store_true",
                        help="Less verbose output")

    args = parser.parse_args()

    devs = []
    used_nodes = []
    g_color.setup(len(args.device))
    for (n, device) in enumerate(args.device):
        m = re.search(r"^(.*)@([1-9][0-9]*)$", device)
        if m is not None:
            node = m.group(1)
            baud = m.group(2)
        else:
            node = device
            baud = args.baudrate
        if node in used_nodes:
            sys.stderr.write("error: %s already open!\n" % node)
            raise SystemExit(1)
        try:
            dev = serial.Serial(node, baud)
        except serial.serialutil.SerialException:
            sys.stderr.write("error opening %s\n" % node)
            raise SystemExit(1)
        if not args.quiet:
            print (g_color.code(n)
                   + node + ", " + str(args.baudrate) + " baud"
                   + g_color.reset)
        used_nodes.append(node)
        devs.append(dev)

    if not args.quiet:
        print "^C to exit"
        print "----------"
    term = Miniterm(devs, transmit_all = args.all)
    term.run()

