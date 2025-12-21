import os
import sys
import shutil
import subprocess
import urllib.request
import zipfile
from lib.modules.base import Component
from lib.core.packages import KnownPackage
from lib.utils.logger import print_info, print_ok, print_err

class Terminal(Component):
    def install(self) -> None:
        try:
            self._install_shell()
            self._install_oh_my_posh()
            self._install_font()
            self._configure_shell()
            print_ok("Terminal setup completed successfully.")
        except Exception as e:
            print_err(f"Terminal setup failed: {e}")
            raise

    def _install_shell(self):
        print_info("Installing Shell...")
        if sys.platform == "win32":
            # Install PowerShell Core
            self.platform.install_package(KnownPackage.POWERSHELL)
        else:
            # Install Zsh
            self.platform.install_package(KnownPackage.ZSH)
            # Try to set as default shell
            try:
                zsh_path = subprocess.check_output(["which", "zsh"]).decode().strip()
                current_shell = os.environ.get("SHELL", "")
                if zsh_path not in current_shell:
                    print_info(f"Setting zsh ({zsh_path}) as default shell...")
                    # chsh usually requires password input, which breaks automation.
                    # We can try, or just warn user.
                    # subprocess.run(["chsh", "-s", zsh_path], check=False) 
                    print_info(f"Please run 'chsh -s {zsh_path}' manually if it's not default.")
            except Exception as e:
                print_err(f"Could not check/set default shell: {e}")

    def _install_oh_my_posh(self):
        print_info("Installing Oh-My-Posh...")
        if sys.platform == "win32":
            self.platform.install_package(KnownPackage.OHMYPOSH)
        else:
            # Linux manual install script (standard recommendation)
            # Check if already installed
            if os.path.exists("/usr/local/bin/oh-my-posh"):
                 print_ok("Oh-My-Posh already installed.")
                 return
            
            print_info("Downloading and installing Oh-My-Posh via script...")
            cmd = "curl -s https://ohmyposh.dev/install.sh | sudo bash -s"
            subprocess.run(cmd, shell=True, check=True)

    def _install_font(self):
        print_info("Installing Font (Caskaydia Cove NF)...")
        if sys.platform == "win32":
            self.platform.install_package(KnownPackage.CASCADIA_CODE_NF)
        else:
            try:
                print_info("Downloading Caskaydia Cove NF...")
                url = "https://github.com/ryanoasis/nerd-fonts/releases/download/v3.3.0/CascadiaCode.zip"
                download_path = "tmp"
                download_file = os.path.join(download_path, "CascadiaCode.zip")
                os.makedirs(download_path, exist_ok=True)
                
                urllib.request.urlretrieve(url, download_file)
                
                font_dir = os.path.expanduser("~/.local/share/fonts")
                os.makedirs(font_dir, exist_ok=True)
                
                print_info(f"Extracting to {font_dir}...")
                with zipfile.ZipFile(download_file, 'r') as zip_ref:
                    # Filter only ttf/otf files or just extract all. Extracting all is easier.
                    zip_ref.extractall(font_dir)
                    
                print_info("Updating font cache...")
                subprocess.run(["fc-cache", "-fv"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                print_ok("Successfully installed Nerd Font on Linux.")
                
            except Exception as e:
                print_err(f"Failed to install font manually: {e}")
                print_info("Skipping automatic font installation. Please install 'CaskaydiaCove Nerd Font' manually.")

    def _configure_shell(self):
        print_info("Configuring Shell...")
        
        # Configure VS Code settings
        try:
            print_info("Updating VS Code terminal settings...")
            if sys.platform == "win32":
                self.platform.update_vscode_setting("terminal.integrated.defaultProfile.windows", "PowerShell")
            else:
                self.platform.update_vscode_setting("terminal.integrated.defaultProfile.linux", "zsh")
            
            self.platform.update_vscode_setting("terminal.integrated.fontFamily", "CaskaydiaCove NF")
            print_ok("VS Code terminal settings updated.")
        except Exception as e:
            print_err(f"Failed to update VS Code settings: {e}")

        if sys.platform == "win32":
             # PowerShell Profile
             # We need to find the profile path. 
             # For pwsh, it's usually in Documents\PowerShell\Microsoft.PowerShell_profile.ps1
             # We can ask PowerShell for the path.
             try:
                 if not shutil.which("pwsh"):
                     print_warn("pwsh not found in PATH. Skipping profile configuration. Please restart terminal and run again.")
                     return

                 result = subprocess.check_output(["pwsh", "-NoProfile", "-Command", "echo $PROFILE"], shell=True)
                 profile_path = result.decode().strip()
                 
                 # Ensure directory exists
                 os.makedirs(os.path.dirname(profile_path), exist_ok=True)
                 
                 init_line = 'oh-my-posh init pwsh --config "$env:POSH_THEMES_PATH/gruvbox.omp.json" | Invoke-Expression'
                 
                 # Read existing
                 content = ""
                 if os.path.exists(profile_path):
                     with open(profile_path, "r") as f:
                         content = f.read()
                 
                 if "oh-my-posh init pwsh" not in content:
                     with open(profile_path, "a") as f:
                         f.write(f"\n{init_line}\n")
                     print_ok(f"Added Oh-My-Posh init to {profile_path}")
                 else:
                     print_info("Oh-My-Posh already configured in profile.")
                     
             except Exception as e:
                 print_err(f"Failed to configure PowerShell profile: {e}")

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
                    print_ok(f"Added Oh-My-Posh init to {zshrc}")
                else:
                    print_info("Oh-My-Posh already configured in .zshrc")
            except Exception as e:
                print_err(f"Failed to configure .zshrc: {e}")