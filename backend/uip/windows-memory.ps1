param([switch]$Persistent) # SPDX-License-Identifier: GPL-3.0-only
$ErrorActionPreference = 'Stop'

$source = @'
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Diagnostics;
using System.Runtime.InteropServices;

public static class DarkstarMemoryNative {
    const uint PROCESS_QUERY_INFORMATION = 0x0400;
    const uint PROCESS_QUERY_LIMITED_INFORMATION = 0x1000;
    const uint PROCESS_VM_OPERATION = 0x0008;
    const uint PROCESS_VM_READ = 0x0010;
    const uint PROCESS_VM_WRITE = 0x0020;
    const uint MEM_COMMIT = 0x1000;
    const uint MEM_PRIVATE = 0x20000;
    const uint PAGE_NOACCESS = 0x01;
    const uint PAGE_READONLY = 0x02;
    const uint PAGE_READWRITE = 0x04;
    const uint PAGE_WRITECOPY = 0x08;
    const uint PAGE_EXECUTE = 0x10;
    const uint PAGE_EXECUTE_READ = 0x20;
    const uint PAGE_EXECUTE_READWRITE = 0x40;
    const uint PAGE_EXECUTE_WRITECOPY = 0x80;
    const uint PAGE_GUARD = 0x100;
    const uint TH32CS_SNAPMODULE = 0x00000008;
    const uint TH32CS_SNAPMODULE32 = 0x00000010;

