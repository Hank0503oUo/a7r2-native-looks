#!/usr/bin/env python3
"""Scan a Sony Backup.bin (BK4) for properties that hold 3x3 colour matrices.

This is how 0x00030001 was found: look for an identity matrix (1.0 = 256/1024/4096) inside any
property, then for runs of int16 triples whose rows sum to 1024, the camera's fixed-point 1.0.
Needs Sony-PMCA-RE (https://github.com/ma1co/Sony-PMCA-RE) for its BackupFile parser:

  PYTHONPATH=/path/to/Sony-PMCA-RE python find_matrix_tables.py Backup.bin
"""
import struct, sys
from pmca.backup import BackupFile

IDENTITY = {(u, 0, 0, 0, u, 0, 0, 0, u) for u in (256, 1024, 4096)}

backup = BackupFile(open(sys.argv[1], 'rb'))
count = 0
for pid, prop in backup.listProperties():
    count += 1
    data = bytes(prop.data)
    for width, fmt in ((2, '<h'), (4, '<i')):
        vals = [struct.unpack_from(fmt, data, i * width)[0] for i in range(len(data) // width)]
        hits = [k for k in range(len(vals) - 8) if tuple(vals[k:k + 9]) in IDENTITY]
        if hits:
            print(f'{pid:#010x} size={len(data)} attr={prop.attr:#x}: identity matrix ({width}-byte words) at word {hits[0]}')
        if width == 2:
            # 3x3 candidates: three rows that each sum to 1024 +- 3 with the diagonal as each row's largest entry
            starts = [k for k in range(len(vals) - 8)
                      if all(abs(sum(vals[k + 3 * r:k + 3 * r + 3]) - 1024) <= 3 for r in range(3))
                      and all(vals[k + 4 * r] == max(vals[k + 3 * r:k + 3 * r + 3]) for r in range(3))]
            chosen = []
            for k in starts:
                if not chosen or k >= chosen[-1] + 9:
                    chosen.append(k)
            if len(chosen) >= 3:
                print(f'{pid:#010x} size={len(data)} attr={prop.attr:#x}: {len(chosen)} matrices with rows summing to 1024 at int16 {chosen}')
print(f'{count} properties scanned')
