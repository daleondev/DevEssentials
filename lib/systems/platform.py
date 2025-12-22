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

    @abstractmethod
    def get_vscode_keybindings_path(self) -> str:
        """Returns the path to VS Code keybindings.json."""
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

    def _load_vscode_keybindings(self) -> list:
        path = self.get_vscode_keybindings_path()
        if not os.path.exists(path):
            return []
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = json.load(f)
                if isinstance(content, list):
                    return content
                return []
        except json.JSONDecodeError as e:
            raise Exception(f"Failed to parse {path}: {e}")

    def _save_vscode_keybindings(self, keybindings: list) -> None:
        path = self.get_vscode_keybindings_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(keybindings, f, indent=4)

    def add_vscode_setting(self, key: str, value: Any) -> None:
        """Adds or updates a VS Code setting."""
        settings = self._load_vscode_settings()
        settings[key] = value
        self._save_vscode_settings(settings)

    def add_vscode_keybinding(self, keybinding: Dict[str, Any]) -> None:
        """Adds a VS Code keybinding if it doesn't already exist."""
        bindings = self._load_vscode_keybindings()
        
        # Check for duplicates based on 'key' and 'command'
        for b in bindings:
            if b.get("key") == keybinding.get("key") and b.get("command") == keybinding.get("command"):
                # Already exists
                return

        bindings.append(keybinding)
        self._save_vscode_keybindings(bindings)

    @abstractmethod
    def create_shortcut(self, target_path: str, shortcut_path: str, description: str = "", icon_path: str = "", working_dir: str = "", hotkey: str = "") -> None:
        """Creates a system shortcut."""
        pass
