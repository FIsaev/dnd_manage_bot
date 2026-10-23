# D&D dice bot (beta)

Reads group messages, spots dice expressions like `3d6+1`, replies to the
message with the result, and keeps the full calculation path in an expandable
quote underneath.

```
🎲 17  3d6(+1)+2
▸ 3d6(+1): 4, 2, 6  (+1 each)  ->  5 + 3 + 7 = 15     <- collapsed quote
  15 + 2 = 17
```

## Where the bonus goes

| You write     | Meaning                                    |
| ------------- | ------------------------------------------ |
| `3d6+1`       | roll 3d6, sum, **+1 to the total**         |
| `3d6(+1)`     | **+1 to every die**, then sum              |
| `(3d6+1)`     | same as `3d6(+1)` — a `+/-` inside brackets belongs to each die |
| `2d6(+3-1)`   | several modifiers in one bracket add up (`+2` per die) |
| `2d6(+1)-3`   | +1 per die, then -3 off the total          |
| `2d4(-5)`     | **a die never goes below 0** → `0 + 0 = 0`, not `-7` |
| `(2d6+1d4)*2` | two dice terms in brackets → ordinary grouping, nothing per-die |

## Keeping the best or worst dice

| You write    | Meaning                                              |
| ------------ | ---------------------------------------------------- |
| `4d6kh3`     | roll 4d6, sum the best 3 — the classic stat roll     |
| `2d20kh1`    | advantage; a bare `kh` means `kh1`                   |
| `2d20kl1`    | disadvantage                                         |
| `4d6kh3(+1)` | +1 on each **kept** die; dropped dice contribute nothing |

Dropped dice stay visible in the calculation path inside `[brackets]`:

```
4d6kh3: 3, 4, 6, [2]  ->  sum = 13
```

Which dice are kept is decided on the raw faces, and a per-die modifier shifts
every die equally, so it can never change the choice. Ties go to the die rolled
first. `4d6k3` (Roll20 style) is not accepted — write `kh`/`kl` explicitly,
because a bare `k` is what Russian players type for `d`.

Also supported: `kh`/`kl` (below), `d20` (count defaults to 1), `d%` (= d100), `*` and `/`,
negative terms (`-d4+10`), nested brackets, and `3к6` / `3д6` for `3d6`.
A note after `#` or `;` is echoed back: `2d6+3 # sneak attack`.

The 0 floor is per die, and the calc path says `min 0` whenever it bit. Maths
outside the dice is untouched, so `1d4-10` still goes negative.

Division is exact, not rounded (`1d6/4` → `1.25`); D&D "round down" is not
applied for you.

## When the bot answers

In a group it stays quiet unless the **whole message** is an expression, so
chat like `i rolled 3d6+1 yesterday` is ignored. `/roll 3d6+1` (or `/r`) always
works, in groups and in DMs. If a message looks like a roll but does not parse
(`3d6+`), it answers with a short error.

## Setup

1. `@BotFather` → `/newbot` → copy the token.
2. **`@BotFather` → `/mybots` → your bot → Bot Settings → Group Privacy →
   Turn off.** Without this Telegram only delivers commands and replies to the
   bot, so bare `3d6+1` messages never arrive.
3. Add the bot to the group.

Needs Python 3.10+ (tested on 3.11 and 3.14). In PowerShell:

```powershell
python -m venv venv
venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
venv\Scripts\python.exe bot.py
```

Then paste your token into `.env`. `BOT_TOKEN` can also come from the
environment instead. Windows PowerShell 5.1 has no `&&` — chain with `;`, or
`a; if ($?) { b }` to stop on failure.

## If it will not start

- `ImportError: cannot import name 'Update' from 'telegram'` — something
  installed the unrelated PyPI package named `telegram`, which overwrites
  `telegram/__init__.py`. The import name is `telegram`, but the package is
  always `python-telegram-bot`. Fix:
  `pip uninstall -y telegram` then
  `pip install --force-reinstall --no-deps -r requirements.txt`.
- `RuntimeError: There is no current event loop` from `run_polling` — that is
  python-telegram-bot 21.x on Python 3.13/3.14. `requirements.txt` asks for
  22.x, which supports them; run `pip install --upgrade -r requirements.txt`.

