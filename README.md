# hacktools
A set of utilities and tools for rom hacking and translations.

## Installing dependencies
Most dependencies are optional, and can be installed with `pip install hacktools[name1,name2]` or `pip install hacktools[all]` to install all of them.
### Dependencies list
 - `nds`: needed for NDS roms and compressed binaries.
 - `armips`: needed for `common.armipsPatch`.
 - `xdelta`: needed for `common.xdeltaPatch`.
 - `ips`: needed for `common.ipsPatch`.
 - `iso`: needed for PSX/PS2 ISO.
 - `psp`: needed for PSP ISO/BIN signing.
 - `graphics`: needed for most functions that deal with graphics.

## Supported platforms and formats
External dependencies not included are marked as `(through *dependency*)`
### NDS
- ROM
- NCGR/NSCR/NCER/NCLR images
- NBFC/NTFT/NBFS/NBFP images
- NFTR fonts
- NARC archives
- Textures in NSBMD 3D files
### PSP
- ISO
- GIM/GMO images
- PGF fonts
- PMF header for MPS movies
- BIN signing (through sign_np)
### PSX
- BIN/ISO
- TIM images
### WonderSwan / WonderSwan Color
- ROM banks
- Assembly (through NASM)
- Raw and tiled images
- Sprites
### GameBoy
- ROM banks
- Assembly (through wla-gb and wlalink)
### Wii
- ISO (through wit)
- TPL images
- ARC archives (through wszst)
- BRFNT fonts (through brfnt2tpl and wimgt)
### Other / Generic
- CPK archives
- ARCH archives
- LZ10, LZ11, Huffman and CRILAYLA compression/decompression
- ARM/MIPS binary patching
- xdelta patch creation
- IPS patch creation
