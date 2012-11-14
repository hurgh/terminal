#!/usr/bin/python
# Based on miniterm sample in pyserial

import sys, os, serial, threading

if os.name == 'nt':
    import msvcrt
    class Console:
        def __enter__(self):
            return self
        def __exit__(self, type, value, traceback):
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
    import termios, sys, os
    class Console:
        def __enter__(self):
            self.fd = sys.stdin.fileno()
            self.old = termios.tcgetattr(self.fd)
            new = termios.tcgetattr(self.fd)
            new[3] = new[3] & ~termios.ICANON & ~termios.ECHO & ~termios.ISIG
            new[6][termios.VMIN] = 1
            new[6][termios.VTIME] = 0
            termios.tcsetattr(self.fd, termios.TCSANOW, new)
            return self
        def __exit__(self, type, value, traceback):
            termios.tcsetattr(self.fd, termios.TCSAFLUSH, self.old)
        def getkey(self):
            c = os.read(self.fd, 1)
            return c
else:
    raise "Sorry, no terminal implementation for your platform (%s) available." % sys.platform

class Miniterm:
    def __init__(self, serial):
        self.serial = serial

    def start(self):
        self.alive = True
        #start serial->console thread
        self.receiver_thread = threading.Thread(target=self.reader)
        self.receiver_thread.setDaemon(1)
        self.receiver_thread.start()
        #enter console->serial loop
        self.transmitter_thread = threading.Thread(target=self.writer)
        self.transmitter_thread.setDaemon(1)
        self.transmitter_thread.start()

    def stop(self):
        self.alive = False

    def join(self, transmit_only=False):
        self.transmitter_thread.join()
        if not transmit_only:
            self.receiver_thread.join()

    def reader(self):
        """loop and copy serial->console"""
        while self.alive:
            data = self.serial.read(1)
            if data == '\r':
                sys.stdout.write('\n')
            else:
                sys.stdout.write(data)
            sys.stdout.flush()

    def writer(self):
        """loop and copy console->serial until ^C"""
        with Console() as console:
            while self.alive:
                try:
                    c = console.getkey()
                except KeyboardInterrupt:
                    c = '\x03'
                if c == '\x03':
                    self.stop()
                    break                                   # exit app
                elif c == '\x00':
                    # don't write null, that will stop the other end
                    pass
                else:
                    self.serial.write(c)                    # send character

    def run(self):
        saved_timeout = self.serial.timeout
        self.serial.timeout = 0.1
        self.start()
        self.join(True)
        self.join()
        self.serial.write('\x00')
        self.serial.timeout = saved_timeout

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Simple serial terminal")
    parser.add_argument('device', metavar='DEVICE',
                        help='serial device')
    parser.add_argument('baudrate', metavar='BAUDRATE', type=int, nargs='?',
                        help='baud rate', default=115200)
    args = parser.parse_args()
    term = Miniterm(serial.Serial(args.device, args.baudrate))
    term.run()

