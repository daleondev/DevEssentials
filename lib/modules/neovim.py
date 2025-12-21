import os
import shutil
import urllib.request
import zipfile
import sys
from lib.modules.base import Component
from lib.core.packages import KnownPackage
from lib.utils.logger import print_info, print_ok, print_err

class Neovim(Component):
    def install(self) -> None:
        try:
            print_info("Installing Neovim...")
            
            if sys.platform == "win32":
                url = "https://github.com/neovim/neovim/releases/download/v0.11.5/nvim-win64.zip"
                archive_name = "nvim.zip"
                
                download_path = "tmp"
                download_file = os.path.join(download_path, archive_name)
                os.makedirs(download_path, exist_ok=True)
                
                print_info(f"Downloading {url}...")
                urllib.request.urlretrieve(url, download_file)
                
                install_path = os.path.join(self.platform.get_home_dir(), "nvim")
                if os.path.exists(install_path):
                    shutil.rmtree(install_path)
                os.mkdir(install_path)
                
                print_info("Extracting...")
                with zipfile.ZipFile(download_file, 'r') as zip_ref:
                    zip_ref.extractall(install_path)
                
                # Zip contains 'nvim-win64' folder
                bin_path = os.path.join(install_path, "nvim-win64", "bin")
                
                print_info(f"Adding {bin_path} to PATH...")
                self.platform.add_to_path(bin_path)
                    
                print_ok("Successfully installed Neovim binary")
                
            elif sys.platform == "linux":
                self.platform.install_package(KnownPackage.NEOVIM)
                print_ok("Successfully installed Neovim via package manager")
                
            else:
                print_err(f"Neovim installation not supported on {sys.platform}")
                return
            
            print_info("Installing VSCode Neovim extension...")
            self.platform.install_vscode_extension("asvetliakov.vscode-neovim")
            print_ok("Successfully installed VSCode Neovim extension")
            
        except Exception as e:
            print_err(f"Failed to install Neovim: {e}")
            raise
