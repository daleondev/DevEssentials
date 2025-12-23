import sys
import subprocess
from lib.modules.base import Component
from lib.core.packages import KnownPackage
from lib.utils.logger import Logger

class Default(Component):
    def install(self) -> None:
        try:
            # 1. Install Git
            Logger.info("Installing Git...")
            self.platform.install_package(KnownPackage.GIT)
            Logger.ok("Successfully installed Git")
            
            # 2. Install VS Code
            Logger.info("Installing VS-Code...")
            if sys.platform != "win32":
                subprocess.run(r'echo "code code/add-microsoft-repo boolean true" | sudo debconf-set-selections', shell=True, check=True)
                subprocess.run("sudo apt-get install wget gpg", shell=True, check=True)
                subprocess.run("wget -qO- https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor > microsoft.gpg", shell=True, check=True)
                subprocess.run("sudo install -D -o root -g root -m 644 microsoft.gpg /usr/share/keyrings/microsoft.gpg", shell=True, check=True)
                subprocess.run("rm -f microsoft.gpg", shell=True, check=True)
                subprocess.run("""echo "Types: deb
URIs: https://packages.microsoft.com/repos/code
Suites: stable
Components: main
Architectures: amd64,arm64,armhf
Signed-By: /usr/share/keyrings/microsoft.gpg
" | sudo tee /etc/apt/sources.list.d/vscode.list > /dev/null
""", shell=True, check=True)
                subprocess.run("sudo apt install apt-transport-https && sudo apt update", shell=True, check=True)
                
            self.platform.install_package(KnownPackage.VS_CODE)
            Logger.ok("Successfully installed VS-Code")

            # 3. Configure VS Code
            Logger.info("Configuring VS-Code...")
            self.platform.add_vscode_setting("editor.fontFamily", "Cascadia Code")
            self.platform.add_vscode_setting("terminal.integrated.stickyScroll.enabled", False)
            self.platform.add_vscode_setting("editor.minimap.enabled", False)
            self.platform.add_vscode_setting("window.zoomLevel", 0.5)
            self.platform.add_vscode_setting("breadcrumbs.enabled", True)
            self.platform.add_vscode_setting("update.showReleaseNotes", False)
            self.platform.add_vscode_setting("zenMode.hideLineNumbers", False)
            self.platform.add_vscode_setting("editor.lineNumbers", "relative")
            self.platform.add_vscode_setting("editor.formatOnSave", True)
            self.platform.add_vscode_setting("workbench.activityBar.location", "hidden")
            self.platform.add_vscode_setting("editor.stickyScroll.enabled", False)
                                             
            self.platform.install_vscode_extension("tomphilbin.gruvbox-themes")
            self.platform.add_vscode_setting("workbench.colorTheme", "Gruvbox Dark (Hard)")
            
            self.platform.install_vscode_extension("s-nlf-fh.glassit")
            self.platform.add_vscode_setting("glassit.alpha", 250)
            
            self.platform.install_vscode_extension("ms-python.python")
            self.platform.install_vscode_extension("ms-python.debugpy")
            self.platform.install_vscode_extension("ms-python.vscode-pylance")
            Logger.ok("Successfully configured VS-Code")

            Logger.ok("Successfully installed default applications")
            
        except Exception as e:
            Logger.err(f"Default installation failed: {e}")
            raise
