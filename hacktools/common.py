import codecs
from io import BytesIO, StringIO
import distutils.dir_util
import logging
import math
import os
import re
import shutil
import sys
import struct
import subprocess
import click
from tqdm import tqdm

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

    def tell(self):
        return self.f.tell()

    def seek(self, pos, whence=0):
        self.f.seek(pos, whence)

    def read(self, n=-1):
        return self.f.read(n)

    def write(self, data):
        self.f.write(data)

    def peek(self, n):
        pos = self.tell()
        ret = self.read(n)
        self.seek(pos)
        return ret

    def writeLine(self, data):
        self.f.write(data + "\n")

    def readInt(self):
        return struct.unpack(self.endian + "i", self.read(4))[0]

    def readUInt(self):
        return struct.unpack(self.endian + "I", self.read(4))[0]

    def readShort(self):
        return struct.unpack(self.endian + "h", self.read(2))[0]

    def readUShort(self):
        return struct.unpack(self.endian + "H", self.read(2))[0]

    def readByte(self):
        return struct.unpack("B", self.read(1))[0]

    def readSByte(self):
        return struct.unpack("b", self.read(1))[0]

    def readHalf(self):
        if self.half is None:
            self.half = self.readByte()
            return self.half & 0x0F
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
        str = ""
        for i in range(length):
            byte = self.readByte()
            # These control characters can be found in texture names, replace them with a space
            if byte == 0x82 or byte == 0x86:
                byte = 0x20
            if byte != 0:
                str += chr(byte)
        return str

    def readNullString(self):
        str = ""
        while True:
            byte = self.readByte()
            if byte == 0:
                break
            else:
                str += chr(byte)
        return str

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

    def writeHalf(self, num):
        if self.half is None:
            self.half = num
        else:
            self.writeByte((num << 4) | self.half)
            self.half = None

    def writeString(self, str):
        self.f.write(str.encode("ascii"))

    def writeZero(self, num):
        if num > 0:
            for i in range(num):
                self.writeByte(0)


# Logging
@click.group(no_args_is_help=True)
@click.option("--log", is_flag=True, default=False)
def cli(log):
    if log:
        logging.basicConfig(handlers=[logging.FileHandler(filename="tool.log", encoding="utf-8", mode="w")], format="[%(levelname)s] %(message)s", level=logging.DEBUG)
    else:
        logging.getLogger().disabled = True


def logMessage(*messages):
    message = " ".join(str(x) for x in messages)
    logging.info(message)
    tqdm.write(message)


def logDebug(*messages):
    message = " ".join(str(x) for x in messages)
    logging.debug(message)


def logWarning(*messages):
    message = " ".join(str(x) for x in messages)
    logging.warning(message)


def logError(*messages):
    message = " ".join(str(x) for x in messages)
    logging.error(message)
    tqdm.write("[ERROR] " + message)


def showProgress(iterable):
    return tqdm(iterable=iterable)


# Strings
def toHex(byte):
    hexstr = hex(byte)[2:].upper()
    if len(hexstr) == 1:
        return "0" + hexstr
    return hexstr


def isAscii(s):
    for i in range(len(s)):
        if ord(s[i]) >= 128:
            return False
    return True


def codeToChar(code):
    try:
        if code < 256:
            return struct.pack("B", code).decode("ascii")
        return struct.pack(">H", code).decode("shift_jis")
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
    if newpointer != pointer:
        logDebug("Shifted pointer", pointer, "to", newpointer)
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
                ret.append(line[6:])
    except UnicodeDecodeError:
        return ret
    return ret


def getSection(f, title, comment="#", fixchars=[]):
    ret = {}
    found = title == ""
    try:
        f.seek(0)
        for line in f:
            line = line.rstrip("\r\n").replace("\ufeff", "")
            if not found and line.startswith("!FILE:" + title):
                found = True
            elif found:
                if title != "" and line.startswith("!FILE:"):
                    break
                elif line.find("=") > 0:
                    split = line.split("=", 1)
                    split[1] = split[1].split(comment)[0]
                    if split[0] not in ret:
                        ret[split[0]] = []
                    for fixchar in fixchars:
                        split[1] = split[1].replace(fixchar[0], fixchar[1])
                    ret[split[0]].append(split[1])
    except UnicodeDecodeError:
        return ret
    return ret


