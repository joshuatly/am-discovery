import logging

from client import AppleMusicClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")


def main():
    client = AppleMusicClient()
    storefronts = ["hk", "jp", "my", "tw", "sg", "us"]
    for sf in storefronts:
        url = client.discover_room_url(sf)
        print(f"{sf.upper()}: {url}")


if __name__ == "__main__":
    main()
