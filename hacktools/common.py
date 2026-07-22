"""Common utilities shared by all the platform modules.

Includes the :class:`Stream` class for binary I/O, CLI bootstrapping for
tools, logging, text section and XLIFF translation files, string extraction
and repacking, folder and patching helpers, and texture utilities.
"""
import codecs
from io import BytesIO, StringIO
import xml.etree.ElementTree as ET
import logging
import math
import os
import re
import shlex
import shutil
import sys
import stat
import struct
import subprocess
import typing
import zlib

hasClick = False
hasTqdm = False
hasGUI = False

try:
    import click
    hasClick = True
except ImportError:
    pass

try:
    from tqdm import tqdm
    hasTqdm = True
except ImportError:
    pass

table = {}


# File reading
class Stream(object):
    """Endian-aware binary stream, wrapping a file or an in-memory buffer.

    The underlying file is opened when entering the context manager. Most
    read and write methods have an At variant that operates at the given
    position and restores the current one afterwards.

    Args:
        fpath: Path of the file to open, unused for memory streams.
        mode: Mode passed to open, or "m" for an in-memory stream.
        little: Whether the stream is little endian.

    Attributes:
        f: The underlying file object, or the file path before opening.
        mode: The mode the stream was created with.
        endian: Endianness prefix used for struct operations, "<" or ">".
        half: Nibble buffered by :meth:`readHalf` and :meth:`writeHalf`, or None.
    """
    def __init__(self, fpath: str = "", mode: str = "m", little: bool = True):
        self.f = fpath
        self.mode = mode
        self.endian = "<" if little else ">"
        self.half: int | None = None

    def __enter__(self):
        if self.mode == "m":
            self.f = BytesIO()
        else:
            self.f = open(self.f, self.mode)
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.f.close()

    def close(self) -> None:
        """Close the underlying file."""
        self.f.close()

    def tell(self) -> int:
        """Return the current position in the stream."""
        return self.f.tell()

    def seek(self, pos: int, whence: int = 0) -> None:
        """Move the current position of the stream.

        Args:
            pos: Offset to move to, relative to whence.
            whence: 0 for absolute, 1 for relative, 2 for relative to the end.
        """
        self.f.seek(pos, whence)

    def read(self, n: int = -1) -> bytes:
        """Read n bytes, or all the remaining ones.

        Args:
            n: Number of bytes to read, or -1 to read until the end.

        Returns:
            The data that was read.
        """
        return self.f.read(n)

    def readAt(self, pos: int, n: int = -1) -> bytes:
        """Read n bytes at pos, restoring the current position afterwards.

        Args:
            pos: Position to read at.
            n: Number of bytes to read, or -1 to read until the end.

        Returns:
            The data that was read.
        """
        current = self.tell()
        self.seek(pos)
        ret = self.read(n)
        self.seek(current)
        return ret

    def write(self, data: bytes) -> None:
        """Write data to the stream.

        Args:
            data: Data to write.
        """
        self.f.write(data)

    def writeAt(self, pos: int, data: bytes) -> None:
        """Write data at pos, restoring the current position afterwards.

        Args:
            pos: Position to write at.
            data: Data to write.
        """
        current = self.tell()
        self.seek(pos)
        self.write(data)
        self.seek(current)

    def peek(self, n: int) -> bytes:
        """Read n bytes without advancing the current position.

        Args:
            n: Number of bytes to read.

        Returns:
            The data that was read.
        """
        pos = self.tell()
        ret = self.read(n)
        self.seek(pos)
        return ret

    def writeLine(self, data: str) -> None:
        """Write a string followed by a line feed, for text mode streams.

        Args:
            data: String to write.
        """
        self.f.write(data + "\n")

    def setEndian(self, little: bool) -> None:
        """Set the endianness of the stream.

        Args:
            little: Whether the stream is little endian.
        """
        self.endian = "<" if little else ">"

    def swapEndian(self) -> None:
        """Switch the stream between little and big endian."""
        self.endian = "<" if self.endian == ">" else ">"

    def readLong(self) -> int:
        """Read a signed 64-bit integer."""
        return struct.unpack(self.endian + "q", self.read(8))[0]

    def readLongAt(self, pos: int) -> int:
        """Read a signed 64-bit integer at pos, restoring the current position."""
        current = self.tell()
        self.seek(pos)
        ret = self.readLong()
        self.seek(current)
        return ret

    def readULong(self) -> int:
        """Read an unsigned 64-bit integer."""
        return struct.unpack(self.endian + "Q", self.read(8))[0]

    def readULongAt(self, pos: int) -> int:
        """Read an unsigned 64-bit integer at pos, restoring the current position."""
        current = self.tell()
        self.seek(pos)
        ret = self.readULong()
        self.seek(current)
        return ret

    def readInt(self) -> int:
        """Read a signed 32-bit integer."""
        return struct.unpack(self.endian + "i", self.read(4))[0]

    def readIntAt(self, pos: int) -> int:
        """Read a signed 32-bit integer at pos, restoring the current position."""
        current = self.tell()
        self.seek(pos)
        ret = self.readInt()
        self.seek(current)
        return ret

    def readUInt(self) -> int:
        """Read an unsigned 32-bit integer."""
        return struct.unpack(self.endian + "I", self.read(4))[0]

    def readUIntAt(self, pos: int) -> int:
        """Read an unsigned 32-bit integer at pos, restoring the current position."""
        current = self.tell()
        self.seek(pos)
        ret = self.readUInt()
        self.seek(current)
        return ret

    def readFloat(self) -> float:
        """Read a 32-bit float."""
        return struct.unpack(self.endian + "f", self.read(4))[0]

    def readFloatAt(self, pos: int) -> float:
        """Read a 32-bit float at pos, restoring the current position."""
        current = self.tell()
        self.seek(pos)
        ret = self.readFloat()
        self.seek(current)
        return ret

    def readDouble(self) -> float:
        """Read a 64-bit float."""
        return struct.unpack(self.endian + "d", self.read(8))[0]

    def readDoubleAt(self, pos: int) -> float:
        """Read a 64-bit float at pos, restoring the current position."""
        current = self.tell()
        self.seek(pos)
        ret = self.readDouble()
        self.seek(current)
        return ret

    def readShort(self) -> int:
        """Read a signed 16-bit integer."""
        return struct.unpack(self.endian + "h", self.read(2))[0]

    def readShortAt(self, pos: int) -> int:
        """Read a signed 16-bit integer at pos, restoring the current position."""
        current = self.tell()
        self.seek(pos)
        ret = self.readShort()
        self.seek(current)
        return ret

    def readUShort(self) -> int:
        """Read an unsigned 16-bit integer."""
        return struct.unpack(self.endian + "H", self.read(2))[0]

    def readUShortAt(self, pos: int) -> int:
        """Read an unsigned 16-bit integer at pos, restoring the current position."""
        current = self.tell()
        self.seek(pos)
        ret = self.readUShort()
        self.seek(current)
        return ret

    def readByte(self) -> int:
        """Read an unsigned 8-bit integer."""
        return struct.unpack("B", self.read(1))[0]

    def readByteAt(self, pos: int) -> int:
        """Read an unsigned 8-bit integer at pos, restoring the current position."""
        current = self.tell()
        self.seek(pos)
        ret = self.readByte()
        self.seek(current)
        return ret

    def readSByte(self) -> int:
        """Read a signed 8-bit integer."""
        return struct.unpack("b", self.read(1))[0]

    def readSByteAt(self, pos: int) -> int:
        """Read a signed 8-bit integer at pos, restoring the current position."""
        current = self.tell()
        self.seek(pos)
        ret = self.readSByte()
        self.seek(current)
        return ret

    def readHalf(self, big: bool = False) -> int:
        """Read a nibble, buffering the byte it belongs to.

        The first call reads and buffers a full byte, the second one consumes
        the remaining nibble.

        Args:
            big: Whether to read the high nibble of a new byte first.

        Returns:
            The nibble that was read.
        """
        if self.half is None:
            self.half = self.readByte()
            if big:
                return self.half >> 4
            return self.half & 0x0f
        else:
            ret = self.half >> 4 if not big else self.half & 0x0f
            self.half = None
            return ret

    def readZeros(self, size: int) -> None:
        """Skip zero bytes, stopping at the first non-zero byte or at size.

        Args:
            size: Position to stop at.
        """
        while self.tell() < size:
            byte = self.readByte()
            if byte != 0x00:
                self.seek(-1, 1)
                break

    def readBytes(self, n: int, upper: bool = False) -> str:
        """Read n bytes and format them as space-separated hex values.

        Args:
            n: Number of bytes to read.
            upper: Whether to use uppercase hex digits.

        Returns:
            The formatted string, with a trailing space.
        """
        ret = ""
        for i in range(n):
            ret += toHex(self.readByte(), upper) + " "
        return ret

    def readString(self, length: int) -> str:
        """Read a fixed-length string, one character per byte.

        Null bytes are skipped, while the 0x82 and 0x86 control characters
        are replaced with a space.

        Args:
            length: Number of bytes to read.

        Returns:
            The string that was read.
        """
        ret = ""
        for _ in range(length):
            byte = self.readByte()
            # These control characters can be found in texture names, replace them with a space
            if byte == 0x82 or byte == 0x86:
                byte = 0x20
            if byte != 0:
                ret += chr(byte)
        return ret

    def readStringAt(self, pos: int, length: int) -> str:
        """Read a fixed-length string at pos, restoring the current position."""
        current = self.tell()
        self.seek(pos)
        ret = self.readString(length)
        self.seek(current)
        return ret

    def readNullString(self) -> str:
        """Read a null-terminated string, one character per byte."""
        ret = ""
        while True:
            byte = self.readByte()
            if byte == 0:
                break
            else:
                ret += chr(byte)
        return ret

    def readNullStringAt(self, pos: int) -> str:
        """Read a null-terminated string at pos, restoring the current position."""
        current = self.tell()
        self.seek(pos)
        ret = self.readNullString()
        self.seek(current)
        return ret

    def readEncodedString(self, encoding: str = "utf-8") -> str:
        """Read a null-terminated string decoded with the given encoding.

        Args:
            encoding: Encoding to decode the string with.

        Returns:
            The decoded string.
        """
        num = 0
        pos = self.tell()
        while True:
            byte = self.readByte()
            if byte == 0:
                break
            else:
                num += 1
        self.seek(pos)
        ret = self.read(num).decode(encoding)
        self.readByte()
        return ret

    def readEncodedStringAt(self, pos: int, encoding: str = "utf-8") -> str:
        """Read a null-terminated encoded string at pos, restoring the current position."""
        current = self.tell()
        self.seek(pos)
        ret = self.readEncodedString(encoding)
        self.seek(current)
        return ret

    def writeLong(self, num: int) -> None:
        """Write num as a signed 64-bit integer."""
        self.f.write(struct.pack(self.endian + "q", num))

    def writeLongAt(self, pos: int, num: int) -> None:
        """Write num as a signed 64-bit integer at pos, restoring the current position."""
        current = self.tell()
        self.seek(pos)
        self.writeLong(num)
        self.seek(current)

    def writeULong(self, num: int) -> None:
        """Write num as an unsigned 64-bit integer."""
        self.f.write(struct.pack(self.endian + "Q", num))

    def writeULongAt(self, pos: int, num: int) -> None:
        """Write num as an unsigned 64-bit integer at pos, restoring the current position."""
        current = self.tell()
        self.seek(pos)
        self.writeULong(num)
        self.seek(current)

    def writeInt(self, num: int) -> None:
        """Write num as a signed 32-bit integer."""
        self.f.write(struct.pack(self.endian + "i", num))

    def writeIntAt(self, pos: int, num: int) -> None:
        """Write num as a signed 32-bit integer at pos, restoring the current position."""
        current = self.tell()
        self.seek(pos)
        self.writeInt(num)
        self.seek(current)

    def writeUInt(self, num: int) -> None:
        """Write num as an unsigned 32-bit integer."""
        self.f.write(struct.pack(self.endian + "I", num))

    def writeUIntAt(self, pos: int, num: int) -> None:
        """Write num as an unsigned 32-bit integer at pos, restoring the current position."""
        current = self.tell()
        self.seek(pos)
        self.writeUInt(num)
        self.seek(current)

    def writeFloat(self, num: float) -> None:
        """Write num as a 32-bit float."""
        self.f.write(struct.pack(self.endian + "f", num))

    def writeFloatAt(self, pos: int, num: float) -> None:
        """Write num as a 32-bit float at pos, restoring the current position."""
        current = self.tell()
        self.seek(pos)
        self.writeFloat(num)
        self.seek(current)

    def writeDouble(self, num: float) -> None:
        """Write num as a 64-bit float."""
        self.f.write(struct.pack(self.endian + "d", num))

    def writeDoubleAt(self, pos: int, num: float) -> None:
        """Write num as a 64-bit float at pos, restoring the current position."""
        current = self.tell()
        self.seek(pos)
        self.writeDouble(num)
        self.seek(current)

    def writeShort(self, num: int) -> None:
        """Write num as a signed 16-bit integer."""
        self.f.write(struct.pack(self.endian + "h", num))

    def writeShortAt(self, pos: int, num: int) -> None:
        """Write num as a signed 16-bit integer at pos, restoring the current position."""
        current = self.tell()
        self.seek(pos)
        self.writeShort(num)
        self.seek(current)

    def writeUShort(self, num: int) -> None:
        """Write num as an unsigned 16-bit integer."""
        self.f.write(struct.pack(self.endian + "H", num))

    def writeUShortAt(self, pos: int, num: int) -> None:
        """Write num as an unsigned 16-bit integer at pos, restoring the current position."""
        current = self.tell()
        self.seek(pos)
        self.writeUShort(num)
        self.seek(current)

    def writeByte(self, num: int) -> None:
        """Write num as an unsigned 8-bit integer."""
        self.f.write(struct.pack("B", num))

    def writeByteAt(self, pos: int, num: int) -> None:
        """Write num as an unsigned 8-bit integer at pos, restoring the current position."""
        current = self.tell()
        self.seek(pos)
        self.writeByte(num)
        self.seek(current)

    def writeSByte(self, num: int) -> None:
        """Write num as a signed 8-bit integer."""
        self.f.write(struct.pack("b", num))

    def writeSByteAt(self, pos: int, num: int) -> None:
        """Write num as a signed 8-bit integer at pos, restoring the current position."""
        current = self.tell()
        self.seek(pos)
        self.writeSByte(num)
        self.seek(current)

    def writeHalf(self, num: int, little: bool = True) -> None:
        """Write a nibble, buffering it until a full byte can be written.

        Args:
            num: Nibble to write.
            little: Whether the first nibble of each byte is the low one.
        """
        if self.half is None:
            self.half = num
        else:
            if little:
                self.writeByte((num << 4) | self.half)
            else:
                self.writeByte((self.half << 4) | num)
            self.half = None

    def writeString(self, str: str) -> None:
        """Write a string encoded as ASCII.

        Args:
            str: String to write.
        """
        self.f.write(str.encode("ascii"))

    def writeZero(self, num: int) -> None:
        """Write num zero bytes.

        Args:
            num: Number of bytes to write.
        """
        self.writeBytes(0x0, num)

    def writeBytes(self, byte: int, num: int) -> None:
        """Write num copies of a byte value.

        Args:
            byte: Byte value to write.
            num: Number of copies to write.
        """
        if num > 0:
            for i in range(num):
                self.writeByte(byte)

    def truncate(self) -> None:
        """Truncate the underlying file at the current position."""
        self.f.truncate()