def getSections(file, comment="#", fixchars=[]):
    sections = {}
    with codecs.open(file, "r", "utf-8") as wsb:
        files = getSectionNames(wsb)
        for file in files:
            sections[file] = getSection(wsb, file, comment, fixchars)
    return sections


def getSectionPercentage(section, chartot=0, transtot=0):
    for s in section.keys():
        strlen = len(s)
        for s2 in section[s]:
            chartot += strlen
            if s2 != "":
                transtot += strlen
    return chartot, transtot


class FontGlyph:
    start = 0
    width = 0
    length = 0
    char = ""
    code = 0
    index = 0

    def __init__(self, start, width, length, char="", code=0, index=0):
        self.start = start
        self.width = width
        self.length = length
        self.char = char
        self.code = code
        self.index = index


def wordwrap(text, glyphs, width, codefunc=None, default=6, linebreak="|", sectionsep=">>"):
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
    lines = [line.strip() for line in lines]
    return linebreak.join(lines)


def centerLines(text, glyphs, width, default=6, linebreak="|", centercode="<<"):
    lines = text.split(linebreak)
    for i in range(len(lines)):
        if not lines[i].startswith(centercode):
            continue
        lines[i] = lines[i][len(centercode):]
        length = 0
        for c in lines[i]:
            length += glyphs[c].length if c in glyphs else default
        spacelen = glyphs[" "].length
        spacing = int(((width - length) / 2) / spacelen)
        lines[i] = (" " * spacing) + lines[i]
    return linebreak.join(lines)


def readEncodedString(f, encoding="shift_jis"):
    sjis = ""
    while True:
        b1 = f.readByte()
        if b1 == 0x0A:
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


def detectEncodedString(f, encoding="shift_jis", startascii=[0x25]):
    ret = ""
    sjis = 0
    while True:
        b1 = f.readByte()
        if b1 == 0x0A:
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
            elif len(ret) > 1 and ret.count("UNK(") < 5:
                ret += "UNK(" + toHex(b1) + toHex(b2) + ")"
            else:
                return ""
    return ret


def detectASCIIString(f, encoding="ascii", startascii=[]):
    ret = ""
    while True:
        b1 = f.readByte()
        if b1 == 0x0A:
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
            f.writeByte(0x0A)
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
    old = 0
    new = 0
    str = ""

    def __init__(self, old, new, str):
        self.old = old
        self.new = new
        self.str = str


def repackBinaryStrings(section, infile, outfile, binranges, freeranges=None, detectFunc=detectEncodedString, writeFunc=writeEncodedString, encoding="shift_jis", pointerstart=0):
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
                    check = detectFunc(fi, encoding)
                    if check != "":
                        if check in section and section[check][0] != "":
                            newsjis = section[check][0]
                            if len(section[check]) > 1:
                                section[check].pop(0)
                            if newsjis == "!":
                                newsjis = ""
                            newsjislog = newsjis.encode("ascii", "ignore")
                            logDebug("Replacing string at", pos, "with", newsjislog)
                            fo.seek(pos)
                            endpos = fi.tell() - 1
                            newlen = writeFunc(fo, newsjis, endpos - pos + 1, encoding)
                            fo.seek(-1, 1)
                            if fo.readByte() != 0:
                                fo.writeZero(1)
                            if newlen < 0:
                                if freeranges is None or pointerstart == 0:
                                    logError("String", newsjislog, "is too long.")
                                else:
                                    # Add this to the freeranges
                                    freeranges.append([pos, endpos])
                                    logDebug("Adding new freerage", pos, endpos)
                                    range = None
                                    rangelen = 0
                                    for c in newsjis:
                                        rangelen += 1 if ord(c) < 256 else 2
                                    for freerange in freeranges:
                                        if freerange[1] - freerange[0] > rangelen:
                                            range = freerange
                                            break
                                    if range is None and newsjis not in strpointers:
                                        logError("No more room! Skipping", newsjislog, "...")
                                        freeranges.pop()
                                    else:
                                        # Write the string in a new portion of the rom
                                        if newsjis in strpointers:
                                            newpointer = strpointers[newsjis]
                                        else:
                                            logDebug("No room for the string", newsjislog, ", redirecting to", toHex(range[0]))
                                            fo.seek(range[0])
                                            writeFunc(fo, newsjis, 0, encoding)
                                            fo.seek(-1, 1)
                                            if fo.readByte() != 0:
                                                fo.writeZero(1)
                                            newpointer = pointerstart + range[0]
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
                                            logDebug("Replaced pointer at", str(index))
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
    distutils.dir_util.copy_tree(f1, f2)


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
        for file in files:
            file = os.path.join(root, file).replace(path, "").replace("\\", "/")
            if len(extensions) > 0 and os.path.splitext(file)[1] not in extensions:
                continue
            ret.append(file)
    return ret


