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
                                             
            self.platform.install_vscode_extension("tomphilbin.gruvbox-themes")
            self.platform.add_vscode_setting("workbench.colorTheme", "Gruvbox Dark (Hard)")
            
            self.platform.install_vscode_extension("s-nlf-fh.glassit")
            self.platform.add_vscode_setting("glassit.alpha", 250)
            Logger.ok("Successfully configured VS-Code")

            Logger.ok("Successfully installed default applications")
            
        except Exception as e:
            Logger.err(f"Default installation failed: {e}")
            raise