# CLI/GUI
if hasClick:
    appname = ""
    appversion = ""
    datafolder = ""
    filecheck = ""
    crc = -1


    def setupTool(_appname: str = "", _appversion: str = "", _datafolder: str = "", _filecheck: str = "", _crc: int = -1) -> None:
        """Set up and run the command-line interface of a tool.

        Args:
            _appname: Name of the tool, shown at startup.
            _appversion: Version of the tool, shown at startup.
            _datafolder: Folder with the tool data files, created if missing.
            _filecheck: Path of a file required to run, usually the rom.
            _crc: Expected CRC32 checksum of the _filecheck file, or -1 to skip the check.
        """
        global appname, appversion, datafolder, filecheck, crc
        appname = _appname
        appversion = _appversion
        datafolder = _datafolder
        filecheck = _filecheck
        crc = _crc
        cli()


    @click.group(invoke_without_command=True)
    @click.option("--log", is_flag=True, default=False)
    @click.option("--gui", is_flag=True, default=False)
    @click.pass_context
    def cli(ctx, log, gui):
        setupFileLogging(log)
        if ctx.invoked_subcommand is None:
            multi = typing.cast(click.MultiCommand, ctx.command)
            ctx.invoke(multi.get_command(ctx, "main"), gui=gui)
        else:
            if not runStartup():
                quit()


    @cli.command(hidden=True)
    @click.option("--gui", is_flag=True, default=False)
    def main(gui):
        if not gui:
            runCLI()
        else:
            runGUI()


    def runStartup(skipcrc: bool = False) -> bool:
        """Log version information and check that the required file is present.

        Args:
            skipcrc: Whether to skip the CRC32 check.

        Returns:
            False if the required file is missing, True otherwise.
        """
        if datafolder != "" and not os.path.isdir(datafolder):
            makeFolder(datafolder)
        if appname != "":
            logMessage(appname + " version " + appversion)
        logMessage("Python", sys.version)
        from . import __version__
        logMessage("hacktools version", __version__)
        if filecheck != "" and not os.path.isfile(filecheck):
            logError(filecheck, "file not found.")
            return False
        if crc >= 0 and not skipcrc and not os.path.isfile(".skipcrc"):
            checkcrc = crcFile(filecheck)
            if crc != checkcrc:
                logMessage("Checksum mismatch for", filecheck, "(" + toHex(checkcrc) + ", expected", toHex(crc) + ")")
                logMessage("The tool might still work but you should run it on a good dump of the game.")
        return True


    def runCLI() -> None:
        """Run the tool as an interactive command prompt."""
        if not runStartup():
            quit()
        if len(sys.argv) > 1:
            cli()
            return
        with click.Context(cli) as ctx:
            click.echo(cli.get_help(ctx))
            click.echo("")
        while True:
            cmd = click.prompt("Type a command").strip()
            cmdlow = cmd.lower()
            if cmdlow == "exit" or cmdlow == "quit" or cmdlow == "q":
                break
            sys.argv = shlex.split(sys.argv[0] + " " + cmd)
            cli(standalone_mode=False)


    def runGUI() -> None:
        """Run the tool with the GUI frontend."""
        global hasGUI
        hasGUI = True
        from .gui import GUIApp
        guiapp = GUIApp()
        guiapp.initialize(cli, appname, appversion, datafolder)
        guiapp.mainloop()


