from pathlib import Path
from yaml import safe_load


class Storage:
    def __init__(self):
        self.file = Path("data.yaml")
        self.file.touch(exist_ok=True)

    def load(self):
        with self.file.open(encoding="utf-8") as f:
            data = safe_load(f)
        return data


if __name__ == "__main__":
    a = Storage()
    b = a.load()
    print(b)