def bundledFile(name):
    if os.path.isfile(name):
        return name
    try:
        return os.path.join(sys._MEIPASS, name)
    except AttributeError:
        return name


def execute(cmd, show=True):
    try:
        result = str(subprocess.check_output(cmd))
    except FileNotFoundError:
        logError("Command too long:", len(cmd))
        return
    except subprocess.CalledProcessError:
        logError("Command error", cmd)
        return
    if result != "":
        if show:
            logMessage(result)
        else:
            logDebug(result)


def xdeltaPatch(patchfile, infile, outfile):
    logMessage("Creating xdelta patch", patchfile, "...")
    xdelta = bundledFile("xdelta.exe")
    if not os.path.isfile(xdelta):
        logError("xdelta not found")
        return
    execute(xdelta + " -f -e -s \"{rom}\" \"{rompatch}\" \"{patch}\"".format(rom=infile, rompatch=outfile, patch=patchfile), False)
    logMessage("Done!")


def armipsPatch(file, defines={}, labels={}):
    logMessage("Applying armips patch ...")
    armips = bundledFile("armips.exe")
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
    (r1, g1, b1, a1) = c1
    (r2, g2, b2, a2) = c2
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
        r = cc58[(color >> 10) & 0x1F]
        g = cc58[(color >> 5) & 0x1F]
        b = cc58[(color) & 0x1F]
    else:
        a = cc38[(color >> 12) & 0x7]
        r = cc48[(color >> 8) & 0xF]
        g = cc48[(color >> 4) & 0xF]
        b = cc48[(color) & 0xF]
    return (r, g, b, a)


def readRGB5A1(color):
    r = cc58[color & 0x1f]
    g = cc58[color >> 5 & 0x1f]
    b = cc58[color >> 10 & 0x1f]
    a = 0 if (color >> 15 & 0x1) == 0 else 255
    return (r, g, b, a)


def getPaletteIndex(palette, color, fixtransp=False, starti=0, palsize=-1, checkalpha=False, zerotransp=True):
    if color[3] == 0 and zerotransp:
        return 0
    if palsize == -1:
        palsize = len(palette)
    zeroalpha = -1
    for i in range(starti, starti + palsize):
        if fixtransp and i == starti:
            continue
        if palette[i][0] == color[0] and palette[i][1] == color[1] and palette[i][2] == color[2] and (not checkalpha or palette[i][3] == color[3]):
            return i - starti
        if palette[i][3] == 0:
            zeroalpha = i - starti
    if palette[starti][0] == color[0] and palette[starti][1] == color[1] and palette[starti][2] == color[2] and (not checkalpha or palette[starti][3] == color[3]):
        return 0
    if checkalpha and color[3] == 0 and zeroalpha != -1:
        return zeroalpha
    mindist = 0xFFFFFFFF
    disti = 0
    for i in range(starti + 1, starti + palsize):
        distance = getColorDistance(color, palette[i], checkalpha)
        if distance < mindist:
            mindist = distance
            disti = i - starti
    logDebug("Color", color, "not found, closest color:", palette[disti])
    return disti


def findBestPalette(palettes, colors):
    if len(palettes) == 1:
        return 0
    mindist = 0xFFFFFFFF
    disti = 0
    for i in range(len(palettes)):
        distance = 0
        for color in colors:
            singledist = 0xFFFFFFFF
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