# Logging
class FileFilter(logging.Filter):
    """Logging filter that hides progress messages starting with "prg-"."""
    def filter(self, record):
        return not record.getMessage().startswith("prg-")


def setupFileLogging(log: bool) -> None:
    """Set up logging to the tool.log file.

    Args:
        log: Whether to also log debug messages.
    """
    logging.getLogger("PIL.PngImagePlugin").setLevel(logging.CRITICAL + 1)
    filehandler = logging.FileHandler(filename="tool.log", encoding="utf-8", mode="w")
    filehandler.addFilter(FileFilter())
    logging.basicConfig(handlers=[filehandler], format="[%(levelname)s] %(message)s", level=logging.DEBUG if log else logging.INFO)


def logMessage(*messages) -> None:
    """Log a message at info level, also shown on the console.

    Args:
        *messages: Values joined with a space.
    """
    message = " ".join(str(x) for x in messages)
    logging.info(message)
    if hasTqdm and sys.stdout is not None:
        tqdm.write(message)


def logDebug(*messages) -> None:
    """Log a message at debug level, only written to the log file.

    Args:
        *messages: Values joined with a space.
    """
    message = " ".join(str(x) for x in messages)
    logging.debug(message)


def logWarning(*messages) -> None:
    """Log a warning message, only written to the log file.

    Args:
        *messages: Values joined with a space.
    """
    message = " ".join(str(x) for x in messages)
    logging.debug("[WARNING] " + message)


def logError(*messages) -> None:
    """Log a message at error level, also shown on the console.

    Args:
        *messages: Values joined with a space.
    """
    message = " ".join(str(x) for x in messages)
    logging.error(message)
    if hasTqdm and sys.stdout is not None:
        tqdm.write("[ERROR] " + message)


def varsHex(o) -> str:
    """Format the attributes of an object like vars, but with ints as hex.

    Args:
        o: Object to format.

    Returns:
        A string with the int, str and list attributes of the object.
    """
    ret = []
    for k in o.__dict__.keys():
        v = o.__dict__.__getitem__(k)
        if type(v) is int:
            ret.append("'" + k + "': " + toHex(v))
        elif type(v) is str:
            ret.append("'" + k + "': '" + v + "'")
        elif type(v) is list:
            ret.append("'" + k + "': " + str(v) + "")
    return ", ".join(ret)


def showProgress(iterable):
    """Wrap an iterable with a progress bar, if tqdm is available.

    Args:
        iterable: Iterable to wrap.

    Returns:
        The wrapped iterable, or the original one if tqdm is not available.
    """
    if hasTqdm:
        if hasGUI:
            from .gui import tqdm_gui
            return tqdm_gui(iterable=iterable)
        else:
            return tqdm(iterable=iterable)
    return iterable


# Strings
def toHex(byte: int, upper: bool = False) -> str:
    """Format a number as hex, without the 0x prefix and padded to two digits.

    Args:
        byte: Number to format.
        upper: Whether to use uppercase hex digits.

    Returns:
        The formatted string, with a minus sign in front if negative.
    """
    hexstr = hex(byte)[2:]
    if not upper:
        hexstr = hexstr.lower()
    else:
        hexstr = hexstr.upper()
    if len(hexstr) == 1:
        return "0" + hexstr
    if hexstr[0] == "x":
        return "-" + hexstr[1:]
    return hexstr


def isAscii(s: str) -> bool:
    """Check if a string only contains printable ASCII characters.

    Args:
        s: String to check.

    Returns:
        True if no character is a control code or above ASCII 127.
    """
    for i in range(len(s)):
        if ord(s[i]) >= 128 or ord(s[i]) < 0x20:
            return False
    return True


def codeToChar(code: int, encoding: str = "shift_jis", little: bool = True) -> str:
    """Convert a character code to a string.

    Args:
        code: Character code, ASCII if below 128, 2-byte encoded otherwise.
        encoding: Encoding used for 2-byte codes.
        little: Byte order of 2-byte codes.

    Returns:
        The decoded character, or an empty string if it can't be decoded.
    """
    try:
        if code < 128:
            return struct.pack("B", code).decode("ascii")
        return struct.pack(("<" if little else ">") + "H", code).decode(encoding)
    except UnicodeDecodeError:
        return ""


def loadTable(tablefile: str) -> None:
    """Load a replacement table file into the global table dictionary.

    Args:
        tablefile: Path of the table file, with one key=value pair per line.
    """
    if os.path.isfile(tablefile):
        with codecs.open(tablefile, "r", "utf-8") as ft:
            for line in ft:
                line = line.strip("\r\n")
                if line.find("=") > 0:
                    linesplit = line.split("=", 1)
                    table[linesplit[0]] = linesplit[1]


def shiftPointer(pointer: int, pointerdiff: dict[int, int]) -> int:
    """Shift a pointer by the length differences that apply before it.

    Args:
        pointer: Original pointer value.
        pointerdiff: Dictionary of position -> length difference.

    Returns:
        The pointer shifted by all the differences at earlier positions.
    """
    newpointer = pointer
    for k, v in pointerdiff.items():
        if k < pointer:
            newpointer += v
    # if newpointer != pointer:
    #    logDebug("Shifted pointer", toHex(pointer), "to", toHex(newpointer))
    return newpointer


def checkShiftJIS(first: int, second: int) -> bool:
    """Check if two bytes form a valid 2-byte Shift-JIS character.

    Args:
        first: First byte.
        second: Second byte.

    Returns:
        True if the bytes are a valid Shift-JIS sequence.
    """
    # Based on https://www.lemoda.net/c/detect-shift-jis/
    status = False
    if (first >= 0x81 and first <= 0x84) or (first >= 0x87 and first <= 0x9f):
        if second >= 0x40 and second <= 0xfc:
            status = True
    elif first >= 0xe0 and first <= 0xef:
        if second >= 0x40 and second <= 0xfc:
            status = True
    return status


def openSection(file: str, filestart: int = 1, fileend: int = 10):
    """Open a text section file, concatenating numbered parts if split.

    Args:
        file: Path of the file, with a {} placeholder for the part number.
        filestart: First part number to check.
        fileend: Last part number to check.

    Returns:
        A file-like object with the file contents, or None if not found.
    """
    if not os.path.isfile(file.format("")):
        if os.path.isfile(file.format(str(filestart))):
            section = StringIO()
            for i in range(filestart, fileend + 1):
                sectionfile = file.format(str(i))
                if os.path.isfile(sectionfile):
                    with codecs.open(sectionfile, "r", "utf-8") as f:
                        section.write(f.read())
                else:
                    break
            return section
        else:
            return None
    else:
        return codecs.open(file.format(""), "r", "utf-8")


def getSectionNames(f) -> list[str]:
    """Get the names of the !FILE: sections in an open section file.

    Args:
        f: File-like object to read from.

    Returns:
        The list of section names.
    """
    ret = []
    try:
        f.seek(0)
        for line in f:
            line = line.rstrip("\r\n").replace("\ufeff", "")
            if line.startswith("!FILE:"):
                ret.append(line[6:].split("#")[0])
    except UnicodeDecodeError:
        return ret
    return ret


def getSection(f, title: str, comment: str = "#", fixchars: list = [], justone: bool = True, inorder: bool = False):
    """Read the entries of a !FILE: section from an open section file.

    Args:
        f: File-like object to read from.
        title: Name of the section, or "" to read from the start.
        comment: Comment marker, contents after it are ignored.
        fixchars: List of (old, new) character replacements to apply.
        justone: Whether to stop at the next section, instead of merging all
            the sections with the same name.
        inorder: Whether to return entries in order instead of a dictionary.

    Returns:
        A dictionary of string -> list of translations, or a list of
        {"name", "value"} entries if inorder is True.
    """
    ret: dict[str, list[str]] | list[dict[str, str]] = {} if not inorder else []
    found = title == ""
    try:
        f.seek(0)
        for line in f:
            line = line.rstrip("\r\n").replace("\ufeff", "")
            if found and line.startswith("!FILE:"):
                if not justone:
                    found = False
                else:
                    break
            if not found and line.startswith("!FILE:" + title):
                found = True
            elif found and line.startswith(comment) and inorder:
                ret.append({"name": line, "value": ""})
            elif found and line.find("=") > 0:
                split = line.split("=", 1)
                split[1] = split[1].split(comment)[0]
                if split[0] not in ret and not inorder:
                    ret[split[0]] = []
                for fixchar in fixchars:
                    split[1] = split[1].replace(fixchar[0], fixchar[1])
                if inorder:
                    ret.append({"name": split[0], "value": split[1]})
                else:
                    ret[split[0]].append(split[1])
    except UnicodeDecodeError:
        return ret
    return ret


