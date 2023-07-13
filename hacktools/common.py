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
    def __init__(self, fpath="", mode="m", little=True):
        self.f = fpath
        self.mode = mode
        self.endian = "<" if little else ">"
        self.half = None

    def __enter__(self):
        if self.mode == "m":
            self.f = BytesIO()
        else:
            self.f = open(self.f, self.mode)
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.f.close()

    def close(self):
        self.f.close()

    def tell(self):
        return self.f.tell()

    def seek(self, pos, whence=0):
        self.f.seek(pos, whence)

    def read(self, n=-1):
        return self.f.read(n)

    def readAt(self, pos, n=-1):
        current = self.tell()
        self.seek(pos)
        ret = self.read(n)
        self.seek(current)
        return ret

    def write(self, data):
        self.f.write(data)

    def writeAt(self, pos, data):
        current = self.tell()
        self.seek(pos)
        self.write(data)
        self.seek(current)

    def peek(self, n):
        pos = self.tell()
        ret = self.read(n)
        self.seek(pos)
        return ret

    def writeLine(self, data):
        self.f.write(data + "\n")

    def setEndian(self, little):
        self.endian = "<" if little else ">"

    def swapEndian(self):
        self.endian = "<" if self.endian == ">" else ">"

    def readLong(self):
        return struct.unpack(self.endian + "q", self.read(8))[0]

    def readLongAt(self, pos):
        current = self.tell()
        self.seek(pos)
        ret = self.readLong()
        self.seek(current)
        return ret

    def readULong(self):
        return struct.unpack(self.endian + "Q", self.read(8))[0]

    def readULongAt(self, pos):
        current = self.tell()
        self.seek(pos)
        ret = self.readULong()
        self.seek(current)
        return ret

    def readInt(self):
        return struct.unpack(self.endian + "i", self.read(4))[0]

    def readIntAt(self, pos):
        current = self.tell()
        self.seek(pos)
        ret = self.readInt()
        self.seek(current)
        return ret

    def readUInt(self):
        return struct.unpack(self.endian + "I", self.read(4))[0]

    def readUIntAt(self, pos):
        current = self.tell()
        self.seek(pos)
        ret = self.readUInt()
        self.seek(current)
        return ret

    def readFloat(self):
        return struct.unpack(self.endian + "f", self.read(4))[0]

    def readFloatAt(self, pos):
        current = self.tell()
        self.seek(pos)
        ret = self.readFloat()
        self.seek(current)
        return ret

    def readDouble(self):
        return struct.unpack(self.endian + "d", self.read(8))[0]

    def readDoubleAt(self, pos):
        current = self.tell()
        self.seek(pos)
        ret = self.readDouble()
        self.seek(current)
        return ret

    def readShort(self):
        return struct.unpack(self.endian + "h", self.read(2))[0]

    def readShortAt(self, pos):
        current = self.tell()
        self.seek(pos)
        ret = self.readShort()
        self.seek(current)
        return ret

    def readUShort(self):
        return struct.unpack(self.endian + "H", self.read(2))[0]

    def readUShortAt(self, pos):
        current = self.tell()
        self.seek(pos)
        ret = self.readUShort()
        self.seek(current)
        return ret

    def readByte(self):
        return struct.unpack("B", self.read(1))[0]

    def readByteAt(self, pos):
        current = self.tell()
        self.seek(pos)
        ret = self.readByte()
        self.seek(current)
        return ret

    def readSByte(self):
        return struct.unpack("b", self.read(1))[0]

    def readSByteAt(self, pos):
        current = self.tell()
        self.seek(pos)
        ret = self.readSByte()
        self.seek(current)
        return ret

    def readHalf(self):
        if self.half is None:
            self.half = self.readByte()
            return self.half & 0x0f
        else:
            ret = self.half >> 4
            self.half = None
            return ret

    def readZeros(self, size):
        while self.tell() < size:
            byte = self.readByte()
            if byte != 0x00:
                self.seek(-1, 1)
                break

    def readBytes(self, n):
        ret = ""
        for i in range(n):
            ret += toHex(self.readByte()) + " "
        return ret

    def readString(self, length):
        ret = ""
        for _ in range(length):
            byte = self.readByte()
            # These control characters can be found in texture names, replace them with a space
            if byte == 0x82 or byte == 0x86:
                byte = 0x20
            if byte != 0:
                ret += chr(byte)
        return ret

    def readStringAt(self, pos, length):
        current = self.tell()
        self.seek(pos)
        ret = self.readString(length)
        self.seek(current)
        return ret

    def readNullString(self):
        ret = ""
        while True:
            byte = self.readByte()
            if byte == 0:
                break
            else:
                ret += chr(byte)
        return ret

    def readNullStringAt(self, pos):
        current = self.tell()
        self.seek(pos)
        ret = self.readNullString()
        self.seek(current)
        return ret

    def readEncodedString(self, encoding="utf-8"):
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

    def readEncodedStringAt(self, pos, encoding="utf-8"):
        current = self.tell()
        self.seek(pos)
        ret = self.readEncodedString(encoding)
        self.seek(current)
        return ret

    def writeLong(self, num):
        self.f.write(struct.pack(self.endian + "q", num))

    def writeLongAt(self, pos, num):
        current = self.tell()
        self.seek(pos)
        self.writeLong(num)
        self.seek(current)

    def writeULong(self, num):
        self.f.write(struct.pack(self.endian + "Q", num))

    def writeULongAt(self, pos, num):
        current = self.tell()
        self.seek(pos)
        self.writeULong(num)
        self.seek(current)

    def writeInt(self, num):
        self.f.write(struct.pack(self.endian + "i", num))

    def writeIntAt(self, pos, num):
        current = self.tell()
        self.seek(pos)
        self.writeInt(num)
        self.seek(current)

    def writeUInt(self, num):
        self.f.write(struct.pack(self.endian + "I", num))

    def writeUIntAt(self, pos, num):
        current = self.tell()
        self.seek(pos)
        self.writeUInt(num)
        self.seek(current)

    def writeFloat(self, num):
        self.f.write(struct.pack(self.endian + "f", num))

    def writeFloatAt(self, pos, num):
        current = self.tell()
        self.seek(pos)
        self.writeFloat(num)
        self.seek(current)

    def writeDouble(self, num):
        self.f.write(struct.pack(self.endian + "d", num))

    def writeDoubleAt(self, pos, num):
        current = self.tell()
        self.seek(pos)
        self.writeDouble(num)
        self.seek(current)

    def writeShort(self, num):
        self.f.write(struct.pack(self.endian + "h", num))

    def writeShortAt(self, pos, num):
        current = self.tell()
        self.seek(pos)
        self.writeShort(num)
        self.seek(current)

    def writeUShort(self, num):
        self.f.write(struct.pack(self.endian + "H", num))

    def writeUShortAt(self, pos, num):
        current = self.tell()
        self.seek(pos)
        self.writeUShort(num)
        self.seek(current)

    def writeByte(self, num):
        self.f.write(struct.pack("B", num))

    def writeByteAt(self, pos, num):
        current = self.tell()
        self.seek(pos)
        self.writeByte(num)
        self.seek(current)

    def writeSByte(self, num):
        self.f.write(struct.pack("b", num))

    def writeSByteAt(self, pos, num):
        current = self.tell()
        self.seek(pos)
        self.writeSByte(num)
        self.seek(current)

    def writeHalf(self, num, little=True):
        if self.half is None:
            self.half = num
        else:
            if little:
                self.writeByte((num << 4) | self.half)
            else:
                self.writeByte((self.half << 4) | num)
            self.half = None

    def writeString(self, str):
        self.f.write(str.encode("ascii"))

    def writeZero(self, num):
        self.writeBytes(0x0, num)

    def writeBytes(self, byte, num):
        if num > 0:
            for i in range(num):
                self.writeByte(byte)

    def truncate(self):
        self.f.truncate()


