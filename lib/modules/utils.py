from lib.modules.base import Component
from lib.core.packages import KnownPackage
from lib.utils.logger import Logger

class Utils(Component):
    def install(self) -> None:
        try:
            Logger.info("Installing Utilities (7zip, Wget, KeePass)...")
            
            # 1. 7zip
            self.platform.install_package(KnownPackage.ZIP7)
            
            # 2. Wget
            self.platform.install_package(KnownPackage.WGET)
            
            # 3. KeePass
            self.platform.install_package(KnownPackage.KEEPASS)
            
            Logger.ok("Successfully installed utilities.")
            
        except Exception as e:
            Logger.err(f"Failed to install utilities: {e}")
            raise
