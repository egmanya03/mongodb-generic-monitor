"""
config.py
config.yaml load karta hai aur poore app ko settings deta hai.
UI se naya DB profile add/delete karne pe, ye seedha config.yaml
file me likh deta hai — permanent rehta hai, restart ke baad bhi.
"""

import yaml
from pathlib import Path

CONFIG_PATH = Path(__file__).parent / "config.yaml"


class Settings:
    def __init__(self):
        self._raw = self._load()
        self.active_profile = self._raw.get("active_profile", "local")

    def _load(self) -> dict:
        with open(CONFIG_PATH, "r") as f:
            return yaml.safe_load(f)

    def _write(self):
        with open(CONFIG_PATH, "w") as f:
            yaml.safe_dump(self._raw, f, sort_keys=False, allow_unicode=True)

    def reload(self):
        self._raw = self._load()

    @property
    def profiles(self) -> dict:
        return self._raw.get("profiles", {})

    def get_profile(self, name: str = None) -> dict:
        name = name or self.active_profile
        if name not in self.profiles:
            raise ValueError(f"Profile '{name}' config.yaml me nahi mila")
        return self.profiles[name]

    def set_active_profile(self, name: str):
        if name not in self.profiles:
            raise ValueError(f"Profile '{name}' config.yaml me nahi mila")
        self.active_profile = name

    def add_profile(self, name: str, mongo_uri: str, db_name: str,
                     requires_vpn: bool = False, label: str = None):
        """Naya DB profile add karke config.yaml me permanently save karta hai."""
        if "profiles" not in self._raw:
            self._raw["profiles"] = {}
        self._raw["profiles"][name] = {
            "mongo_uri": mongo_uri,
            "db_name": db_name,
            "requires_vpn": requires_vpn,
            "label": label or name,
        }
        self._write()

    def delete_profile(self, name: str):
        """Profile ko config.yaml se permanently hata deta hai."""
        if name not in self._raw.get("profiles", {}):
            raise ValueError(f"Profile '{name}' nahi mila")
        if len(self._raw["profiles"]) <= 1:
            raise ValueError("Kam se kam ek profile hona zaroori hai — isse delete nahi kar sakte")
        del self._raw["profiles"][name]
        if self.active_profile == name:
            self.active_profile = next(iter(self._raw["profiles"]))
        self._write()

    @property
    def default_limit(self) -> int:
        return self._raw.get("query", {}).get("default_limit", 50)

    @property
    def max_limit(self) -> int:
        return self._raw.get("query", {}).get("max_limit", 500)

    @property
    def host(self) -> str:
        return self._raw.get("server", {}).get("host", "0.0.0.0")

    @property
    def port(self) -> int:
        return self._raw.get("server", {}).get("port", 8000)

    @property
    def matrix(self) -> dict:
        return self._raw.get("matrix", {})


settings = Settings()