def getSections(file: str, comment: str = "#", fixchars: list = [], inorder: bool = False) -> dict:
    """Read all the sections from a section file.

    Args:
        file: Path of the section file.
        comment: Comment marker, contents after it are ignored.
        fixchars: List of (old, new) character replacements to apply.
        inorder: Whether sections contain ordered entries, see :func:`getSection`.

    Returns:
        A dictionary of section name -> section entries.
    """
    sections = {}
    with codecs.open(file, "r", "utf-8") as wsb:
        files = getSectionNames(wsb)
        for file in files:
            sections[file] = getSection(wsb, file, comment, fixchars, inorder=inorder)
    return sections


def getSectionPercentage(section: dict, chartot: int = 0, transtot: int = 0) -> tuple[int, int]:
    """Count the total and translated characters in a section.

    Args:
        section: Section dictionary returned by :func:`getSection`.
        chartot: Character count to add to.
        transtot: Translated character count to add to.

    Returns:
        A tuple (chartot, transtot) with the updated counts.
    """
    for s in section.keys():
        strlen = len(s)
        for s2 in section[s]:
            chartot += strlen
            if s2 != "":
                transtot += strlen
    return chartot, transtot


def mergeSections(file1: str, file2: str, output: str, comment: str = "#", fixchars: list = []) -> None:
    """Merge two section files, filling empty translations in file1 from file2.

    Args:
        file1: Path of the main section file.
        file2: Path of the section file to take missing translations from.
        output: Path of the merged output file.
        comment: Comment marker, contents after it are ignored.
        fixchars: List of (old, new) character replacements to apply.
    """
    sections1 = getSections(file1, comment, fixchars, inorder=True)
    sections2 = getSections(file2, comment, fixchars)
    with codecs.open(output, "w", "utf-8") as out:
        for section in sections1.keys():
            out.write("!FILE:" + section + "\n")
            for v in sections1[section]:
                s = v["name"]
                if s.startswith(comment):
                    out.write(s + "\n")
                    continue
                sectionstr = v["value"]
                if sectionstr == "":
                    for section2 in sections2.keys():
                        if s in sections2[section2] and sections2[section2][s][0] != "":
                            sectionstr = sections2[section2][s][0]
                            break
                out.write(s + "=" + sectionstr + "\n")


class TranslationFile:
    """Translation file in the XLIFF format used by Weblate.

    Args:
        path: Path of the xliff file to load, or "" to create an empty one.

    Attributes:
        files: Dictionary of file name -> XML file element.
        lookup: Dictionary of source text -> translation, filled by :meth:`preloadLookup`.
        offlookup: Dictionary of offset -> source text, filled by :meth:`preloadLookup`.
        offsets: Dictionary of file name -> list of offsets, filled by :meth:`preloadOffsets`.
        chartot: Total character count, filled by :meth:`preloadLookup`.
        transtot: Translated character count, filled by :meth:`preloadLookup`.
        root: Root XML element.
    """
    def __init__(self, path: str = ""):
        self.files = {}
        self.lookup: dict[str, str] = {}
        self.chartot = 0
        self.transtot = 0
        if path == "":
            self.root = ET.Element("xliff")
            self.root.set("version", "1.2")
            self.root.set("xmlns", "urn:oasis:names:tc:xliff:document:1.2")
        else:
            ET.register_namespace("", "urn:oasis:names:tc:xliff:document:1.2")
            tree = ET.parse(path)
            self.root = tree.getroot()
            for file in self.root:
                self.files[file.attrib["original"]] = file

    def mergeSection(self, path: str, filename: str = "", section: str = "", comments: str = "#", fixchars: list = []) -> None:
        """Merge the translations from a section file into this file.

        Args:
            path: Path of the section file.
            filename: Only merge into this file entry, or "" for all of them.
            section: Name of the section to read, or "" to read from the start.
            comments: Comment marker, contents after it are ignored.
            fixchars: List of (old, new) character replacements to apply.
        """
        with codecs.open(path, "r", "utf-8") as bin:
            mergesection = getSection(bin, section, comments, fixchars=fixchars, justone=False)
        # Check the merge section
        for file in self.root:
            if filename != "" and file.attrib["original"] != filename:
                continue
            for unit in file[0]:
                check = unit[0].text
                if check in mergesection and mergesection[check][0] != "":
                    newcheck = mergesection[check][0]
                    if len(mergesection[check]) > 1:
                        mergesection[check].pop(0)
                    unit[1].text = newcheck
                    unit[1].set("state", "translated")
                    unit.set("approved", "no")
    
    def addEntry(self, text: str, filename: str, offset: int, translation: str = "", comment: str = "") -> None:
        """Add a translation unit to a file, creating the file entry if needed.

        Args:
            text: Source text.
            filename: Name of the file entry.
            offset: Offset of the string, used as the unit ID.
            translation: Translated text, if any.
            comment: Note to attach to the unit, if any.
        """
        # Check if we need to add a new file
        if filename not in self.files:
            file = ET.SubElement(self.root, "file", {"xml:space": "preserve"})
            file.set("original", filename)
            file.set("source-language", "ja")
            file.set("target-language", "en")
            ET.SubElement(file, "body")
            self.files[filename] = file
        else:
            file = self.files[filename]
        # Add the new entry
        unit = ET.SubElement(file[0], "trans-unit", {"id": str(offset), "xml:space": "preserve"})
        source = ET.SubElement(unit, "source")
        source.text = text
        target = ET.SubElement(unit, "target")
        if translation != "":
            target.text = translation
        if comment != "":
            note = ET.SubElement(unit, "note")
            note.text = comment

    def preloadLookup(self, comments: str = "#") -> None:
        """Fill the lookup dictionaries and the progress counts.

        Args:
            comments: Comment marker, stripped from the translations.
        """
        self.lookup = {}
        self.offlookup = {}
        self.chartot = 0
        self.transtot = 0
        for file in self.files:
            for unit in self.files[file][0]:
                self.offlookup[int(unit.attrib["id"])] = unit[0].text
                self.chartot += len(unit[0].text)
                if unit[1].text is not None and unit[1].text != "":
                    if comments in unit[1].text:
                        unit[1].text = unit[1].text.split(comments)[0]
                    self.lookup[unit[0].text] = unit[1].text
                    self.transtot += len(unit[0].text)

    def preloadOffsets(self) -> None:
        """Fill the offsets dictionary with the unit IDs of each file."""
        self.offsets: dict[str, list[int]] = {}
        for file in self.files:
            self.offsets[file] = []
            for unit in self.files[file][0]:
                self.offsets[file].append(int(unit.attrib["id"]))

    def getEntry(self, text: str, filename: str, offset: int) -> str:
        """Get the translation for a string.

        Tries to match by offset first, then by source text in the same file
        entry, then by source text in the whole lookup.

        Args:
            text: Source text.
            filename: Name of the file entry.
            offset: Offset of the string.

        Returns:
            The translation, or "" if not found or not translated.
        """
        stroffset = str(offset)
        if filename in self.files:
            # Try to match offset
            for unit in self.files[filename][0]:
                if unit.attrib["id"] == stroffset and unit[1].text is not None and unit[1].text != "":
                    return unit[1].text
            # Try to match string
            for unit in self.files[filename][0]:
                if unit[0].text == text and unit[1].text is not None and unit[1].text != "":
                    return unit[1].text
        # If nothing was found, run a search on the whole file
        if text in self.lookup:
            return self.lookup[text]
        return ""

    def setEntry(self, text: str, filename: str, offset: int, newtext: str) -> None:
        """Set the translation for a string, matched by offset or source text.

        Args:
            text: Source text.
            filename: Name of the file entry.
            offset: Offset of the string.
            newtext: Translation to set.
        """
        stroffset = str(offset)
        if filename in self.files:
            # Try to match offset
            for unit in self.files[filename][0]:
                if unit.attrib["id"] == stroffset:
                    unit[1].text = newtext
                    return
            # Try to match string
            for unit in self.files[filename][0]:
                if unit[0].text == text:
                    unit[1].text = newtext

    def hasFile(self, filename: str) -> bool:
        """Check if a file entry exists.

        Args:
            filename: Name of the file entry.

        Returns:
            True if the file entry exists.
        """
        return filename in self.files

    def getProgress(self) -> float:
        """Return the translation percentage, as counted by :meth:`preloadLookup`."""
        if self.chartot == 0:
            return 0
        return (100 * self.transtot) / self.chartot

    def save(self, filename: str, dummy: bool = False) -> None:
        """Save the translation file, formatted like Weblate would.

        Args:
            filename: Output path, parent folders are created if missing.
            dummy: Whether to add a dummy entry, to avoid saving an empty file.
        """
        if dummy:
            self.addEntry("dummy line", "dummy", 0, "dummy translation", "Ignore this")
        makeFolders(os.path.dirname(filename))
        self._pretty_print(self.root)
        xmlstr = ET.tostring(self.root, encoding="unicode", xml_declaration=True)
        # Change this to match what Weblate does
        xmlstr = xmlstr.replace("<target />", "<target/>") + "\n"
        xmlstr = xmlstr.replace("<?xml version='1.0' encoding='utf-8'?>", "<?xml version=\"1.0\" encoding=\"UTF-8\"?>")
        with codecs.open(filename, "w", "utf-8") as f:
            f.write(xmlstr)

    def _pretty_print(self, current, parent=None, index=-1, depth=0):
        for i, node in enumerate(current):
            self._pretty_print(node, current, i, depth + 1)
        if parent is not None:
            if index == 0:
                parent.text = "\n" + ("  " * depth)
            else:
                parent[index - 1].tail = "\n" + ("  " * depth)
            if index == len(parent) - 1:
                current.tail = "\n" + ("  " * (depth - 1))


