import os
import json
import glob
try:
    import winreg
    from win32com.client import Dispatch
except ImportError:
    winreg = None
    Dispatch = None
import subprocess
from typing import Union, Dict, Any
from lib.systems.platform import Platform
from lib.utils.logger import Logger
from lib.core.packages import KnownPackage

class WindowsPlatform(Platform):
    def install_package(self, package: Union[str, KnownPackage]) -> None:
        if isinstance(package, KnownPackage):
            package_name = package.value.win
        else:
            package_name = package

        Logger.info(f"Installing {package_name} via Winget...")
        cmd = [
            "winget", "install", "-e", 
            "--id", package_name, 
            "--scope", "user", 
            "--accept-package-agreements", 
            "--accept-source-agreements",
            "--silent"
        ]
        
        try:
            # shell=True might be needed if winget is not in direct path but usually it is.
            # However, for consistency with other windows commands, I'll keep default unless needed.
            # Actually, `winget` is an exe, but `shell=True` helps with path resolution sometimes.
            # I'll try without shell=True first as it's safer, but if it fails I might need it.
            # The bat file uses it directly.
            subprocess.run(cmd, check=True, shell=True) 
            Logger.ok(f"Successfully installed {package_name}")
        except subprocess.CalledProcessError as e:
            if e.returncode != 0x8A15002B:
                Logger.err(f"Failed to install {package_name}: {e}")
                raise

    def add_to_path(self, folder_path: str) -> None:
        key_path = r"Environment"
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, 
                                 winreg.KEY_ALL_ACCESS)
        except FileNotFoundError:
            key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path)

        try:
            try:
                current_path_value, _ = winreg.QueryValueEx(key, "Path")
            except FileNotFoundError:
                current_path_value = ""

            if folder_path in current_path_value:
                Logger.warn(f"'{folder_path}' is already in the PATH.")
                return

            new_path_value = current_path_value + (";" if current_path_value else "") + folder_path

            winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, new_path_value)
            
            # Update current process environment so subsequent commands work immediately
            os.environ["PATH"] = new_path_value
            
            Logger.ok(f"Successfully added '{folder_path}' to User PATH.")
            
        except Exception as e:
            Logger.err(f"Failed to add path variable: {e}")
            raise
        
        finally:
            winreg.CloseKey(key)

    def install_vscode_extension(self, extension_id: str) -> None:
        # Assuming 'code' is in PATH.
        # On Windows, shell=True is often needed for batch files/cmd commands to resolve correctly if not direct executables.
        subprocess.run(["code", "--install-extension", extension_id], shell=True, check=True, stdout=subprocess.DEVNULL)

    def get_home_dir(self) -> str:
        return os.path.expanduser("~")

    def get_vscode_settings_path(self) -> str:
        return os.path.join(os.environ["APPDATA"], "Code", "User", "settings.json")

    def get_vscode_keybindings_path(self) -> str:
        return os.path.join(os.environ["APPDATA"], "Code", "User", "keybindings.json")

    def create_shortcut(self, target_path: str, shortcut_path: str, description: str = "", icon_path: str = "", working_dir: str = "", hotkey: str = "") -> None:
        if not Dispatch:
            Logger.err("win32com.client not available. Cannot create shortcut.")
            return

        try:
            shell = Dispatch('WScript.Shell')
            shortcut = shell.CreateShortCut(shortcut_path)
            shortcut.TargetPath = target_path
            if description:
                shortcut.Description = description
            if icon_path:
                shortcut.IconLocation = icon_path
            if working_dir:
                shortcut.WorkingDirectory = working_dir
            if hotkey:
                shortcut.Hotkey = hotkey
            shortcut.save()
            Logger.ok(f"Shortcut created at '{shortcut_path}'" + (f" with hotkey '{hotkey}'" if hotkey else ""))
        except Exception as e:
            Logger.err(f"Failed to create shortcut: {e}")

    def get_windows_terminal_settings_path(self) -> str:
        """Finds the Windows Terminal settings.json path."""
        local_app_data = os.environ.get("LOCALAPPDATA")
        if not local_app_data:
            return ""
        
        packages_dir = os.path.join(local_app_data, "Packages")
        # Pattern to find Windows Terminal package folder
        pattern = os.path.join(packages_dir, "Microsoft.WindowsTerminal_*")
        matches = glob.glob(pattern)
        
        if matches:
            # Sort to pick the one that looks most like the main release if multiple?
            # Usually there is one. We take the first one.
            package_dir = matches[0]
            settings_path = os.path.join(package_dir, "LocalState", "settings.json")
            if os.path.exists(settings_path):
                return settings_path
        
        return ""

    def get_windows_terminal_executable(self) -> str:
        """Finds the Windows Terminal executable path."""
        # It's usually in C:\Program Files\WindowsApps\Microsoft.WindowsTerminal_...
        # But accessing WindowsApps is restricted. 
        # Better to point to the App execution alias which is accessible?
        # App execution alias: %LOCALAPPDATA%\Microsoft\WindowsApps\wt.exe
        # But for the shortcut target, we might want the real exe or wt.exe.
        # The TODO example showed: "C:\Program Files\WindowsApps\Microsoft.WindowsTerminal_...\WindowsTerminal.exe"
        # However, accessing that path often gives Permission Denied even for reading.
        # A safer bet for a shortcut target is `wt.exe` if it's in path, or finding where `wt.exe` points.
        # But let's try to find the installation path as requested.
        
        # We can try to deduce it from the package path found in settings path search, 
        # but that was in LocalAppData. The exe is in Program Files.
        
        # Heuristic: Match the version string from LocalAppData package to Program Files WindowsApps.
        settings_path = self.get_windows_terminal_settings_path()
        if settings_path:
            # ...\Packages\Microsoft.WindowsTerminal_8wekyb3d8bbwe\LocalState\settings.json
            # Extract the folder name
            package_folder_name = os.path.basename(os.path.dirname(os.path.dirname(settings_path)))
            
            # Now look in C:\Program Files\WindowsApps
            # Note: listing C:\Program Files\WindowsApps requires admin usually.
            # If we can't list, we can't find it easily this way.
            
            # Alternative: Use `where wt`
            try:
                wt_path = subprocess.check_output(["where", "wt"], shell=True).decode().strip().splitlines()[0]
                return wt_path
            except Exception:
                pass

        return ""

    def update_windows_terminal_settings(self, updates: Dict[str, Any]) -> None:
        """Updates Windows Terminal settings.json."""
        path = self.get_windows_terminal_settings_path()
        if not path:
            Logger.err("Could not find Windows Terminal settings path.")
            return

        try:
            with open(path, 'r', encoding='utf-8') as f:
                # Use json.load, hoping no comments or valid JSON
                content = json.load(f)
            
            # Helper to merge dictionaries
            def deep_merge(target, source):
                for key, value in source.items():
                    if isinstance(value, dict) and key in target and isinstance(target[key], dict):
                        deep_merge(target[key], value)
                    else:
                        target[key] = value

            # Handle schemes specifically: Append if not exists
            if "schemes" in updates and isinstance(updates["schemes"], list):
                existing_schemes = content.get("schemes", [])
                existing_names = {s.get("name") for s in existing_schemes}
                
                for scheme in updates["schemes"]:
                    if scheme.get("name") not in existing_names:
                        existing_schemes.append(scheme)
                        Logger.info(f"Added scheme: {scheme.get('name')}")
                    else:
                        # Update existing scheme? For now, we skip or overwrite?
                        # Let's overwrite/update the existing one with same name
                        for i, s in enumerate(existing_schemes):
                            if s.get("name") == scheme.get("name"):
                                existing_schemes[i] = scheme
                                Logger.info(f"Updated scheme: {scheme.get('name')}")
                                break
                
                content["schemes"] = existing_schemes
                # Remove schemes from updates to avoid overwriting with the list again in the loop below if we processed it
                # But since we're iterating 'updates' next, let's just copy 'updates' and remove 'schemes'
                updates_copy = updates.copy()
                del updates_copy["schemes"]
            else:
                updates_copy = updates

            # Apply other updates
            deep_merge(content, updates_copy)
                
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(content, f, indent=4)
            
            Logger.ok("Updated Windows Terminal settings.")
            
        except json.JSONDecodeError:
            Logger.err(f"Failed to parse {path}. It might contain comments.")
        except Exception as e:
            Logger.err(f"Failed to update Windows Terminal settings: {e}")

    def update_windows_terminal_profile(self, profile_name: str, settings: Dict[str, Any]) -> None:
        path = self.get_windows_terminal_settings_path()
        if not path: return
        
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = json.load(f)
            
            profiles = content.get("profiles")
            profile_list = []
            if isinstance(profiles, list):
                profile_list = profiles
            elif isinstance(profiles, dict) and "list" in profiles:
                profile_list = profiles["list"]
            
            updated = False
            for p in profile_list:
                if p.get("name") == profile_name:
                    p.update(settings)
                    updated = True
                    break
            
            if updated:
                with open(path, 'w', encoding='utf-8') as f:
                    json.dump(content, f, indent=4)
                Logger.ok(f"Updated Windows Terminal profile '{profile_name}'")
            else:
                Logger.warn(f"Profile '{profile_name}' not found in Windows Terminal settings.")
                
        except Exception as e:
            Logger.err(f"Failed to update profile: {e}")
<<<<<<< HEAD

    def refresh_windows_path(self):
        path_keys = [
            ('SYSTEM', winreg.HKEY_LOCAL_MACHINE, r'SYSTEM\CurrentControlSet\Control\Session Manager\Environment'),
            ('USER', winreg.HKEY_CURRENT_USER, r'Environment')
        ]

        new_path_parts = []
        for name, root, subkey in path_keys:
            try:
                with winreg.OpenKey(root, subkey) as key:
                    raw_value, type_ = winreg.QueryValueEx(key, 'Path')

                    if type_ == winreg.REG_EXPAND_SZ:
                        expanded_value = winreg.ExpandEnvironmentStrings(raw_value)
                    else:
                        expanded_value = raw_value
                    
                    if "%" in expanded_value:
                        Logger.warn(f"[{name}] WARNING: Unexpanded variables remain: {expanded_value}")

                    new_path_parts.append(expanded_value)
                    
            except FileNotFoundError:
                Logger.error(f"[{name}] Key not found.")
                continue

        if new_path_parts:
            final_path = ';'.join(new_path_parts)
            os.environ['PATH'] = final_path
            Logger.ok("PATH updated successfully")
=======
>>>>>>> refs/remotes/origin/main
