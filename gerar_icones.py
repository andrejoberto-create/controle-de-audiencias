"""Gera ícones PNG para o PWA usando apenas bibliotecas padrão."""
import struct, zlib, base64

def png(size, bg=(0, 53, 128), fg=(201, 168, 76)):
    w = h = size
    rows = []
    cx, cy, r = w // 2, h // 2, int(w * 0.38)
    br = int(w * 0.10)

    for y in range(h):
        row = b'\x00'
        for x in range(w):
            dx, dy = x - cx, y - cy
            # Círculo dourado
            if dx*dx + dy*dy <= r*r:
                row += bytes(fg)
            # Borda arredondada azul (cantos)
            elif (x < br and y < br and (x-br)**2+(y-br)**2 > br*br) or \
                 (x >= w-br and y < br and (x-(w-br))**2+(y-br)**2 > br*br) or \
                 (x < br and y >= h-br and (x-br)**2+(y-(h-br))**2 > br*br) or \
                 (x >= w-br and y >= h-br and (x-(w-br))**2+(y-(h-br))**2 > br*br):
                row += b'\x00\x00\x00'
            else:
                row += bytes(bg)
        rows.append(row)

    raw = b''.join(rows)
    compressed = zlib.compress(raw)

    def chunk(name, data):
        c = name + data
        return struct.pack('>I', len(data)) + c + struct.pack('>I', zlib.crc32(c) & 0xffffffff)

    ihdr_data = struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0)
    return (b'\x89PNG\r\n\x1a\n' +
            chunk(b'IHDR', ihdr_data) +
            chunk(b'IDAT', compressed) +
            chunk(b'IEND', b''))

import os
base = os.path.dirname(__file__)
for size, name in [(192, 'icon-192.png'), (512, 'icon-512.png')]:
    path = os.path.join(base, 'static', name)
    with open(path, 'wb') as f:
        f.write(png(size))
    print(f'✅ {name} gerado ({size}x{size})')