class FontGlyph:
    """Position and width information for a single font glyph.

    Attributes:
        start: Start offset of the glyph in the font.
        width: Width of the glyph.
        length: Horizontal space occupied by the glyph when drawn.
        char: Character the glyph represents.
        code: Character code.
        index: Index of the glyph in the font.
    """
    def __init__(self, start, width, length, char="", code=0, index=0):
        self.start: int = start
        self.width: int = width
        self.length: int = length
        self.char: str = char
        self.code: int = code
        self.index: int = index


def wordwrap(text: str, glyphs: dict[str, FontGlyph], width: int, codefunc=None, default: int = 6, linebreak: str = "|", sectionsep: str = ">>", strip: bool = True) -> str:
    """Word wrap text to fit a pixel width, based on glyph lengths.

    Args:
        text: Text to wrap.
        glyphs: Dictionary of character -> :class:`FontGlyph`.
        width: Maximum line width, in pixels.
        codefunc: Function called with (text, position) that returns the
            length of the control code at that position, or 0 if none.
        default: Length of characters not found in glyphs.
        linebreak: Line break marker.
        sectionsep: Separator between sections that are wrapped independently.
        strip: Whether to strip whitespace from the wrapped lines.

    Returns:
        The wrapped text, with lines joined by linebreak.
    """
    # Based on http://code.activestate.com/recipes/577946-word-wrap-for-proportional-fonts/
    lines = []
    if sectionsep != "" and text.count(sectionsep) > 0:
        lines = text.split(sectionsep)
        for i in range(len(lines)):
            lines[i] = wordwrap(lines[i], glyphs, width, codefunc, default, linebreak, sectionsep)
        return sectionsep.join(lines)
    if linebreak != "\n":
        text = text.replace(linebreak, "\n")
    pattern = re.compile(r"(\s+)")
    lookup = dict((c, glyphs[c].length if c in glyphs else default) for c in set(text))
    for line in text.splitlines():
        tokens = pattern.split(line)
        tokens.append("")
        widths = []
        for token in tokens:
            tokenwidth = 0
            i = 0
            while i < len(token):
                if codefunc is not None:
                    skip = codefunc(token, i)
                    if skip > 0:
                        i += skip
                        continue
                tokenwidth += lookup[token[i]]
                i += 1
            widths.append(tokenwidth)
        start, total = 0, 0
        for index in range(0, len(tokens), 2):
            if total + widths[index] > width:
                end = index + 2 if index == start else index
                lines.append("".join(tokens[start:end]))
                start, total = end, 0
                if end == index + 2:
                    continue
            total += widths[index] + widths[index + 1]
        if start < len(tokens):
            lines.append("".join(tokens[start:]))
    if strip:
        lines = [line.strip() for line in lines]
    else:
        for i in range(len(lines)):
            if lines[i].startswith(" "):
                lines[i] = lines[i][1:]
            if lines[i].endswith(" "):
                lines[i] = lines[i][:-1]
    return linebreak.join(lines)


def centerLines(text: str, glyphs: dict[str, FontGlyph], width: int, codefunc=None, default: int = 6, linebreak: str = "|", centercode: str = "<<") -> str:
    """Center the lines marked with centercode, by prepending spaces.

    Args:
        text: Text with the lines to center.
        glyphs: Dictionary of character -> :class:`FontGlyph`.
        width: Total width to center within, in pixels.
        codefunc: Function called with (text, position) that returns the
            length of the control code at that position, or 0 if none.
        default: Length of characters not found in glyphs.
        linebreak: Line break marker.
        centercode: Marker at the start of the lines to center.

    Returns:
        The text with the marked lines centered.
    """
    lines = text.split(linebreak)
    for i in range(len(lines)):
        if not lines[i].startswith(centercode):
            continue
        lines[i] = lines[i][len(centercode):]
        length = 0
        j = 0
        while j < len(lines[i]):
            if codefunc is not None:
                skip = codefunc(lines[i], j)
                if skip > 0:
                    j += skip
                    continue
            length += glyphs[lines[i][j]].length if lines[i][j] in glyphs else default
            j += 1
        spacelen = glyphs[" "].length
        spacing = int(((width - length) / 2) / spacelen)
        lines[i] = (" " * spacing) + lines[i]
    return linebreak.join(lines)


def readEncodedString(f: Stream, encoding: str = "shift_jis", upper: bool = False) -> str:
    """Read a null-terminated encoded string from a stream.

    Line feeds are read as "|", and invalid 2-byte sequences followed by
    0x01 are kept as UNK(xxyy) markers.

    Args:
        f: Stream to read from.
        encoding: Encoding used for 2-byte characters.
        upper: Whether UNK markers use uppercase hex digits.

    Returns:
        The decoded string.
    """
    sjis = ""
    while True:
        b1 = f.readByte()
        if b1 == 0x0a:
            sjis += "|"
        elif b1 == 0x00:
            break
        else:
            b2 = f.readByte()
            if not checkShiftJIS(b1, b2):
                if b2 == 0x01:
                    sjis += "UNK(" + toHex(b1, upper) + toHex(b2, upper) + ")"
                else:
                    f.seek(-1, 1)
                    sjis += chr(b1)
            else:
                f.seek(-2, 1)
                try:
                    sjis += f.read(2).decode(encoding).replace("〜", "～")
                except UnicodeDecodeError:
                    logError("[ERROR] UnicodeDecodeError")
                    sjis += "[ERROR" + str(f.tell() - 2) + "]"
    return sjis


def detectEncodedString(f: Stream, encoding: str = "shift_jis", startascii: list = [0x25], startenc: list = [], upper: bool = False) -> str:
    """Try to read a null-terminated encoded string from a stream.

    Args:
        f: Stream to read from.
        encoding: Encoding used for 2-byte characters.
        startascii: ASCII bytes the string is allowed to start with.
        startenc: (first, second) byte tuples allowed as unknown start codes.
        upper: Whether UNK markers use uppercase hex digits.

    Returns:
        The detected string, or "" if the data doesn't look like one.
    """
    ret = ""
    sjis = 0
    while True:
        b1 = f.readByte()
        if b1 == 0x0a:
            ret += "|"
        elif b1 == 0x00:
            break
        elif b1 >= 28 and b1 <= 126 and (len(ret) > 0 or b1 in startascii):
            ret += chr(b1)
        else:
            b2 = f.readByte()
            if checkShiftJIS(b1, b2):
                f.seek(-2, 1)
                try:
                    ret += f.read(2).decode(encoding).replace("〜", "～")
                    sjis += 1
                except UnicodeDecodeError:
                    if ret.count("UNK(") >= 5:
                        return ""
                    ret += "UNK(" + toHex(b1, upper) + toHex(b2, upper) + ")"
            elif (b1, b2) in startenc or (len(ret) > 1 and ret.count("UNK(") < 5):
                ret += "UNK(" + toHex(b1, upper) + toHex(b2, upper) + ")"
            else:
                return ""
    return ret


def detectASCIIString(f: Stream, encoding: str = "ascii", startascii: list = []) -> str:
    """Try to read a null-terminated ASCII string from a stream.

    Args:
        f: Stream to read from.
        encoding: Unused, kept for compatibility with :func:`detectEncodedString`.
        startascii: Unused, kept for compatibility with :func:`detectEncodedString`.

    Returns:
        The detected string, or "" if a non-ASCII byte is found.
    """
    ret = ""
    while True:
        b1 = f.readByte()
        if b1 == 0x0a:
            ret += "|"
        elif b1 == 0x00:
            break
        elif b1 >= 28 and b1 <= 126:
            ret += chr(b1)
        else:
            return ""
    return ret


