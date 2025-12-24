import sys
import shutil
import subprocess
import os
import json
import urllib.request
from typing import Dict, Any, List
from lib.modules.base import Component
from lib.core.packages import KnownPackage
from lib.utils.logger import Logger

class Default(Component):
    VSCODE_SETTINGS: Dict[str, Any] = {
        "editor.fontFamily": "Cascadia Code",
        "terminal.integrated.stickyScroll.enabled": False,
        "editor.minimap.enabled": False,
        "window.zoomLevel": 0.5,
        "breadcrumbs.enabled": True,
        "update.showReleaseNotes": False,
        "zenMode.hideLineNumbers": False,
        "editor.lineNumbers": "relative",
        "editor.formatOnSave": True,
        "workbench.activityBar.location": "hidden",
        "editor.stickyScroll.enabled": False,
        "workbench.colorTheme": "Gruvbox Dark (Hard)",
        "glassit.alpha": 250,
    }

    VSCODE_EXTENSIONS: List[str] = [
        "tomphilbin.gruvbox-themes",
        "s-nlf-fh.glassit",
        "ms-python.python",
        "ms-python.debugpy",
        "ms-python.vscode-pylance",
    ]

    VSCODE_DEB_URL = "https://code.visualstudio.com/sha/download?build=stable&os=linux-deb-x64"

    def install(self) -> None:
        try:
            self._install_git()
            self._install_vscode()
            self._configure_vscode()
            Logger.ok("Default setup completed successfully.")
        except Exception as e:
            Logger.err(f"Default installation failed: {e}")
            raise

    def _install_git(self) -> None:
        Logger.info("Installing Git...")
        self.platform.install_package(KnownPackage.GIT)

    def _install_vscode(self) -> None:
        Logger.info("Installing VS-Code...")
        if sys.platform != "win32":
            self._install_vscode_deb_linux()
        else:
            self.platform.install_package(KnownPackage.VS_CODE)

            if hasattr(self.platform, "refresh_windows_path"):
                self.platform.refresh_windows_path()

    def _install_vscode_deb_linux(self) -> None:
        """Downloads and installs the VS Code .deb package directly."""
        if shutil.which("code"):
            Logger.info("VS Code is already installed. Skipping download.")
            return

        if not shutil.which("apt"):
            # Fallback for non-apt systems (e.g. Arch, Fedora), though this script seems apt-centric for Linux setup.
            # Assuming Arch/Pacman might have 'code' in community or AUR, so we try standard install if apt is missing.
            self.platform.install_package(KnownPackage.VS_CODE)
            return

        deb_path = os.path.join(os.getcwd(), "tmp", "vscode.deb")
        os.makedirs(os.path.dirname(deb_path), exist_ok=True)
        
        try:
            Logger.info(f"Downloading VS Code .deb from {self.VSCODE_DEB_URL}...")
            # Headers required sometimes to avoid 403 Forbidden or redirect issues
            req = urllib.request.Request(
                self.VSCODE_DEB_URL, 
                headers={'User-Agent': 'Mozilla/5.0'}
            )
            with urllib.request.urlopen(req) as response, open(deb_path, 'wb') as out_file:
                shutil.copyfileobj(response, out_file)
            
            Logger.info("Installing VS Code .deb...")
            # 'apt install ./file.deb' resolves dependencies automatically
            subprocess.run(["sudo", "apt", "install", "-y", f"./{os.path.basename(deb_path)}"], cwd=os.path.dirname(deb_path), check=True)
            
            Logger.ok("Successfully installed VS Code via .deb")
            
        except Exception as e:
            Logger.err(f"Failed to install VS Code .deb: {e}")
            raise
        finally:
            if os.path.exists(deb_path):
                os.remove(deb_path)

    def _configure_vscode(self) -> None:
        Logger.info("Configuring VS-Code...")
        
        Logger.info("Installing Extensions...")
        for extension in self.VSCODE_EXTENSIONS:
            self.platform.install_vscode_extension(extension)

        Logger.info("Applying Settings...")
        for key, value in self.VSCODE_SETTINGS.items():
            self.platform.add_vscode_setting(key, value)
            
        self._configure_keybindings()
            
        Logger.ok("Successfully configured VS-Code")

    def _configure_keybindings(self) -> None:
        """Installs default keybindings from files/keybindings.json (excluding neovim specific ones)."""
        keybindings_source = os.path.join(os.getcwd(), "files", "keybindings.json")
        if not os.path.exists(keybindings_source):
            Logger.warn(f"Keybindings file not found at {keybindings_source}")
            return

        try:
            with open(keybindings_source, "r", encoding="utf-8") as f:
                # Basic comment stripping since standard json doesn't support comments
                content = f.read()
                # Very simple comment removal (single line //)
                lines = [line for line in content.splitlines() if not line.strip().startswith("//")]
                keybindings = json.loads("\n".join(lines))
            
            # Filter out neovim specific bindings
            default_bindings = [
                kb for kb in keybindings 
                if "neovim" not in kb.get("when", "") and "neovim" not in kb.get("command", "")
            ]
            
            for binding in default_bindings:
                self.platform.add_vscode_keybinding(binding)
                
            Logger.ok("Default VS Code keybindings configured.")
            
        except json.JSONDecodeError as e:
            Logger.warn(f"Failed to parse keybindings.json: {e}")
        except Exception as e:
            Logger.warn(f"Failed to configure keybindings: {e}")
