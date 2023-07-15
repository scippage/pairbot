This uses the [discord.py](https://discordpy.readthedocs.io/en/stable/) wrapper around the Discord API.

```
pip install discord
pip install python-dotenv
```

Edit .env to add the keys read by `os.getenv` in the code.

```
nohup python bot.py &
```

The server administrator should use the appropriate administrator-only commands to configure how notifications get sent out.

This bot allows users to use Discord application commands ("slash commands") to sign up for pair programming practice according to their preferred schedule. User schedules are stored locally in a sqlite database.

Functionality is fairly minimal and example usage should be referenced through the code.