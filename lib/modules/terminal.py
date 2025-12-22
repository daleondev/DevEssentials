import os
import sys
import shutil
import subprocess
import urllib.request
import zipfile
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
            
            # Find installation path of windows terminal and configure it
            if hasattr(self.platform, "get_windows_terminal_settings_path"):
                settings_path = self.platform.get_windows_terminal_settings_path()
                if settings_path:
                    Logger.info(f"Found Windows Terminal settings at {settings_path}")
                    # Make pwsh the default terminal
                    # "PowerShell" is the usual name for the profile.
                    self.platform.update_windows_terminal_settings({"defaultProfile": "PowerShell"})
                else:
                    Logger.warn("Could not find Windows Terminal settings.")

            Logger.ok(f"Pwsh installed and configured.")
            
            Logger.info("Creating Pwsh shortcut...")
            link_directory = os.path.join(self.platform.get_home_dir(), "AppData", "Roaming", "Microsoft", "Windows", "Start Menu", "Programs")
            link_filepath = os.path.join(link_directory, "Windows Terminal.lnk")
            
            target_path = "wt.exe"
            if hasattr(self.platform, "get_windows_terminal_executable"):
                found_path = self.platform.get_windows_terminal_executable()
                if found_path:
                    target_path = found_path
            
            self.platform.create_shortcut(
                target_path=target_path,
                shortcut_path=link_filepath,
                description="Windows Terminal",
                working_dir=link_directory,
                icon_path=target_path,
                hotkey="CTRL+ALT+T"
            )
            
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
            # Use curl but piping to sudo bash is risky if not interactive.
            # But the user asked for this.
            cmd = "curl -s https://ohmyposh.dev/install.sh | sudo bash -s"
            subprocess.run(cmd, shell=True, check=True)

    def _install_font(self):
        Logger.info("Installing Font (Cascadia Mono NF)...")
        
        url = "https://github.com/microsoft/cascadia-code/releases/download/v2407.24/CascadiaCode-2407.24.zip"
        zip_name = "CascadiaCode.zip"
        download_dir = os.path.join(os.getcwd(), "tmp")
        os.makedirs(download_dir, exist_ok=True)
        download_file = os.path.join(download_dir, zip_name)

        try:
            Logger.info(f"Downloading font from {url}...")
            urllib.request.urlretrieve(url, download_file)
            
            if sys.platform == "win32":
                extract_dir = os.path.join(download_dir, "CascadiaCode")
                with zipfile.ZipFile(download_file, 'r') as zip_ref:
                    zip_ref.extractall(extract_dir)
                
                Logger.info("Font downloaded. Installing on Windows is complex via script.")
                Logger.info(f"Please install the fonts in '{extract_dir}' manually (Select all -> Right Click -> Install).")
                # Attempt to open the folder
                os.startfile(extract_dir)

            else:
                font_dir = os.path.expanduser("~/.local/share/fonts")
                os.makedirs(font_dir, exist_ok=True)
                
                Logger.info(f"Extracting to {font_dir}...")
                with zipfile.ZipFile(download_file, 'r') as zip_ref:
                    # Filter only ttf/otf files or just extract all.
                    # Flattening structure is better but extracting all is simple.
                    for member in zip_ref.namelist():
                        if member.lower().endswith((".ttf", ".otf")):
                            # We want to flatten the directory structure
                            filename = os.path.basename(member)
                            source = zip_ref.open(member)
                            target = open(os.path.join(font_dir, filename), "wb")
                            with source, target:
                                shutil.copyfileobj(source, target)

                Logger.info("Updating font cache...")
                subprocess.run(["fc-cache", "-fv"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                Logger.ok("Successfully installed Nerd Font on Linux.")

        except Exception as e:
            Logger.err(f"Failed to install font: {e}")
            Logger.info("Skipping automatic font installation. Please install 'CaskaydiaCove Nerd Font' manually.")
        finally:
            # Cleanup zip
            if os.path.exists(download_file):
                os.remove(download_file)

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
                     
                 # Set Cascadia Mono NF as Pwsh font in Windows Terminal settings
                 # We iterate over profiles to find the one with "PowerShell" name or just update defaults?
                 # Updating "profiles.defaults" is safer to ensure it applies.
                 if hasattr(self.platform, "update_windows_terminal_settings"):
                     self.platform.update_windows_terminal_settings({
                         "profiles": {
                             "defaults": {
                                 "font": {
                                     "face": "Cascadia Mono NF"
                                 }
                             }
                         }
                     })
                     Logger.ok("Updated Windows Terminal default font to Cascadia Mono NF")
                     
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
                #   (This is terminal-emulator dependent and cannot be easily set for 'zsh' itself, 
                #    which runs inside a terminal. We already set it for VS Code and Windows Terminal.
                #    For Linux terminals like gnome-terminal, it's complex/dconf. Leaving as comment or log.)
                Logger.info("Note: Please set your terminal emulator font to 'Cascadia Mono NF' manually.")
                
            except Exception as e:
                Logger.err(f"Failed to configure .zshrc: {e}")