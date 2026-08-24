#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Generate the Windows amd64 COFF resource object for Darkstar.exe.

The output contains the canonical Darkstar icon as RT_ICON/RT_GROUP_ICON
resources. It uses only the Python standard library so maintainers can
regenerate the checked-in .syso without a third-party resource compiler.
"""

from __future__ import annotations

import argparse
import struct
from dataclasses import dataclass
from pathlib import Path

IMAGE_FILE_MACHINE_AMD64 = 0x8664
IMAGE_SCN_CNT_INITIALIZED_DATA = 0x00000040
IMAGE_SCN_ALIGN_4BYTES = 0x00300000
IMAGE_SCN_MEM_READ = 0x40000000
IMAGE_REL_AMD64_ADDR32NB = 0x0003
IMAGE_SYM_CLASS_STATIC = 3
RT_ICON = 3
RT_GROUP_ICON = 14
LANG_EN_US = 0x0409


@dataclass(frozen=True)
class IconEntry:
    width: int
    height: int
    color_count: int
    reserved: int
    planes: int
    bit_count: int
    size: int
    offset: int
    payload: bytes


def align(value: int, boundary: int) -> int:
    return (value + boundary - 1) & ~(boundary - 1)


def parse_ico(path: Path) -> list[IconEntry]:
    data = path.read_bytes()
    if len(data) < 6:
        raise ValueError("ICO file is truncated")
    reserved, icon_type, count = struct.unpack_from("<HHH", data, 0)
    if reserved != 0 or icon_type != 1 or count < 1:
        raise ValueError("Not a Windows icon file")
    table_end = 6 + count * 16
    if table_end > len(data):
        raise ValueError("ICO directory is truncated")
    entries: list[IconEntry] = []
    for index in range(count):
        pos = 6 + index * 16
        width, height, colors, reserved_byte, planes, bits, size, offset = struct.unpack_from("<BBBBHHII", data, pos)
        end = offset + size
        if offset < table_end or end > len(data):
            raise ValueError(f"ICO image {index} points outside the file")
        entries.append(IconEntry(width, height, colors, reserved_byte, planes, bits, size, offset, data[offset:end]))
    return entries


def directory_header(id_entries: int) -> bytes:
    return struct.pack("<IIHHHH", 0, 0, 0, 0, 0, id_entries)


def directory_entry(resource_id: int, target_offset: int, is_directory: bool) -> bytes:
    target = target_offset | (0x80000000 if is_directory else 0)
    return struct.pack("<II", resource_id, target)


def build_rsrc(icon_entries: list[IconEntry]) -> tuple[bytes, list[int]]:
    n = len(icon_entries)
    buf = bytearray()

    def reserve(size: int) -> int:
        offset = len(buf)
        buf.extend(b"\0" * size)
        return offset

    root = reserve(16 + 2 * 8)
    icon_type_dir = reserve(16 + n * 8)
    icon_id_dirs = [reserve(16 + 8) for _ in range(n)]
    group_type_dir = reserve(16 + 8)
    group_id_dir = reserve(16 + 8)
    data_entries = [reserve(16) for _ in range(n + 1)]

    while len(buf) % 4:
        buf.append(0)

    # Group icon ID 1; individual icon images IDs 2..N+1.
    group_blob_offset = len(buf)
    group = bytearray(struct.pack("<HHH", 0, 1, n))
    for idx, entry in enumerate(icon_entries, start=2):
        group.extend(struct.pack(
            "<BBBBHHIH",
            entry.width,
            entry.height,
            entry.color_count,
            entry.reserved,
            entry.planes,
            entry.bit_count,
            entry.size,
            idx,
        ))
    buf.extend(group)
    while len(buf) % 4:
        buf.append(0)

    icon_blob_offsets: list[int] = []
    for entry in icon_entries:
        icon_blob_offsets.append(len(buf))
        buf.extend(entry.payload)
        while len(buf) % 4:
            buf.append(0)

    # Root directory: RT_ICON then RT_GROUP_ICON, sorted by numeric type ID.
    buf[root:root + 16] = directory_header(2)
    buf[root + 16:root + 24] = directory_entry(RT_ICON, icon_type_dir, True)
    buf[root + 24:root + 32] = directory_entry(RT_GROUP_ICON, group_type_dir, True)

    buf[icon_type_dir:icon_type_dir + 16] = directory_header(n)
    for i, icon_dir in enumerate(icon_id_dirs):
        icon_id = i + 2
        pos = icon_type_dir + 16 + i * 8
        buf[pos:pos + 8] = directory_entry(icon_id, icon_dir, True)
        buf[icon_dir:icon_dir + 16] = directory_header(1)
        buf[icon_dir + 16:icon_dir + 24] = directory_entry(LANG_EN_US, data_entries[i], False)

    buf[group_type_dir:group_type_dir + 16] = directory_header(1)
    buf[group_type_dir + 16:group_type_dir + 24] = directory_entry(1, group_id_dir, True)
    buf[group_id_dir:group_id_dir + 16] = directory_header(1)
    buf[group_id_dir + 16:group_id_dir + 24] = directory_entry(LANG_EN_US, data_entries[n], False)

    relocation_offsets: list[int] = []
    for i, entry in enumerate(icon_entries):
        data_pos = data_entries[i]
        # The first DWORD is section-relative here. IMAGE_REL_AMD64_ADDR32NB
        # relocates it to the final PE RVA when Go links the object.
        struct.pack_into("<IIII", buf, data_pos, icon_blob_offsets[i], entry.size, 0, 0)
        relocation_offsets.append(data_pos)
    struct.pack_into("<IIII", buf, data_entries[n], group_blob_offset, len(group), 0, 0)
    relocation_offsets.append(data_entries[n])

    return bytes(buf), relocation_offsets


def write_coff(path: Path, section_data: bytes, relocations: list[int]) -> None:
    file_header_size = 20
    section_header_size = 40
    raw_offset = file_header_size + section_header_size
    raw_size = len(section_data)
    relocation_offset = align(raw_offset + raw_size, 4)
    relocation_size = len(relocations) * 10
    symbol_offset = relocation_offset + relocation_size
    number_of_symbols = 2  # section symbol + one auxiliary section-definition record

    out = bytearray()
    out.extend(struct.pack(
        "<HHIIIHH",
        IMAGE_FILE_MACHINE_AMD64,
        1,
        0,
        symbol_offset,
        number_of_symbols,
        0,
        0,
    ))
    out.extend(struct.pack(
        "<8sIIIIIIHHI",
        b".rsrc\0\0\0",
        0,
        0,
        raw_size,
        raw_offset,
        relocation_offset,
        0,
        len(relocations),
        0,
        IMAGE_SCN_CNT_INITIALIZED_DATA | IMAGE_SCN_ALIGN_4BYTES | IMAGE_SCN_MEM_READ,
    ))
    out.extend(section_data)
    out.extend(b"\0" * (relocation_offset - len(out)))

    for offset in relocations:
        out.extend(struct.pack("<IIH", offset, 0, IMAGE_REL_AMD64_ADDR32NB))

    # Static .rsrc section symbol. Relocations above target symbol-table index 0.
    out.extend(struct.pack("<8sIhHBB", b".rsrc\0\0\0", 0, 1, 0, IMAGE_SYM_CLASS_STATIC, 1))
    # Auxiliary section-definition symbol record (18 bytes).
    out.extend(struct.pack("<IHHIhBBH", raw_size, len(relocations), 0, 0, 0, 0, 0, 0))
    # COFF string table: only its 4-byte length because all names fit inline.
    out.extend(struct.pack("<I", 4))
    path.write_bytes(out)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ico", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    entries = parse_ico(args.ico)
    section, relocs = build_rsrc(entries)
    write_coff(args.out, section, relocs)
    print(f"wrote {args.out} ({len(section)} resource bytes, {len(relocs)} relocations)")


if __name__ == "__main__":
    main()
