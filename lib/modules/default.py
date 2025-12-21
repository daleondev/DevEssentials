from lib.modules.base import Component
from lib.core.packages import KnownPackage
from lib.utils.logger import print_info, print_ok, print_err

class Default(Component):
    def install(self) -> None:
        try:
            # 1. Install Git
            print_info("Installing Git...")
            self.platform.install_package(KnownPackage.GIT)
            print_ok("Successfully installed Git")

            # 2. Configure VS Code
            print_info("Installing VS-Code extensions...")
            extensions = [
                "tomphilbin.gruvbox-themes",
                "s-nlf-fh.glassit"
            ]
            for ext in extensions:
                self.platform.install_vscode_extension(ext)
            print_ok("Successfully installed VS-Code extensions")
            
        except Exception as e:
            print_err(f"Default installation failed: {e}")
            raise
