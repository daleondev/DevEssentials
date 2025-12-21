from abc import ABC, abstractmethod
from typing import Union
from lib.core.packages import KnownPackage

class Platform(ABC):
    @abstractmethod
    def add_to_path(self, folder_path: str) -> None:
        """Adds a folder to the user's PATH persistently."""
        pass

    @abstractmethod
    def install_vscode_extension(self, extension_id: str) -> None:
        """Installs a VS Code extension."""
        pass

    @abstractmethod
    def install_package(self, package: Union[str, KnownPackage]) -> None:
        """Installs a system package."""
        pass
    
    @abstractmethod
    def get_home_dir(self) -> str:
        """Returns the user's home directory."""
        pass
