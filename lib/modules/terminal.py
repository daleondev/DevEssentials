import os
import sys
import shutil
import subprocess
import urllib.request
import zipfile
import json
from lib.modules.base import Component
from lib.core.packages import KnownPackage
from lib.utils.logger import Logger

class Terminal(Component):
    FONT_URL = "https://github.com/microsoft/cascadia-code/releases/download/v2407.24/CascadiaCode-2407.24.zip"
    FONT_NAME = "Cascadia Mono NF"
    
    OMP_CONFIG_URL = "https://raw.githubusercontent.com/JanDeDobbeleer/oh-my-posh/main/themes/powerlevel10k_rainbow.omp.json"
    
    OMZ_INSTALL_SCRIPT_URL = "https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh"
    
    ZSH_PLUGINS = [
        ("https://github.com/romkatv/powerlevel10k.git", "themes/powerlevel10k"),
        ("https://github.com/zsh-users/zsh-syntax-highlighting.git", "plugins/zsh-syntax-highlighting"),
        ("https://github.com/zsh-users/zsh-autosuggestions", "plugins/zsh-autosuggestions")
    ]

    ZSHRC_TEMPLATE = """export ZSH="$HOME/.oh-my-zsh"

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

    GRUVBOX_THEME_WIN = {
        "name": "GruvboxDarkHard",
        "black": "#1b1b1b",
        "red": "#cc241d",
        "green": "#98971a",
        "yellow": "#d79921",
        "blue": "#458588",
        "purple": "#b16286",
        "cyan": "#689d6a",
        "white": "#a89984",
        "brightBlack": "#928374",
        "brightRed": "#fb4934",
        "brightGreen": "#b8bb26",
        "brightYellow": "#fabd2f",
        "brightBlue": "#83a598",
        "brightPurple": "#d3869b",
        "brightCyan": "#8ec07c",
        "brightWhite": "#ebdbb2",
        "background": "#1b1b1b",
        "foreground": "#ebdbb2",
        "selectionBackground": "#665c54",
        "cursorColor": "#ebdbb2"
    }

    GRUVBOX_PALETTE_LINUX = [
        '#282828', '#CC241D', '#98971A', '#D79921', '#458588', '#B16286', '#689D6A', '#A89984',
        '#928374', '#FB4934', '#B8BB26', '#FABD2F', '#83A598', '#D3869B', '#8EC07C', '#EBDBB2'
    ]

    def install(self) -> None:
        """Orchestrates the terminal environment setup."""
        try:
            self._install_shell()
            self._setup_prompts()
            self._install_font()
            self._configure_terminal_settings()
            Logger.ok("Terminal setup completed successfully.")
        except Exception as e:
            Logger.err(f"Terminal setup failed: {e}")
            raise

    def _install_shell(self) -> None:
        """Installs the platform-specific shell."""
        if sys.platform == "win32":
            Logger.info("Installing Pwsh...")
            self.platform.install_package(KnownPackage.POWERSHELL)
        else:
            Logger.info("Installing Zsh...")
            self.platform.install_package(KnownPackage.ZSH)
            Logger.info("Installing tmux...")
            self.platform.install_package(KnownPackage.TMUX)

    def _setup_prompts(self) -> None:
        """Configures the shell prompt (Oh-My-Posh for Windows, Oh-My-Zsh for Linux)."""
        if sys.platform == "win32":
            self._setup_oh_my_posh()
        else:
            self._setup_oh_my_zsh()

    def _setup_oh_my_posh(self) -> None:
        """Installs and configures Oh-My-Posh on Windows."""
        Logger.info("Installing Oh-My-Posh...")
        self.platform.install_package(KnownPackage.OHMYPOSH)

        # PowerShell Profile Configuration
        try:
            if not shutil.which("pwsh"):
                Logger.warn("pwsh not found in PATH. Skipping profile configuration.")
                return

            result = subprocess.check_output(["pwsh", "-NoProfile", "-Command", "echo $PROFILE"], shell=True)
            profile_path = result.decode().strip()
            
            os.makedirs(os.path.dirname(profile_path), exist_ok=True)
            
            init_line = f'oh-my-posh init pwsh --config "{self.OMP_CONFIG_URL}" | Invoke-Expression'
            
            content = ""
            if os.path.exists(profile_path):
                with open(profile_path, "r", encoding="utf-8") as f:
                    content = f.read()
            
            if "oh-my-posh init pwsh" not in content:
                with open(profile_path, "a", encoding="utf-8") as f:
                    f.write(f"{init_line}\n")
                    f.write(f"cls\n")
                Logger.ok(f"Added Oh-My-Posh init to {profile_path}")
            else:
                Logger.info("Oh-My-Posh already configured in profile.")
                
        except Exception as e:
            Logger.err(f"Failed to configure PowerShell profile: {e}")

        Logger.ok("Successfully configured Oh-My-Posh")

    def _setup_oh_my_zsh(self) -> None:
        """Installs and configures Oh-My-Zsh on Linux."""
        Logger.info("Installing Oh-My-Zsh...")

        config_path = os.path.join(self.platform.get_home_dir(), ".oh-my-zsh")
        if os.path.exists(config_path):
            shutil.rmtree(config_path)

        Logger.info("Downloading and installing Oh-My-Zsh via script...")
        cmd = f'sh -c "$(curl -fsSL {self.OMZ_INSTALL_SCRIPT_URL})" "" --unattended'
        subprocess.run(cmd, shell=True, check=True)

        # Plugins and Themes
        custom_dir = os.path.join(config_path, "custom")
        
        for repo_url, relative_path in self.ZSH_PLUGINS:
            target_path = os.path.join(custom_dir, relative_path)
            cmd = f"git clone --depth=1 {repo_url} {target_path}"
            subprocess.run(cmd, shell=True, check=True)

        zshrc_path = os.path.join(self.platform.get_home_dir(), ".zshrc")
        try:
            with open(zshrc_path, "w", encoding="utf-8") as f:
                f.write(self.ZSHRC_TEMPLATE)
            Logger.ok(f"Created default .zshrc at {zshrc_path}")
        except Exception as e:
            Logger.warn(f"Failed to create .zshrc: {e}")

        Logger.ok("Successfully configured Oh-My-Zsh")

    def _check_font_installed(self) -> bool:
        """Checks if Cascadia Mono NF is already installed."""
        if sys.platform == "win32":
            # Check standard Windows Fonts directory
            # Windows fonts can be installed in %WINDIR%\Fonts or %LOCALAPPDATA%\Microsoft\Windows\Fonts
            fonts_dirs = [
                os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts"),
                os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Windows", "Fonts")
            ]
            
            # Simple check for filename existence as a proxy
            # CascadiaCode usually installs as 'CascadiaCode*.ttf'
            for directory in fonts_dirs:
                if os.path.exists(directory):
                    for f in os.listdir(directory):
                        if "CascadiaMonoNF" in f or "CascadiaCodeNF" in f:
                            return True
            return False
            
        else:
            # Linux: Use fc-list
            if not shutil.which("fc-list"):
                return False
            try:
                output = subprocess.check_output(["fc-list", ":family"], text=True)
                return self.FONT_NAME in output
            except Exception:
                return False

    def _install_font(self) -> None:
        """Downloads and installs Cascadia Mono NF font."""
        if self._check_font_installed():
            Logger.info(f"Font '{self.FONT_NAME}' is already installed.")
            return

        Logger.info(f"Installing Font ({self.FONT_NAME})...")
        
        zip_name = "CascadiaCode.zip"
        download_dir = os.path.join(os.getcwd(), "tmp")
        os.makedirs(download_dir, exist_ok=True)
        download_file = os.path.join(download_dir, zip_name)

        try:
            Logger.info(f"Downloading font from {self.FONT_URL}...")
            urllib.request.urlretrieve(self.FONT_URL, download_file)
            
            if sys.platform == "win32":
                self._install_font_windows(download_dir, download_file)
            else:
                self._install_font_linux(download_file)

        except Exception as e:
            Logger.err(f"Failed to install font: {e}")
            Logger.info(f"Skipping automatic font installation. Please install '{self.FONT_NAME}' manually.")

        finally:
            if os.path.exists(download_file):
                os.remove(download_file)

    def _install_font_windows(self, download_dir: str, download_file: str) -> None:
        extract_dir = os.path.join(download_dir, "CascadiaCode")
        with zipfile.ZipFile(download_file, 'r') as zip_ref:
            zip_ref.extractall(extract_dir)
        
        Logger.info("Font downloaded. Installing on Windows is complex via script.")
        Logger.info(f"Please install the fonts in '{extract_dir}' manually (Select all -> Right Click -> Install).")
        os.startfile(extract_dir)

    def _install_font_linux(self, download_file: str) -> None:
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

    def _configure_terminal_settings(self) -> None:
        """Configures settings for VS Code and System Terminal."""
        Logger.info("Configuring Shell...")
        self._configure_vscode()
        
        if sys.platform == "win32":
            self._configure_windows_terminal()
        else:
            self._configure_gnome_terminal()

    def _configure_vscode(self) -> None:
        try:
            Logger.info("Updating VS Code terminal settings...")
            if sys.platform == "win32":
                self.platform.add_vscode_setting("terminal.integrated.defaultProfile.windows", "PowerShell")
            else:
                self.platform.add_vscode_setting("terminal.integrated.defaultProfile.linux", "zsh")
            
            self.platform.add_vscode_setting("terminal.integrated.fontFamily", self.FONT_NAME)          
            Logger.ok("VS Code terminal settings updated.")
        except Exception as e:
            Logger.err(f"Failed to update VS Code settings: {e}")

    def _configure_windows_terminal(self) -> None:
        Logger.info("Configuring Windows Terminal...")
        if hasattr(self.platform, "get_windows_terminal_settings_path"):
            settings_path = self.platform.get_windows_terminal_settings_path()
            if settings_path:
                Logger.info(f"Found Windows Terminal settings at {settings_path}")
                
                updates = {
                    "defaultProfile": "PowerShell",
                    "profiles": {
                        "defaults": {
                            "colorScheme": self.GRUVBOX_THEME_WIN["name"],
                            "font": {
                                "face": self.FONT_NAME
                            }
                        }
                    },
                    "schemes": [self.GRUVBOX_THEME_WIN]
                }
                self.platform.update_windows_terminal_settings(updates)
            else:
                Logger.warn("Could not find Windows Terminal settings")
        
        Logger.ok(f"Windows Terminal configured")
        
        # Shortcut creation
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

    def _configure_gnome_terminal(self) -> None:
        Logger.info("Configuring Gnome Terminal...")
        
        theme_data = {
            "palette": self.GRUVBOX_PALETTE_LINUX,
            "background": "#282828",
            "foreground": "#EBDBB2",
            "font": f"{self.FONT_NAME} 12",
            "transparency_percent": 5
        }
        
        if hasattr(self.platform, "configure_gnome_terminal"):
                self.platform.configure_gnome_terminal(theme_data)
            