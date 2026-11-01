import sys, re, struct, mmap
f = open(sys.argv[1], 'rb'); m = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
print('size', len(m))
# PE sections / overlay / certificate table
pe = struct.unpack_from('<I', m, 0x3c)[0]; nsec = struct.unpack_from('<H', m, pe + 6)[0]; optsz = struct.unpack_from('<H', m, pe + 20)[0]
magic = struct.unpack_from('<H', m, pe + 24)[0]; dd = pe + 24 + (96 if magic == 0x10b else 112)
cert_off, cert_size = struct.unpack_from('<II', m, dd + 4 * 8)
end = 0
for i in range(nsec):
    s = pe + 24 + optsz + 40 * i
    name = m[s:s + 8].rstrip(b'\0').decode('latin-1'); vsz, va, rsz, roff = struct.unpack_from('<IIII', m, s + 8)
    print(f'section {name:8} raw_off={roff:#x} raw_size={rsz:#x}'); end = max(end, roff + rsz)
print(f'overlay starts {end:#x}, cert table off={cert_off:#x} size={cert_size:#x}')
print('overlay head', m[end:end + 32])
for name, pat in [('lzh', rb'..-lh[0-7d]-'), ('zip', rb'PK\x03\x04'), ('7z', rb"7z\xbc\xaf'\x1c"), ('cab', rb'MSCF\0\0\0\0'),
                  ('FirmwareData', rb'FirmwareData'), ('FDAT', rb'UDTRFIRM|FDAT'), ('xz', rb'\xfd7zXZ\0'), ('gzip', rb'\x1f\x8b\x08')]:
    hits = [x.start() for x in re.finditer(pat, m)][:6]
    print(f'{name:12} count~{len(hits)} first={[hex(h) for h in hits]}')
