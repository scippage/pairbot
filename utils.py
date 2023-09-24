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

def get_random_leetcode_problem(difficulty: str):
    if difficulty == "Any":
        problems_pool = leetcode_problems
    else: 
        problems_pool = [problem for problem in leetcode_problems if problem["difficulty"] == difficulty] 
           
    selected_problem = random.choice(problems_pool)
    return {
        "title": selected_problem["text"],
        "url": selected_problem["href"]
    }       
    
def get_user_name(user: discord.User):
    if user.global_name is not None:
        return user.global_name
    elif user.nick is not None:
        return user.nick
    else:
        return user.name