    [StructLayout(LayoutKind.Sequential)]
    struct MEMORY_BASIC_INFORMATION {
        public IntPtr BaseAddress;
        public IntPtr AllocationBase;
        public uint AllocationProtect;
        public UIntPtr RegionSize;
        public uint State;
        public uint Protect;
        public uint Type;
    }

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    struct MODULEENTRY32 {
        public uint dwSize;
        public uint th32ModuleID;
        public uint th32ProcessID;
        public uint GlblcntUsage;
        public uint ProccntUsage;
        public IntPtr modBaseAddr;
        public uint modBaseSize;
        public IntPtr hModule;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 256)] public string szModule;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 260)] public string szExePath;
    }

    [StructLayout(LayoutKind.Sequential)]
    struct FILETIME { public uint Low; public uint High; }

    [DllImport("kernel32.dll", SetLastError = true)] static extern IntPtr OpenProcess(uint access, bool inheritHandle, int processId);
    [DllImport("kernel32.dll", SetLastError = true)] static extern bool CloseHandle(IntPtr handle);
    [DllImport("kernel32.dll", SetLastError = true)] static extern bool ReadProcessMemory(IntPtr process, IntPtr address, byte[] buffer, UIntPtr size, out UIntPtr read);
    [DllImport("kernel32.dll", SetLastError = true)] static extern bool WriteProcessMemory(IntPtr process, IntPtr address, byte[] buffer, UIntPtr size, out UIntPtr written);
    [DllImport("kernel32.dll", SetLastError = true)] static extern UIntPtr VirtualQueryEx(IntPtr process, IntPtr address, out MEMORY_BASIC_INFORMATION info, UIntPtr length);
    [DllImport("kernel32.dll", SetLastError = true)] static extern bool GetProcessTimes(IntPtr process, out FILETIME creation, out FILETIME exit, out FILETIME kernel, out FILETIME user);
    [DllImport("kernel32.dll", SetLastError = true)] static extern bool IsWow64Process(IntPtr process, out bool wow64);
    [DllImport("kernel32.dll", SetLastError = true)] static extern IntPtr CreateToolhelp32Snapshot(uint flags, uint processId);
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)] static extern bool Module32FirstW(IntPtr snapshot, ref MODULEENTRY32 entry);
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)] static extern bool Module32NextW(IntPtr snapshot, ref MODULEENTRY32 entry);

    public sealed class ProcessInfo {
        public int pid { get; set; }
        public string creationTime { get; set; }
        public int pointerSize { get; set; }
    }
    public sealed class ModuleInfo {
        public string name { get; set; }
        public string path { get; set; }
        public string baseAddress { get; set; }
        public long size { get; set; }
    }
    public sealed class RegionInfo {
        public string baseAddress { get; set; }
        public string allocationBase { get; set; }
        public long size { get; set; }
        public uint state { get; set; }
        public uint protect { get; set; }
        public uint type { get; set; }
        public bool readable { get; set; }
        public bool writable { get; set; }
        public bool executable { get; set; }
    }
    public sealed class ReadResult {
        public ProcessInfo process { get; set; }
        public string address { get; set; }
        public string bytesBase64 { get; set; }
        public int length { get; set; }
    }
    public sealed class ReadManyResult {
        public ProcessInfo process { get; set; }
        public ReadResult[] values { get; set; }
    }
    public sealed class SearchHit {
        public string address { get; set; }
        public string bytesBase64 { get; set; }
    }
    public sealed class SearchResult {
        public ProcessInfo process { get; set; }
        public SearchHit[] matches { get; set; }
        public long bytesScanned { get; set; }
        public bool truncated { get; set; }
    }
    public sealed class WriteResult {
        public ProcessInfo process { get; set; }
        public string address { get; set; }
        public int bytesWritten { get; set; }
        public string beforeBase64 { get; set; }
        public string afterBase64 { get; set; }
    }
    public sealed class PointerStep {
        public string readAddress { get; set; }
        public string pointerValue { get; set; }
        public string offset { get; set; }
        public string resultAddress { get; set; }
    }
    public sealed class PointerResult {
        public ProcessInfo process { get; set; }
        public string finalAddress { get; set; }
        public PointerStep[] steps { get; set; }
    }

    static ulong ToUInt64(IntPtr value) { return unchecked((ulong)value.ToInt64()); }
    static IntPtr ToIntPtr(ulong value) { return new IntPtr(unchecked((long)value)); }
    static string Hex(ulong value) { return "0x" + value.ToString("X"); }
    static ulong ParseAddress(string value) {
        string text = (value ?? "").Trim();
        if (text.StartsWith("0x", StringComparison.OrdinalIgnoreCase)) return Convert.ToUInt64(text.Substring(2), 16);
        return Convert.ToUInt64(text, 10);
    }
    static long FileTime(FILETIME value) { return unchecked((long)(((ulong)value.High << 32) | value.Low)); }
    static Exception Win32(string operation) { return new Win32Exception(Marshal.GetLastWin32Error(), operation); }
    static IntPtr Open(int pid, uint access) {
        IntPtr handle = OpenProcess(access, false, pid);
        if (handle == IntPtr.Zero) throw Win32("OpenProcess failed");
        return handle;
    }
    static ProcessInfo Info(IntPtr handle, int pid) {
        FILETIME creation, exit, kernel, user;
        if (!GetProcessTimes(handle, out creation, out exit, out kernel, out user)) throw Win32("GetProcessTimes failed");
        bool wow64 = false;
        if (!IsWow64Process(handle, out wow64)) throw Win32("IsWow64Process failed");
        int pointerSize = Environment.Is64BitOperatingSystem && !wow64 ? 8 : 4;
        if (pointerSize > IntPtr.Size) throw new InvalidOperationException("A 64-bit PowerShell host is required to inspect this 64-bit target process.");
        return new ProcessInfo { pid = pid, creationTime = FileTime(creation).ToString(), pointerSize = pointerSize };
    }
    static void VerifyIdentity(ProcessInfo info, string expectedCreationTime) {
        if (!String.IsNullOrWhiteSpace(expectedCreationTime) && !String.Equals(info.creationTime, expectedCreationTime.Trim(), StringComparison.Ordinal)) {
            throw new InvalidOperationException("The connected process identity changed; refusing to reuse a memory address from an earlier process instance.");
        }
    }
    static bool IsReadable(uint protect, uint state) {
        if (state != MEM_COMMIT || (protect & PAGE_GUARD) != 0 || (protect & PAGE_NOACCESS) != 0) return false;
        uint baseProtect = protect & 0xFF;
        return baseProtect == PAGE_READONLY || baseProtect == PAGE_READWRITE || baseProtect == PAGE_WRITECOPY || baseProtect == PAGE_EXECUTE_READ || baseProtect == PAGE_EXECUTE_READWRITE || baseProtect == PAGE_EXECUTE_WRITECOPY;
    }
    static bool IsExecutable(uint protect) {
        uint baseProtect = protect & 0xFF;
        return baseProtect == PAGE_EXECUTE || baseProtect == PAGE_EXECUTE_READ || baseProtect == PAGE_EXECUTE_READWRITE || baseProtect == PAGE_EXECUTE_WRITECOPY;
    }
    static bool IsWritableNonExecutable(uint protect, uint state) {
        if (state != MEM_COMMIT || (protect & PAGE_GUARD) != 0 || IsExecutable(protect)) return false;
        uint baseProtect = protect & 0xFF;
        return baseProtect == PAGE_READWRITE || baseProtect == PAGE_WRITECOPY;
    }
    static bool Query(IntPtr handle, ulong address, out MEMORY_BASIC_INFORMATION info) {
        UIntPtr result = VirtualQueryEx(handle, ToIntPtr(address), out info, (UIntPtr)Marshal.SizeOf(typeof(MEMORY_BASIC_INFORMATION)));
        return result != UIntPtr.Zero;
    }
    static byte[] ReadHandle(IntPtr handle, ulong address, int length) {
        if (length < 1 || length > 1048576) throw new ArgumentOutOfRangeException("length", "Read length must be between 1 and 1048576 bytes.");
        byte[] buffer = new byte[length];
        UIntPtr read;
        if (!ReadProcessMemory(handle, ToIntPtr(address), buffer, (UIntPtr)length, out read)) throw Win32("ReadProcessMemory failed");
        ulong count = read.ToUInt64();
        if (count != (ulong)length) throw new InvalidOperationException("ReadProcessMemory returned a partial read.");
        return buffer;
    }
    static ulong ReadPointer(IntPtr handle, ulong address, int pointerSize) {
        byte[] bytes = ReadHandle(handle, address, pointerSize);
        return pointerSize == 4 ? BitConverter.ToUInt32(bytes, 0) : BitConverter.ToUInt64(bytes, 0);
    }

    public static ProcessInfo GetInfo(int pid, string expectedCreationTime) {
        IntPtr handle = Open(pid, PROCESS_QUERY_LIMITED_INFORMATION);
        try { ProcessInfo info = Info(handle, pid); VerifyIdentity(info, expectedCreationTime); return info; }
        finally { CloseHandle(handle); }
    }

    public static ModuleInfo[] GetModules(int pid, string expectedCreationTime) {
        ProcessInfo info = GetInfo(pid, expectedCreationTime);
        IntPtr snapshot = CreateToolhelp32Snapshot(TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32, unchecked((uint)pid));
        if (snapshot == new IntPtr(-1)) throw Win32("CreateToolhelp32Snapshot failed");
        try {
            var result = new List<ModuleInfo>();
            MODULEENTRY32 entry = new MODULEENTRY32();
            entry.dwSize = unchecked((uint)Marshal.SizeOf(typeof(MODULEENTRY32)));
            if (!Module32FirstW(snapshot, ref entry)) {
                int error = Marshal.GetLastWin32Error();
                if (error == 18) return result.ToArray();
                throw new Win32Exception(error, "Module32FirstW failed");
            }
            do {
                result.Add(new ModuleInfo { name = entry.szModule ?? "", path = entry.szExePath ?? "", baseAddress = Hex(ToUInt64(entry.modBaseAddr)), size = entry.modBaseSize });
                entry.dwSize = unchecked((uint)Marshal.SizeOf(typeof(MODULEENTRY32)));
            } while (Module32NextW(snapshot, ref entry));
            return result.ToArray();
        } finally { CloseHandle(snapshot); }
    }

    public static RegionInfo[] GetRegions(int pid, string startText, string endText, int maxRegions, string expectedCreationTime) {
        IntPtr handle = Open(pid, PROCESS_QUERY_INFORMATION | PROCESS_VM_READ);
        try {
            ProcessInfo info = Info(handle, pid); VerifyIdentity(info, expectedCreationTime);
            ulong start = String.IsNullOrWhiteSpace(startText) ? 0UL : ParseAddress(startText);
            ulong end = String.IsNullOrWhiteSpace(endText) ? 0x7FFFFFFFFFFFFFFFUL : ParseAddress(endText);
            if (end <= start) throw new ArgumentException("end_address must be greater than start_address.");
            int limit = Math.Max(1, Math.Min(maxRegions <= 0 ? 500 : maxRegions, 5000));
            var result = new List<RegionInfo>();
            ulong cursor = start;
            while (cursor < end && result.Count < limit) {
                MEMORY_BASIC_INFORMATION region;
                if (!Query(handle, cursor, out region)) break;
                ulong baseAddress = ToUInt64(region.BaseAddress);
                ulong size = region.RegionSize.ToUInt64();
                if (size == 0) break;
                ulong regionEnd = baseAddress > UInt64.MaxValue - size ? UInt64.MaxValue : baseAddress + size;
                if (regionEnd > start && baseAddress < end) {
                    result.Add(new RegionInfo {
                        baseAddress = Hex(baseAddress), allocationBase = Hex(ToUInt64(region.AllocationBase)), size = size > Int64.MaxValue ? Int64.MaxValue : (long)size,
                        state = region.State, protect = region.Protect, type = region.Type,
                        readable = IsReadable(region.Protect, region.State), writable = IsWritableNonExecutable(region.Protect, region.State), executable = IsExecutable(region.Protect),
                    });
                }
                if (regionEnd <= cursor) break;
                cursor = regionEnd;
            }
            return result.ToArray();
        } finally { CloseHandle(handle); }
    }

    public static ReadResult Read(int pid, string addressText, int length, string expectedCreationTime) {
        IntPtr handle = Open(pid, PROCESS_QUERY_INFORMATION | PROCESS_VM_READ);
        try {
            ProcessInfo info = Info(handle, pid); VerifyIdentity(info, expectedCreationTime);
            ulong address = ParseAddress(addressText);
            byte[] bytes = ReadHandle(handle, address, length);
            return new ReadResult { process = info, address = Hex(address), bytesBase64 = Convert.ToBase64String(bytes), length = bytes.Length };
        } finally { CloseHandle(handle); }
    }

    public static ReadManyResult ReadMany(int pid, string[] addresses, int length, string expectedCreationTime) {
        if (addresses == null || addresses.Length > 5000) throw new ArgumentException("read_many is limited to 5000 addresses.");
        IntPtr handle = Open(pid, PROCESS_QUERY_INFORMATION | PROCESS_VM_READ);
        try {
            ProcessInfo info = Info(handle, pid); VerifyIdentity(info, expectedCreationTime);
            var result = new List<ReadResult>();
            foreach (string addressText in addresses) {
                ulong address = ParseAddress(addressText);
                byte[] bytes = ReadHandle(handle, address, length);
                result.Add(new ReadResult { process = null, address = Hex(address), bytesBase64 = Convert.ToBase64String(bytes), length = bytes.Length });
            }
            return new ReadManyResult { process = info, values = result.ToArray() };
        } finally { CloseHandle(handle); }
    }

    static bool PatternMatches(byte[] data, int offset, byte[] pattern, byte[] mask) {
        for (int index = 0; index < pattern.Length; index++) {
            if (mask != null && mask.Length > index && mask[index] == 0) continue;
            if (data[offset + index] != pattern[index]) return false;
        }
        return true;
    }

    public static SearchResult Search(int pid, byte[] pattern, byte[] mask, string startText, string endText, long maxBytes, int maxMatches, bool writableOnly, bool privateOnly, string expectedCreationTime) {
        if (pattern == null || pattern.Length < 1 || pattern.Length > 512) throw new ArgumentException("Search pattern must contain 1 to 512 bytes.");
        if (mask != null && mask.Length != pattern.Length) throw new ArgumentException("Search mask length must equal pattern length.");
        long scanLimit = Math.Max(1, Math.Min(maxBytes <= 0 ? 33554432L : maxBytes, 134217728L));
        int matchLimit = Math.Max(1, Math.Min(maxMatches <= 0 ? 500 : maxMatches, 5000));
        IntPtr handle = Open(pid, PROCESS_QUERY_INFORMATION | PROCESS_VM_READ);
        try {
            ProcessInfo info = Info(handle, pid); VerifyIdentity(info, expectedCreationTime);
            ulong start = String.IsNullOrWhiteSpace(startText) ? 0UL : ParseAddress(startText);
            ulong end = String.IsNullOrWhiteSpace(endText) ? 0x7FFFFFFFFFFFFFFFUL : ParseAddress(endText);
            if (end <= start) throw new ArgumentException("end_address must be greater than start_address.");
            var hits = new List<SearchHit>();
            var seen = new HashSet<ulong>();
            long scanned = 0;
            bool truncated = false;
            ulong cursor = start;
            const int chunkLimit = 1048576;
            int overlap = Math.Max(0, pattern.Length - 1);
            while (cursor < end && scanned < scanLimit && hits.Count < matchLimit) {
                MEMORY_BASIC_INFORMATION region;
                if (!Query(handle, cursor, out region)) break;
                ulong regionBase = ToUInt64(region.BaseAddress);
                ulong regionSize = region.RegionSize.ToUInt64();
                if (regionSize == 0) break;
                ulong regionEnd = regionBase > UInt64.MaxValue - regionSize ? UInt64.MaxValue : regionBase + regionSize;
                ulong from = Math.Max(regionBase, start);
                ulong to = Math.Min(regionEnd, end);
                bool eligible = IsReadable(region.Protect, region.State) && (!writableOnly || IsWritableNonExecutable(region.Protect, region.State)) && (!privateOnly || region.Type == MEM_PRIVATE);
                if (eligible && to > from) {
                    ulong position = from;
                    while (position < to && scanned < scanLimit && hits.Count < matchLimit) {
                        ulong remaining = to - position;
                        int requested = (int)Math.Min((ulong)chunkLimit, remaining);
                        long budget = scanLimit - scanned;
                        if (budget < pattern.Length) { scanned = scanLimit; break; }
                        if (budget < requested) requested = (int)budget;
                        if (requested < pattern.Length) break;
                        byte[] data;
                        try { data = ReadHandle(handle, position, requested); }
                        catch { break; }
                        scanned += requested;
                        for (int index = 0; index <= data.Length - pattern.Length && hits.Count < matchLimit; index++) {
                            if (!PatternMatches(data, index, pattern, mask)) continue;
                            ulong address = position + unchecked((ulong)index);
                            if (!seen.Add(address)) continue;
                            byte[] value = new byte[pattern.Length];
                            Buffer.BlockCopy(data, index, value, 0, pattern.Length);
                            hits.Add(new SearchHit { address = Hex(address), bytesBase64 = Convert.ToBase64String(value) });
                        }
                        int advance = requested - overlap;
                        if (advance <= 0) break;
                        position += unchecked((ulong)advance);
                    }
                }
                if (regionEnd <= cursor) break;
                cursor = regionEnd;
            }
            if (cursor < end || hits.Count >= matchLimit || scanned >= scanLimit) truncated = true;
            return new SearchResult { process = info, matches = hits.ToArray(), bytesScanned = scanned, truncated = truncated };
        } finally { CloseHandle(handle); }
    }

    static void AssertWritableRange(IntPtr handle, ulong address, int length) {
        ulong end = checked(address + unchecked((ulong)length));
        ulong cursor = address;
        while (cursor < end) {
            MEMORY_BASIC_INFORMATION region;
            if (!Query(handle, cursor, out region)) throw Win32("VirtualQueryEx failed while validating write range");
            ulong baseAddress = ToUInt64(region.BaseAddress);
            ulong regionSize = region.RegionSize.ToUInt64();
            ulong regionEnd = checked(baseAddress + regionSize);
            if (!IsWritableNonExecutable(region.Protect, region.State)) throw new InvalidOperationException("Memory writes are limited to committed writable, non-executable pages. Darkstar does not change page protections.");
            if (regionEnd <= cursor) throw new InvalidOperationException("Invalid target memory region while validating write range.");
            cursor = Math.Min(regionEnd, end);
        }
    }

    public static WriteResult Write(int pid, string addressText, byte[] bytes, byte[] expected, bool allowUnchecked, string expectedCreationTime) {
        if (bytes == null || bytes.Length < 1 || bytes.Length > 4096) throw new ArgumentException("Memory writes are limited to 1..4096 bytes.");
        if ((expected == null || expected.Length == 0) && !allowUnchecked) throw new InvalidOperationException("A guarded memory write requires expected bytes, or allow_unchecked_write=true.");
        if (expected != null && expected.Length > 0 && expected.Length != bytes.Length) throw new ArgumentException("Expected bytes must have the same length as the write payload.");
        IntPtr handle = Open(pid, PROCESS_QUERY_INFORMATION | PROCESS_VM_READ | PROCESS_VM_WRITE | PROCESS_VM_OPERATION);
        try {
            ProcessInfo info = Info(handle, pid); VerifyIdentity(info, expectedCreationTime);
            ulong address = ParseAddress(addressText);
            AssertWritableRange(handle, address, bytes.Length);
            byte[] before = ReadHandle(handle, address, bytes.Length);
            if (expected != null && expected.Length > 0) {
                for (int index = 0; index < expected.Length; index++) if (before[index] != expected[index]) throw new InvalidOperationException("Guarded memory write rejected because the current bytes no longer match expected_bytes.");
            }
            UIntPtr written;
            if (!WriteProcessMemory(handle, ToIntPtr(address), bytes, (UIntPtr)bytes.Length, out written)) throw Win32("WriteProcessMemory failed");
            if (written.ToUInt64() != (ulong)bytes.Length) throw new InvalidOperationException("WriteProcessMemory returned a partial write.");
            byte[] after = ReadHandle(handle, address, bytes.Length);
            return new WriteResult { process = info, address = Hex(address), bytesWritten = bytes.Length, beforeBase64 = Convert.ToBase64String(before), afterBase64 = Convert.ToBase64String(after) };
        } finally { CloseHandle(handle); }
    }

    public static PointerResult FollowPointerChain(int pid, string baseAddressText, string[] offsets, string expectedCreationTime) {
        if (offsets == null || offsets.Length < 1 || offsets.Length > 32) throw new ArgumentException("Pointer chains require 1..32 offsets.");
        IntPtr handle = Open(pid, PROCESS_QUERY_INFORMATION | PROCESS_VM_READ);
        try {
            ProcessInfo info = Info(handle, pid); VerifyIdentity(info, expectedCreationTime);
            ulong current = ParseAddress(baseAddressText);
            var steps = new List<PointerStep>();
            foreach (string offsetText in offsets) {
                ulong pointer = ReadPointer(handle, current, info.pointerSize);
                long signedOffset = Convert.ToInt64((offsetText ?? "0").Trim().StartsWith("0x", StringComparison.OrdinalIgnoreCase) ? Convert.ToInt64(offsetText.Trim().Substring(2), 16) : Convert.ToInt64(offsetText));
                ulong next = signedOffset >= 0 ? checked(pointer + unchecked((ulong)signedOffset)) : checked(pointer - unchecked((ulong)(-signedOffset)));
                steps.Add(new PointerStep { readAddress = Hex(current), pointerValue = Hex(pointer), offset = signedOffset.ToString(), resultAddress = Hex(next) });
                current = next;
            }
            return new PointerResult { process = info, finalAddress = Hex(current), steps = steps.ToArray() };
        } finally { CloseHandle(handle); }
    }
}
'@

