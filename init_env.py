"""Bootstrap helper to prepare config.json and data directory."""
from gym_service import ConfigManager, DataStore


def main() -> None:
    cfg_mgr = ConfigManager()
    cfg = cfg_mgr.load()  # creates config.json if missing
    DataStore(cfg["storage_dir"])  # ensures data directory and file path exist
    print("✅ 配置文件和数据目录已就绪: config.json,", cfg["storage_dir"])


if __name__ == "__main__":
    main()
