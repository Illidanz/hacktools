"""Support for Game Boy ROMs, split into banks.

ROMs are extracted and repacked as a set of bank_xx.bin files, one per
bank, with xx being the bank number in hex. ASM patches are applied by
calling the wla-gb and wlalink executables externally.
"""
import os
from hacktools import common


def extractRom(romfile: str, extractfolder: str, workfolder: str = "", banksize: int = 0x4000) -> None:
    """Extract a Game Boy ROM to a folder, splitting it into banks.

    Args:
        romfile: Path of the ROM file.
        extractfolder: Path of the folder to extract to.
        workfolder: Optional path of a work folder the extracted files are
            copied to.
        banksize: Size of a single bank.
    """
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


def repackRom(romfile: str, rompatch: str, workfolder: str, patchfile: str = "", banksize: int = 0x4000) -> None:
    """Repack a Game Boy ROM from the bank files in a folder.

    The global checksum in the ROM header is recalculated after the banks
    are joined.

    Args:
        romfile: Path of the original ROM file.
        rompatch: Path of the output ROM file.
        workfolder: Path of the folder with the bank files.
        patchfile: Path of the xdelta patch to create, an ips patch is also
            created next to it. No patches are created if empty.
        banksize: Size of a single bank.
    """
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


def asmPatch(file: str, workfolder: str, banks: list[int] = [0x0], banksize: int = 0x4000) -> None:
    """Apply an ASM patch with wla-gb, then extract the patched banks.

    The asm file is compiled with wla-gb and linked with wlalink into a
    temporary patched ROM, and the given banks are extracted from it into
    the work folder. If a .txt file with the same name as the asm file
    exists, it's used as the linkfile, otherwise a temporary one is created.

    Args:
        file: Path of the asm file.
        workfolder: Path of the folder the patched banks are extracted to.
        banks: List of bank numbers the patch is expected to change.
        banksize: Size of a single bank.
    """
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