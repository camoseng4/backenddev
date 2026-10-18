import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "service"))
from snapshot import Snapshot

if __name__ == "__main__":
    # Manual cloud-connected driver; never execute during routine test discovery.
    print(Snapshot(1))