# CLI/GUI
if hasClick:
    appname = ""
    appversion = ""
    datafolder = ""
    filecheck = ""
    crc = -1


    def setupTool(_appname="", _appversion="", _datafolder="", _filecheck="", _crc=-1):
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


    def runStartup(nocrc=False):
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
        if crc >= 0 and not nocrc:
            checkcrc = crcFile(filecheck)
            if crc != checkcrc:
                logMessage("Checksum mismatch for", filecheck, "(" + toHex(checkcrc) + ", expected", toHex(crc) + ")")
                logMessage("The tool might still work but you should run it on a good dump of the game.")
        return True


    def runCLI():
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


    def runGUI():
        global hasGUI
        hasGUI = True
        from .gui import GUIApp
        guiapp = GUIApp()
        guiapp.initialize(cli, appname, appversion, datafolder)
        guiapp.mainloop()


# Logging
class FileFilter(logging.Filter):
    def filter(self, record):
        return not record.getMessage().startswith("prg-")


def setupFileLogging(log):
    logging.getLogger("PIL.PngImagePlugin").setLevel(logging.CRITICAL + 1)
    filehandler = logging.FileHandler(filename="tool.log", encoding="utf-8", mode="w")
    filehandler.addFilter(FileFilter())
    logging.basicConfig(handlers=[filehandler], format="[%(levelname)s] %(message)s", level=logging.DEBUG if log else logging.INFO)


