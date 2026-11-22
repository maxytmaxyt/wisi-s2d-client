import ctypes
from ctypes import wintypes

GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
OPEN_EXISTING = 3
IOCTL_SCSI_PASS_THROUGH_DIRECT = 0x0004D014

class SCSI_PASS_THROUGH_DIRECT(ctypes.Structure):
    _fields_ = [
        ("Length", wintypes.USHORT),
        ("ScsiStatus", wintypes.BYTE),
        ("PathId", wintypes.BYTE),
        ("TargetId", wintypes.BYTE),
        ("Lun", wintypes.BYTE),
        ("CdbLength", wintypes.BYTE),
        ("SenseInfoLength", wintypes.BYTE),
        ("DataIn", wintypes.BYTE),
        ("DataTransferLength", wintypes.ULONG),
        ("TimeOutValue", wintypes.ULONG),
        ("DataBuffer", ctypes.c_void_p),
        ("SenseInfoOffset", wintypes.ULONG),
        ("Cdb", wintypes.BYTE * 16),
    ]

class SPTD_WITH_SENSE(ctypes.Structure):
    _fields_ = [
        ("sptd", SCSI_PASS_THROUGH_DIRECT),
        ("sense", wintypes.BYTE * 64),
    ]

def send_scsi(handle, cdb_bytes, data_in_len=0, timeout=2):
    sptd_sense = SPTD_WITH_SENSE()
    sptd = sptd_sense.sptd
    sptd.Length = ctypes.sizeof(SCSI_PASS_THROUGH_DIRECT)
    sptd.CdbLength = len(cdb_bytes)
    sptd.SenseInfoLength = 64
    sptd.SenseInfoOffset = ctypes.sizeof(SCSI_PASS_THROUGH_DIRECT)
    sptd.TimeOutValue = timeout
    
    for i, b in enumerate(cdb_bytes):
        sptd.Cdb[i] = b

    if data_in_len > 0:
        buf = ctypes.create_string_buffer(data_in_len)
        sptd.DataIn = 1 # DATA_IN
        sptd.DataTransferLength = data_in_len
        sptd.DataBuffer = ctypes.cast(buf, ctypes.c_void_p)
    else:
        buf = None
        sptd.DataIn = 2 # NO_DATA
        sptd.DataTransferLength = 0
        sptd.DataBuffer = None

    bytes_returned = wintypes.DWORD(0)
    ok = ctypes.windll.kernel32.DeviceIoControl(
        handle,
        IOCTL_SCSI_PASS_THROUGH_DIRECT,
        ctypes.byref(sptd_sense),
        ctypes.sizeof(sptd_sense),
        ctypes.byref(sptd_sense),
        ctypes.sizeof(sptd_sense),
        ctypes.byref(bytes_returned),
        None
    )
    if not ok:
        err = ctypes.windll.kernel32.GetLastError()
        return False, f"Err={err}", b"", bytes(sptd_sense.sense)
    
    resp_data = buf.raw[:sptd.DataTransferLength] if buf else b""
    return True, f"ScsiStatus=0x{sptd.ScsiStatus:02x}", resp_data, bytes(sptd_sense.sense)

h = ctypes.windll.kernel32.CreateFileW(r"\\.\D:", GENERIC_READ | GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE, None, OPEN_EXISTING, 0, None)
if h == -1:
    print("Cannot open D:")
    exit(1)

# READ (10): 28 00 [LBA 4B] 00 [Len 2B] 00
read_cdb = bytes([0x28, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x01, 0x00])
ok, status, data, sense = send_scsi(h, read_cdb, data_in_len=512*1024)
print('READ (10) Block 0:', ok, status, 'len=', len(data), 'sense:', sense[:18].hex())
if ok and len(data) > 0:
    print('Data preview:', data[:64].hex())

ctypes.windll.kernel32.CloseHandle(h)
