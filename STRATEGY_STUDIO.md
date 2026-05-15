# Strategy Studio — quick reference

The **Strategy Studio** card lives below the AI Portfolio Assistant on the trading dashboard. You type a small piece of code, click **Execute**, and your snippet runs in a sandboxed paper-trading engine — no real broker, no real money. The seed cash is whatever you set in the *Initial Cash Deposit* field on the form.

The same reference is also available inside the app under the **Commands** button at the top-right of the Strategy Studio card.

---

## How a run works

- You write the snippet in the editor.
- Click **Execute** (or press `Ctrl/Cmd + Enter` while focused in the editor).
- The server parses, validates, and runs the code with safety limits:
  - **5 seconds** wall-clock cap.
  - **50 000** operations cap (covers all loop iterations + function calls).
- Each `buy(...)`, `sell(...)`, `log(...)` appends a timestamped line to the console below the editor.
- After the run finishes you get a one-line summary: duration, number of trades, ending cash, mark-to-market portfolio value, and remaining positions.

Cash and positions reset **every** run — Strategy Studio runs are self-contained sandboxes, not live brokerage state.

---

## Market commands

| Command | Description |
| --- | --- |
| `price("TICKER")` | Latest close from Yahoo Finance, cached for the current run. Returns a `float`. |
| `buy("TICKER", shares)` | Paper-buys `shares` (integer). Blocked if the required cash is more than `cash()`. |
| `sell("TICKER", shares)` | Paper-sells `shares` (integer). Blocked if you don't currently hold enough. |
| `position("TICKER")` | Current shares held in this run (`int`). |
| `cash()` | Remaining cash for this run (`float`). |
| `log(*args)` / `print(*args)` | Writes a line to the console. |

Tickers are always normalized to upper-case, so `price("nvda")` and `price("NVDA")` are equivalent.

---

## Control flow

| Construct | Behavior |
| --- | --- |
| `if condition: …` | Runs the block **once** if the condition is true. `elif`/`else` work as expected. |
| `for var in range(N): …` | Runs the block exactly `N` times. `range(start, stop, step)` is supported. |
| `while condition: …` | Runs until the condition becomes false. `while True:` works but is bounded by the 5 s / 50 000-op safety limit. |
| `break` / `continue` / `pass` | Standard loop control. |

Comparisons (`>`, `<`, `>=`, `<=`, `==`, `!=`, `in`, `not in`, `is`, `is not`), boolean operators (`and`, `or`, `not`), arithmetic (`+ - * / // % **`), bitwise operators, conditional expressions (`a if cond else b`), tuples, lists, dicts, sets, slicing, and subscripting are all supported.

---

## Allowed builtins

`range`, `len`, `min`, `max`, `abs`, `round`, `sum`, `int`, `float`, `str`, `bool`, plus the literals `True`, `False`, `None`.

Everything else is intentionally blocked: no `import`, no attribute access (`x.attr`), no function or class definitions, no `eval`/`exec`, no I/O, no networking, no `__dunder__` access. The parser rejects the program before it runs.

---

## Examples

### Single conditional buy

```python
if price("NVDA") > 150:
    buy("NVDA", 100)
    log("Bought NVDA at", price("NVDA"))
```

### Bounded loop — scale into a position

```python
for i in range(5):
    if cash() > 1000:
        buy("AAPL", 5)
        log("Tranche", i + 1, "added; cash now", cash())
```

### `while` with a real exit condition

```python
target_shares = 50
while position("MSFT") < target_shares:
    if cash() < price("MSFT"):
        log("Out of cash before hitting target.")
        break
    buy("MSFT", 1)
log("Final MSFT position:", position("MSFT"))
```

### Trim a winner

```python
held = position("TSLA")
if held >= 20 and price("TSLA") > 250:
    sell("TSLA", held // 2)
    log("Trimmed half of TSLA above $250.")
```

---

## What you'll see in the console

```
14:02:33 BUY    100 NVDA   @ $478.12   cost $47,812.00   cash left $52,188.00
14:02:33 Bought NVDA at 478.12
14:02:33 — Done in 612 ms · 1 trade · cash $52,188.00 (start $100,000.00) · portfolio $99,892.00 · positions: NVDA=100
```

- `BUY` / `SELL` lines are highlighted in mint green.
- `log(...)` / `print(...)` lines are in plain text.
- Errors (over-budget order, syntax error, safety-limit timeout) appear in red.
- The summary at the bottom shows duration, trade count, cash before & after, mark-to-market portfolio, and ending positions.

---

## Limits & honest notes

- **Paper trading only.** No order is ever sent to a broker. Prices come from Yahoo Finance's daily close, cached per run.
- **No persistence.** Cash, positions, and `price()` cache reset for every Execute click.
- **Sandboxed by AST.** The parser whitelists a small set of node types; anything else is rejected before execution. The injected `_tick()` at every loop iteration is what enforces the 5 s / 50 000-op safety limits even inside `while True:`.
- **One process, one run at a time** in the current implementation — long-running scripts will block the Flask worker for up to 5 seconds.

That's it. Type, execute, read the console, iterate.
