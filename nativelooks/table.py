#!/usr/bin/env python3
"""A7R II native colour-matrix table: backup property 0x00030001 (1536 bytes = 768 little-endian int16).

17 slot matrices live at fixed int16 offsets; each is a 3x3 row-major matrix with 1.0 = 1024.
Every command works on a table read from YOUR camera, so no Sony data ships with this project.

  table.py read-cmds  -o cmds_read.txt                     updater-shell script that only reads the table
  table.py extract    pmca.log -o my_original.bin          save the table from a pmca updatershell log
  table.py show       my_original.bin                      print the 17 slot matrices
  table.py build      --base my_original.bin --looks ../looks/v2.json -o looks_v2.bin
  table.py write-cmds looks_v2.bin -o cmds_write.txt       read, write, read back, sync
  table.py verify     pmca.log --before my_original.bin --after looks_v2.bin
  table.py testplan   --base my_original.bin --round 1 -o test1.bin --plan round1-plan.json
"""
import argparse, colorsys, json, re, struct, sys

PROP = 0x00030001
SIZE = 1536
OFFSETS = [36, 45, 54, 63, 72, 81, 90, 99, 108, 117, 401, 512, 521, 530, 539, 548, 557]
# Measured on an ILCE-7RM2 with firmware 4.01 (experiments/slot-mapping). Slots 5, 8 and 9 were not seen.
SLOT_USERS = {
    0: 'Standard, Night Scene, Sepia, PP2 (Still)', 1: 'Vivid', 2: 'Portrait', 3: 'Landscape', 4: 'Sunset',
    5: '(unmapped)', 6: 'PP1 (Movie), PP3 (ITU709)', 7: 'PP4 (ITU709 Matrix)', 8: '(unmapped)', 9: '(unmapped)',
    10: 'PP7 (S-Gamut / S-Log2)', 11: 'PP5, PP6 (Cine)', 12: 'Neutral', 13: 'Clear', 14: 'Deep', 15: 'Light', 16: 'Autumn Leaves',
}
UNMAPPED = {5, 8, 9}


def load(path):
    data = open(path, 'rb').read()
    if len(data) != SIZE:
        sys.exit(f'{path}: expected {SIZE} bytes, got {len(data)}')
    return list(struct.unpack('<768h', data))


def save(path, values):
    assert len(values) == 768 and all(-32768 <= v <= 32767 for v in values)
    open(path, 'wb').write(struct.pack('<768h', *values))


def matrix(values, slot):
    o = OFFSETS[slot]
    return values[o:o + 9]


def check_layout(values, label):
    """Refuse tables that do not look like the A7R II layout (wrong model or firmware)."""
    near = sum(all(abs(sum(matrix(values, s)[r * 3:r * 3 + 3]) - 1024) <= 60 for r in range(3)) for s in range(17))
    if near < 14:
        sys.exit(f'{label}: only {near}/17 slots have rows summing to about 1024; this is not the expected table layout')


def hexdump(values):
    return ' '.join('%02x' % b for b in struct.pack('<768h', *values))


def write_script(path, lines):
    open(path, 'w', newline='').write('\r\n'.join(lines) + '\r\n')


def log_reads(path):
    """Every 1536-byte `bk r` result printed in a pmca updatershell log, in order."""
    reads = []
    for line in open(path, encoding='utf-8', errors='replace'):
        line = line.lstrip('>').strip()
        hx = re.findall(r'\b[0-9a-f]{2}\b', line)
        if len(hx) == SIZE and len(line) <= SIZE * 3 + 4:
            reads.append(list(struct.unpack('<768h', bytes(int(h, 16) for h in hx))))
    return reads


def cmd_read_cmds(a):
    write_script(a.output, ['bk r 0x%08x' % PROP, 'exit'])
    print(f'wrote {a.output}')


def cmd_extract(a):
    reads = log_reads(a.log)
    if not reads:
        sys.exit(f'no {SIZE}-byte read found in {a.log}')
    values = reads[a.index]
    check_layout(values, a.log)
    save(a.output, values)
    print(f'{len(reads)} read(s) in log; saved read #{a.index % len(reads)} to {a.output}')


def cmd_show(a):
    values = load(a.table)
    check_layout(values, a.table)
    for s in range(17):
        m = matrix(values, s)
        rows = ' | '.join(' '.join('%5d' % x for x in m[r * 3:r * 3 + 3]) for r in range(3))
        sums = [sum(m[r * 3:r * 3 + 3]) for r in range(3)]
        print(f'slot {s:2d} @{OFFSETS[s]:3d}  {rows}   row sums {sums}  {SLOT_USERS[s]}')


