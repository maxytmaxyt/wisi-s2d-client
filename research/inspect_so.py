import zipfile
import io
from elftools.elf.elffile import ELFFile

with zipfile.ZipFile('C:/Users/thiel/Downloads/TV2Smart_3.M20260803.0-rev-a14aeb377_APKPure.xapk') as z:
    apk_data = z.read('config.arm64_v8a.apk')
    with zipfile.ZipFile(io.BytesIO(apk_data)) as inner:
        so_data = inner.read('lib/arm64-v8a/libsecure_module.so')
        elf = ELFFile(io.BytesIO(so_data))
        symtab = elf.get_section_by_name('.dynsym')
        for sym in symtab.iter_symbols():
            if any(k in sym.name.lower() for k in ['chunk', 'boot', 'fw', 'abs', 'crc', 'flash', 'upgrade']):
                print(f"{sym.name}: val=0x{sym['st_value']:x}, size={sym['st_size']}")
