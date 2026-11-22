import ctypes
from ctypes import wintypes
import struct

GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
OPEN_EXISTING = 3

IOCTL_SCSI_PASS_THROUGH_DIRECT = 0x0004D014
SCSI_IOCTL_DATA_IN = 1
SCSI_IOCTL_DATA_OUT = 0

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

# Also allocate space for SenseBuffer right after the structure
class SPTD_WITH_SENSE(ctypes.Structure):
    _fields_ = [
        ("sptd", SCSI_PASS_THROUGH_DIRECT),
        ("sense", wintypes.BYTE * 32),
    ]

def send_scsi_cmd(handle, cdb_bytes, data_in_len=0, data_out=None):
    sptd_sense = SPTD_WITH_SENSE()
    sptd = sptd_sense.sptd
    sptd.Length = ctypes.sizeof(SCSI_PASS_THROUGH_DIRECT)
    sptd.CdbLength = len(cdb_bytes)
    sptd.SenseInfoLength = 32
    sptd.SenseInfoOffset = ctypes.sizeof(SCSI_PASS_THROUGH_DIRECT)
    sptd.TimeOutValue = 5
    
    for i, b in enumerate(cdb_bytes):
        sptd.Cdb[i] = b

    if data_in_len > 0:
        buf = ctypes.create_string_buffer(data_in_len)
        sptd.DataIn = SCSI_IOCTL_DATA_IN
        sptd.DataTransferLength = data_in_len
        sptd.DataBuffer = ctypes.cast(buf, ctypes.c_void_p)
    elif data_out:
        buf = ctypes.create_string_buffer(data_out)
        sptd.DataIn = SCSI_IOCTL_DATA_OUT
        sptd.DataTransferLength = len(data_out)
        sptd.DataBuffer = ctypes.cast(buf, ctypes.c_void_p)
    else:
        buf = None
        sptd.DataIn = 2 # SCSI_IOCTL_DATA_UNSPECIFIED
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
        return False, f"DeviceIoControl failed with GetLastError={err}", b""
    
    if sptd.ScsiStatus != 0:
        return False, f"SCSI error status=0x{sptd.ScsiStatus:02x}", bytes(sptd_sense.sense)
    
    resp_data = buf.raw[:sptd.DataTransferLength] if buf else b""
    return True, "OK", resp_data

h = ctypes.windll.kernel32.CreateFileW(
    r"\\.\D:",
    GENERIC_READ | GENERIC_WRITE,
    FILE_SHARE_READ | FILE_SHARE_WRITE,
    None,
    OPEN_EXISTING,
    0,
    None
)

if h == -1:
    print("Failed to open \\\\.\\D:, err=", ctypes.windll.kernel32.GetLastError())
else:
    print("Successfully opened \\\\.\\D:, handle=", h)
    
    # 1. Test standard SCSI INQUIRY (36 bytes)
    inquiry_cdb = bytes([0x12, 0, 0, 0, 36, 0])
    ok, msg, data = send_scsi_cmd(h, inquiry_cdb, data_in_len=36)
    print(f"Standard INQUIRY: ok={ok}, msg={msg}, len={len(data)}")
    if ok:
        print("  Inquiry Hex:", data.hex())
        print("  Inquiry ASCII:", "".join(chr(b) if 32 <= b <= 126 else "." for b in data))
        
    # 2. Test APIX Phase 1 Dongle Info: CDB = 0xFA + 'APIX' + 0x00 + 10x 0x00
    apix_info_cdb = bytes([0xFA]) + b"APIX" + bytes([0x00]) + bytes(10)
    ok, msg, data = send_scsi_cmd(h, apix_info_cdb, data_in_len=64)
    print(f"APIX 0xFA/0x00: ok={ok}, msg={msg}, len={len(data)}")
    if ok:
        print("  APIX Hex:", data.hex())
        print("  APIX ASCII:", "".join(chr(b) if 32 <= b <= 126 else "." for b in data))

    ctypes.windll.kernel32.CloseHandle(h)