def cmd_build(a):
    base = load(a.base)
    check_layout(base, a.base)
    looks = json.load(open(a.looks, encoding='utf-8'))
    new = list(base)
    for entry in looks['slots']:
        s, m = entry['slot'], entry['matrix']
        if s in UNMAPPED and not a.allow_unmapped:
            sys.exit(f'slot {s} is unmapped (its camera mode is unknown); pass --allow-unmapped to write it anyway')
        if s in a.protect:
            sys.exit(f'slot {s} ({SLOT_USERS[s]}) is protected; drop it from --protect to overwrite it')
        if len(m) != 9 or not all(-4096 < x < 4096 for x in m):
            sys.exit(f'slot {s}: matrix must be 9 integers with 1.0 = 1024')
        o = OFFSETS[s]
        new[o:o + 9] = m
        print(f"slot {s:2d} {SLOT_USERS[s]:32} -> {entry.get('look', '')}")
    changed = [i for i in range(768) if new[i] != base[i]]
    inside = {o + k for o in OFFSETS for k in range(9)}
    assert all(i in inside for i in changed), 'only matrix words may change'
    save(a.output, new)
    print(f'wrote {a.output}: {len(changed)} int16 words changed, all inside slot matrices')


def cmd_write_cmds(a):
    values = load(a.table)
    check_layout(values, a.table)
    r = 'bk r 0x%08x' % PROP
    write_script(a.output, [r, 'bk w 0x%08x %s' % (PROP, hexdump(values)), r, 'bk s', 'exit'])
    print(f'wrote {a.output}: read, write, read back, sync')


def cmd_verify(a):
    reads = log_reads(a.log)
    before, after = load(a.before), load(a.after)
    if len(reads) < 2:
        sys.exit(f'expected a read before and after the write, found {len(reads)} read(s)')
    ok_before, ok_after = reads[0] == before, reads[-1] == after
    print(f'first read == {a.before}: {ok_before}')
    print(f'last read  == {a.after}: {ok_after}')
    if not ok_after:
        sys.exit('VERIFY FAILED: the camera does not hold the expected table')
    print('VERIFY OK')


def cmd_testplan(a):
    """Tint every slot with a different hue so one grey photo per mode reveals which slot it uses.
    Round 2 shuffles the hues ((i*5) mod 17) so neighbouring slots cannot be confused."""
    base = load(a.base)
    check_layout(base, a.base)
    new, plan = list(base), []
    for i, o in enumerate(OFFSETS):
        j = i if a.round == 1 else (i * 5) % 17
        gains = [round(1024 * c) for c in colorsys.hsv_to_rgb(j / 17, 0.6, 1.0)]
        new[o:o + 9] = [gains[0], 0, 0, 0, gains[1], 0, 0, 0, gains[2]]
        plan.append(dict(slot=i, int16_index=o, hue_deg=round(j / 17 * 360, 1), gains=gains))
    save(a.output, new)
    json.dump(plan, open(a.plan, 'w'), indent=1)
    print(f'wrote {a.output} and {a.plan}')


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('read-cmds'); s.add_argument('-o', '--output', default='cmds_read.txt'); s.set_defaults(f=cmd_read_cmds)
    s = sub.add_parser('extract'); s.add_argument('log'); s.add_argument('-o', '--output', required=True)
    s.add_argument('--index', type=int, default=0, help='which read in the log (0 = first, -1 = last)'); s.set_defaults(f=cmd_extract)
    s = sub.add_parser('show'); s.add_argument('table'); s.set_defaults(f=cmd_show)
    s = sub.add_parser('build'); s.add_argument('--base', required=True); s.add_argument('--looks', required=True)
    s.add_argument('-o', '--output', required=True); s.add_argument('--allow-unmapped', action='store_true')
    s.add_argument('--protect', type=int, nargs='*', default=[0, 10], help='slots that must not change (default: 0 Standard, 10 S-Log2)')
    s.set_defaults(f=cmd_build)
    s = sub.add_parser('write-cmds'); s.add_argument('table'); s.add_argument('-o', '--output', required=True); s.set_defaults(f=cmd_write_cmds)
    s = sub.add_parser('verify'); s.add_argument('log'); s.add_argument('--before', required=True); s.add_argument('--after', required=True)
    s.set_defaults(f=cmd_verify)
    s = sub.add_parser('testplan'); s.add_argument('--base', required=True); s.add_argument('--round', type=int, choices=(1, 2), required=True)
    s.add_argument('-o', '--output', required=True); s.add_argument('--plan', required=True); s.set_defaults(f=cmd_testplan)
    a = p.parse_args()
    a.f(a)


if __name__ == '__main__':
    main()
