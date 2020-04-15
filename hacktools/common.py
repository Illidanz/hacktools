import codecs
from io import BytesIO
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

    def writeUInt(self, num):
        self.f.write(struct.pack(self.endian + "I", num))

    def writeShort(self, num):
        self.f.write(struct.pack(self.endian + "h", num))

    def writeUShort(self, num):
        self.f.write(struct.pack(self.endian + "H", num))

    def writeByte(self, num):
        self.f.write(struct.pack("B", num))

    def writeSByte(self, num):
        self.f.write(struct.pack("b", num))

    def writeHalf(self, num):
        if self.half is None:
            self.half = num
        else:
            self.writeByte((num << 4) | self.half)
            self.half = None

    def writeString(self, str):
        self.f.write(str.encode("ascii"))

    def writeZero(self, num):
        for i in range(num):
            self.writeByte(0)


# Logging
@click.group(no_args_is_help=True)
@click.option("--log", is_flag=True, default=False)
def cli(log):
    if log:
        logging.basicConfig(filename="tool.log", filemode="w", format="[%(levelname)s] %(message)s", level=logging.DEBUG)
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


def getSectionPercentage(section, chartot=0, transtot=0):
    for s in section.keys():
        strlen = len(s)
        for s2 in section[s]:
            chartot += strlen
            if s2 != "":
                transtot += strlen
    return chartot, transtot


def wordwrap(text, glyphs, width, codefunc=None, default=6, linebreak="|", sectionsep=">>"):
    # Based on http://code.activestate.com/recipes/577946-word-wrap-for-proportional-fonts/
    lines = []
    if text.count(sectionsep) > 0:
        lines = text.split(sectionsep)
        for i in range(len(lines)):
            lines[i] = wordwrap(lines[i], glyphs, width, codefunc, default, linebreak, sectionsep)
        return sectionsep.join(lines)
    text = text.replace(linebreak, "\n")
    pattern = re.compile(r"(\s+)")
    lookup = dict((c, glyphs[c][2] if c in glyphs else default) for c in set(text))
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


def armipsPatch(file):
    logMessage("Applying armips patch ...")
    armips = bundledFile("armips.exe")
    if not os.path.isfile(armips):
        logError("armips not found")
    else:
        execute(armips + " {binpatch}".format(binpatch=file), False)
        logMessage("Done!")


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


def getPaletteIndex(palette, color, fixtrasp=False, starti=0, palsize=-1, checkalpha=False, zerotrasp=True):
    if color[3] == 0 and zerotrasp:
        return 0
    if palsize == -1:
        palsize = len(palette)
    zeroalpha = -1
    for i in range(starti, starti + palsize):
        if fixtrasp and i == starti:
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


def drawPalette(pixels, palette, width, ystart=0):
    for x in range(len(palette)):
        j = width + ((x % 8) * 5)
        i = ystart + ((x // 8) * 5)
        for j2 in range(5):
            for i2 in range(5):
                pixels[j + j2, i + i2] = palette[x]
    return pixels
