#!/usr/bin/env python3
"""
Download the MITRE ATT&CK Enterprise STIX bundle into source/app/resources/.

Usage:
    python scripts/download_mitre_attack.py

Requires: requests  (pip install requests)
"""
import os
import sys
from pathlib import Path

DEST = Path(__file__).parent.parent / 'source' / 'app' / 'resources' / 'enterprise-attack.json'
URL = 'https://raw.githubusercontent.com/mitre/cti/master/enterprise-attack/enterprise-attack.json'


def main():
    try:
        import requests
    except ImportError:
        print("Please install requests:  pip install requests")
        sys.exit(1)

    print(f"Downloading ATT&CK Enterprise bundle from MITRE CTI …")
    resp = requests.get(URL, stream=True, timeout=120)
    resp.raise_for_status()

    size = 0
    with open(DEST, 'wb') as f:
        for chunk in resp.iter_content(chunk_size=65536):
            f.write(chunk)
            size += len(chunk)

    print(f"Saved {size // 1024} KB -> {DEST}")


if __name__ == '__main__':
    main()
