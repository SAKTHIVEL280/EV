"""Child processes never outlive core (docs/ARCHITECTURE.md §1).

- Windows: children are assigned to a Job Object created with
  JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE. Core holds the only handle; when core
  exits for any reason the OS closes it and kills every child.
- Linux: PR_SET_PDEATHSIG makes the kernel send SIGKILL to the child when the
  thread that spawned it (core's event loop thread) dies.
"""

import ctypes
import signal
import subprocess
import sys
from typing import Any

if sys.platform == "win32":
    from ctypes import wintypes

    _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS = 9
    _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
    _PROCESS_SET_QUOTA = 0x0100
    _PROCESS_TERMINATE = 0x0001

    class _BasicLimits(ctypes.Structure):
        _fields_ = (
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        )

    class _IoCounters(ctypes.Structure):
        _fields_ = tuple(
            (name, ctypes.c_uint64)
            for name in (
                "ReadOperationCount",
                "WriteOperationCount",
                "OtherOperationCount",
                "ReadTransferCount",
                "WriteTransferCount",
                "OtherTransferCount",
            )
        )

    class _ExtendedLimits(ctypes.Structure):
        _fields_ = (
            ("BasicLimitInformation", _BasicLimits),
            ("IoInfo", _IoCounters),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        )

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    _kernel32.CreateJobObjectW.argtypes = (wintypes.LPVOID, wintypes.LPCWSTR)
    _kernel32.SetInformationJobObject.restype = wintypes.BOOL
    _kernel32.SetInformationJobObject.argtypes = (
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPVOID,
        wintypes.DWORD,
    )
    _kernel32.OpenProcess.restype = wintypes.HANDLE
    _kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    _kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
    _kernel32.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
    _kernel32.CloseHandle.restype = wintypes.BOOL
    _kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)


class ChildGuard:
    """Owns the platform mechanism that ties children's lifetime to core."""

    def __init__(self) -> None:
        self._job: int | None = None
        if sys.platform == "win32":
            job = _kernel32.CreateJobObjectW(None, None)
            if not job:
                raise ctypes.WinError(ctypes.get_last_error())
            limits = _ExtendedLimits()
            limits.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            ok = _kernel32.SetInformationJobObject(
                job,
                _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS,
                ctypes.byref(limits),
                ctypes.sizeof(limits),
            )
            if not ok:
                error = ctypes.get_last_error()
                _kernel32.CloseHandle(job)
                raise ctypes.WinError(error)
            self._job = job

    def spawn_kwargs(self) -> dict[str, Any]:
        """Extra keyword arguments for subprocess creation."""
        if sys.platform == "win32":
            return {"creationflags": subprocess.CREATE_NO_WINDOW}
        if sys.platform == "linux":
            return {"preexec_fn": _die_with_parent}
        return {}

    def adopt(self, pid: int) -> None:
        """Windows: put a just-started child into the job. No-op elsewhere."""
        if sys.platform == "win32" and self._job is not None:
            process = _kernel32.OpenProcess(_PROCESS_SET_QUOTA | _PROCESS_TERMINATE, False, pid)
            if not process:
                raise ctypes.WinError(ctypes.get_last_error())
            try:
                if not _kernel32.AssignProcessToJobObject(self._job, process):
                    raise ctypes.WinError(ctypes.get_last_error())
            finally:
                _kernel32.CloseHandle(process)

    def close(self) -> None:
        """Windows: close the job handle, killing every adopted child (used by tests)."""
        if sys.platform == "win32" and self._job is not None:
            _kernel32.CloseHandle(self._job)
            self._job = None


def _die_with_parent() -> None:
    # Runs in the forked child before exec: only async-signal-safe work here.
    pr_set_pdeathsig = 1
    libc = ctypes.CDLL(None, use_errno=True)
    libc.prctl(pr_set_pdeathsig, signal.SIGKILL)