def writeEncodedString(f: Stream, s: str, maxlen: int = 0, encoding: str = "shift_jis", zerobytes: int = 1) -> int:
    """Write an encoded string to a stream, terminated by zero bytes.

    "|" characters are written as line feeds, and UNK(xxyy) markers as
    their raw bytes.

    Args:
        f: Stream to write to.
        s: String to write.
        maxlen: Maximum length in bytes, or 0 for no limit.
        encoding: Encoding used for non-ASCII characters.
        zerobytes: Number of zero bytes used as terminator.

    Returns:
        The number of bytes written, or -1 if the string doesn't fit in maxlen.
    """
    i = 0
    x = 0
    s = s.replace("～", "〜")
    while x < len(s):
        c = s[x]
        if c == "U" and x < len(s) - 4 and s[x:x+4] == "UNK(":
            if maxlen > 0 and i+2 > maxlen:
                return -1
            code = s[x+4] + s[x+5]
            f.write(bytes.fromhex(code))
            code = s[x+6] + s[x+7]
            f.write(bytes.fromhex(code))
            x += 8
            i += 2
        elif c == "|":
            if maxlen > 0 and i+1 > maxlen:
                return -1
            f.writeByte(0x0a)
            i += 1
        elif ord(c) < 128:
            if maxlen > 0 and i+1 > maxlen:
                return -1
            f.writeByte(ord(c))
            i += 1
        else:
            if maxlen > 0 and i+2 > maxlen:
                return -1
            f.write(c.encode(encoding))
            i += 2
        x += 1
    if zerobytes > 0:
        if zerobytes > 1:
            if maxlen > 0 and i+1 > maxlen:
                return -1
            i += zerobytes - 1
        f.writeZero(zerobytes)
    return i


def extractBinaryStrings(infile: str, binranges: list, func=detectEncodedString, encoding: str = "shift_jis") -> tuple[list[str], list[list[int]]]:
    """Extract encoded strings from ranges of a binary file.

    Args:
        infile: Path of the binary file.
        binranges: List of (start, end) ranges to scan.
        func: Function used to detect strings, called with (stream, encoding).
        encoding: Encoding passed to func.

    Returns:
        A tuple (strings, positions), where positions holds the list of
        offsets each string was found at.
    """
    strings = []
    positions = []
    insize = os.path.getsize(infile)
    with Stream(infile, "rb") as f:
        for binrange in binranges:
            f.seek(binrange[0])
            while f.tell() < binrange[1] and f.tell() < insize - 2:
                pos = f.tell()
                check = func(f, encoding)
                if check != "":
                    if check not in strings:
                        logDebug("Found string", check, "at", toHex(pos))
                        strings.append(check)
                        positions.append([pos])
                    else:
                        positions[strings.index(check)].append(pos)
                    pos = f.tell() - 1
                f.seek(pos + 1)
    return strings, positions


class BinaryPointer:
    """Old and new location of a string relocated by :func:`repackBinaryStrings`.

    Attributes:
        old: Pointer to the original string location.
        new: Pointer to the new string location.
        str: The string the pointer refers to.
    """
    def __init__(self, old, new, str):
        self.old: int = old
        self.new: int = new
        self.str: bytes = str


def repackBinaryStrings(section, infile: str, outfile: str, binranges: list, freeranges: list | None = None, readfunc=detectEncodedString, writefunc=writeEncodedString, encoding: str = "shift_jis", pointerstart: int = 0, injectstart: int = 0, fallbackf: Stream | None = None, injectfallback: int = 0, sectionname: str = "bin", preformat=None, postformat=None, pointeralign: int = 1) -> tuple[list[BinaryPointer], list | None]:
    """Repack translated strings into ranges of a binary file.

    Strings found in binranges are replaced in place when the translation
    fits. When it doesn't and freeranges is given, the translation is written
    in one of those ranges instead, pointers to it are searched and updated
    in the whole file, and the freed space is added to the free ranges pool.

    Args:
        section: Dictionary of translations, or a :class:`TranslationFile`.
        infile: Path of the original binary file.
        outfile: Path of the output binary file, already copied from infile.
        binranges: List of (start, end) ranges to scan.
        freeranges: List of (start, end) ranges that can hold relocated
            strings. A range can have a third element with the pointer start
            to use for it, or a boolean to use injectstart.
        readfunc: Function used to detect strings, called with (stream, encoding).
        writefunc: Function used to write strings, called with
            (stream, string, maxlen, encoding).
        encoding: Encoding passed to readfunc and writefunc.
        pointerstart: Value added to file offsets to form pointers, usually
            the load address of the binary.
        injectstart: Pointer start for free ranges marked with a boolean.
        fallbackf: Stream to write strings to when no free range has room.
        injectfallback: Pointer start of the fallback stream, 0 to disable it.
        sectionname: File entry name used when section is a TranslationFile.
        preformat: Function called on each detected string, returning
            (string, pre, post) data passed to postformat.
        postformat: Function called with (translation, pre, post), returning
            the final string to write.
        pointeralign: Alignment required for pointer matches, to skip false
            positives.

    Returns:
        A tuple (notfound, freeranges) with the list of :class:`BinaryPointer`
        that weren't found and the updated free ranges, or None if freeranges
        wasn't given.
    """
    insize = os.path.getsize(infile)
    notfound = []
    with Stream(infile, "rb") as fi:
        if freeranges is not None:
            allbin = fi.read()
            strpointers: dict[str, int] = {}
            freeranges = [list(x) for x in freeranges]
        with Stream(outfile, "r+b") as fo:
            for binrange in binranges:
                fi.seek(binrange[0])
                while fi.tell() < binrange[1] and fi.tell() < insize - 2:
                    pos = fi.tell()
                    check = readfunc(fi, encoding)
                    if check != "":
                        pre = post = ""
                        if preformat is not None:
                            check, pre, post = preformat(check)
                        if isinstance(section, TranslationFile):
                            newsjis = section.getEntry(check, sectionname, pos)
                        else:
                            newsjis = section[check][0] if check in section else ""
                            if newsjis != "":
                                if len(section[check]) > 1:
                                    section[check].pop(0)
                        if newsjis != "":
                            if newsjis == "!":
                                newsjis = ""
                            if postformat is not None:
                                newsjis = postformat(newsjis, pre, post)
                            newsjislog = newsjis.encode("ascii", "ignore")
                            logDebug("Replacing string at", toHex(pos), "with", newsjislog)
                            fo.seek(pos)
                            endpos = fi.tell() - 1
                            newlen = writefunc(fo, newsjis, endpos - pos + 1, encoding)
                            fo.seek(-1, 1)
                            if fo.readByte() != 0:
                                fo.writeZero(1)
                            if newlen < 0:
                                if (freeranges is None and injectfallback == 0) or pointerstart == 0:
                                    logError("String", newsjislog, "is too long.")
                                else:
                                    # Add this to the freeranges
                                    freeranges.append([pos, endpos])
                                    logDebug("Adding new freerange", toHex(pos), toHex(endpos))
                                    range = None
                                    rangelen = 0
                                    for c in newsjis:
                                        rangelen += 1 if ord(c) < 256 else 2
                                    for freerange in freeranges:
                                        if freerange[1] - freerange[0] > rangelen:
                                            range = freerange
                                            break
                                    if range is None and newsjis not in strpointers and injectfallback == 0:
                                        logError("No more room! Skipping", newsjislog, "...")
                                        freeranges.pop()
                                    else:
                                        # Write the string in a new portion of the rom
                                        if newsjis in strpointers:
                                            newpointer = strpointers[newsjis]
                                        elif range is None:
                                            logDebug("No room for the string", newsjislog, ", redirecting to fallback")
                                            fallbackpos = fallbackf.tell()
                                            writefunc(fallbackf, newsjis, 0, encoding)
                                            fallbackf.seek(-1, 1)
                                            if fallbackf.readByte() != 0:
                                                fallbackf.writeZero(1)
                                            newpointer = injectfallback + fallbackpos
                                            strpointers[newsjis] = newpointer
                                        else:
                                            logDebug("No room for the string", newsjislog, ", redirecting to", toHex(range[0]))
                                            fo.seek(range[0])
                                            writefunc(fo, newsjis, 0, encoding)
                                            fo.seek(-1, 1)
                                            if fo.readByte() != 0:
                                                fo.writeZero(1)
                                            newpointer = range[0]
                                            # For the injected range, add injectstart, otherwise add pointerstart
                                            if (len(range) == 3):
                                                if isinstance(range[2], bool):
                                                    newpointer += injectstart
                                                else:
                                                    newpointer += int(range[2])
                                            else:
                                                newpointer += pointerstart
                                            range[0] = fo.tell()
                                            strpointers[newsjis] = newpointer
                                        # Search and replace the old pointer
                                        pointer = pointerstart + pos
                                        pointersearch = struct.pack("<I", pointer)
                                        index = 0
                                        logDebug("Searching for pointer", toHex(pointer))
                                        foundone = False
                                        while index < len(allbin):
                                            index = allbin.find(pointersearch, index)
                                            if index < 0:
                                                break
                                            # Skip matches that aren't aligned: the pattern can collide with
                                            # bytes inside code/data, and overwriting those corrupts the binary
                                            if pointeralign > 1 and index % pointeralign != 0:
                                                index += 1
                                                continue
                                            foundone = True
                                            logDebug("Replaced pointer at", toHex(pointerstart + index), "with", toHex(newpointer))
                                            fo.seek(index)
                                            fo.writeUInt(newpointer)
                                            index += 4
                                        if not foundone:
                                            logWarning("Pointer", toHex(pointer), "->", toHex(newpointer), "not found for string", newsjislog)
                                            # freeranges.pop()
                                            notfound.append(BinaryPointer(pointer, newpointer, newsjislog))
                            else:
                                fo.writeZero(endpos - fo.tell())
                        pos = fi.tell() - 1
                    fi.seek(pos + 1)
    return notfound, freeranges


