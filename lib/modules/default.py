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

            # 2. Configure VS Code
            Logger.info("Installing VS-Code extensions...")
            extensions = [
                "tomphilbin.gruvbox-themes",
                "s-nlf-fh.glassit"
            ]
            for ext in extensions:
                self.platform.install_vscode_extension(ext)
            Logger.ok("Successfully installed VS-Code extensions")
            
        except Exception as e:
            Logger.err(f"Default installation failed: {e}")
            raise
