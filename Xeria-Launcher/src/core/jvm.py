import shlex


def default_jvm_flags(ram, gc):
    ram = int(ram); half = max(1, ram // 2)
    gc = (gc or "G1GC").upper()
    out = [f"-Xmx{ram}G", f"-Xms{half}G", "-XX:+UnlockExperimentalVMOptions"]
    if gc == "ZGC":
        out += ["-XX:+UseZGC"]
    elif gc == "PARALLEL":
        out += ["-XX:+UseParallelGC"]
    elif gc == "SERIAL":
        out += ["-XX:+UseSerialGC"]
    else:
        out += ["-XX:+UseG1GC", "-XX:G1NewSizePercent=20",
                "-XX:G1ReservePercent=20", "-XX:MaxGCPauseMillis=50",
                "-XX:G1HeapRegionSize=32M"]
    out += [
        "-XX:+DisableExplicitGC", "-XX:+AlwaysPreTouch",
        "-XX:+ParallelRefProcEnabled", "-XX:+PerfDisableSharedMem",
        "-XX:+UseStringDeduplication", "-XX:+OptimizeStringConcat",
        "-Dfile.encoding=UTF-8", "-Dstdout.encoding=UTF-8",
        "-Dstderr.encoding=UTF-8",
        "-Dminecraft.launcher.brand=xeria", "-Dminecraft.launcher.version=1.0",
        "-Dlog4j2.formatMsgNoLookups=true",
        "-Dfml.ignoreInvalidMinecraftCertificates=true",
        "-Dfml.ignorePatchDiscrepancies=true",
    ]
    return out


def build_jvm_flags(profile, settings, native_dirs, sep):
    ram = int(profile.ram)
    gc = (profile.override_gc or settings.get("gc", "G1GC") or "G1GC")
    default = (settings.get("default_jvm_flags", "") or "").strip()
    combined = ((settings.get("jvm_flags", "") or "") + " " +
                default + " " +
                (profile.override_jvm_flags or "")).strip()
    user_flags = []
    if combined:
        try: user_flags = shlex.split(combined)
        except Exception: user_flags = combined.split()
    flags = default_jvm_flags(ram, gc)
    if native_dirs:
        flags.append(f"-Djava.library.path={sep.join(native_dirs)}")
    flags.extend(user_flags)
    return flags