def logMessage(*messages):
    message = " ".join(str(x) for x in messages)
    logging.info(message)
    if hasTqdm and sys.stdout is not None:
        tqdm.write(message)


def logDebug(*messages):
    message = " ".join(str(x) for x in messages)
    logging.debug(message)


def logWarning(*messages):
    message = " ".join(str(x) for x in messages)
    logging.debug("[WARNING]" + message)


def logError(*messages):
    message = " ".join(str(x) for x in messages)
    logging.error(message)
    if hasTqdm and sys.stdout is not None:
        tqdm.write("[ERROR] " + message)


def varsHex(o):
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
    if hasTqdm:
        if hasGUI:
            from .gui import tqdm_gui
            return tqdm_gui(iterable=iterable)
        else:
            return tqdm(iterable=iterable)
    return iterable


# Strings
def toHex(byte):
    hexstr = hex(byte)[2:].lower()
    if len(hexstr) == 1:
        return "0" + hexstr
    if hexstr[0] == "x":
        return "-" + hexstr[1:]
    return hexstr


def isAscii(s):
    for i in range(len(s)):
        if ord(s[i]) >= 128 or ord(s[i]) < 0x20:
            return False
    return True


def codeToChar(code, encoding="shift_jis"):
    try:
        if code < 256:
            return struct.pack("B", code).decode("ascii")
        return struct.pack(">H", code).decode(encoding)
    except UnicodeDecodeError:
        return ""


def loadTable(tablefile):
    if os.path.isfile(tablefile):
        with codecs.open(tablefile, "r", "utf-8") as ft:
            for line in ft:
                line = line.strip("\r\n")
                if line.find("=") > 0:
                    linesplit = line.split("=", 1)
                    table[linesplit[0]] = linesplit[1]


def shiftPointer(pointer, pointerdiff):
    newpointer = pointer
    for k, v in pointerdiff.items():
        if k < pointer:
            newpointer += v
    # if newpointer != pointer:
    #    logDebug("Shifted pointer", toHex(pointer), "to", toHex(newpointer))
    return newpointer


def checkShiftJIS(first, second):
    # Based on https://www.lemoda.net/c/detect-shift-jis/
    status = False
    if (first >= 0x81 and first <= 0x84) or (first >= 0x87 and first <= 0x9f):
        if second >= 0x40 and second <= 0xfc:
            status = True
    elif first >= 0xe0 and first <= 0xef:
        if second >= 0x40 and second <= 0xfc:
            status = True
    return status


def openSection(file, filestart=1, fileend=10):
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


def getSectionNames(f):
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


def getSection(f, title, comment="#", fixchars=[], justone=True, inorder=False):
    ret = {} if not inorder else []
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


