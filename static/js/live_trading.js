/* eslint-disable no-undef */
/*
 *  TradeSphere — Live Trading runner
 *  ──────────────────────────────────
 *  • Pulls the same saved-strategy list out of localStorage that the Studio
 *    and the Dashboard's Imported pane use (key: tradesphere_strategies_v1).
 *  • POSTs the selected strategy + starting cash to /start_live_trading.
 *  • Polls /live_status/<id> every second to stream new trade lines into
 *    the log pane and update the cash / portfolio / positions strip.
 *  • Persists the run_id in sessionStorage so navigating away and coming
 *    back to /live_trading resumes the live view (the backend keeps the
 *    run alive in a daemon thread).
 *  • Only successful trades land in the log — errors, "not enough cash",
 *    and conditions that didn't trigger are silently swallowed server-side.
 */
(function () {
    "use strict";

    const STORAGE_KEY = "tradesphere_strategies_v1";
    const RUN_ID_KEY = "tradesphere_live_run_id";
    const POLL_INTERVAL_MS = 1000;
    const TOTAL_SECONDS = 300;

    // ── DOM ──────────────────────────────────────────────────────────────
    const $ = (id) => document.getElementById(id);

    const els = {
        select: $("liveStrategySelect"),
        preview: $("liveStrategyPreview"),
        savedCount: $("liveSavedCount"),
        initialCash: $("liveInitialCash"),
        startBtn: $("liveStartBtn"),
        stopBtn: $("liveStopBtn"),
        clearBtn: $("liveClearBtn"),
        progressBar: $("liveProgressBar"),
        progressLabel: $("liveProgressLabel"),
        tradesLabel: $("liveTradesLabel"),
        statusLine: $("liveStatusLine"),
        cash: $("liveCash"),
        portfolio: $("livePortfolioValue"),
        pnl: $("livePnl"),
        positions: $("livePositions"),
        output: $("liveOutput"),
        hint: $("liveHint"),
    };

    let pollTimer = null;
    let currentRunId = null;
    let logCursor = 0;
    let startingCash = 100000;

    // ── localStorage helpers ─────────────────────────────────────────────
    function loadSaved() {
        try {
            const raw = localStorage.getItem(STORAGE_KEY);
            const list = raw ? JSON.parse(raw) : [];
            return Array.isArray(list) ? list : [];
        } catch (_e) {
            return [];
        }
    }

    function readInitialCash() {
        const raw = (els.initialCash?.value || "").replace(/[^0-9.]/g, "");
        const v = parseFloat(raw);
        return Number.isFinite(v) && v > 0 ? v : 100000;
    }

    function formatInitialCash() {
        if (!els.initialCash) return;
        const v = readInitialCash();
        els.initialCash.value = v.toLocaleString(undefined, {
            maximumFractionDigits: 0,
        });
    }

    function fmtMoney(v) {
        const n = Number(v);
        if (!Number.isFinite(n)) return "$0.00";
        const sign = n < 0 ? "-" : "";
        return (
            sign +
            "$" +
            Math.abs(n).toLocaleString(undefined, {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2,
            })
        );
    }

    function fmtClock(secElapsed) {
        const s = Math.max(0, Math.min(TOTAL_SECONDS, Math.round(secElapsed)));
        const mm = Math.floor(s / 60);
        const ss = s % 60;
        const tMM = Math.floor(TOTAL_SECONDS / 60);
        const tSS = TOTAL_SECONDS % 60;
        return (
            `${mm}:${String(ss).padStart(2, "0")} / ` +
            `${tMM}:${String(tSS).padStart(2, "0")}`
        );
    }

    function escapeHtml(s) {
        return String(s).replace(/[&<>"']/g, (c) =>
            ({
                "&": "&amp;",
                "<": "&lt;",
                ">": "&gt;",
                '"': "&quot;",
                "'": "&#39;",
            }[c]),
        );
    }

    // ── Saved-strategies picker ──────────────────────────────────────────
    function showPreview() {
        const id = els.select.value;
        const s = loadSaved().find((x) => x.id === id);
        if (!s) {
            els.preview.value = "";
            els.startBtn.disabled = true;
            return;
        }
        els.preview.value = s.code || "";
        els.startBtn.disabled = !!currentRunId; // only enabled when no run is live
    }

    function refreshSaved() {
        const list = loadSaved()
            .slice()
            .sort((a, b) => (b.updated_at || 0) - (a.updated_at || 0));
        els.savedCount.textContent = `${list.length} saved`;
        if (list.length === 0) {
            els.select.innerHTML =
                '<option value="">— No saved strategies —</option>';
            els.preview.value = "";
            els.startBtn.disabled = true;
            return;
        }
        const prev = els.select.value;
        els.select.innerHTML = list
            .map(
                (s) =>
                    `<option value="${escapeHtml(s.id)}">${escapeHtml(
                        s.name,
                    )}${s.compiled ? "" : " (uncompiled)"}</option>`,
            )
            .join("");
        const keep = list.find((s) => s.id === prev);
        els.select.value = keep ? prev : list[0].id;
        showPreview();
    }

    // ── Polling + rendering ──────────────────────────────────────────────
    function appendLogEntries(entries) {
        if (!entries || entries.length === 0) return;
        const html = entries
            .map((e) => {
                const ts = escapeHtml(e.ts || "");
                const level = escapeHtml(e.level || "trade");
                const msg = escapeHtml(e.msg || "");
                return `<div class="log-${level}"><span class="log-ts">${ts}</span> ${msg}</div>`;
            })
            .join("");
        els.output.insertAdjacentHTML("beforeend", html);
        els.output.classList.add("is-active");
        els.output.scrollTop = els.output.scrollHeight;
    }

    function updateStrip(s) {
        els.cash.textContent = fmtMoney(s.cash);
        els.portfolio.textContent = fmtMoney(s.portfolio_value);
        const pnl = (s.portfolio_value || 0) - (s.starting_cash || 0);
        els.pnl.textContent =
            (pnl >= 0 ? "+" : "−") +
            fmtMoney(Math.abs(pnl)).replace(/^[-+]/, "");
        els.pnl.classList.toggle("text-success", pnl >= 0);
        els.pnl.classList.toggle("text-danger", pnl < 0);
        const positions = Object.entries(s.positions || {});
        els.positions.textContent = positions.length
            ? positions.map(([t, q]) => `${t}=${q}`).join(", ")
            : "—";
    }

    function updateProgress(s) {
        const ticks = Math.max(0, Math.min(TOTAL_SECONDS, s.tick_count || 0));
        const pct = (ticks / TOTAL_SECONDS) * 100;
        els.progressBar.style.width = `${pct}%`;
        els.progressBar.setAttribute("aria-valuenow", String(ticks));
        els.progressLabel.textContent = fmtClock(ticks);
        els.tradesLabel.textContent = `${s.trade_count || 0} trade${
            s.trade_count === 1 ? "" : "s"
        }`;
        if (s.is_complete) {
            els.statusLine.textContent = s.error
                ? `Stopped — ${s.error}`
                : "Complete";
        } else if (s.is_running) {
            els.statusLine.textContent = `Running · ${fmtClock(ticks)}`;
        } else {
            els.statusLine.textContent = "Idle";
        }
    }

    async function pollOnce() {
        if (!currentRunId) return;
        try {
            const res = await fetch(
                `/live_status/${encodeURIComponent(currentRunId)}?since=${logCursor}`,
            );
            if (res.status === 404) {
                // Run id is gone (server restart). Reset.
                stopPolling();
                clearActiveRun();
                els.statusLine.textContent = "Run not found";
                return;
            }
            const data = await res.json();
            if (!data || !data.ok) return;
            if (Array.isArray(data.log) && data.log.length) {
                appendLogEntries(data.log);
                logCursor = data.log_total;
            } else if (typeof data.log_total === "number") {
                logCursor = data.log_total;
            }
            updateStrip(data);
            updateProgress(data);
            if (data.is_complete) {
                stopPolling();
                clearActiveRun();
                els.startBtn.disabled = !els.select.value;
                els.stopBtn.disabled = true;
            }
        } catch (_e) {
            // transient network blip; try again next tick
        }
    }

    function startPolling() {
        if (pollTimer) return;
        pollOnce();
        pollTimer = setInterval(pollOnce, POLL_INTERVAL_MS);
    }

    function stopPolling() {
        if (pollTimer) {
            clearInterval(pollTimer);
            pollTimer = null;
        }
    }

    function rememberActiveRun(runId) {
        currentRunId = runId;
        try {
            sessionStorage.setItem(RUN_ID_KEY, runId);
        } catch (_e) { /* ignore */ }
    }

    function clearActiveRun() {
        currentRunId = null;
        try {
            sessionStorage.removeItem(RUN_ID_KEY);
        } catch (_e) { /* ignore */ }
    }

    // ── Start / Stop / Clear handlers ────────────────────────────────────
    async function onStart() {
        const id = els.select.value;
        const s = loadSaved().find((x) => x.id === id);
        if (!s) return;

        formatInitialCash();
        startingCash = readInitialCash();

        els.startBtn.disabled = true;
        els.stopBtn.disabled = false;
        els.statusLine.textContent = "Starting…";
        els.output.innerHTML = "";
        logCursor = 0;
        // Seed the strip with the starting state so the user sees something
        // before the first poll lands.
        updateStrip({
            cash: startingCash,
            portfolio_value: startingCash,
            starting_cash: startingCash,
            positions: {},
        });
        updateProgress({ tick_count: 0, trade_count: 0, is_running: true });

        try {
            const res = await fetch("/start_live_trading", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    code: s.code,
                    initial_cash: startingCash,
                }),
            });
            const data = await res.json();
            if (!data.ok) {
                els.statusLine.textContent = `Error — ${data.error || "could not start"}`;
                appendLogEntries([
                    { ts: nowTs(), level: "error", msg: data.error || "Could not start run." },
                ]);
                els.startBtn.disabled = !els.select.value;
                els.stopBtn.disabled = true;
                return;
            }
            rememberActiveRun(data.run_id);
            startPolling();
        } catch (err) {
            els.statusLine.textContent = `Error — ${err.message}`;
            els.startBtn.disabled = !els.select.value;
            els.stopBtn.disabled = true;
        }
    }

    async function onStop() {
        if (!currentRunId) return;
        els.stopBtn.disabled = true;
        try {
            await fetch(
                `/stop_live_trading/${encodeURIComponent(currentRunId)}`,
                { method: "POST" },
            );
        } catch (_e) { /* ignore */ }
        // The next poll tick will see is_complete=true and clean up. We
        // already pre-disabled Stop so the user can't double-fire.
    }

    function onClear() {
        els.output.innerHTML = "";
        els.output.classList.remove("is-active");
    }

    function nowTs() {
        const d = new Date();
        return (
            String(d.getHours()).padStart(2, "0") +
            ":" +
            String(d.getMinutes()).padStart(2, "0") +
            ":" +
            String(d.getSeconds()).padStart(2, "0")
        );
    }

    // ── Resume an in-flight run on revisit ───────────────────────────────
    async function maybeResume() {
        let runId = null;
        try {
            runId = sessionStorage.getItem(RUN_ID_KEY);
        } catch (_e) { /* ignore */ }
        if (!runId) return;
        // Verify the run still exists server-side; if not, clear stale id.
        try {
            const res = await fetch(
                `/live_status/${encodeURIComponent(runId)}?since=0`,
            );
            if (res.status === 404) {
                clearActiveRun();
                return;
            }
            const data = await res.json();
            if (!data || !data.ok) {
                clearActiveRun();
                return;
            }
            if (data.is_complete) {
                // Show the final state once, then clear so a new run can start.
                rememberActiveRun(runId);
                if (Array.isArray(data.log) && data.log.length) {
                    appendLogEntries(data.log);
                    logCursor = data.log_total;
                }
                updateStrip(data);
                updateProgress(data);
                clearActiveRun();
                els.startBtn.disabled = !els.select.value;
                els.stopBtn.disabled = true;
                return;
            }
            // It's still running — re-attach.
            rememberActiveRun(runId);
            if (Array.isArray(data.log) && data.log.length) {
                appendLogEntries(data.log);
                logCursor = data.log_total;
            }
            updateStrip(data);
            updateProgress(data);
            els.startBtn.disabled = true;
            els.stopBtn.disabled = false;
            startPolling();
        } catch (_e) {
            clearActiveRun();
        }
    }

    // ── Wire up ──────────────────────────────────────────────────────────
    document.addEventListener("DOMContentLoaded", () => {
        if (!els.select || !els.startBtn) return;
        els.select.addEventListener("change", showPreview);
        els.startBtn.addEventListener("click", onStart);
        els.stopBtn.addEventListener("click", onStop);
        els.clearBtn.addEventListener("click", onClear);
        els.initialCash?.addEventListener("blur", formatInitialCash);

        window.addEventListener("focus", refreshSaved);
        window.addEventListener("storage", (e) => {
            if (e.key === STORAGE_KEY) refreshSaved();
        });

        refreshSaved();
        maybeResume();
    });

    // Stop the polling timer when the page is hidden (e.g. iframe unmount)
    // BUT keep the server-side run going so coming back resumes the view.
    window.addEventListener("pagehide", stopPolling);
})();
