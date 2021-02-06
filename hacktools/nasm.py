import codecs
import os
import shlex
from hacktools import common


def run(asmfile):
    # Support a syntax similar to armips, but simplified:
    # .open file: opens a file
    # .org 0x100: seek opened file to 0x100
    #      Everything between this and the next .org/.close
    #      is compiled and wrote to the file with nasm
    # .import 0x200 file: imports the specified file and writes it to the address
    # .close: close the opened file (required)
    tempfile = "asm.tmp"
    tempout = "asm.bin"
    with codecs.open(asmfile, "r", "utf-8") as asmf:
        lines = asmf.readlines()
    currf = None
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line == ".close":
            common.logDebug("Closing file")
            if currf is not None:
                currf.close()
                currf = None
        elif line.startswith(".open"):
            parameters = shlex.split(line[5:].strip())
            filename = parameters[0]
            common.logDebug("Opening file", filename)
            if not os.path.isfile(filename):
                common.logError("File", filename, "not found.")
                break
            currf = common.Stream(filename, "rb+").__enter__()
        elif line.startswith(".import"):
            filename = line[7:].strip()
            parameters = shlex.split(line[7:].strip())
            filename = parameters[1]
            if not os.path.isfile(filename):
                common.logError("File", filename, "not found.")
                break
            importpos = parameters[0]
            if importpos.startswith("0x"):
                importpos = int(importpos.replace("0x", ""), 16)
            else:
                importpos = int(importpos)
            currf.seek(importpos)
            with common.Stream(filename, "rb") as importfile:
                currf.write(importfile.read())
        elif line.startswith(".org"):
            orgpos = line[4:].strip()
            if orgpos.startswith("0x"):
                orgpos = int(orgpos.replace("0x", ""), 16)
            else:
                orgpos = int(orgpos)
            common.logDebug("Seeking to", orgpos)
            currf.seek(orgpos)
            # Read up until the next .org or .close and send to nasm
            j = i + 1
            nasmlines = "[BITS 16]\ncpu 186\norg " + str(orgpos) + "\n"
            while j < len(lines):
                nasmline = lines[j].strip()
                if nasmline.startswith(".org") or nasmline.startswith(".close") or nasmline.startswith(".import"):
                    i = j - 1
                    break
                else:
                    if nasmline != "" and not nasmline.startswith(";"):
                        nasmlines += nasmline + "\n"
                    j += 1
            common.logDebug("NASM lines:", nasmlines.strip().replace("\n", " | "))
            # Write the nasm lines to a file and compile them
            with codecs.open(tempfile, "w", "utf-8") as tempf:
                tempf.write(nasmlines)
            nasm = common.bundledExecutable("nasm.exe")
            common.execute(nasm + " -O1 -o " + tempout + " -f bin " + tempfile, False)
            # Read the temp file and write it to the opened one
            with common.Stream(tempout, "rb") as tempf:
                currf.write(tempf.read())
            os.remove(tempfile)
            os.remove(tempout)
        i += 1
    if currf is not None:
        currf.close()
