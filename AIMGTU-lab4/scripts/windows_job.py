"""Windows Job Object: a commit limit for a process tree, not physical RAM emulation."""
from __future__ import annotations
import ctypes,os
from ctypes import wintypes as W

class BasicLimit(ctypes.Structure):
    _fields_=[('PerProcessUserTimeLimit',ctypes.c_longlong),('PerJobUserTimeLimit',ctypes.c_longlong),
              ('LimitFlags',W.DWORD),('MinimumWorkingSetSize',ctypes.c_size_t),('MaximumWorkingSetSize',ctypes.c_size_t),
              ('ActiveProcessLimit',W.DWORD),('Affinity',ctypes.c_size_t),('PriorityClass',W.DWORD),('SchedulingClass',W.DWORD)]
class IoCounters(ctypes.Structure):
    _fields_=[(name,ctypes.c_ulonglong) for name in ['ReadOperationCount','WriteOperationCount','OtherOperationCount','ReadTransferCount','WriteTransferCount','OtherTransferCount']]
class ExtendedLimit(ctypes.Structure):
    _fields_=[('BasicLimitInformation',BasicLimit),('IoInfo',IoCounters),('ProcessMemoryLimit',ctypes.c_size_t),
              ('JobMemoryLimit',ctypes.c_size_t),('PeakProcessMemoryUsed',ctypes.c_size_t),('PeakJobMemoryUsed',ctypes.c_size_t)]

class MemoryJob:
    def __init__(self,limit_bytes):
        if os.name!='nt':raise OSError('This memory-limit test requires Windows')
        self.api=ctypes.WinDLL('kernel32',use_last_error=True)
        self.api.CreateJobObjectW.argtypes=[ctypes.c_void_p,W.LPCWSTR];self.api.CreateJobObjectW.restype=W.HANDLE
        self.api.SetInformationJobObject.argtypes=[W.HANDLE,ctypes.c_int,ctypes.c_void_p,W.DWORD];self.api.SetInformationJobObject.restype=W.BOOL
        self.api.QueryInformationJobObject.argtypes=[W.HANDLE,ctypes.c_int,ctypes.c_void_p,W.DWORD,ctypes.c_void_p];self.api.QueryInformationJobObject.restype=W.BOOL
        self.api.AssignProcessToJobObject.argtypes=[W.HANDLE,W.HANDLE];self.api.AssignProcessToJobObject.restype=W.BOOL
        self.api.OpenProcess.argtypes=[W.DWORD,W.BOOL,W.DWORD];self.api.OpenProcess.restype=W.HANDLE
        self.api.CloseHandle.argtypes=[W.HANDLE];self.api.CloseHandle.restype=W.BOOL
        self.api.IsProcessInJob.argtypes=[W.HANDLE,W.HANDLE,ctypes.POINTER(W.BOOL)];self.api.IsProcessInJob.restype=W.BOOL
        self.handle=self.api.CreateJobObjectW(None,None)
        if not self.handle:raise ctypes.WinError(ctypes.get_last_error())
        self.limit=ExtendedLimit();self.limit.BasicLimitInformation.LimitFlags=0x200|0x2000
        self.limit.JobMemoryLimit=limit_bytes
        if not self.api.SetInformationJobObject(self.handle,9,ctypes.byref(self.limit),ctypes.sizeof(self.limit)):
            error=ctypes.WinError(ctypes.get_last_error());self.close();raise error
    def info(self):
        info=ExtendedLimit()
        if not self.api.QueryInformationJobObject(self.handle,9,ctypes.byref(info),ctypes.sizeof(info),None):raise ctypes.WinError(ctypes.get_last_error())
        return {'limit_bytes':info.JobMemoryLimit,'peak_job_commit_bytes':info.PeakJobMemoryUsed}
    def assign(self,pid):
        if self.contains(pid):return
        handle=self.api.OpenProcess(0x0100|0x0001|0x1000,False,pid)
        if not handle:raise ctypes.WinError(ctypes.get_last_error())
        try:
            if not self.api.AssignProcessToJobObject(self.handle,handle):
                error=ctypes.WinError(ctypes.get_last_error())
                raise OSError(f'Cannot assign PID {pid} to memory job: {error}')
        finally:self.api.CloseHandle(handle)
    def contains(self,pid):
        handle=self.api.OpenProcess(0x1000,False,pid)
        if not handle:return False
        try:
            result=W.BOOL()
            return bool(self.api.IsProcessInJob(handle,self.handle,ctypes.byref(result)) and result.value)
        finally:self.api.CloseHandle(handle)
    def close(self):
        if self.handle:self.api.CloseHandle(self.handle);self.handle=None
    def __enter__(self):return self
    def __exit__(self,*args):self.close()
