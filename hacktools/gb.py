import os
from hacktools import common


def extractRom(romfile, extractfolder, workfolder="", banksize=0x4000):
    common.logMessage("Extracting ROM", romfile, "...")
    common.makeFolder(extractfolder)
    filesize = os.path.getsize(romfile)
    banknum = filesize // banksize
    common.logMessage("Extracting", banknum, "banks ...")
    with common.Stream(romfile, "rb") as f:
        for i in range(banknum):
            bankname = "bank_"
            if i < 0x10:
                bankname += "0"
            bankname += format(i, "x")
            with common.Stream(extractfolder + bankname + ".bin", "wb") as fout:
                fout.write(f.read(banksize))
    if workfolder != "":
        common.copyFolder(extractfolder, workfolder)
    common.logMessage("Done!")


def repackRom(romfile, rompatch, workfolder, patchfile="", banksize=0x4000):
    common.logMessage("Repacking ROM", rompatch, "...")
    filesize = os.path.getsize(romfile)
    banknum = filesize // banksize
    common.logMessage("Repacking", banknum, "banks ...")
    with common.Stream(rompatch, "wb") as fout:
        for i in range(banknum):
            bankname = "bank_"
            if i < 0x10:
                bankname += "0"
            bankname += format(i, "x")
            with common.Stream(workfolder + bankname + ".bin", "rb") as f:
                fout.write(f.read())
    # Calculate and write the global checksum
    with common.Stream(rompatch, "rb+", False) as fout:
        checksum = sum(fout.read(0x14e))
        fout.seek(0x150)
        checksum += sum(fout.read(filesize - 0x150))
        fout.seek(0x14e)
        fout.writeUShort(checksum & 0xffff)
    common.logMessage("Done!")
    # Create patch
    if patchfile != "":
        common.xdeltaPatch(patchfile, romfile, rompatch)
        common.ipsPatch(patchfile.replace(".xdelta", ".ips"), romfile, rompatch)


def asmPatch(file, workfolder, banks=[0x0], banksize=0x4000):
    common.logMessage("Applying ASM patch ...")
    wlagb = common.bundledExecutable("wla-gb.exe")
    if not os.path.isfile(wlagb):
        common.logError("wla-gb not found")
        return
    wlalink = common.bundledExecutable("wlalink.exe")
    if not os.path.isfile(wlalink):
        common.logError("wlalink not found")
        return
    # Create the output file
    ofile = file.replace(".asm", ".o")
    if os.path.isfile(ofile):
        os.remove(ofile)
    common.execute(wlagb + " -o {ofile} {binpatch}".format(binpatch=file, ofile=ofile), False)
    if not os.path.isfile(ofile):
        return
    # Run the linker and create a temporary patched ROM
    tempfile = file.replace(".asm", ".txt")
    deletetemp = False
    if not os.path.isfile(tempfile):
        deletetemp = True
        with open(tempfile, "w") as f:
            f.write("[objects]\n")
            f.write(ofile + "\n")
    temprom = "temprom.gb"
    common.execute(wlalink + " -r {tempfile} {temprom}".format(tempfile=tempfile, temprom=temprom), False)
    if deletetemp:
        os.remove(tempfile)
    os.remove(ofile)
    # Extract the banks we're interested in from the temp ROM
    with common.Stream(temprom, "rb") as f:
        for i in banks:
            bankname = "bank_"
            if i < 0x10:
                bankname += "0"
            bankname += format(i, "x")
            f.seek(i * banksize)
            with common.Stream(workfolder + bankname + ".bin", "wb") as fout:
                fout.write(f.read(banksize))
    os.remove(temprom)
    common.logMessage("Done!")