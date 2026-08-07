from __future__ import annotations

from app.config import load_config
from app.database import AgentDatabase


def main() -> None:
    config = load_config()
    db = AgentDatabase(config.database_path)
    db.initialize()
    print(f"Initialized database at {config.database_path}")


if __name__ == "__main__":
    main()

