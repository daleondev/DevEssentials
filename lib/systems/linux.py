import os
import shutil
import subprocess
from typing import Union
from lib.systems.platform import Platform
from lib.utils.logger import print_ok, print_warn, print_err, print_info
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
            print_err("No supported package manager found (apt, pacman).")
            raise NotImplementedError("Package manager not supported.")

        print_info(f"Installing {package_name} via {manager}...")
        try:
            subprocess.run(cmd, check=True)
            print_ok(f"Successfully installed {package_name}")
        except subprocess.CalledProcessError as e:
            print_err(f"Failed to install {package_name}: {e}")
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
                            print_warn(f"'{folder_path}' is already in {rc_file}.")
                            continue
                    
                    with open(config_path, "a") as f:
                        f.write(line_to_add)
                    updated.append(rc_file)

            if updated:
                print_ok(f"Added path to {', '.join(updated)}. Restart terminal to apply.")
            elif not updated:
                # If no rc files found or all already have it, maybe warn if none found?
                # But .bashrc almost always exists.
                pass
            
        except Exception as e:
            print_err(f"Failed to add path variable: {e}")
            raise

    def install_vscode_extension(self, extension_id: str) -> None:
        subprocess.run(["code", "--install-extension", extension_id], check=True, stdout=subprocess.DEVNULL)

    def get_home_dir(self) -> str:
        return os.path.expanduser("~")

    def get_vscode_settings_path(self) -> str:
        return os.path.join(self.get_home_dir(), ".config", "Code", "User", "settings.json")