def getSections(file, comment="#", fixchars=[], inorder=False):
    sections = {}
    with codecs.open(file, "r", "utf-8") as wsb:
        files = getSectionNames(wsb)
        for file in files:
            sections[file] = getSection(wsb, file, comment, fixchars, inorder=inorder)
    return sections


def getSectionPercentage(section, chartot=0, transtot=0):
    for s in section.keys():
        strlen = len(s)
        for s2 in section[s]:
            chartot += strlen
            if s2 != "":
                transtot += strlen
    return chartot, transtot


def mergeSections(file1, file2, output, comment="#", fixchars=[]):
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
    def __init__(self, path=""):
        self.files = {}
        self.lookup = {}
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

    def mergeSection(self, path, filename="", section="", comments="#", fixchars=[]):
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
    
    def addEntry(self, text, filename, offset, translation="", comment=""):
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

    def preloadLookup(self):
        self.lookup = {}
        self.chartot = 0
        self.transtot = 0
        for file in self.files:
            for unit in self.files[file][0]:
                self.chartot += len(unit[0].text)
                if unit[1].text is not None and unit[1].text != "":
                    self.lookup[unit[0].text] = unit[1].text
                    self.transtot += len(unit[0].text)

    def getEntry(self, text, filename, offset):
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

    def hasFile(self, filename):
        return filename in self.files

    def getProgress(self):
        if self.chartot == 0:
            return 0
        return (100 * self.transtot) / self.chartot

    def save(self, filename, dummy=False):
        if dummy:
            self.addEntry("dummy line", "dummy", 0, "dummy translation", "Ignore this")
        makeFolders(os.path.dirname(filename))
        self._pretty_print(self.root)
        xmlstr = ET.tostring(self.root, encoding="unicode", xml_declaration=True)
        # Change this to match what Weblate does
        xmlstr = xmlstr.replace("<target />", "<target/>") + "\n"
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
    def __init__(self, start, width, length, char="", code=0, index=0):
        self.start = start
        self.width = width
        self.length = length
        self.char = char
        self.code = code
        self.index = index


def wordwrap(text, glyphs, width, codefunc=None, default=6, linebreak="|", sectionsep=">>", strip=True):
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


def centerLines(text, glyphs, width, codefunc=None, default=6, linebreak="|", centercode="<<"):
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


def readEncodedString(f, encoding="shift_jis"):
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
                    sjis += "UNK(" + toHex(b1) + toHex(b2) + ")"
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


def detectEncodedString(f, encoding="shift_jis", startascii=[0x25], startenc=[]):
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
                    ret += "UNK(" + toHex(b1) + toHex(b2) + ")"
            elif (b1, b2) in startenc or (len(ret) > 1 and ret.count("UNK(") < 5):
                ret += "UNK(" + toHex(b1) + toHex(b2) + ")"
            else:
                return ""
    return ret


def detectASCIIString(f, encoding="ascii", startascii=[]):
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


def writeEncodedString(f, s, maxlen=0, encoding="shift_jis"):
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
    f.writeByte(0x00)
    return i


def extractBinaryStrings(infile, binranges, func=detectEncodedString, encoding="shift_jis"):
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
                        logDebug("Found string at", pos)
                        strings.append(check)
                        positions.append([pos])
                    else:
                        positions[strings.index(check)].append(pos)
                    pos = f.tell() - 1
                f.seek(pos + 1)
    return strings, positions


class BinaryPointer:
    def __init__(self, old, new, str):
        self.old = old
        self.new = new
        self.str = str


