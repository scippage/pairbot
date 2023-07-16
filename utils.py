import argparse
import json


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("-d", "--dev", action="store_true", help="use dev environment")
    return parser.parse_args()


def read_guild_to_channel(path: str):
    with open(path, "r") as f:
        return json.load(f)
