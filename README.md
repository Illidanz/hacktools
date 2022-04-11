# hacktools
A set of utilities and tools for rom hacking and translations.

## Supported platforms and formats
External dependencies not included are marked as `(through *dependency*)`
### NDS
- ROM (through ndstool)
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
- BIN (through psximager)
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
- IPS patch creation
- xdelta patch creation (through xdelta)
