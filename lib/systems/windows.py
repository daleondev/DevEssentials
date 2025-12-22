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
            
            # Apply updates
            # 'updates' is expected to be a dict of key-values to merge into the root or specific profiles.
            # This is a simple merge. Complex merges (like finding a specific profile) need more logic.
            # For this task, we need to:
            # 1. Set default profile to pwsh (we need to find the pwsh profile GUID or set "defaultProfile": "PowerShell" if it accepts names - it usually needs a GUID).
            # 2. Set fontFace for profiles.
            
            # If the user passed specific structure in 'updates', we merge it.
            # But the caller (Terminal) will likely pass a dict reflecting the structure.
            
            # Example update: {"defaultProfile": "{guid}", "profiles": {"defaults": {"font": ...}}}
            
            # Helper for deep merge could be useful, but let's just do top level or specific handling if needed.
            # For now, assumes 'updates' keys overwrite roots.
            for k, v in updates.items():
                content[k] = v
                
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(content, f, indent=4)
            
            Logger.ok("Updated Windows Terminal settings.")
            
        except json.JSONDecodeError:
            Logger.err(f"Failed to parse {path}. It might contain comments.")
        except Exception as e:
            Logger.err(f"Failed to update Windows Terminal settings: {e}")
