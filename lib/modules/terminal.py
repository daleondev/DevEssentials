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
            self._install_oh_my_xxx()
            self._install_font()
            # self._configure_shell()
            Logger.ok("Terminal setup completed successfully.")
        except Exception as e:
            Logger.err(f"Terminal setup failed: {e}")
            raise

    def _install_shell(self):
        if sys.platform == "win32":
            Logger.info("Installing Pwsh...")
            self.platform.install_package(KnownPackage.POWERSHELL)
            
        else:
            Logger.info("Installing Zsh...")
            self.platform.install_package(KnownPackage.ZSH)

            Logger.info("Installing tmux...")
            self.platform.install_package(KnownPackage.TMUX)

    def _install_oh_my_xxx(self):
        if sys.platform == "win32":
            Logger.info("Installing Oh-My-Posh...")
            self.platform.install_package(KnownPackage.OHMYPOSH)

            # PowerShell Profile
            try:
                if not shutil.which("pwsh"):
                    Logger.warn("pwsh not found in PATH. Skipping profile configuration. Please restart terminal and run again.")
                    return

                result = subprocess.check_output(["pwsh", "-NoProfile", "-Command", "echo $PROFILE"], shell=True)
                profile_path = result.decode().strip()
                
                # Ensure directory exists
                os.makedirs(os.path.dirname(profile_path), exist_ok=True)
                
                init_line = 'oh-my-posh init pwsh --config "https://raw.githubusercontent.com/JanDeDobbeleer/oh-my-posh/main/themes/powerlevel10k_lean.omp.json" | Invoke-Expression'
                
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

            Logger.ok("Successfully configured Oh-My-Posh")

        else:
            Logger.info("Installing Oh-My-Zsh...")

            config_path = os.path.join(self.platform.get_home_dir(), ".oh-my-zsh")
            if os.path.exists(config_path):
                shutil.rmtree(config_path)

            Logger.info("Downloading and installing Oh-My-Zsh via script...")
            cmd = r'sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)" "" --unattended'
            subprocess.run(cmd, shell=True, check=True)
            cmd = "git clone --depth=1 https://github.com/romkatv/powerlevel10k.git ${ZSH_CUSTOM:-$HOME/.oh-my-zsh/custom}/themes/powerlevel10k"
            subprocess.run(cmd, shell=True, check=True)
            cmd = "git clone https://github.com/zsh-users/zsh-syntax-highlighting.git ${ZSH_CUSTOM:-$HOME/.oh-my-zsh/custom}/plugins/zsh-syntax-highlighting"
            subprocess.run(cmd, shell=True, check=True)
            cmd = "git clone https://github.com/zsh-users/zsh-autosuggestions ${ZSH_CUSTOM:-$HOME/.oh-my-zsh/custom}/plugins/zsh-autosuggestions"
            subprocess.run(cmd, shell=True, check=True)

            zshrc_path = os.path.join(self.platform.get_home_dir(), ".zshrc");
            zshrc_content = """export ZSH="$HOME/.oh-my-zsh"

# --- THEME ---
ZSH_THEME="powerlevel10k/powerlevel10k"

# --- PLUGINS ---
# git: Standard git shortcuts
# zsh-syntax-highlighting: Colors your commands
# zsh-autosuggestions: Suggests commands as you type
# vi-mode: Adds Vim bindings to your shell (ESC to go to normal mode!)
plugins=(
    git
    zsh-syntax-highlighting
    zsh-autosuggestions
    vi-mode
)

# --- USER CONFIGURATION ---
source $ZSH/oh-my-zsh.sh

# --- VIM MODE CONFIG ---
VI_MODE_SET_CURSOR=true

# --- POWERLEVEL10K CACHE ---
[[ ! -f ~/.p10k.zsh ]] || source ~/.p10k.zsh
"""
            try:
                with open(zshrc_path, "w", encoding="utf-8") as f:
                    f.write(zshrc_content)
                Logger.ok(f"Created default .zshrc at {zshrc_path}")
            except Exception as e:
                Logger.warn(f"Failed to create .zshrc: {e}")

        Logger.ok("Successfully configured Oh-My-Zsh")

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
                os.startfile(extract_dir)

            else:
                font_dir = os.path.expanduser("~/.local/share/fonts")
                os.makedirs(font_dir, exist_ok=True)
                
                Logger.info(f"Extracting to {font_dir}...")
                with zipfile.ZipFile(download_file, 'r') as zip_ref:
                    for member in zip_ref.namelist():
                        if member.lower().endswith((".ttf", ".otf")):
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
            Logger.info("Skipping automatic font installation. Please install 'Cascadia Mono NF' manually.")

        finally:
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
            Logger.info("Configuring Windows Terminal...")
            if hasattr(self.platform, "get_windows_terminal_settings_path"):
                settings_path = self.platform.get_windows_terminal_settings_path()
                if settings_path:
                    Logger.info(f"Found Windows Terminal settings at {settings_path}")
                    self.platform.update_windows_terminal_settings({"defaultProfile": "PowerShell"})
                else:
                    Logger.warn("Could not find Windows Terminal settings")
            Logger.ok(f"Windows Terminal configured")
            
            Logger.info("Creating Windows Terminal shortcut...")
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
            pass