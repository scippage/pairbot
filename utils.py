import argparse
import json
import random

import discord


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("-d", "--dev", action="store_true", help="use dev environment")
    return parser.parse_args()


def read_guild_to_channel(path: str):
    with open(path, "r") as f:
        return json.load(f)


def load_leetcode_problems():
    with open('Problems.json', 'r') as file:
        return json.load(file)
    
    
leetcode_problems = load_leetcode_problems()

def get_random_leetcode_problem():
    problem = random.choice(leetcode_problems)
    return {
        "title": problem["text"],
        "url": problem["href"]
    }
    
def get_user_name(user: discord.User):
    if user.global_name is not None:
        return user.global_name
    elif user.nick is not None:
        return user.nick
    else:
        return user.name