# Folders
def makeFolder(folder: str, clear: bool = True) -> None:
    """Create a folder, optionally deleting an existing one first.

    Args:
        folder: Path of the folder to create.
        clear: Whether to delete the existing folder first.
    """
    if clear:
        clearFolder(folder)
    os.mkdir(folder)


def clearFolder(folder: str) -> None:
    """Delete a folder and its contents, clearing read-only flags.

    Args:
        folder: Path of the folder to delete.
    """
    if os.path.isdir(folder):
        # Ensure files aren't marked as read-only
        for root, dirs, files in os.walk(folder, topdown=False):
            for name in files:
                filename = os.path.join(root, name)
                os.chmod(filename, stat.S_IWUSR)
        shutil.rmtree(folder)


def copyFolder(f1: str, f2: str) -> None:
    """Copy a folder, replacing the destination.

    Args:
        f1: Path of the source folder.
        f2: Path of the destination folder.
    """
    clearFolder(f2)
    shutil.copytree(f1, f2)


def mergeFolder(f1: str, f2: str) -> None:
    """Copy a folder into another, overwriting the files that exist in both.

    Args:
        f1: Path of the source folder.
        f2: Path of the destination folder.
    """
    shutil.copytree(f1, f2, dirs_exist_ok=True)


def copyFile(f1: str, f2: str) -> None:
    """Copy a file, replacing the destination.

    Args:
        f1: Path of the source file.
        f2: Path of the destination file.
    """
    if os.path.isfile(f2):
        os.remove(f2)
    shutil.copyfile(f1, f2)


def makeFolders(path: str) -> None:
    """Create a folder and its parents, ignoring the ones that exist.

    Args:
        path: Path of the folder to create.
    """
    try:
        os.makedirs(path)
    except FileExistsError:
        pass


def getFiles(path: str, extensions: str | list = []) -> list[str]:
    """List all the files in a folder, recursively.

    Args:
        path: Path of the folder to scan.
        extensions: Extension or list of extensions to filter by.

    Returns:
        The file paths relative to path, sorted and with forward slashes.
    """
    if isinstance(extensions, str) and extensions != "":
        extensions = [extensions]
    ret = []
    for (root, dirs, files) in os.walk(path):
        for file in sorted(files):
            file = os.path.join(root, file).replace(path, "").replace("\\", "/")
            if len(extensions) > 0 and os.path.splitext(file)[1] not in extensions:
                continue
            ret.append(file)
    return ret


def getFolders(path: str) -> list[str]:
    """List all the subfolders in a folder, recursively.

    Args:
        path: Path of the folder to scan.

    Returns:
        The folder paths relative to path, sorted and with forward slashes.
    """
    ret = []
    for (root, dirs, files) in os.walk(path):
        for dir in sorted(dirs):
            dir = os.path.join(root, dir).replace(path, "").replace("\\", "/")
            ret.append(dir)
    return ret


def bundledFile(name: str) -> str:
    """Get the path of a data file, supporting PyInstaller bundles.

    Args:
        name: Name of the file.

    Returns:
        The file name, or its path in the PyInstaller temporary folder.
    """
    if os.path.isfile(name):
        return name
    try:
        return os.path.join(sys._MEIPASS, name)
    except AttributeError:
        return name


def bundledExecutable(name: str) -> str:
    """Get the path of an executable, supporting PyInstaller bundles.

    The .exe extension is stripped when not running on Windows.

    Args:
        name: Name of the executable, with the .exe extension.

    Returns:
        The executable path, possibly in the PyInstaller temporary folder.
    """
    if os.name != "nt":
        name = name.replace(".exe", "")
    if os.path.isfile(name):
        if os.name != "nt":
            name = "./" + name
        return name
    try:
        return os.path.join(sys._MEIPASS, name)
    except AttributeError:
        return name


def execute(cmd: str, show: bool = True) -> None:
    """Run a command, logging its output.

    Args:
        cmd: Command line to run.
        show: Whether to log the output at info level instead of debug.
    """
    result = ""
    try:
        if os.name != "nt":
            result = str(subprocess.check_output(shlex.split(cmd)))
        else:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            result = str(subprocess.check_output(cmd, startupinfo=startupinfo))
    except FileNotFoundError:
        logError("Command too long:", len(cmd), cmd)
        if result != "":
            logError(result)
        return
    except subprocess.CalledProcessError:
        logError("Command error", cmd)
        if result != "":
            logError(result)
        return
    if result != "":
        if show:
            logMessage(result)
        else:
            logDebug(result)


def crcFile(f: str) -> int:
    """Calculate the CRC32 checksum of a file.

    Args:
        f: Path of the file.

    Returns:
        The CRC32 checksum.
    """
    buffersize = 0x10000
    crc = 0
    with open(f, "rb") as crcf:
        buffer = crcf.read(buffersize)
        while len(buffer) > 0:
            crc = zlib.crc32(buffer, crc)
            buffer = crcf.read(buffersize)
    return crc & 0xffffffff


def crc16(data: bytes) -> int:
    """Calculate the CRC16 checksum of some data, in the MODBUS variant.

    Args:
        data: Data to checksum.

    Returns:
        The CRC16 checksum.
    """
    crc = 0xffff
    for i in range(len(data)):
        crc ^= data[i]
        for j in range(8):
            carry = crc & 1
            crc >>= 1
            if carry:
                crc ^= 0xa001
    return crc & 0xffff


def xdeltaPatch(patchfile: str, infile: str, outfile: str) -> None:
    """Create an xdelta patch, using pyxdelta or calling the xdelta executable externally.

    Args:
        patchfile: Path of the patch file to create.
        infile: Path of the original file.
        outfile: Path of the modified file.
    """
    logMessage("Creating xdelta patch", patchfile, "...")
    try:
        import pyxdelta
        pyxdelta.run(infile, outfile, patchfile)
    except ImportError:
        xdelta = bundledExecutable("xdelta.exe")
        if not os.path.isfile(xdelta):
            logError("xdelta not found")
            return
        execute(xdelta + " -f -e -s \"{rom}\" \"{rompatch}\" \"{patch}\"".format(rom=infile, rompatch=outfile, patch=patchfile), False)
    logMessage("Done!")


def ipsPatch(patchfile: str, infile: str, outfile: str) -> None:
    """Create an ips patch, using ips_util.

    Args:
        patchfile: Path of the patch file to create.
        infile: Path of the original file.
        outfile: Path of the modified file.
    """
    try:
        from ips_util import Patch
    except ImportError:
        logError("ips_util not found")
        return
    logMessage("Creating ips patch", patchfile, "...")
    with Stream(infile, "rb") as f:
        indata = f.read()
    with Stream(outfile, "rb") as f:
        outdata = f.read()
    result = Patch.create(indata, outdata)
    with Stream(patchfile, "wb") as f:
        f.write(result.encode())
    logMessage("Done!")


def armipsPatch(file: str, defines: dict = {}, labels: dict = {}) -> None:
    """Apply an armips patch, using pyarmips or calling the armips executable externally.

    Args:
        file: Path of the asm file.
        defines: Dictionary of symbol -> value, passed as -equ.
        labels: Dictionary of label -> value, passed as -definelabel.
    """
    logMessage("Applying armips patch ...")
    try:
        import pyarmips
        pyarmips.run(file)
    except ImportError:
        armips = bundledExecutable("armips.exe")
        if not os.path.isfile(armips):
            logError("armips not found")
            return
        params = ""
        for define in defines:
            params += " -equ " + define + " " + str(defines[define])
        for label in labels:
            params += " -definelabel " + label + " " + str(labels[label])
        execute(armips + " {binpatch}{params}".format(binpatch=file, params=params), False)
    logMessage("Done!")


