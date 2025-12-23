import os
import shutil
import urllib.request
import zipfile
import sys
import json
from lib.modules.base import Component
from lib.core.packages import KnownPackage
from lib.utils.logger import Logger

class Neovim(Component):
    def install(self) -> None:
        try:
            self._install_neovim()
            self._install_vscode_extension()
            self._configure_neovim()
            self._configure_vscode_keybindings()
            Logger.ok("Neovim setup completed successfully.")
        except Exception as e:
            Logger.err(f"Failed to install Neovim: {e}")
            raise

    def _install_neovim(self) -> None:
        Logger.info("Installing Neovim...")
        
        if sys.platform == "win32":
            self._install_neovim_windows()
        elif sys.platform == "linux":
            self.platform.install_package(KnownPackage.NEOVIM)
            Logger.ok("Successfully installed Neovim via package manager")
        else:
            Logger.err(f"Neovim installation not supported on {sys.platform}")
            raise NotImplementedError(f"Unsupported platform: {sys.platform}")

    def _install_neovim_windows(self) -> None:
        url = "https://github.com/neovim/neovim/releases/download/v0.11.5/nvim-win64.zip"
        archive_name = "nvim.zip"
        
        download_path = os.path.join(os.getcwd(), "tmp")
        download_file = os.path.join(download_path, archive_name)
        os.makedirs(download_path, exist_ok=True)
        
        Logger.info(f"Downloading {url}...")
        try:
            urllib.request.urlretrieve(url, download_file)
            
            install_path = os.path.join(self.platform.get_home_dir(), "nvim")
            if os.path.exists(install_path):
                shutil.rmtree(install_path)
            os.mkdir(install_path)
            
            Logger.info("Extracting...")
            with zipfile.ZipFile(download_file, 'r') as zip_ref:
                zip_ref.extractall(install_path)
            
            # Zip contains 'nvim-win64' folder
            bin_path = os.path.join(install_path, "nvim-win64", "bin")
            
            Logger.info(f"Adding {bin_path} to PATH...")
            self.platform.add_to_path(bin_path)
                
            Logger.ok("Successfully installed Neovim binary")
        finally:
            if os.path.exists(download_file):
                os.remove(download_file)

    def _install_vscode_extension(self) -> None:
        Logger.info("Installing VSCode Neovim extension...")
        self.platform.install_vscode_extension("asvetliakov.vscode-neovim")
        Logger.ok("Successfully installed VSCode Neovim extension")

    def _configure_neovim(self) -> None:
        Logger.info("Configuring Neovim...")
        
        if sys.platform == "win32":
            # LOCALAPPDATA is standard for Windows config
            base_dir = os.environ.get("LOCALAPPDATA", os.path.join(self.platform.get_home_dir(), "AppData", "Local"))
            config_dir = os.path.join(base_dir, "nvim")
        else:
            config_dir = os.path.join(self.platform.get_home_dir(), ".config", "nvim")
            
        os.makedirs(config_dir, exist_ok=True)
        init_lua_target = os.path.join(config_dir, "init.lua")
        
        init_lua_source = os.path.join(os.getcwd(), "files", "init.lua")
        
        if os.path.exists(init_lua_source):
            try:
                shutil.copy2(init_lua_source, init_lua_target)
                Logger.ok(f"Copied init.lua to {init_lua_target}")
            except Exception as e:
                Logger.warn(f"Failed to copy init.lua: {e}")
        else:
            Logger.warn(f"Source init.lua not found at {init_lua_source}")

    def _configure_vscode_keybindings(self) -> None:
        """Installs Neovim-specific keybindings from files/keybindings.json."""
        Logger.info("Configuring VS Code Neovim keybindings...")
        keybindings_source = os.path.join(os.getcwd(), "files", "keybindings.json")
        
        if not os.path.exists(keybindings_source):
            Logger.warn(f"Keybindings file not found at {keybindings_source}")
            return

        try:
            with open(keybindings_source, "r", encoding="utf-8") as f:
                content = f.read()
                # Basic comment stripping
                lines = [line for line in content.splitlines() if not line.strip().startswith("//")]
                keybindings = json.loads("\n".join(lines))
            
            # Filter for neovim specific bindings
            neovim_bindings = [
                kb for kb in keybindings 
                if "neovim" in kb.get("when", "") or "neovim" in kb.get("command", "")
            ]
            
            count = 0
            for binding in neovim_bindings:
                self.platform.add_vscode_keybinding(binding)
                count += 1
                
            Logger.ok(f"Configured {count} Neovim keybindings for VS Code.")
            
        except json.JSONDecodeError as e:
            Logger.warn(f"Failed to parse keybindings.json: {e}")
        except Exception as e:
            Logger.warn(f"Failed to configure keybindings: {e}")
