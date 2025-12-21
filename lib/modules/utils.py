from lib.modules.base import Component
from lib.core.packages import KnownPackage
from lib.utils.logger import print_info, print_ok, print_err

class Utils(Component):
    def install(self) -> None:
        try:
            print_info("Installing Utilities (7zip, Wget, KeePass)...")
            
            # 1. 7zip
            self.platform.install_package(KnownPackage.ZIP7)
            
            # 2. Wget
            self.platform.install_package(KnownPackage.WGET)
            
            # 3. KeePass
            self.platform.install_package(KnownPackage.KEEPASS)
            
            print_ok("Successfully installed utilities.")
            
        except Exception as e:
            print_err(f"Failed to install utilities: {e}")
            raise
