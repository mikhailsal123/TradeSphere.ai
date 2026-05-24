/*  Strategy Studio (standalone page)
 *  -------------------------------------------------------------------------
 *  Provides: write → compile → save → execute, with saved strategies kept in
 *  localStorage under the key STORAGE_KEY (shared with the Trading Dashboard's
 *  "Import Strategy" card so saved scripts can be imported there).
 */
(function () {
    "use strict";

    const loadStrategies = () => TradeSphereStrategies.loadSavedStrategies();
    const persistStrategies = (list) => TradeSphereStrategies.persistStrategies(list);

    function makeId() {
        return "s_" + Date.now().toString(36) + "_" + Math.random().toString(36).slice(2, 8);
    }

    // ── small UI helpers ────────────────────────────────────────────────────
    function escape(s) {
        return String(s).replace(/[&<>"']/g, (c) =>
            ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
        );
    }

    function formatTs(t) {
        if (!t) return "";
        try {
            return new Date(t).toLocaleString();
        } catch (_e) {
            return "";
        }
    }

    // ── refs ───────────────────────────────────────────────────────────────
    let editor; // CodeMirror instance (preferred) — falls back to <textarea> if CM didn't load.
    let editorIsCM = false;
    let textarea; // raw <textarea id="strategyCodeEditor"> (used as initial source + fallback).
    let nameInput;
    let compileStatusEl;
    let output;
    let listEl;
    let countEl;

    let lastCompileOk = false;
    let lastCompiledCode = null;

    // Tiny abstraction over CodeMirror vs. plain textarea so the rest of the
    // file doesn't have to branch every time it reads/writes the buffer.
    function getCode() {
        return editorIsCM ? editor.getValue() : editor.value;
    }
    function setCode(s) {
        if (editorIsCM) editor.setValue(s);
        else editor.value = s;
    }
    function focusEditor() {
        if (editorIsCM) editor.focus();
        else editor.focus();
    }

    // ── snippet expansion + autocomplete ───────────────────────────────────
    // Keyword → expansion. Trailing `|` marks the cursor landing spot after
    // insertion (we strip it and set the cursor there). Indentation lines up
    // with the user's current indent so snippets nest correctly inside `for`/
    // `while` blocks.
    const SNIPPETS = {
        example:
            'if price("NVDA") > 150:\n    buy("NVDA", 100)\n    log("Bought NVDA at", price("NVDA"))\n\nfor i in range(3):\n    if cash() > 1000:\n        buy("AAPL", 5)|',
        ex: 'if price("NVDA") > 150:\n    buy("NVDA", 100)\n    log("Bought NVDA at", price("NVDA"))\n\nfor i in range(3):\n    if cash() > 1000:\n        buy("AAPL", 5)|',
        if: 'if |:\n    ',
        elif: 'elif |:\n    ',
        else: 'else:\n    |',
        for: 'for i in range(|):\n    ',
        while: 'while |:\n    ',
        price: 'price("|")',
        buy: 'buy("|", )',
        sell: 'sell("|", )',
        position: 'position("|")',
        cash: 'cash()|',
        log: 'log(|)',
        print: 'print(|)',
        range: 'range(|)',
    };

    // Completion list (sorted; shown by the hint popup). Subset of allowed
    // identifiers so users see only things that will pass the AST whitelist.
    const COMPLETION_WORDS = [
        "buy", "cash", "elif", "else", "for", "if", "log", "position", "price",
        "print", "range", "sell", "while", "and", "or", "not", "in", "True",
        "False", "None", "break", "continue", "pass", "abs", "len", "max",
        "min", "round", "sum", "int", "float",
    ];

    // Word currently being typed before the cursor (for snippet/completion
    // matching). Returns { word, from, to } so we can replace it cleanly.
    function getWordBeforeCursor() {
        const cursor = editor.getCursor();
        const line = editor.getLine(cursor.line);
        let i = cursor.ch;
        while (i > 0 && /[\w]/.test(line[i - 1])) i--;
        const word = line.slice(i, cursor.ch);
        return {
            word,
            from: { line: cursor.line, ch: i },
            to: cursor,
        };
    }

    // Tab handler — runs in priority order:
    //   1. Editor empty → insert the full example template.
    //   2. Word before cursor matches a snippet keyword exactly → expand it.
    //   3. Word before cursor is a non-empty prefix of completion words →
    //      pop the hint menu so user can pick with arrows + Enter/Tab.
    //   4. Otherwise → indent (default CodeMirror Tab behavior).
    function handleTab(cm) {
        if (!getCode().trim()) {
            insertSnippet("example", { from: cm.getCursor(), to: cm.getCursor() });
            return;
        }

        const { word, from, to } = getWordBeforeCursor();
        if (word && Object.prototype.hasOwnProperty.call(SNIPPETS, word)) {
            insertSnippet(word, { from, to });
            return;
        }

        if (word && COMPLETION_WORDS.some((w) => w.startsWith(word) && w !== word)) {
            cm.showHint({ completeSingle: false, hint: tradesphereHint });
            return;
        }

        // Defer to CodeMirror's default Tab (insertSoftTab / indentMore).
        return window.CodeMirror.Pass;
    }

    // Insert a snippet at `range`, indented to the start of the current line,
    // and place the cursor on the first `|` mark (which we strip).
    function insertSnippet(keyword, range) {
        const template = SNIPPETS[keyword];
        if (!template) return;
        const cursor = editor.getCursor();
        const line = editor.getLine(cursor.line) || "";
        const indentMatch = line.match(/^[ \t]*/);
        const indent = indentMatch ? indentMatch[0] : "";

        // Reindent every line after the first to keep snippet nesting correct.
        const indented = template
            .split("\n")
            .map((row, i) => (i === 0 ? row : indent + row))
            .join("\n");

        const cursorMark = indented.indexOf("|");
        const finalText = cursorMark >= 0 ? indented.replace("|", "") : indented;

        editor.replaceRange(finalText, range.from, range.to);

        if (cursorMark >= 0) {
            // Convert the offset within `finalText` back into a line/ch coord.
            const before = finalText.slice(0, cursorMark);
            const lines = before.split("\n");
            const target = {
                line: range.from.line + lines.length - 1,
                ch:
                    lines.length === 1
                        ? range.from.ch + lines[0].length
                        : lines[lines.length - 1].length,
            };
            editor.setCursor(target);
        }
    }

    // Hint source for the show-hint addon: completes COMPLETION_WORDS that
    // start with whatever's currently being typed (case-sensitive).
    function tradesphereHint(cm) {
        const { word, from, to } = getWordBeforeCursor();
        if (!word) return null;
        const list = COMPLETION_WORDS.filter((w) => w.startsWith(word) && w !== word);
        if (list.length === 0) return null;
        return { list, from, to };
    }

    // ── render saved list ──────────────────────────────────────────────────
    function renderSavedList() {
        const list = loadStrategies();
        countEl.textContent = `${list.length} saved`;

        if (list.length === 0) {
            listEl.innerHTML =
                '<div class="saved-strategies-empty text-dark">' +
                '<i class="fas fa-folder-open"></i>' +
                '<p class="small mb-0 mt-2">No saved strategies yet. Compile, name, and save your first strategy on the left.</p>' +
                "</div>";
            return;
        }

        // Newest first.
        const sorted = list.slice().sort((a, b) => (b.updated_at || 0) - (a.updated_at || 0));

        listEl.innerHTML = sorted
            .map((s) => {
                const compiledBadge = s.compiled
                    ? '<span class="badge bg-success">compiled</span>'
                    : '<span class="badge bg-warning text-dark">uncompiled</span>';
                const preview = (s.code || "").split("\n").slice(0, 3).join("\n");
                return (
                    `<div class="saved-strategy" data-id="${escape(s.id)}">` +
                    `<div class="saved-strategy-head d-flex align-items-center justify-content-between">` +
                    `<div class="saved-strategy-title" title="${escape(s.name)}">${escape(s.name)}</div>` +
                    `<div class="saved-strategy-actions">` +
                    `<button class="btn btn-sm btn-outline-primary" type="button" data-action="load" title="Load into editor"><i class="fas fa-pen"></i></button>` +
                    `<button class="btn btn-sm btn-outline-danger" type="button" data-action="delete" title="Delete saved strategy"><i class="fas fa-trash"></i></button>` +
                    `</div>` +
                    `</div>` +
                    `<div class="saved-strategy-meta">${compiledBadge} <small class="text-dark">Updated ${escape(formatTs(s.updated_at))}</small></div>` +
                    `<pre class="saved-strategy-preview"><code>${escape(preview)}${(s.code || "").split("\n").length > 3 ? "\n…" : ""}</code></pre>` +
                    `</div>`
                );
            })
            .join("");
    }

    function findById(id) {
        return loadStrategies().find((s) => s.id === id) || null;
    }

    function deleteById(id) {
        const list = loadStrategies().filter((s) => s.id !== id);
        persistStrategies(list);
        renderSavedList();
    }

    // ── compile / save / run ───────────────────────────────────────────────
    async function compileCurrent({ silent = false } = {}) {
        const code = getCode();
        if (!code.trim()) {
            setCompileStatus("Editor is empty.", "error");
            lastCompileOk = false;
            lastCompiledCode = null;
            return false;
        }

        if (!silent) setCompileStatus("Compiling…", "info");
        try {
            const res = await fetch("/compile_strategy", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ code }),
            });
            const data = await res.json().catch(() => ({ ok: false, error: "Server returned non-JSON." }));
            if (data.ok) {
                lastCompileOk = true;
                lastCompiledCode = code;
                setCompileStatus("Compile passed ✓", "ok");
                return true;
            }
            lastCompileOk = false;
            lastCompiledCode = null;
            const where = data.line ? ` (line ${data.line})` : "";
            setCompileStatus(`Compile failed${where}: ${data.error || "Unknown error."}`, "error");
            return false;
        } catch (err) {
            lastCompileOk = false;
            lastCompiledCode = null;
            setCompileStatus(`Compile network error: ${err.message}`, "error");
            return false;
        }
    }

    function setCompileStatus(msg, level) {
        compileStatusEl.textContent = msg;
        compileStatusEl.classList.remove("status-ok", "status-error", "status-info");
        if (level === "ok") compileStatusEl.classList.add("status-ok");
        else if (level === "error") compileStatusEl.classList.add("status-error");
        else if (level === "info") compileStatusEl.classList.add("status-info");
    }

    async function saveCurrent() {
        const name = (nameInput.value || "").trim();
        if (!name) {
            setCompileStatus("Give the strategy a name before saving.", "error");
            nameInput.focus();
            return;
        }
        const code = getCode();
        if (!code.trim()) {
            setCompileStatus("Editor is empty.", "error");
            return;
        }

        // Auto-compile if the user changed code since last compile (or never compiled).
        const needsRecompile = !lastCompileOk || lastCompiledCode !== code;
        if (needsRecompile) {
            const ok = await compileCurrent({ silent: false });
            if (!ok) return;
        }

        const list = loadStrategies();
        // If a strategy with this name exists, update it; otherwise insert.
        const now = Date.now();
        const idx = list.findIndex((s) => s.name === name);
        if (idx >= 0) {
            list[idx] = Object.assign({}, list[idx], {
                code,
                compiled: true,
                updated_at: now,
            });
        } else {
            list.push({
                id: makeId(),
                name,
                code,
                compiled: true,
                created_at: now,
                updated_at: now,
            });
        }
        persistStrategies(list);
        renderSavedList();
        setCompileStatus(`Saved “${name}” ✓`, "ok");
    }

    async function runCurrent() {
        const code = getCode();
        if (!code.trim()) {
            renderOutput([{ level: "error", msg: "Editor is empty." }], null);
            return;
        }
        const runBtn = document.getElementById("strategyRunBtn");
        const originalLabel = runBtn.innerHTML;
        runBtn.disabled = true;
        runBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Running…';

        try {
            const initialCash = 100000; // Studio runs always seed from a fixed $100k sandbox.
            const res = await fetch("/run_strategy", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ code, initial_cash: initialCash }),
            });
            const data = await res.json().catch(() => ({ ok: false, error: "Server returned non-JSON." }));
            if (!data.ok) {
                renderOutput([{ level: "error", msg: data.error || "Unknown server error." }], null);
            } else {
                renderOutput(data.log || [], data);
            }
        } catch (err) {
            renderOutput([{ level: "error", msg: "Network error: " + err.message }], null);
        } finally {
            runBtn.disabled = false;
            runBtn.innerHTML = originalLabel;
        }
    }

    function renderOutput(entries, fullData) {
        const ts = new Date().toLocaleTimeString([], { hour12: false });
        let body = "";
        if (!entries || entries.length === 0) {
            body = `<div class="log-log"><span class="log-ts">${ts}</span> (no output)</div>`;
        } else {
            body = entries
                .map((entry) => {
                    const level = (entry && entry.level) || "log";
                    return `<div class="log-${escape(level)}"><span class="log-ts">${ts}</span> ${escape(entry.msg || "")}</div>`;
                })
                .join("");
        }

        let summary = "";
        if (fullData && fullData.ok) {
            const positions = Object.entries(fullData.positions || {}).filter(([, qty]) => qty > 0);
            const posStr = positions.length ? positions.map(([t, q]) => `${t}=${q}`).join(", ") : "none";
            const fmt = (n) =>
                (Number(n) || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
            const trades = (fullData.trades || []).length;
            summary =
                `<div class="log-summary">` +
                `— Done in ${fullData.duration_ms || 0} ms · ` +
                `${trades} trade${trades === 1 ? "" : "s"} · ` +
                `cash $${fmt(fullData.final_cash)} (start $${fmt(fullData.starting_cash)}) · ` +
                `portfolio $${fmt(fullData.portfolio_value)} · ` +
                `positions: ${escape(posStr)}` +
                `</div>`;
        }

        output.innerHTML = body + summary;
        output.classList.add("is-active");
        output.scrollTop = output.scrollHeight;
    }

    function loadStrategyIntoEditor(id) {
        const s = findById(id);
        if (!s) return;
        setCode(s.code || "");
        nameInput.value = s.name || "";
        lastCompileOk = !!s.compiled;
        lastCompiledCode = lastCompileOk ? getCode() : null;
        setCompileStatus(
            s.compiled ? `Loaded “${s.name}” (compiled).` : `Loaded “${s.name}”. Compile to verify.`,
            s.compiled ? "ok" : "info"
        );
        focusEditor();
    }

    // CodeMirror theme follows TradeSphere's data-theme attribute on <html>.
    function pickCmTheme() {
        return document.documentElement.getAttribute("data-theme") === "dark"
            ? "material-darker"
            : "default";
    }

    // ── boot ───────────────────────────────────────────────────────────────
    document.addEventListener("DOMContentLoaded", () => {
        textarea = document.getElementById("strategyCodeEditor");
        nameInput = document.getElementById("strategyName");
        compileStatusEl = document.getElementById("strategyCompileStatus");
        output = document.getElementById("strategyOutput");
        listEl = document.getElementById("savedStrategiesList");
        countEl = document.getElementById("savedStrategiesCount");

        if (typeof window.CodeMirror === "function") {
            editor = window.CodeMirror.fromTextArea(textarea, {
                mode: "python",
                theme: pickCmTheme(),
                lineNumbers: true,
                indentUnit: 4,
                tabSize: 4,
                indentWithTabs: false,
                smartIndent: true,
                lineWrapping: false,
                autoCloseBrackets: true,
                matchBrackets: true,
                viewportMargin: Infinity,
                extraKeys: {
                    Tab: handleTab,
                    "Ctrl-Space": (cm) =>
                        cm.showHint({ completeSingle: false, hint: tradesphereHint }),
                    "Cmd-Enter": runCurrent,
                    "Ctrl-Enter": runCurrent,
                },
            });
            editor.setSize(null, 360);
            editorIsCM = true;

            // Live cancellation of the previous compile result once the user
            // edits the buffer (matches the textarea fallback below).
            editor.on("change", () => {
                if (lastCompiledCode !== null && lastCompiledCode !== getCode()) {
                    lastCompileOk = false;
                    setCompileStatus("Edited — recompile before saving.", "info");
                }
            });

            // Re-theme the editor when light/dark toggles at runtime.
            new MutationObserver(() => editor.setOption("theme", pickCmTheme())).observe(
                document.documentElement,
                { attributes: true, attributeFilter: ["data-theme"] }
            );
        } else {
            // CodeMirror failed to load (offline / CDN blocked) — fall back to
            // the plain textarea with the original Tab-indents-4-spaces and
            // Ctrl/Cmd+Enter behavior so the page is still usable.
            editor = textarea;
            editorIsCM = false;
            editor.addEventListener("keydown", (e) => {
                if (e.key === "Tab") {
                    e.preventDefault();
                    const { selectionStart: s, selectionEnd: t, value: v } = editor;
                    editor.value = v.slice(0, s) + "    " + v.slice(t);
                    editor.selectionStart = editor.selectionEnd = s + 4;
                } else if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
                    e.preventDefault();
                    runCurrent();
                }
            });
            editor.addEventListener("input", () => {
                if (lastCompiledCode !== null && lastCompiledCode !== getCode()) {
                    lastCompileOk = false;
                    setCompileStatus("Edited — recompile before saving.", "info");
                }
            });
        }

        document.getElementById("strategyRunBtn").addEventListener("click", runCurrent);
        document.getElementById("strategyCompileBtn").addEventListener("click", () => compileCurrent());
        document.getElementById("strategySaveBtn").addEventListener("click", saveCurrent);
        document.getElementById("strategyClearBtn").addEventListener("click", () => {
            output.innerHTML = "";
            output.classList.remove("is-active");
        });

        // Saved-list delegation (load + delete buttons).
        listEl.addEventListener("click", (e) => {
            const btn = e.target.closest("button[data-action]");
            if (!btn) return;
            const card = btn.closest(".saved-strategy");
            if (!card) return;
            const id = card.dataset.id;
            const action = btn.dataset.action;
            if (action === "load") {
                loadStrategyIntoEditor(id);
            } else if (action === "delete") {
                const s = findById(id);
                if (!s) return;
                if (confirm(`Delete saved strategy “${s.name}”?`)) {
                    deleteById(id);
                }
            }
        });

        renderSavedList();
    });
})();
