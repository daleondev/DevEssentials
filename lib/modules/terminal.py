import os
import sys
import shutil
import subprocess
import urllib.request
import zipfile
from win32com.client import Dispatch
from lib.modules.base import Component
from lib.core.packages import KnownPackage
from lib.utils.logger import Logger

class Terminal(Component):
    def install(self) -> None:
        try:
            self._install_shell()
            self._install_oh_my_posh()
            self._install_font()
            self._configure_shell()
            Logger.ok("Terminal setup completed successfully.")
        except Exception as e:
            Logger.err(f"Terminal setup failed: {e}")
            raise

    def _install_shell(self):
        
        if sys.platform == "win32":
            Logger.info("Installing Pwsh...")
            self.platform.install_package(KnownPackage.POWERSHELL)
            
            # TODO: 
            #   find installation path of windows terminal (e.g. C:\Users\User\AppData\Local\Packages\Microsoft.WindowsTerminal_8wekyb3d8bbwe)
            #   edit windows terminal settings (e.g. C:\Users\User\AppData\Local\Packages\Microsoft.WindowsTerminal_8wekyb3d8bbwe\LocalState\settings.json) 
            #   create a function for editing the settings.json in platform -> windows
            #   make pwsh the default terminal
            Logger.ok(f"Pwsh installed as default terminal")
            
            Logger.info("Creating Pwsh shortcut...")
            link_directory = os.path.join(self.platform.get_home_dir(), "AppData", "Roaming", "Microsoft", "Windows", "Start Menu", "Programs")
            link_filepath = os.path.join(link_directory, "Windows Terminal.lnk")
            
            # TODO: 
            #   create a function for creating shortcuts in platform
            #   use installation path found previously instead of hardcoded
            shell = Dispatch('WScript.Shell')
            shortcut = shell.CreateShortCut(link_filepath)    
            shortcut.Targetpath = os.path.join("C:\\", "Program Files", "WindowsApps", "Microsoft.WindowsTerminal_1.23.13503.0_x64__8wekyb3d8bbwe", "WindowsTerminal.exe")
            shortcut.WorkingDirectory = link_directory
            shortcut.Description = "Windows Terminal"
            shortcut.Hotkey = "CTRL+ALT+T"
            shortcut.save()
            Logger.ok(f"Pwsh shortcut created at '{link_filepath}' with hotkey CTRL+ALT+T")
            
        else:
            Logger.info("Installing Zsh...")
            self.platform.install_package(KnownPackage.ZSH)
            # Try to set as default shell
            try:
                zsh_path = subprocess.check_output(["which", "zsh"]).decode().strip()
                current_shell = os.environ.get("SHELL", "")
                if zsh_path not in current_shell:
                    Logger.info(f"Setting zsh ({zsh_path}) as default shell...")
                    # chsh usually requires password input, which breaks automation.
                    # We can try, or just warn user.
                    # subprocess.run(["chsh", "-s", zsh_path], check=False) 
                    Logger.info(f"Please run 'chsh -s {zsh_path}' manually if it's not default.")
                else:
                    Logger.ok(f"Zsh installed as default terminal")
            except Exception as e:
                Logger.err(f"Could not check/set default shell: {e}")

    def _install_oh_my_posh(self):
        Logger.info("Installing Oh-My-Posh...")
        if sys.platform == "win32":
            self.platform.install_package(KnownPackage.OHMYPOSH)
        else:
            # Linux manual install script (standard recommendation)
            # Check if already installed
            if os.path.exists("/usr/local/bin/oh-my-posh"):
                 Logger.ok("Oh-My-Posh already installed.")
                 return
            
            Logger.info("Downloading and installing Oh-My-Posh via script...")
            cmd = "curl -s https://ohmyposh.dev/install.sh | sudo bash -s"
            subprocess.run(cmd, shell=True, check=True)

    def _install_font(self):
        Logger.info("Installing Font (Cascadia Mono NF)...")
        if sys.platform == "win32":
            # TODO: 
            #   manually download cascadia code from github (e.g. https://github.com/microsoft/cascadia-code/releases/download/v2407.24/CascadiaCode-2407.24.zip)
            #   unzip to tmp folder and install cascadia mono nf
        else:
            try:
                # TODO: 
                #   manually download cascadia code from github (e.g. https://github.com/microsoft/cascadia-code/releases/download/v2407.24/CascadiaCode-2407.24.zip)
                #   unzip to tmp folder and install cascadia mono nf
                
                urllib.request.urlretrieve(url, download_file)
                
                font_dir = os.path.expanduser("~/.local/share/fonts")
                os.makedirs(font_dir, exist_ok=True)
                
                Logger.info(f"Extracting to {font_dir}...")
                with zipfile.ZipFile(download_file, 'r') as zip_ref:
                    # Filter only ttf/otf files or just extract all. Extracting all is easier.
                    zip_ref.extractall(font_dir)
                    
                Logger.info("Updating font cache...")
                subprocess.run(["fc-cache", "-fv"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                Logger.ok("Successfully installed Nerd Font on Linux.")
                
            except Exception as e:
                Logger.err(f"Failed to install font manually: {e}")
                Logger.info("Skipping automatic font installation. Please install 'CaskaydiaCove Nerd Font' manually.")

    def _configure_shell(self):
        Logger.info("Configuring Shell...")
        
        # Configure VS Code settings
        try:
            Logger.info("Updating VS Code terminal settings...")
            if sys.platform == "win32":
                self.platform.add_vscode_setting("terminal.integrated.defaultProfile.windows", "PowerShell")
            else:
                self.platform.add_vscode_setting("terminal.integrated.defaultProfile.linux", "zsh")
            
            self.platform.add_vscode_setting("terminal.integrated.fontFamily", "Cascadia Mono NF")          
            Logger.ok("VS Code terminal settings updated.")
        except Exception as e:
            Logger.err(f"Failed to update VS Code settings: {e}")

        if sys.platform == "win32":
             # PowerShell Profile
             # We need to find the profile path. 
             # For pwsh, it's usually in Documents\PowerShell\Microsoft.PowerShell_profile.ps1
             # We can ask PowerShell for the path.
             try:
                 if not shutil.which("pwsh"):
                     Logger.warn("pwsh not found in PATH. Skipping profile configuration. Please restart terminal and run again.")
                     return

                 result = subprocess.check_output(["pwsh", "-NoProfile", "-Command", "echo $PROFILE"], shell=True)
                 profile_path = result.decode().strip()
                 
                 # Ensure directory exists
                 os.makedirs(os.path.dirname(profile_path), exist_ok=True)
                 
                 init_line = 'oh-my-posh init pwsh --config "https://raw.githubusercontent.com/JanDeDobbeleer/oh-my-posh/main/themes/gruvbox.omp.json" | Invoke-Expression'
                 
                 # Read existing
                 content = ""
                 if os.path.exists(profile_path):
                     with open(profile_path, "r") as f:
                         content = f.read()
                 
                 if "oh-my-posh init pwsh" not in content:
                     with open(profile_path, "a") as f:
                         f.write(f"\n{init_line}\n")
                     Logger.ok(f"Added Oh-My-Posh init to {profile_path}")
                 else:
                     Logger.info("Oh-My-Posh already configured in profile.")
                     
                # TODO: 
                #   set cascadia mono nf as pwsh font
                     
             except Exception as e:
                 Logger.err(f"Failed to configure PowerShell profile: {e}")

        else:
            # Zsh .zshrc
            zshrc = os.path.join(self.platform.get_home_dir(), ".zshrc")
            init_line = 'eval "$(oh-my-posh init zsh --config https://raw.githubusercontent.com/JanDeDobbeleer/oh-my-posh/main/themes/gruvbox.omp.json)"'
            
            try:
                content = ""
                if os.path.exists(zshrc):
                    with open(zshrc, "r") as f:
                        content = f.read()
                
                if "oh-my-posh init zsh" not in content:
                    with open(zshrc, "a") as f:
                        f.write(f"\n{init_line}\n")
                    Logger.ok(f"Added Oh-My-Posh init to {zshrc}")
                else:
                    Logger.info("Oh-My-Posh already configured in .zshrc")
                    
                # TODO: 
                #   set cascadia mono nf as zsh font
            except Exception as e:
                Logger.err(f"Failed to configure .zshrc: {e}")