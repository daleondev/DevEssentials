import os
import shutil
import subprocess
from typing import Union
from lib.systems.platform import Platform
from lib.utils.logger import Logger
from lib.core.packages import KnownPackage

class LinuxPlatform(Platform):
    def install_package(self, package: Union[str, KnownPackage]) -> None:
        if isinstance(package, KnownPackage):
            package_name = package.value.linux
        else:
            package_name = package

        if shutil.which("apt"):
            manager = "apt"
            cmd = ["sudo", "apt", "install", "-y", package_name]
        elif shutil.which("pacman"):
            manager = "pacman"
            cmd = ["sudo", "pacman", "-S", "--noconfirm", package_name]
        else:
            Logger.err("No supported package manager found (apt, pacman).")
            raise NotImplementedError("Package manager not supported.")

        Logger.info(f"Installing {package_name} via {manager}...")
        try:
            subprocess.run(cmd, check=True)
            Logger.ok(f"Successfully installed {package_name}")
        except subprocess.CalledProcessError as e:
            Logger.err(f"Failed to install {package_name}: {e}")
            raise

    def add_to_path(self, folder_path: str) -> None:
        home = self.get_home_dir()
        line_to_add = f'\nexport PATH="$PATH:{folder_path}"\n'
        
        targets = [".bashrc", ".zshrc"]
        updated = []

        try:
            for rc_file in targets:
                config_path = os.path.join(home, rc_file)
                if os.path.exists(config_path):
                    with open(config_path, "r") as f:
                        content = f.read()
                        if f"export PATH=\"$PATH:{folder_path}\"" in content:
                            Logger.warn(f"'{folder_path}' is already in {rc_file}.")
                            continue
                    
                    with open(config_path, "a") as f:
                        f.write(line_to_add)
                    updated.append(rc_file)

            if updated:
                Logger.ok(f"Added path to {', '.join(updated)}. Restart terminal to apply.")
            elif not updated:
                # If no rc files found or all already have it, maybe warn if none found?
                # But .bashrc almost always exists.
                pass
            
        except Exception as e:
            Logger.err(f"Failed to add path variable: {e}")
            raise

    def install_vscode_extension(self, extension_id: str) -> None:
        subprocess.run(["code", "--install-extension", extension_id], check=True, stdout=subprocess.DEVNULL)

    def get_home_dir(self) -> str:
        return os.path.expanduser("~")

    def get_vscode_settings_path(self) -> str:
        return os.path.join(self.get_home_dir(), ".config", "Code", "User", "settings.json")

    def get_vscode_keybindings_path(self) -> str:
        return os.path.join(self.get_home_dir(), ".config", "Code", "User", "keybindings.json")

    def create_shortcut(self, target_path: str, shortcut_path: str, description: str = "", icon_path: str = "", working_dir: str = "", hotkey: str = "") -> None:
        """Creates a .desktop file if shortcut_path ends with .desktop, otherwise does nothing."""
        if not shortcut_path.endswith(".desktop"):
            Logger.warn("Linux shortcut creation only supports .desktop files.")
            return

        if hotkey:
            Logger.warn("Hotkeys are not standard in .desktop files and might not work implicitly.")

        try:
            content = f"""[Desktop Entry]
Type=Application
Name={os.path.splitext(os.path.basename(shortcut_path))[0]}
Comment={description}
Exec={target_path}
Icon={icon_path}
Terminal=false
"""
            if working_dir:
                content += f"Path={working_dir}\n"
            
            with open(shortcut_path, "w") as f:
                f.write(content)
            
            # Make it executable
            os.chmod(shortcut_path, 0o755)
            Logger.ok(f"Created desktop entry at {shortcut_path}")
        except Exception as e:
            Logger.err(f"Failed to create desktop entry: {e}")
