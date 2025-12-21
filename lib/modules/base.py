from abc import ABC, abstractmethod
from lib.systems.platform import Platform

class Component(ABC):
    def __init__(self, platform: Platform):
        self.platform = platform

    @abstractmethod
    def install(self) -> None:
        """Performs the installation logic."""
        pass
