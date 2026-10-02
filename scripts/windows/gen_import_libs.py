"""Generate MSVC import libraries (.lib) for the Qt6 DLLs bundled with PySide6.

Parses the PE export table of each Qt6*.dll and drives lib.exe to produce
import libraries usable at link time. The resulting libs refer to symbols
exported by the PySide6-bundled DLLs, so the linked binaries load against the
exact Qt build the Python process already has in memory.
"""
import pathlib
import struct
import subprocess
import sys


def pe_exports(dll_path):
    data = open(dll_path, "rb").read()
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe : pe + 4] != b"PE\0\0":
        raise ValueError("not a PE file")
    num_sections = struct.unpack_from("<H", data, pe + 6)[0]
    opt_size = struct.unpack_from("<H", data, pe + 20)[0]
    magic = struct.unpack_from("<H", data, pe + 24)[0]
    is64 = magic == 0x20B
    dd_base = pe + 24 + (112 if is64 else 96)
    export_rva = struct.unpack_from("<I", data, dd_base)[0]
    pdata_rva, pdata_size = struct.unpack_from("<II", data, dd_base + 3 * 8)
    sec_base = pe + 24 + opt_size
    secs = []
    for i in range(num_sections):
        b = sec_base + 40 * i
        name = data[b : b + 8].rstrip(bytes([0]))
        vsize, vaddr, rawsize, rawptr = struct.unpack_from("<IIII", data, b + 8)
        secs.append((vaddr, max(vsize, 1), rawptr, name))

    def rva2off(rva):
        for vaddr, vsize, rawptr, name in secs:
            if vaddr <= rva < vaddr + vsize:
                return rawptr + (rva - vaddr)
        return None

    def is_function_rva(rva):
        for vaddr, vsize, rawptr, name in secs:
            if vaddr <= rva < vaddr + vsize:
                return name.startswith(b".text")
        return False

    if not export_rva:
        return []
    eoff = rva2off(export_rva)
    if eoff is None:
        return []
    n_names = struct.unpack_from("<I", data, eoff + 24)[0]
    names_rva = struct.unpack_from("<I", data, eoff + 32)[0]
    ords_rva = struct.unpack_from("<I", data, eoff + 36)[0]
    addr_rva = struct.unpack_from("<I", data, eoff + 28)[0]
    noff = rva2off(names_rva)
    eords = rva2off(ords_rva)
    eaddr = rva2off(addr_rva)
    out = []
    for i in range(n_names):
        nrva = struct.unpack_from("<I", data, noff + 4 * i)[0]
        o = rva2off(nrva)
        end = data.index(b"\0", o)
        name = data[o:end].decode("ascii", "ignore")
        ord_index = struct.unpack_from("<H", data, eords + 2 * i)[0]
        rva = struct.unpack_from("<I", data, eaddr + 4 * ord_index)[0]
        out.append((name, rva, is_function_rva(rva)))
    return out


def is_data_symbol(export_entry):
    return not export_entry[2]


def main():
    import PySide6

    pyside_dir = pathlib.Path(PySide6.__file__).resolve().parent
    sdk_lib = pathlib.Path(__file__).resolve().parents[2] / ".deps" / "windows" / "sdk" / "lib"
    def_dir = sdk_lib / "def"
    def_dir.mkdir(parents=True, exist_ok=True)
    failures = []
    dlls = sorted(p for p in pyside_dir.glob("Qt6*.dll") if "Qml" in p.name
                  or p.stem in ("Qt6Core", "Qt6Gui", "Qt6Widgets", "Qt6OpenGL",
                                "Qt6OpenGLWidgets", "Qt6Network", "Qt6Quick",
                                "Qt6QuickControls2", "Qt6QuickTemplates2",
                                "Qt6QuickWidgets", "Qt6QuickShapes",
                                "Qt6ShaderTools", "Qt6Concurrent", "Qt6DBus",
                                "Qt6Xml"))
    for dll in dlls:
        name = dll.stem
        try:
            exports = pe_exports(dll)
            if not exports:
                failures.append((name, "no exports"))
                continue
            def_path = def_dir / (name + ".def")
            with open(def_path, "w", newline="\r\n") as fh:
                fh.write("LIBRARY %s\nEXPORTS\n" % name)
                for sym, _rva, is_func in exports:
                    suffix = "" if is_func else " DATA"
                    fh.write("    %s%s\n" % (sym, suffix))
            lib_path = sdk_lib / (name + ".lib")
            proc = subprocess.run(
                ["lib.exe", "/nologo", "/machine:X64",
                 "/def:%s" % def_path, "/out:%s" % lib_path],
                capture_output=True, text=True)
            if proc.returncode != 0 or not lib_path.exists():
                failures.append((name, (proc.stdout + proc.stderr)[:400]))
        except Exception as exc:  # noqa: BLE001 - report and continue
            failures.append((name, str(exc)[:400]))
    print("generated libs for %d dlls, %d failures" % (len(dlls) - len(failures), len(failures)))
    for name, err in failures:
        print("FAIL %s: %s" % (name, err))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
