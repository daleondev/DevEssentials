from abc import ABC, abstractmethod
from typing import Union, Any, Dict
import json
import os
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

    @abstractmethod
    def get_vscode_settings_path(self) -> str:
        """Returns the path to VS Code settings.json."""
        pass

    def _load_vscode_settings(self) -> Dict[str, Any]:
        path = self.get_vscode_settings_path()
        if not os.path.exists(path):
            return {}
        try:
            with open(path, 'r', encoding='utf-8') as f:
                # Note: standard json module does not support comments (JSONC).
                # If settings.json has comments, this will fail.
                return json.load(f)
        except json.JSONDecodeError as e:
            raise Exception(f"Failed to parse {path}. It might contain comments or be invalid JSON: {e}")

    def _save_vscode_settings(self, settings: Dict[str, Any]) -> None:
        path = self.get_vscode_settings_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(settings, f, indent=4)

    def check_vscode_setting_exists(self, key: str) -> bool:
        settings = self._load_vscode_settings()
        return key in settings

    def update_vscode_setting(self, key: str, value: Any) -> None:
        """Adds or updates a VS Code setting."""
        settings = self._load_vscode_settings()
        settings[key] = value
        self._save_vscode_settings(settings)
        """Returns the user's home directory."""
        pass