def deltaToFrame(delta, fps: int = 30) -> int:
    """Convert a time delta to a frame count.

    Args:
        delta: datetime.timedelta to convert.
        fps: Frames per second.

    Returns:
        The number of frames, rounded up.
    """
    return int((delta.seconds * fps) + math.ceil(delta.microseconds / (1000 * 1000 / fps)))


# Generic texture
def readPalette(p: int) -> tuple:
    """Convert a 15-bit BGR color to an opaque RGBA tuple.

    Args:
        p: 15-bit color value.

    Returns:
        The (r, g, b, 255) tuple.
    """
    return (((p >> 0) & 0x1f) << 3, ((p >> 5) & 0x1f) << 3, ((p >> 10) & 0x1f) << 3, 0xff)


def getColorDistance(c1: tuple, c2: tuple, checkalpha: bool = False) -> float:
    """Calculate the Euclidean distance between two colors.

    Args:
        c1: First color, as an RGB or RGBA tuple.
        c2: Second color, as an RGB or RGBA tuple.
        checkalpha: Whether to include the alpha channel.

    Returns:
        The distance between the colors.
    """
    if len(c1) == 4:
        (r1, g1, b1, a1) = c1
    else:
        (r1, g1, b1) = c1
        a1 = 255
    if len(c2) == 4:
        (r2, g2, b2, a2) = c2
    else:
        (r2, g2, b2) = c2
        a2 = 255
    sum = (r1 - r2) ** 2 + (g1 - g2) ** 2 + (b1 - b2) ** 2
    if checkalpha:
        sum += (a1 - a2) ** 2
    return math.sqrt(sum)


def sumColors(c1: tuple, c2: tuple, a: int = 1, b: int = 1, c: int = 2) -> tuple:
    """Calculate the weighted sum (c1 * a + c2 * b) / c of two colors.

    Args:
        c1: First color, as an RGBA tuple. The result keeps its alpha.
        c2: Second color, as an RGBA tuple.
        a: Weight of the first color.
        b: Weight of the second color.
        c: Divisor of the weighted sum.

    Returns:
        The resulting RGBA tuple.
    """
    (r1, g1, b1, a1) = c1
    (r2, g2, b2, a2) = c2
    return ((r1 * a + r2 * b) // c, (g1 * a + g2 * b) // c, (b1 * a + b2 * b) // c, a1)


# https://github.com/marco-calautti/Rainbow/blob/master/Rainbow.ImgLib/ImgLib/Common/ImageUtils.cs
cc38 = [
    0x00, 0x24, 0x49, 0x6d,  0x92, 0xb6, 0xdb, 0xff
]
cc48 = [
    0x00, 0x11, 0x22, 0x33,  0x44, 0x55, 0x66, 0x77,  0x88, 0x99, 0xaa, 0xbb,  0xcc, 0xdd, 0xee, 0xff
]
cc58 = [
    0x00, 0x08, 0x10, 0x19,  0x21, 0x29, 0x31, 0x3a,  0x42, 0x4a, 0x52, 0x5a,  0x63, 0x6b, 0x73, 0x7b,
    0x84, 0x8c, 0x94, 0x9c,  0xa5, 0xad, 0xb5, 0xbd,  0xc5, 0xce, 0xd6, 0xde,  0xe6, 0xef, 0xf7, 0xff
]


# https://github.com/marco-calautti/Rainbow/blob/master/Rainbow.ImgLib/ImgLib/Encoding/Implementation/ColorCodecRGB5A3.cs
def readRGB5A3(color: int) -> tuple:
    """Convert an RGB5A3 color to an RGBA tuple.

    If the high bit is set the color is an opaque RGB555, otherwise it has
    a 3-bit alpha and 4-bit color channels.

    Args:
        color: 16-bit color value.

    Returns:
        The (r, g, b, a) tuple.
    """
    r, g, b, a = (0, 0, 0, 0)
    if color & 0x8000 != 0:
        a = 255
        r = cc58[(color >> 10) & 0x1f]
        g = cc58[(color >> 5) & 0x1f]
        b = cc58[(color) & 0x1f]
    else:
        a = cc38[(color >> 12) & 0x7]
        r = cc48[(color >> 8) & 0xf]
        g = cc48[(color >> 4) & 0xf]
        b = cc48[(color) & 0xf]
    return (r, g, b, a)


def readRGB5A1(color: int) -> tuple:
    """Convert an RGB5A1 color to an RGBA tuple.

    Args:
        color: 16-bit color value.

    Returns:
        The (r, g, b, a) tuple, with a either 0 or 255.
    """
    r = cc58[color & 0x1f]
    g = cc58[color >> 5 & 0x1f]
    b = cc58[color >> 10 & 0x1f]
    a = 0 if (color >> 15 & 0x1) == 0 else 255
    return (r, g, b, a)


def getPaletteIndex(palette: list, color: tuple, fixtransp: bool = False, starti: int = 0, palsize: int = -1, checkalpha: bool = False, zerotransp: bool = True, backwards: bool = False, logcolor: bool = False) -> int:
    """Get the index of the palette color that best matches a color.

    Args:
        palette: List of RGBA color tuples.
        color: RGBA color tuple to search for.
        fixtransp: Whether to skip the first palette entry when matching.
        starti: Index of the first palette entry to consider.
        palsize: Number of palette entries to consider, or -1 for all.
        checkalpha: Whether to compare the alpha channel too.
        zerotransp: Whether to return 0 for fully transparent colors.
        backwards: Whether to search the palette backwards.
        logcolor: Whether to log colors that aren't matched exactly.

    Returns:
        The index of the exact color or of the closest one, relative to starti.
    """
    if zerotransp and color[3] == 0:
        return 0
    if palsize == -1:
        palsize = len(palette)
    zeroalpha = -1
    palrange = range(starti, starti + palsize)
    if backwards:
        palrange = reversed(palrange)
    for i in palrange:
        if fixtransp and i == starti:
            continue
        if palette[i][0] == color[0] and palette[i][1] == color[1] and palette[i][2] == color[2] and (not checkalpha or palette[i][3] == color[3]):
            return i - starti
        if checkalpha and palette[i][3] == 0:
            zeroalpha = i - starti
    if palette[starti][0] == color[0] and palette[starti][1] == color[1] and palette[starti][2] == color[2] and (not checkalpha or palette[starti][3] == color[3]):
        return 0
    if checkalpha and color[3] == 0 and zeroalpha != -1:
        return zeroalpha
    mindist = 0xffffffff
    disti = 0
    palrange = range(starti + 1, starti + palsize)
    if backwards:
        palrange = reversed(palrange)
    for i in palrange:
        distance = getColorDistance(color, palette[i], checkalpha)
        if distance < mindist:
            mindist = distance
            disti = i - starti
    if logcolor:
        logDebug("Color", color, "not found, closest color:", palette[disti])
    return disti


def findBestPalette(palettes: list, colors: list) -> int:
    """Get the index of the palette that best matches a list of colors.

    Args:
        palettes: List of palettes, each a list of RGBA color tuples.
        colors: List of RGBA color tuples to match.

    Returns:
        The index of the palette with the smallest total distance.
    """
    if len(palettes) == 1:
        return 0
    mindist = 0xffffffff
    disti = 0
    for i in range(len(palettes)):
        distance = 0
        for color in colors:
            singledist = 0xffffffff
            for palcolor in palettes[i]:
                singledist = min(singledist, getColorDistance(color, palcolor))
            distance += singledist
        if distance < mindist:
            mindist = distance
            disti = i
            if mindist == 0:
                break
    return disti


def drawPalette(pixels, palette: list, width: int, ystart: int = 0, transp: bool = True):
    """Draw a palette as 5x5 pixel swatches, 8 per row.

    Args:
        pixels: PIL pixel access object to draw on.
        palette: List of RGBA color tuples.
        width: X position to start drawing at, usually the image width.
        ystart: Y position to start drawing at.
        transp: Whether to keep the alpha channel of the colors.

    Returns:
        The pixels object.
    """
    for x in range(len(palette)):
        j = width + ((x % 8) * 5)
        i = ystart + ((x // 8) * 5)
        for j2 in range(5):
            for i2 in range(5):
                color = palette[x]
                if not transp:
                    color = (color[0], color[1], color[2], 255)
                pixels[j + j2, i + i2] = color
    return pixels


def flipTile(tile: list, hflip: bool, vflip: bool, tilewidth: int = 8, tileheight: int = 8) -> list:
    """Flip a tile horizontally and/or vertically.

    Args:
        tile: Flat list of tile values, one row after the other.
        hflip: Whether to flip the tile horizontally.
        vflip: Whether to flip the tile vertically.
        tilewidth: Width of the tile.
        tileheight: Height of the tile.

    Returns:
        The flipped tile, as a new list.
    """
    newtile = [0] * len(tile)
    xrange = range(0, tilewidth) if not hflip else range(tilewidth - 1, -1, -1)
    yrange = range(0, tileheight) if not vflip else range(tileheight - 1, -1, -1)
    i = 0
    for y in yrange:
        for x in xrange:
            newtile[i] = tile[y * tileheight + x]
            i += 1
    return newtile