def repackBinaryStrings(section, infile, outfile, binranges, freeranges=None, readfunc=detectEncodedString, writefunc=writeEncodedString, encoding="shift_jis", pointerstart=0, injectstart=0, fallbackf=None, injectfallback=0, sectionname="bin"):
    insize = os.path.getsize(infile)
    notfound = []
    with Stream(infile, "rb") as fi:
        if freeranges is not None:
            allbin = fi.read()
            strpointers = {}
            freeranges = [list(x) for x in freeranges]
        with Stream(outfile, "r+b") as fo:
            for binrange in binranges:
                fi.seek(binrange[0])
                while fi.tell() < binrange[1] and fi.tell() < insize - 2:
                    pos = fi.tell()
                    check = readfunc(fi, encoding)
                    if check != "":
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
                                    logDebug("Adding new freerage", toHex(pos), toHex(endpos))
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
                                                newpointer += injectstart
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
    return notfound


# Folders
def makeFolder(folder, clear=True):
    if clear:
        clearFolder(folder)
    os.mkdir(folder)


def clearFolder(folder):
    if os.path.isdir(folder):
        shutil.rmtree(folder)


def copyFolder(f1, f2):
    clearFolder(f2)
    shutil.copytree(f1, f2)


def mergeFolder(f1, f2):
    import distutils.dir_util
    distutils.dir_util.copy_tree(f1, f2, verbose=0)


def copyFile(f1, f2):
    if os.path.isfile(f2):
        os.remove(f2)
    shutil.copyfile(f1, f2)


def makeFolders(path):
    try:
        os.makedirs(path)
    except FileExistsError:
        pass


def getFiles(path, extensions=[]):
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


def getFolders(path):
    ret = []
    for (root, dirs, files) in os.walk(path):
        for dir in sorted(dirs):
            dir = os.path.join(root, dir).replace(path, "").replace("\\", "/")
            ret.append(dir)
    return ret


def bundledFile(name):
    if os.path.isfile(name):
        return name
    try:
        return os.path.join(sys._MEIPASS, name)
    except AttributeError:
        return name


def bundledExecutable(name):
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


def execute(cmd, show=True):
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


def crcFile(f):
    buffersize = 0x10000
    crc = 0
    with open(f, "rb") as crcf:
        buffer = crcf.read(buffersize)
        while len(buffer) > 0:
            crc = zlib.crc32(buffer, crc)
            buffer = crcf.read(buffersize)
    return crc & 0xffffffff


def crc16(data):
    crc = 0xffff
    for i in range(len(data)):
        crc ^= data[i]
        for j in range(8):
            carry = crc & 1
            crc >>= 1
            if carry:
                crc ^= 0xa001
    return crc & 0xffff


def xdeltaPatch(patchfile, infile, outfile):
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


def ipsPatch(patchfile, infile, outfile):
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


def armipsPatch(file, defines={}, labels={}):
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


def deltaToFrame(delta, fps=30):
    return int((delta.seconds * fps) + math.ceil(delta.microseconds / (1000 * 1000 / fps)))


# Generic texture
def readPalette(p):
    return (((p >> 0) & 0x1f) << 3, ((p >> 5) & 0x1f) << 3, ((p >> 10) & 0x1f) << 3, 0xff)


def getColorDistance(c1, c2, checkalpha=False):
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


def sumColors(c1, c2, a=1, b=1, c=2):
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
def readRGB5A3(color):
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


def readRGB5A1(color):
    r = cc58[color & 0x1f]
    g = cc58[color >> 5 & 0x1f]
    b = cc58[color >> 10 & 0x1f]
    a = 0 if (color >> 15 & 0x1) == 0 else 255
    return (r, g, b, a)


def getPaletteIndex(palette, color, fixtransp=False, starti=0, palsize=-1, checkalpha=False, zerotransp=True, backwards=False, logcolor=False):
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


def findBestPalette(palettes, colors):
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


def drawPalette(pixels, palette, width, ystart=0, transp=True):
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


def flipTile(tile, hflip, vflip, tilewidth=8, tileheight=8):
    newtile = [0] * len(tile)
    xrange = range(0, tilewidth) if not hflip else range(tilewidth - 1, -1, -1)
    yrange = range(0, tileheight) if not vflip else range(tileheight - 1, -1, -1)
    i = 0
    for y in yrange:
        for x in xrange:
            newtile[i] = tile[y * tileheight + x]
            i += 1
    return newtile
