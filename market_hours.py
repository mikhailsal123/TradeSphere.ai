"""
US cash equity (NYSE) schedule for blocking fills outside regular sessions.

- Simulation: daily bars → trades only on NYSE *session* calendar days.
  Intraday bars → trades only when XNYS is open on that minute (9:30–16:00 ET).
- Live / Strategy Studio Execute: trades only during regular session minutes.

Depends on ``exchange-calendars`` (XNYS). If import fails, weekend + rough RTH are
applied but exchange holidays may be missed (see logs).
"""

from __future__ import annotations

import logging
from datetime import datetime, time, timedelta
from typing import Union

import pandas as pd

_log = logging.getLogger(__name__)

_XNYS = None
_CALENDAR_LOADED = False


def _load_calendar():
    global _XNYS, _CALENDAR_LOADED
    if _CALENDAR_LOADED:
        return
    _CALENDAR_LOADED = True
    try:
        import exchange_calendars as xcals

        _XNYS = xcals.get_calendar('XNYS')
    except Exception as e:
        _log.warning(
            'exchange-calendars unavailable (%s); using weekday-only fallback '
            '(NYSE holidays may be treated as open). Install exchange-calendars.',
            e,
        )
        _XNYS = False


_load_calendar()


def _to_ny(ts: Union[datetime, pd.Timestamp]) -> pd.Timestamp:
    """Naive datetimes are treated as **already in NY wall-clock time**.

    ``ambiguous='infer'`` only works on a DatetimeIndex, not on a scalar — using
    it here previously raised, fell through to ``tz_localize('UTC')``, and
    silently shifted everything by 4–5 hours. Use ``ambiguous=False`` (treat
    DST repeats as winter) + ``nonexistent='shift_forward'`` (DST spring
    forward) so naive timestamps stay where the simulator intended them.
    """
    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        try:
            return t.tz_localize(
                'America/New_York',
                ambiguous=False,
                nonexistent='shift_forward',
            )
        except (TypeError, ValueError):
            return t.tz_localize('UTC').tz_convert('America/New_York')
    return t.tz_convert('America/New_York')


def equity_sim_trade_execution_allowed(ts: Union[datetime, pd.Timestamp], yf_interval: str) -> bool:
    """Return True if a simulated fill is allowed at ``ts``.

    ``yf_interval`` matches Portfolio / Yahoo (``'1d'`` vs minute/hour bars).
    """
    daily = str(yf_interval or '1d').lower() == '1d'
    if _XNYS:
        ts_ny = _to_ny(ts)
        if daily:
            return bool(_XNYS.is_session(pd.Timestamp(ts_ny.date())))
        return bool(_XNYS.is_open_on_minute(ts_ny))

    # Fallback without exchange_calendars
    ts_ny = _to_ny(ts)
    if ts_ny.weekday() >= 5:
        return False
    if daily:
        return True
    minutes = ts_ny.hour * 60 + ts_ny.minute
    return (9 * 60 + 30) <= minutes < (16 * 60)


def equity_live_rth_execution_allowed(when: Union[datetime, pd.Timestamp, None] = None) -> bool:
    """Wall-clock: allow orders only during NYSE regular session minutes."""
    ts_ny = pd.Timestamp.now(tz='America/New_York') if when is None else _to_ny(when)
    if _XNYS:
        return bool(_XNYS.is_open_on_minute(ts_ny))
    if ts_ny.weekday() >= 5:
        return False
    tod = ts_ny.time()
    return time(9, 30) <= tod < time(16, 0)


def next_session_time(ts: Union[datetime, pd.Timestamp], yf_interval: str) -> pd.Timestamp:
    """Advance ``ts`` forward to the next valid trading bar.

    - Daily interval → next NYSE session date at midnight (naive of clock).
    - Intraday interval → next session-minute (9:30 ET open if currently
      outside RTH, or current minute if already open).

    Returned timestamp is *tz-naive in America/New_York wall clock* so it slots
    straight into the simulator's existing naive-datetime arithmetic.
    """
    daily = str(yf_interval or '1d').lower() == '1d'
    ts_ny = _to_ny(ts)

    if _XNYS:
        if daily:
            d = pd.Timestamp(ts_ny.date())
            if _XNYS.is_session(d):
                return pd.Timestamp(d)
            try:
                nxt = _XNYS.date_to_session(d, direction='next')
            except Exception:
                nxt = d
                for _ in range(14):
                    nxt = nxt + pd.Timedelta(days=1)
                    if _XNYS.is_session(nxt):
                        break
            return pd.Timestamp(pd.Timestamp(nxt).date())
        # Intraday: snap to the next open minute on or after ts_ny.
        if _XNYS.is_open_on_minute(ts_ny):
            return ts_ny.tz_localize(None)
        try:
            nxt = _XNYS.next_minute(ts_ny)
        except Exception:
            nxt = None
        if nxt is None:
            return ts_ny.tz_localize(None)
        nxt = pd.Timestamp(nxt)
        if nxt.tzinfo is None:
            nxt = nxt.tz_localize('UTC')
        return nxt.tz_convert('America/New_York').tz_localize(None)

    # Fallback path (no exchange_calendars): weekday + 9:30–16:00 ET only.
    cur = ts_ny
    safety = 14 * 24 * 60  # at most ~two weeks of minute steps
    if daily:
        while cur.weekday() >= 5 and safety > 0:
            cur = cur + pd.Timedelta(days=1)
            safety -= 1
        return pd.Timestamp(cur.date())
    while safety > 0:
        if cur.weekday() < 5:
            tod = cur.time()
            if tod < time(9, 30):
                cur = cur.replace(hour=9, minute=30, second=0, microsecond=0)
                return cur.tz_localize(None)
            if time(9, 30) <= tod < time(16, 0):
                return cur.tz_localize(None)
            # After close → next day's open
            nxt = (cur + pd.Timedelta(days=1)).replace(hour=9, minute=30, second=0, microsecond=0)
            cur = nxt
            continue
        # Weekend → advance to Monday open
        cur = (cur + pd.Timedelta(days=1)).replace(hour=9, minute=30, second=0, microsecond=0)
        safety -= 1
    return cur.tz_localize(None)
