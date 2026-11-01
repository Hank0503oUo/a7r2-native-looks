"""Extract the uncompressed file container appended to Sony's 2022-resigned firmware updater .exe.
Layout after the last PE section: 2x FILETIME, u32 groups(?), then per group:
  u32 guidLen, u32 count, UTF-16 guid, count x [u32 nameLen, u32 size, UTF-16 name, u64 FILETIME]
followed by the file contents back to back in table order."""
import struct, sys, os
src, out = sys.argv[1], sys.argv[2]
f = open(src, 'rb'); data_end = None
f.seek(0x3c); pe = struct.unpack('<I', f.read(4))[0]
f.seek(pe + 6); nsec = struct.unpack('<H', f.read(2))[0]; f.seek(pe + 20); optsz = struct.unpack('<H', f.read(2))[0]
f.seek(pe + 24); magic = struct.unpack('<H', f.read(2))[0]
f.seek(pe + 24 + (96 if magic == 0x10b else 112) + 32); cert_off = struct.unpack('<I', f.read(4))[0]
end = 0
for i in range(nsec):
    f.seek(pe + 24 + optsz + 40 * i + 16); rsz, roff = struct.unpack('<II', f.read(8)); end = max(end, roff + rsz)
f.seek(end); hdr = f.read(24); ngroups = struct.unpack_from('<I', hdr, 16)[0]
pos = end + 24 - 4  # first guidLen sits at +0x1c; tolerate either layout below
f.seek(end + 0x1c)
entries = []
for g in range(ngroups):
    gl, n = struct.unpack('<II', f.read(8)); guid = f.read(gl * 2).decode('utf-16-le')
    for _ in range(n):
        nl, size = struct.unpack('<II', f.read(8)); name = f.read(nl * 2).decode('utf-16-le'); ft = struct.unpack('<Q', f.read(8))[0]
        entries.append((guid, name, size))
start = f.tell(); total = sum(e[2] for e in entries)
print(f'groups={ngroups} files={len(entries)} data@{start:#x} total={total} ends@{start+total:#x} cert@{cert_off:#x}')
assert start + total <= cert_off
os.makedirs(out, exist_ok=True); off = start
for guid, name, size in entries:
    f.seek(off); d = os.path.join(out, guid.strip('!')); os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, name), 'wb') as o:
        left = size
        while left:
            b = f.read(min(left, 1 << 22)); o.write(b); left -= len(b)
    print(f'{size:>11}  {guid[:12]}  {name}'); off += size
