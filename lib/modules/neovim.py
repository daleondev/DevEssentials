import os
import shutil
import urllib.request
import zipfile
import sys
import json
import subprocess
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
            self._install_neovim_windows_bob()
        elif sys.platform == "linux":
            self._install_neovim_linux_bob()
        else:
            Logger.err(f"Neovim installation not supported on {sys.platform}")
            raise NotImplementedError(f"Unsupported platform: {sys.platform}")

    def _install_neovim_windows_bob(self) -> None:
        Logger.info("Installing Neovim via Bob (version manager)...")
        
        # Command for Powershell installation as recommended by Bob readme
        install_cmd = 'powershell -c "irm https://raw.githubusercontent.com/MordechaiHadad/bob/master/scripts/install.ps1 | iex"'
        
        try:
            Logger.info("Running bob install script...")
            subprocess.run(install_cmd, shell=True, check=True)
            
<<<<<<< HEAD
            if hasattr(self.platform, "refresh_windows_path"):
                self.platform.refresh_windows_path()

            Logger.info("Installing latest stable Neovim via Bob...")
            subprocess.run(["bob", "install", "latest"], check=True)
            subprocess.run(["bob", "use", "latest"], check=True)
            
            # Bob links nvim to nvim-bin inside .bob data folder?
            # Actually on Windows, bob usually creates shims or adds the version path.
            # 'bob use' should make 'nvim' available in the path managed by bob.
            # We need to make sure that path is in our PATH.
            
            # Usually: %USERPROFILE%\.local\share\bob\nvim-bin on Linux
            # On Windows: %USERPROFILE%\AppData\Local\bob\nvim-bin
            local_app_data = os.environ.get("LOCALAPPDATA")
            bob_nvim_bin = os.path.join(local_app_data, "bob", "nvim-bin")
            
=======
            # Bob installs to %USERPROFILE%\.bob\bin by default on Windows? Or usually just adds itself to path.
            # The script should handle adding bob to PATH for current session if possible, but let's check.
            # Usually we need to refresh environment or find where it is.
            
            # Common location: C:\Users\<User>\.bob\bin or C:\Users\<User>\AppData\Local\bob\bin?
            # According to script, it installs to $HOME/.bob/bin by default unless configured.
            user_profile = os.environ.get("USERPROFILE")
            bob_bin = os.path.join(user_profile, ".bob", "bin")
            
            bob_exe = os.path.join(bob_bin, "bob.exe")
            
            if not os.path.exists(bob_exe):
                # Try to find in path if script added it already (unlikely to propagate to this process instantly)
                if shutil.which("bob"):
                    bob_exe = "bob"
                else:
                    Logger.warn(f"Could not find bob at {bob_exe}. Attempting to proceed assuming it's in PATH or standard location.")
            else:
                 self.platform.add_to_path(bob_bin)

            Logger.info("Installing latest stable Neovim via Bob...")
            # Use full path if we found it, otherwise hope for PATH
            cmd_base = bob_exe if os.path.exists(bob_exe) else "bob"
            
            subprocess.run([cmd_base, "install", "latest"], check=True)
            subprocess.run([cmd_base, "use", "latest"], check=True)
            
            # Bob links nvim to nvim-bin inside .bob data folder?
            # Actually on Windows, bob usually creates shims or adds the version path.
            # 'bob use' should make 'nvim' available in the path managed by bob.
            # We need to make sure that path is in our PATH.
            
            # Usually: %USERPROFILE%\.local\share\bob\nvim-bin on Linux
            # On Windows: %USERPROFILE%\AppData\Local\bob\nvim-bin
            local_app_data = os.environ.get("LOCALAPPDATA")
            bob_nvim_bin = os.path.join(local_app_data, "bob", "nvim-bin")
            
>>>>>>> refs/remotes/origin/main
            self.platform.add_to_path(bob_nvim_bin)
            
            # Update VS Code setting
            nvim_exe = os.path.join(bob_nvim_bin, "nvim.exe")
            self.platform.add_vscode_setting("vscode-neovim.neovimExecutablePaths.win32", nvim_exe)
            
            Logger.ok("Neovim installed and configured via Bob.")

        except subprocess.CalledProcessError as e:
            Logger.err(f"Failed during Bob execution: {e}")
            raise
        except Exception as e:
            Logger.err(f"Failed to install Neovim via Bob: {e}")
            raise

    def _install_neovim_linux_bob(self) -> None:
        Logger.info("Installing Neovim via Bob (version manager)...")
        
        install_cmd = "curl -fsSL https://raw.githubusercontent.com/MordechaiHadad/bob/master/scripts/install.sh | bash"
        
        try:
            # Install bob
            Logger.info("Running bob install script...")
            subprocess.run(install_cmd, shell=True, check=True)
            
            # Bob is installed to ~/.local/bin by default
            bob_path = os.path.expanduser("~/.local/bin/bob")
            
            if not os.path.exists(bob_path):
                # Fallback check or maybe it's in PATH already?
                if shutil.which("bob"):
                    bob_path = "bob"
                else:
                    raise FileNotFoundError("Could not find 'bob' executable after installation.")

            # Ensure ~/.local/bin is in PATH for future sessions
            self.platform.add_to_path(os.path.dirname(bob_path) if os.path.isabs(bob_path) else os.path.expanduser("~/.local/bin"))

            Logger.info("Installing latest stable Neovim via Bob...")
            subprocess.run([bob_path, "install", "latest"], check=True)
            subprocess.run([bob_path, "use", "latest"], check=True)
            
            # Add ~/.local/share/bob/nvim-bin to PATH (this is where bob links the active nvim)
            bob_nvim_bin = os.path.expanduser("~/.local/share/bob/nvim-bin")
            self.platform.add_to_path(bob_nvim_bin)
            
            # We also need to tell VS Code where it is
            self.platform.add_vscode_setting("vscode-neovim.neovimExecutablePaths.linux", os.path.join(bob_nvim_bin, "nvim"))
            
            Logger.ok("Neovim installed and configured via Bob.")

        except subprocess.CalledProcessError as e:
            Logger.err(f"Failed during Bob execution: {e}")
            raise
        except Exception as e:
            Logger.err(f"Failed to install Neovim via Bob: {e}")
            raise

    def _install_vscode_extension(self) -> None:
        Logger.info("Installing VSCode Neovim extension...")
        self.platform.install_vscode_extension("asvetliakov.vscode-neovim")
        # Path configuration is now handled in the install methods because paths differ by method
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
