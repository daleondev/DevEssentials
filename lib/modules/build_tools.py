from lib.modules.base import Component
from lib.core.packages import KnownPackage
from lib.utils.logger import Logger

class BuildTools(Component):
    def install(self) -> None:
        try:
            Logger.info("Installing Build Tools (Compiler, CMake, Ninja)...")
            
            # 1. Compiler Toolchain
            # Windows: WinLibs (MinGW-w64 + GCC + LLVM/Clang + UCRT)
            # Linux: build-essential (GCC + Make)
            self.platform.install_package(KnownPackage.GCC_TOOLCHAIN)
            
            # 2. CMake
            self.platform.install_package(KnownPackage.CMAKE)
            
            # 3. Ninja
            self.platform.install_package(KnownPackage.NINJA)
            
            Logger.ok("Successfully installed build tools.")
            
        except Exception as e:
            Logger.err(f"Failed to install build tools: {e}")
            raise
