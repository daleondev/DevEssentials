from lib.modules.base import Component
from lib.utils.logger import print_info, print_ok, print_err

class VSCode(Component):
    def install(self) -> None:
        try:
            print_info("Installing VS-Code extensions...")
            extensions = [
                "tomphilbin.gruvbox-themes",
                "s-nlf-fh.glassit"
            ]
            for ext in extensions:
                self.platform.install_vscode_extension(ext)
            print_ok("Successfully installed VS-Code extensions")
            
        except Exception as e:
            print_err(f"Failed to install VS-Code extensions: {e}")
            raise
