# Blackjack

Private multiplayer blackjack for up to 6 players, built with Python + Flask + Flask-SocketIO.

## Rules

| Setting | Value |
|---|---|
| Decks | 6 |
| Blackjack payout | 3:2 |
| Dealer hits soft 17 | Yes |
| Double down | Any two cards |
| Splits | Yes |
| Starting chips | 2,000 (editable) |
| Minimum bet | 25 chips |
| Maximum bet | Stack only |

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Project structure

```
game.py          # Core game logic (no web dependencies)
test_game.py     # Smoke tests for game logic
requirements.txt # Python dependencies
```

## Running tests

```bash
python test_game.py
```

## Stack

- **Backend:** Python, Flask, Flask-SocketIO
- **Real-time:** WebSockets via Socket.IO
- **Auth:** Flask-Login (password-protected, private)
