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
        shell_config = os.path.join(home, ".bashrc") 
        # Note: This simple check might fail for zsh or other shells, keeping it simple as per original script for now.
        line_to_add = f'\nexport PATH="$PATH:{folder_path}"\n'

        try:
            if os.path.exists(shell_config):
                with open(shell_config, "r") as f:
                    content = f.read()
                    if f"export PATH=\"$PATH:{folder_path}\"" in content:
                        print_warn(f"'{folder_path}' is already in the PATH.")
                        return
            
            with open(shell_config, "a") as f:
                f.write(line_to_add)
            
            print_ok(f"Added to {shell_config}. Run 'source {shell_config}' or restart terminal.")
            
        except Exception as e:
            print_err(f"Failed to add path variable: {e}")
            raise

    def install_vscode_extension(self, extension_id: str) -> None:
        subprocess.run(["code", "--install-extension", extension_id], check=True, stdout=subprocess.DEVNULL)

    def get_home_dir(self) -> str:
        return os.path.expanduser("~")