## Hosting

Long polling is the default, so the bot needs **no inbound port, no domain and
no TLS** — anything that keeps a process alive will do. Run exactly one
instance: two processes polling the same token make Telegram reject one with
`409 Conflict`. Never commit `.env`; set the token in the host's own
environment or secrets UI.

### Docker, on any VPS

```bash
docker compose up -d --build
docker compose logs -f
```

The token is read from `.env` at run time and never baked into the image
(`.dockerignore` keeps it out), the bot restarts unless you stop it yourself,
and the log files are capped at 3 x 10 MB.

### A VPS without Docker

`deploy/dnd-bot.service` is a ready systemd unit: restart on failure,
`NoNewPrivileges`, read-only system. Put the repo in `/opt/dnd_manage_bot`
with a venv beside it, then:

```bash
sudo cp deploy/dnd-bot.service /etc/systemd/system/
sudo systemctl enable --now dnd-bot
journalctl -u dnd-bot -f
```

### Render

A Render web service must open a port, and polling never opens one — that is
exactly the `no open ports detected` deploy failure. Two ways out:

1. **Web service in webhook mode** — works on the free plan. `render.yaml` sets
   this up: build `pip install -r requirements.txt`, start `python bot.py`.
   Render injects `PORT` (10000 by default) and the bot binds it on `0.0.0.0`.
   Set `BOT_TOKEN` and `WEBHOOK_URL` under Environment, where `WEBHOOK_URL` is
   the service's own address plus a path —
   `https://<service-name>.onrender.com/telegram` — then redeploy. Render does
   not read `Procfile`, so the start command comes from `render.yaml` or the
   dashboard.
2. **Background worker in polling mode** — paid, but nothing to configure: no
   port, no public URL, no webhook variables.

Free-plan caveat: a free web service spins down after 15 minutes without
inbound traffic and takes about a minute to wake up, so the first roll after a
quiet spell arrives late or not at all — Telegram will not wait that long for
the webhook. Pinging the URL from outside every ~10 minutes keeps it awake and
costs about 744 instance hours a month, just inside the 750 free hours, as long
as it is the only free service in the workspace.

### Other PaaS: Railway, Fly, Heroku

`Procfile` declares a `worker` process and `.python-version` pins the runtime.
Set `BOT_TOKEN` in the platform's variables, deploy, and keep the instance
count at 1. Choose a **worker / background** service, not a web service.

If the platform only sells web services and insists on an open port, switch to
webhook mode with these variables:

| Variable         | Value                                                     |
| ---------------- | --------------------------------------------------------- |
| `WEBHOOK_URL`    | public https URL, e.g. `https://your-app.onrender.com/telegram` |
| `PORT`           | normally injected by the platform (default 8080)          |
| `WEBHOOK_SECRET` | optional random string Telegram echoes back in a header   |

The URL path is derived from `WEBHOOK_URL`, so there is nothing else to wire
up. Removing `WEBHOOK_URL` returns the bot to polling — python-telegram-bot
deletes the webhook on every polling start, so switching modes needs no
cleanup.

Serverless (Lambda, Cloud Functions) does not fit this beta: polling wants a
long-lived process and webhook mode expects a persistent server.

## Trying it without a token

```bash
python dice.py "3d6(+1)+2"
```

## Tests

```bash
python -m unittest discover -p "test_*.py"
```

## Files

- `dice.py` — tokenizer, parser, roller, calculation path. No dependencies.
- `bot.py` — Telegram layer: the message gate and the reply layout.
- `test_dice.py`, `test_bot.py` — 62 tests, rolls scripted so they are exact.
- `Dockerfile`, `compose.yaml`, `Procfile`, `render.yaml`, `.python-version`,
  `deploy/dnd-bot.service` — deployment, see Hosting above.

## Limits (abuse guards)

200 characters per expression, 200 dice per term, 500 dice per roll,
10000 sides per die, 16 levels of brackets.

## Not in this beta

Exploding dice, re-roll buttons, per-chat defaults, nat-20/nat-1 highlighting.
