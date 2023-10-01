# Pairbot

## About

This bot allows users to use Discord application commands ("slash commands") to sign up for pair programming practice according to their preferred schedule. User schedules are stored locally in a sqlite database.

Functionality is fairly minimal and example usage should be referenced through the code.

The server administrator should use the appropriate administrator-only commands to configure how notifications get sent out.

## Development

Place your Discord bot token in .env:

``` sh
BOT_TOKEN_DEV=...
```

Dependencies are managed with [Hatch](https://hatch.pypa.io/latest/):

``` sh
hatch env create
hatch run dev
```

Run [black](https://pypi.org/project/black/) and [isort](https://pycqa.github.io/isort/index.html) on your code:

``` sh
hatch run style:check
hatch run style:format
```