Add-Type -TypeDefinition $source -Language CSharp

function Read-Payload {
    $raw = [Console]::In.ReadToEnd()
    if ([string]::IsNullOrWhiteSpace($raw)) { return [pscustomobject]@{} }
    return $raw | ConvertFrom-Json
}

function Text-Or-Null($value) {
    if ($null -eq $value) { return $null }
    return [string]$value
}

function Bytes-From-Base64($value) {
    if ($null -eq $value -or [string]::IsNullOrWhiteSpace([string]$value)) { return $null }
    return [Convert]::FromBase64String([string]$value)
}

function String-Array($value) {
    if ($null -eq $value) { return [string[]]@() }
    return [string[]]@($value | ForEach-Object { [string]$_ })
}

function Invoke-DarkstarPayload([object]$Payload) {
    $pidValue = [int]$Payload.pid
    $expectedCreationTime = Text-Or-Null $Payload.expectedCreationTime
    $result = switch ([string]$Payload.operation) {
        'memory_info' { [DarkstarMemoryNative]::GetInfo($pidValue, $expectedCreationTime) }
        'memory_modules' { [pscustomobject]@{ process = [DarkstarMemoryNative]::GetInfo($pidValue, $expectedCreationTime); modules = [DarkstarMemoryNative]::GetModules($pidValue, $expectedCreationTime) } }
        'memory_regions' {
            [pscustomobject]@{
                process = [DarkstarMemoryNative]::GetInfo($pidValue, $expectedCreationTime)
                regions = [DarkstarMemoryNative]::GetRegions($pidValue, (Text-Or-Null $Payload.startAddress), (Text-Or-Null $Payload.endAddress), [int]$Payload.maxRegions, $expectedCreationTime)
            }
        }
        'memory_read' { [DarkstarMemoryNative]::Read($pidValue, [string]$Payload.address, [int]$Payload.length, $expectedCreationTime) }
        'memory_read_many' { [DarkstarMemoryNative]::ReadMany($pidValue, (String-Array $Payload.addresses), [int]$Payload.length, $expectedCreationTime) }
        'memory_search' {
            [DarkstarMemoryNative]::Search(
                $pidValue, (Bytes-From-Base64 $Payload.patternBase64), (Bytes-From-Base64 $Payload.maskBase64),
                (Text-Or-Null $Payload.startAddress), (Text-Or-Null $Payload.endAddress), [long]$Payload.maxBytes,
                [int]$Payload.maxMatches, $Payload.writableOnly -eq $true, $Payload.privateOnly -eq $true, $expectedCreationTime
            )
        }
        'memory_write' {
            [DarkstarMemoryNative]::Write(
                $pidValue, [string]$Payload.address, (Bytes-From-Base64 $Payload.bytesBase64),
                (Bytes-From-Base64 $Payload.expectedBase64), $Payload.allowUnchecked -eq $true, $expectedCreationTime
            )
        }
        'memory_pointer_chain' { [DarkstarMemoryNative]::FollowPointerChain($pidValue, [string]$Payload.baseAddress, (String-Array $Payload.offsets), $expectedCreationTime) }
        default { throw "Unsupported memory bridge operation: $($Payload.operation)" }
    }
    return $result
}

if ($Persistent) {
    while ($null -ne ($line = [Console]::In.ReadLine())) {
        if ([string]::IsNullOrWhiteSpace($line)) { continue }
        $requestId = ''
        try {
            $request = $line | ConvertFrom-Json
            $requestId = [string]$request.id
            $response = [pscustomobject]@{ id = $requestId; ok = $true; value = (Invoke-DarkstarPayload $request.payload) }
        } catch {
            $response = [pscustomobject]@{ id = $requestId; ok = $false; error = $_.Exception.Message }
        }
        [Console]::Out.WriteLine(($response | ConvertTo-Json -Depth 10 -Compress)); [Console]::Out.Flush()
    }
    exit 0
}

try {
    (Invoke-DarkstarPayload (Read-Payload)) | ConvertTo-Json -Depth 8 -Compress
} catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 1
}
