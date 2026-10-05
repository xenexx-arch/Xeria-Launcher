import os, sys, json, zipfile, subprocess, platform, tempfile, shutil
from pathlib import Path

from PyQt5.QtCore import Qt, QSize
from PyQt5.QtWidgets import (
    QMessageBox, QDialog, QFileDialog, QInputDialog, QListWidgetItem,
)
from core import theme
from core.paths import (PROFILES_DIR, MANIFEST_URL,
                        IS_WIN, IS_MAC, NO_WINDOW, XERIA_ROOT)
from core.java import best_java, recommended_java_for
from core.worker import Worker
from instances.profile import Profile
from ui.dialogs import (ChooseInstallDialog, ModpackSearchDialog,
                        ProfileDialog)
from ui.helpers import s_menu
from ui.loader_icons import loader_icon_sync, fetch_loader_icon
import requests


class ProfilesMixin:
    ROW_HEIGHT = 56
    ROW_GAP = 6

    def load_profiles(self):
        self.plist.blockSignals(True)
        self.plist.clear()
        self.plist.setSpacing(self.ROW_GAP)
        self._row_map = []
        self.profiles = Profile.load_all()

        for p in self.profiles:
            it = QListWidgetItem(f"{p.name}\n{p.version}")
            it.setSizeHint(QSize(0, self.ROW_HEIGHT))
            loader = (p.loader or "vanilla").lower()
            cached = loader_icon_sync(loader)
            if cached is not None:
                it.setIcon(cached)
            self.plist.addItem(it)
            self._row_map.append(p)

        self.plist.blockSignals(False)

        for p in self.profiles:
            loader = (p.loader or "vanilla").lower()
            if loader_icon_sync(loader) is None:
                fetch_loader_icon(loader, self._apply_loader_icon)

        if self.profiles:
            self.plist.setCurrentRow(0)
        else:
            self.current_profile = None
            self._update_card()

    def _on_row_changed(self, row):
        if row < 0 or row >= len(self._row_map):
            self.current_profile = None
            self._update_card()
            self._set_launch_state(self._running_profile is not None,
                                   self._running_profile)
            return
        self.current_profile = self._row_map[row]
        self._update_card()
        self._set_launch_state(self._running_profile is not None,
                               self._running_profile)

    def _update_card(self):
        p = self.current_profile
        if p is None:
            self.card_title.setText("No instance selected")
            self.card_sub.setText('Click "+" to create an instance')
            return
        self.card_title.setText(p.name)

        ld = {"vanilla": "Vanilla", "fabric": "Fabric", "forge": "Forge",
              "neoforge": "NeoForge", "quilt": "Quilt"}.get(p.loader, p.loader)

        gc = p.override_gc or self.settings.get("gc", "G1GC")
        gc_names = {
            "G1GC": "G1GC",
            "ZGC": "ZGC",
            "Parallel": "ParallelGC",
            "Serial": "SerialGC",
        }
        gc_label = gc_names.get(gc, gc)
        gc_suffix = " (profile override)" if p.override_gc else ""

        want = recommended_java_for(p.version)
        if isinstance(want, (list, tuple)):
            jver = want[0] if want else "?"
        elif isinstance(want, dict):
            jver = want.get("version") or want.get("major") or "?"
        else:
            jver = want

        java_path = None
        try:
            java_path = best_java(p.version, log=None,
                                  override=p.override_java_path or
                                  self.settings.get("java_path", ""))
        except Exception:
            pass
        vendor = self._java_vendor(java_path) if java_path else ""

        if vendor:
            java_label = f"Java {vendor} {jver}"
        else:
            java_label = f"Java {jver}"

        self.card_sub.setText(
            f"{ld} {p.version}, {p.ram} GB RAM with "
            f"{gc_label}{gc_suffix} and {java_label}")

    def _java_vendor(self, java_path):
        import subprocess, re
        if not java_path:
            return ""
        if not hasattr(self, "_vendor_cache"):
            self._vendor_cache = {}
        if java_path in self._vendor_cache:
            return self._vendor_cache[java_path]
        try:
            out = subprocess.run([java_path, "-version"],
                                 capture_output=True, text=True, timeout=5,
                                 creationflags=NO_WINDOW)
            txt = (out.stderr or "") + (out.stdout or "")
        except Exception:
            self._vendor_cache[java_path] = ""
            return ""
        m = re.search(r"OpenJDK Runtime Environment (\w+)-", txt)
        if m:
            result = m.group(1)
        else:
            result = "OpenJDK"
            for name in ("Oracle", "Temurin", "Zulu", "Corretto",
                         "Liberica", "Microsoft", "Semeru", "OpenJ9"):
                if name in txt:
                    result = name
                    break
        self._vendor_cache[java_path] = result
        return result

    def add_new(self):
        ch = ChooseInstallDialog(self)
        if ch.exec_() != QDialog.Accepted or not ch.choice: return
        if ch.choice == "blank": self._add_blank_profile()
        elif ch.choice == "local": self._add_local_modpack()
        elif ch.choice == "modrinth": self._add_modrinth_modpack()

    def _add_blank_profile(self):
        if not self.releases:
            try:
                d = requests.get(MANIFEST_URL, timeout=8).json()
                self.manifest = d
                self.releases = [v for v in d["versions"]
                                 if v["type"] == "release"]
            except Exception as e:
                QMessageBox.critical(self, "Error",
                                     f"Cannot fetch versions:\n{e}"); return
        dlg = ProfileDialog(self, self.releases, self.settings)
        if dlg.exec_() != QDialog.Accepted: return
        name, ver, ram, loader = dlg.values()
        if not name:
            QMessageBox.warning(self, "Error", "Name required."); return
        if any(c in name for c in r'/\:*?"<>|'):
            QMessageBox.warning(self, "Error", "Invalid characters."); return
        if (PROFILES_DIR / f"{name}.json").exists():
            QMessageBox.warning(self, "Exists",
                                f"'{name}' already exists."); return
        p = Profile(name)
        p.version = ver; p.ram = ram; p.loader = loader
        dlg.apply(p)
        p.dir; p.save()
        self.console.log("ok", f"created '{name}'")
        self.load_profiles()

    def _add_local_modpack(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Modpack", str(Path.home()),
            "Modpacks (*.xerpack *.zip *.mrpack);;All files (*)")
        if not path: return
        w = Worker(self._install_local_modpack_task, path)
        w.log.connect(self.console.log, Qt.QueuedConnection)
        w.progress.connect(lambda *a: self.console.log("progress", a),
                           Qt.QueuedConnection)
        w.progress_end.connect(lambda: self.console.log("progress_end", None),
                               Qt.QueuedConnection)
        w.done.connect(self._modpack_done, Qt.QueuedConnection)
        self._track(w); w.start()

    def _install_local_modpack_task(self, path, log, progress, progress_end):
        from integration import modpack
        return modpack.install(path, log=log, progress=progress,
                               progress_end=progress_end)

    def _add_modrinth_modpack(self):
        dlg = ModpackSearchDialog(self, self.console.log)
        if dlg.exec_() != QDialog.Accepted or not dlg.result: return
        hit = dlg.result
        w = Worker(self._download_and_install_modpack, hit)
        w.log.connect(self.console.log, Qt.QueuedConnection)
        w.progress.connect(lambda *a: self.console.log("progress", a),
                           Qt.QueuedConnection)
        w.progress_end.connect(lambda: self.console.log("progress_end", None),
                               Qt.QueuedConnection)
        w.done.connect(self._modpack_done, Qt.QueuedConnection)
        self._track(w); w.start()

    def _download_and_install_modpack(self, hit, log, progress, progress_end):
        from integration import modrinth, modpack
        picked = modrinth.pick_modpack_file(hit["id"])
        if not picked:
            log("error", "no .mrpack found"); return None
        url, filename, ver = picked
        log("ok", f"version {ver}: {filename}")
        tmp = Path(tempfile.gettempdir()) / filename
        try:
            with requests.get(url, stream=True, timeout=180) as r:
                r.raise_for_status()
                total = int(r.headers.get("content-length", 0)); done = 0
                with open(tmp, "wb") as f:
                    for chunk in r.iter_content(65536):
                        f.write(chunk); done += len(chunk)
                        if total and progress:
                            progress(filename, done, total, "", "")
            if progress_end: progress_end()
        except Exception as e:
            log("error", f"download failed: {e}"); return None
        name = modpack.install(str(tmp), log=log, progress=progress,
                               progress_end=progress_end)
        try: tmp.unlink()
        except Exception: pass
        return name

    def _modpack_done(self, name):
        if name:
            self.console.log("ok", f"modpack '{name}' installed")
            self.load_profiles()
        else:
            self.console.log("error", "modpack install failed")

    def edit_profile(self):
        if not self.current_profile: return
        p = self.current_profile
        dlg = ProfileDialog(self, self.releases, self.settings, profile=p)
        if dlg.exec_() != QDialog.Accepted: return
        name, ver, ram, loader = dlg.values()
        if not name:
            QMessageBox.warning(self, "Error", "Name required."); return
        old = p.name
        if name != old:
            if any(c in name for c in r'/\:*?"<>|'):
                QMessageBox.warning(self, "Error",
                                    "Invalid characters."); return
            if (PROFILES_DIR / f"{name}.json").exists():
                QMessageBox.warning(self, "Exists",
                                    f"'{name}' exists."); return
            (PROFILES_DIR / f"{old}.json").rename(
                PROFILES_DIR / f"{name}.json")
            if (PROFILES_DIR / old).exists():
                (PROFILES_DIR / old).rename(PROFILES_DIR / name)
            p.name = name
        p.version = ver; p.ram = ram; p.loader = loader
        dlg.apply(p)
        p.save(); self.load_profiles()

    def rename_profile(self):
        if not self.current_profile: return
        old = self.current_profile.name
        new, ok = QInputDialog.getText(self, "Rename", "New name:", text=old)
        if not ok or not new.strip(): return
        new = new.strip()
        if new == old: return
        if any(c in new for c in r'/\:*?"<>|'):
            QMessageBox.warning(self, "Error", "Invalid characters."); return
        if (PROFILES_DIR / f"{new}.json").exists():
            QMessageBox.warning(self, "Exists", f"'{new}' exists."); return
        (PROFILES_DIR / f"{old}.json").rename(PROFILES_DIR / f"{new}.json")
        (PROFILES_DIR / old).rename(PROFILES_DIR / new)
        self.load_profiles()

    def duplicate_profile(self):
        if not self.current_profile: return
        src = self.current_profile
        new_name = f"{src.name} (copy)"; n = 1
        while (PROFILES_DIR / f"{new_name}.json").exists():
            new_name = f"{src.name} (copy {n})"; n += 1
        p = Profile(new_name)
        p.version = src.version; p.ram = src.ram; p.loader = src.loader
        p.override_gc = src.override_gc
        p.override_jvm_flags = src.override_jvm_flags
        p.override_env_vars = src.override_env_vars
        p.override_java_path = src.override_java_path
        p.override_wrapper = src.override_wrapper
        p.override_nvidia_fix = getattr(src, "override_nvidia_fix", False)
        p.dir; p.save()
        try:
            if src.dir.exists():
                shutil.copytree(str(src.dir), str(p.dir),
                                dirs_exist_ok=True)
        except Exception: pass
        self.load_profiles()

    def delete_profile(self):
        if not self.current_profile: return
        if QMessageBox.question(self, "Delete",
            f"Delete '{self.current_profile.name}'?\n"
            f"Mods and worlds removed too."
        ) != QMessageBox.Yes: return
        n = self.current_profile.name
        Profile.delete(n)
        self.console.log("warn", f"deleted '{n}'")
        self.current_profile = None; self.load_profiles()

    def open_folder(self):
        if not self.current_profile: return
        p = str(self.current_profile.dir)
        try:
            if IS_WIN: os.startfile(p)
            elif IS_MAC: subprocess.Popen(["open", p])
            else: subprocess.Popen(["xdg-open", p])
        except Exception as e:
            self.console.log("error", f"open folder failed: {e}")

    def export_mrpack(self):
        if not self.current_profile: return
        p = self.current_profile
        default_name = f"{p.name}.mrpack"
        path, _ = QFileDialog.getSaveFileName(
            self, "Export as Modrinth pack",
            str(Path.home() / default_name),
            "Modrinth pack (*.mrpack);;Zip (*.zip)")
        if not path: return
        self.console.log("info", f"exporting '{p.name}' as .mrpack")
        w = Worker(self._export_task, p, path)
        w.log.connect(self.console.log, Qt.QueuedConnection)
        w.progress.connect(lambda *a: self.console.log("progress", a),
                           Qt.QueuedConnection)
        w.progress_end.connect(lambda: self.console.log("progress_end", None),
                               Qt.QueuedConnection)
        self._track(w); w.start()

    def _export_task(self, profile, path, log, progress, progress_end):
        from integration import modpack
        return modpack.export_mrpack(profile, path, log=log,
                                     progress=progress,
                                     progress_end=progress_end)

    def import_instance(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Import instance", str(Path.home()),
            "Xeria pack (*.xeriapack *.zip *.mrpack);;All files (*)")
        if not path: return
        if path.lower().endswith(".mrpack"):
            w = Worker(self._install_local_modpack_task, path)
            w.log.connect(self.console.log, Qt.QueuedConnection)
            w.progress.connect(lambda *a: self.console.log("progress", a),
                               Qt.QueuedConnection)
            w.progress_end.connect(
                lambda: self.console.log("progress_end", None),
                Qt.QueuedConnection)
            w.done.connect(self._modpack_done, Qt.QueuedConnection)
            self._track(w); w.start()
            return
        self.console.log("info", f"importing {Path(path).name}")

        def task(log, progress, progress_end):
            with zipfile.ZipFile(path) as z:
                names = z.namelist()
                root_json = next((n for n in names
                                  if n.endswith(".json") and "/" not in n),
                                 None)
                if not root_json:
                    log("error", "no profile json in pack"); return None
                data = json.loads(z.read(root_json))
                base = Path(root_json).stem
                name = base; n = 1
                while (PROFILES_DIR / f"{name}.json").exists():
                    name = f"{base} ({n})"; n += 1
                total = max(1, len(names))
                for i, member in enumerate(names, 1):
                    if member == root_json: continue
                    target = PROFILES_DIR / member
                    if member.endswith("/"):
                        target.mkdir(parents=True, exist_ok=True); continue
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with z.open(member) as src, open(target, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    if progress and i % 20 == 0:
                        progress("import", i, total, "", "")
                (PROFILES_DIR / f"{name}.json").write_text(
                    json.dumps(data, indent=2))
                if progress_end: progress_end()
                log("ok", f"imported as '{name}'")
                return name

        w = Worker(task)
        w.log.connect(self.console.log, Qt.QueuedConnection)
        w.progress.connect(lambda *a: self.console.log("progress", a),
                           Qt.QueuedConnection)
        w.progress_end.connect(lambda: self.console.log("progress_end", None),
                               Qt.QueuedConnection)
        w.done.connect(lambda _: self.load_profiles(), Qt.QueuedConnection)
        self._track(w); w.start()

    def backup_instance(self):
        if not self.current_profile: return
        import datetime
        p = self.current_profile
        backups = XERIA_ROOT / "backups"
        backups.mkdir(parents=True, exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        dest = backups / f"{p.name}-{ts}.zip"
        self.console.log("info", f"backup → {dest.name}")

        def task(log, progress, progress_end):
            files = []
            game_dir = p.dir
            for sub in ("mods", "resourcepacks", "shaderpacks",
                        "config", "saves"):
                d = game_dir / sub
                if not d.exists(): continue
                for f in d.rglob("*"):
                    if f.is_file():
                        files.append((f, str(f.relative_to(game_dir))))
            total = max(1, len(files))
            with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
                for i, (src, arc) in enumerate(files, 1):
                    z.write(src, arc)
                    if progress and i % 20 == 0:
                        progress("backup", i, total, "", "")
            if progress_end: progress_end()
            log("ok", f"backup saved ({dest.stat().st_size // 1024} KB)")

        w = Worker(task)
        w.log.connect(self.console.log, Qt.QueuedConnection)
        w.progress.connect(lambda *a: self.console.log("progress", a),
                           Qt.QueuedConnection)
        w.progress_end.connect(lambda: self.console.log("progress_end", None),
                               Qt.QueuedConnection)
        self._track(w); w.start()

    def copy_launch_command(self):
        if not self.current_profile: return
        p = self.current_profile
        try:
            from core.java import best_java as _bj
            from core.jvm import default_jvm_flags as _djf
            java_override = (p.override_java_path or
                             self.settings.get("java_path", ""))
            java = _bj(p.version, log=None, override=java_override) or "java"
            gc = p.override_gc or self.settings.get("gc", "G1GC")
            combined = ((self.settings.get("jvm_flags", "") or "") + " " +
                        (p.override_jvm_flags or "")).strip()
            import shlex as _sh
            user_flags = _sh.split(combined) if combined else []
            jvm = _djf(p.ram, gc) + user_flags
            cmd = [java] + jvm + [
                "-cp", "<classpath>",
                "net.minecraft.client.main.Main",
                "--username", self._get_username(),
                "--version", p.version,
                "--gameDir", str(p.dir),
                "--assetsDir", str(MC_ROOT / "assets"),
                "--assetIndex", "legacy",
                "--uuid", self._uuid(self._get_username()),
                "--accessToken",
                    self.account.mc_access if self.account.signed_in else "0",
                "--userType", "msa" if self.account.signed_in else "legacy",
                "--versionType", "release"]
            wrapper = (p.override_wrapper or
                       self.settings.get("wrapper_command", "").strip())
            if wrapper: cmd = _sh.split(wrapper) + cmd
            text = " ".join(_sh.quote(c) for c in cmd)
            from PyQt5.QtGui import QGuiApplication
            QGuiApplication.clipboard().setText(text)
            self.console.log("ok", "launch command copied to clipboard")
        except Exception as e:
            self.console.log("error", f"copy command failed: {e}")

    def open_logs(self):
        if not self.current_profile: return
        logs = self.current_profile.dir / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        try:
            if IS_WIN: os.startfile(str(logs))
            elif IS_MAC: subprocess.Popen(["open", str(logs)])
            else: subprocess.Popen(["xdg-open", str(logs)])
        except Exception as e:
            self.console.log("error", f"open logs failed: {e}")
