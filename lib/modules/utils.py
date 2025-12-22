from lib.modules.base import Component
from lib.core.packages import KnownPackage
from lib.utils.logger import Logger

class Utils(Component):
    def install(self) -> None:
        try:
            Logger.info("Installing Utilities (Wget, KeePass)...")
            
            # 1. Wget
            self.platform.install_package(KnownPackage.WGET)
            
            # 2. KeePass
            self.platform.install_package(KnownPackage.KEEPASS)
            
            Logger.ok("Successfully installed utilities.")
            
        except Exception as e:
            Logger.err(f"Failed to install utilities: {e}")
            raise
