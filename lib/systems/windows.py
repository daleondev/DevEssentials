import os
try:
    import winreg
except ImportError:
    winreg = None
import subprocess
from typing import Union
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
