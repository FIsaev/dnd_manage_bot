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
- `test_dice.py`, `test_bot.py` — 61 tests, rolls scripted so they are exact.

## Limits (abuse guards)

200 characters per expression, 200 dice per term, 500 dice per roll,
10000 sides per die, 16 levels of brackets.

## Not in this beta

Exploding dice, re-roll buttons, per-chat defaults, nat-20/nat-1 highlighting.
