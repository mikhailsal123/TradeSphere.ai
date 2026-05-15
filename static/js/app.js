let currentSimulationId = null;
let statusInterval = null;
let aiChatVisible = false;

function teebyChatAvatarHtml(small) {
    const src =
        typeof window.TEEBY_AVATAR_URL === 'string' && window.TEEBY_AVATAR_URL
            ? window.TEEBY_AVATAR_URL
            : '/static/media/teeby-avatar.png';
    const wrapCls = 'teeby-chat-avatar-wrap' + (small ? ' teeby-chat-avatar-wrap--sm' : '');
    const dim = small ? 62 : 84;
    return (
        '<span class="' +
        wrapCls +
        '" aria-hidden="true">' +
        '<img class="teeby-chat-img" src="' +
        src +
        '" alt="Teeby" width="' +
        dim +
        '" height="' +
        dim +
        '" loading="lazy" decoding="async">' +
        '</span>'
    );
}

(function () {
    function updateTsThemeToggleGlyph() {
        var btn = document.getElementById('tsThemeToggle');
        if (!btn) return;
        var dark = document.documentElement.getAttribute('data-theme') === 'dark';
        btn.innerHTML = dark
            ? '<i class="fas fa-sun" aria-hidden="true"></i>'
            : '<i class="fas fa-moon" aria-hidden="true"></i>';
    }

    function applyTradeSphereTheme(t) {
        if (t !== 'light' && t !== 'dark') return;
        document.documentElement.setAttribute('data-theme', t);
        try {
            localStorage.setItem('tradesphere-theme', t);
        } catch (e) { /* ignore */ }
        updateTsThemeToggleGlyph();
    }

    window.addEventListener('message', function (e) {
        var d = e.data;
        if (d && d.type === 'tradesphere-theme' && (d.theme === 'light' || d.theme === 'dark')) {
            applyTradeSphereTheme(d.theme);
        }
    });

    var params = new URLSearchParams(window.location.search);
    var urlT = params.get('theme');
    if (urlT === 'light' || urlT === 'dark') {
        applyTradeSphereTheme(urlT);
    } else {
        try {
            var s = localStorage.getItem('tradesphere-theme');
            if (s === 'light' || s === 'dark') applyTradeSphereTheme(s);
        } catch (err) { /* ignore */ }
    }

    document.addEventListener('DOMContentLoaded', function () {
        var tsThemeToggle = document.getElementById('tsThemeToggle');
        if (tsThemeToggle) {
            updateTsThemeToggleGlyph();
            tsThemeToggle.addEventListener('click', function () {
                var next = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
                applyTradeSphereTheme(next);
            });
        }
    });
})();

// Initialize the application
document.addEventListener('DOMContentLoaded', function() {
    console.log('DOMContentLoaded - Initializing app...');

    // Duration slider update — refresh the "Last X hours/days of trading"
    // summary + min/max captions on every slider tick.
    const durationSlider = document.getElementById('durationDays');
    if (durationSlider) {
        durationSlider.addEventListener('input', updateDurationLimits);
    }
    
    // Form submission
    const simulationForm = document.getElementById('simulationForm');
    if (simulationForm) {
        simulationForm.addEventListener('submit', startSimulation);
    }
    
    // Stop button
    document.getElementById('stopBtn').addEventListener('click', stopSimulation);
    
    // Initialize tooltips
    var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
    
    // Initialize AI chat functionality
    initializeAIChat();
    
    // Set initial welcome time
    const welcomeTime = document.getElementById('aiWelcomeTime');
    if (welcomeTime) {
        welcomeTime.textContent = new Date().toLocaleTimeString();
    }
    
    // currentSimulationId will be set when a simulation starts
    
    // Initialize duration limits
    updateDurationLimits();
    
    // Add real-time portfolio validation
    initializePortfolioValidation();
    
    // Plot type buttons
    document.querySelectorAll('[data-plot-type]').forEach(btn => {
        btn.addEventListener('click', function() {
            const plotType = this.getAttribute('data-plot-type');
            loadPlot(plotType);
        });
    });
    
    // Show AI advisor immediately for testing
    setTimeout(() => {
        showAIAdvisor();
    }, 500);

    document.querySelectorAll('#tickersContainer input[type="text"]').forEach((input) => {
        if (input.value.trim()) {
            validateTicker(input);
        }
    });
    document.querySelectorAll('#tradingRulesContainer .ticker-select').forEach((sel) => {
        if (sel.value.trim()) {
            validateTradingRuleTicker(sel);
        }
    });

    // 3D roulette tilt for the Stock Positions list — must run after the rows
    // exist in the DOM and after layout has settled so getBoundingClientRect()
    // returns real numbers.
    initTickerRoulette();

    // Show the correct starting hedge margin (50% of Initial Cash) from page load,
    // and keep it in sync if the user edits the Initial Cash input. Once a sim
    // is running, updateHedgeMarginBalance(data) overwrites this with live values.
    initInitialMarginDisplay();

    // Import Strategy (pick a saved Studio strategy + Run → /run_strategy → console output).
    initImportStrategy();

    // Strategy card segmented switch (Manual ⇄ Imported).
    initStrategyModeSwitch();

    // Floating Teeby live-chat widget (launcher → slide-in chat panel).
    initTeebyWidget();
});

/* =========================================================================
   Initial cash helpers (live comma formatting + numeric reader)
   -------------------------------------------------------------------------
   The Initial Cash Deposit input is now <input type="text"> with a "$"
   prefix and comma-grouped digits (e.g. "110,000"). readInitialCash()
   strips commas before parseFloat so every existing reader keeps working,
   and formatInitialCash() rewrites the field as the user types while doing
   its best to preserve the cursor position relative to the digits.
   ========================================================================= */
function readInitialCash() {
    const el = document.getElementById('initialCash');
    if (!el) return NaN;
    return parseFloat(String(el.value || '').replace(/,/g, ''));
}

function formatInitialCash() {
    const input = document.getElementById('initialCash');
    if (!input) return;
    const raw = String(input.value || '');
    const digitsOnly = raw.replace(/[^\d]/g, '');
    if (!digitsOnly) {
        input.value = '';
        return;
    }

    // Count digits to the LEFT of the caret so we can restore it after
    // re-formatting (insertions of commas would otherwise shift it).
    const caret = input.selectionStart ?? raw.length;
    const digitsLeftOfCaret = raw.slice(0, caret).replace(/[^\d]/g, '').length;

    const num = parseInt(digitsOnly, 10);
    const formatted = num.toLocaleString('en-US');
    input.value = formatted;

    // Walk the formatted string from the start, counting digits, and place
    // the caret right after the same Nth digit we had before.
    let pos = 0;
    let seen = 0;
    while (pos < formatted.length && seen < digitsLeftOfCaret) {
        if (/\d/.test(formatted[pos])) seen++;
        pos++;
    }
    try { input.setSelectionRange(pos, pos); } catch (_e) { /* ignore */ }
}

/* =========================================================================
   Initial hedge margin display
   -------------------------------------------------------------------------
   Mirrors Portfolio.py: `hedge_margin_available = cash * 0.5`. The HTML
   shipped with $0.00 hardcoded; this keeps the displayed value matching
   the formula the backend will actually use when the sim starts.
   ========================================================================= */
function updateInitialMarginDisplay() {
    const cashInput = document.getElementById('initialCash');
    const hedgeMarginElement = document.getElementById('hedgeMarginBalance');
    if (!cashInput || !hedgeMarginElement) return;

    const cash = readInitialCash();
    if (!Number.isFinite(cash) || cash < 0) return;

    const margin = cash * 0.5;
    const formatted = margin.toLocaleString('en-US', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
    });

    const valueSpan = hedgeMarginElement.querySelector('span:last-of-type');
    if (valueSpan) {
        valueSpan.textContent = `$${formatted}`;
    }
}

function initInitialMarginDisplay() {
    const cashInput = document.getElementById('initialCash');
    if (!cashInput) return;
    // Format whatever was in there on page load + on every keystroke.
    formatInitialCash();
    cashInput.addEventListener('input', () => {
        formatInitialCash();
        updateInitialMarginDisplay();
    });
    updateInitialMarginDisplay();
}

/* =========================================================================
   Stock Positions roulette tilt
   -------------------------------------------------------------------------
   On every scroll of #tickersContainer (Stock Positions) we measure each .ticker-input's
   distance from the container's vertical center and apply a 3D transform
   (rotateX + translateZ + scale) plus opacity falloff. The container's CSS
   perspective + mask edges give the slot-wheel feel; this script supplies
   the per-row motion.
   ========================================================================= */
function applyTickerRouletteEffect() {
    const container = document.getElementById('tickersContainer');
    if (!container) return;
    const items = container.querySelectorAll('.ticker-input');
    if (!items.length) return;

    const cRect = container.getBoundingClientRect();
    const cCenter = cRect.top + cRect.height / 2;
    const half = cRect.height / 2;
    if (half <= 0) return; // container not laid out yet

    items.forEach((item) => {
        const r = item.getBoundingClientRect();
        const itemCenter = r.top + r.height / 2;
        const offset = itemCenter - cCenter; // - above center, + below
        const t = Math.min(1, Math.abs(offset) / half); // 0 at center → 1 at edge

        // Above center → tilt toward viewer (positive rotateX);
        // below center → tilt away (negative rotateX).
        const rotateX = -(offset / half) * 30;
        const scale = 1 - t * 0.22;
        const opacity = 1 - t * 0.55;
        const translateZ = -t * 55;

        item.style.transform =
            `perspective(800px) rotateX(${rotateX}deg) translateZ(${translateZ}px) scale(${scale})`;
        item.style.opacity = String(Math.max(0.4, opacity));
    });
}

function initTickerRoulette() {
    const container = document.getElementById('tickersContainer');
    if (!container) return;

    let queued = false;
    const schedule = () => {
        if (queued) return;
        queued = true;
        requestAnimationFrame(() => {
            queued = false;
            applyTickerRouletteEffect();
        });
    };

    // Initial apply (also re-applies after fonts/images shift layout).
    schedule();
    setTimeout(schedule, 100);

    container.addEventListener('scroll', schedule, { passive: true });
    window.addEventListener('resize', schedule);

    // Re-apply whenever rows are added/removed (addTicker / removeTicker).
    const observer = new MutationObserver(schedule);
    observer.observe(container, { childList: true });
}

async function startSimulation(e) {
    e.preventDefault();
    const formData = collectFormData();
    
    // Validate all tickers immediately before form validation
    await validateAllTickers();
    
    if (!validateForm(formData)) {
        console.log('Form validation failed');
        return;
    }
    
    // Show loading state
    const startBtn = document.getElementById('startBtn');
    const stopBtn = document.getElementById('stopBtn');
    const progressCard = document.getElementById('progressCard');
    
    startBtn.disabled = true;
    startBtn.innerHTML = '<span class="loading-spinner"></span> …';
    progressCard.style.display = 'block';

    // Bring the results panel into view as soon as the user kicks off a sim.
    try {
        progressCard.scrollIntoView({ behavior: 'smooth', block: 'start' });
    } catch {
        progressCard.scrollIntoView();
    }

    fetch('/start_simulation', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(formData)
    })
    .then(async (response) => {
        let data;
        try {
            data = await response.json();
        } catch {
            throw new Error(response.statusText || 'Server returned non-JSON');
        }
        if (!response.ok) {
            throw new Error(data.error || data.message || `Request failed (${response.status})`);
        }
        return data;
    })
    .then((data) => {
        if (data.success) {
            currentSimulationId = data.simulation_id;
            // Stale benchmark series (aligned to the previous run's timestamps) — drop them.
            for (const k of Object.keys(_benchmarkCache)) delete _benchmarkCache[k];
            _activeBenchmarks.clear();
            document.querySelectorAll('.benchmark-chip.active').forEach((c) => c.classList.remove('active'));
            startBtn.style.display = 'none';
            stopBtn.style.display = 'block';
            startStatusPolling();
            document.getElementById('resultsContainer').innerHTML = '';
            document.getElementById('finalMetricsCard').style.display = 'none';
        } else {
            alert('Error: ' + (data.error || 'Unknown error'));
            resetForm();
        }
    })
    .catch((error) => {
        alert('Error starting simulation: ' + error.message);
        resetForm();
    });
}

function stopSimulation() {
    if (currentSimulationId) {
        fetch(`/stop_simulation/${currentSimulationId}`, {
            method: 'POST'
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                resetForm();
            }
        });
    }
}

function startStatusPolling() {
    statusInterval = setInterval(() => {
        fetch(`/simulation_status/${currentSimulationId}`)
        .then(async (response) => {
            const data = await response.json().catch(() => ({}));
            if (!response.ok) {
                throw new Error(data.error || `Status ${response.status}`);
            }
            return data;
        })
        .then((data) => {
            updateProgress(data);
            updateResults(data);
            
            if (data.is_complete) {
                clearInterval(statusInterval);
                statusInterval = null;
                if (data.error) {
                    alert('Simulation ended with an error: ' + data.error);
                }
                resetForm();
            }
        })
        .catch(() => {});
    }, 500);
}

function updateProgress(data) {
    const progressBar = document.getElementById('progressBar');
    const progressText = document.getElementById('progressText');
    const results = Array.isArray(data.results) ? data.results : [];
    const p = typeof data.progress === 'number' && !Number.isNaN(data.progress) ? data.progress : 0;
    const pct = Math.max(0, Math.min(100, Math.round(p * 100)));
    progressBar.style.width = pct + '%';
    progressBar.setAttribute('aria-valuenow', pct);
    
    if (data.is_complete) {
        progressText.textContent = 'Simulation Complete!';
    } else if (p > 0 && Number.isFinite(p)) {
        const approxTotal = Math.max(results.length, Math.round(results.length / p));
        progressText.textContent = `Progress: ${pct}% (step ${results.length} of ~${approxTotal})`;
    } else {
        progressText.textContent = `Starting… (${results.length} update${results.length === 1 ? '' : 's'})`;
    }
}

function updateResults(data) {
    const resultsContainer = document.getElementById('resultsContainer');
    
    if (data.results && data.results.length > 0) {
        // Clear loading message if it exists
        if (resultsContainer.innerHTML.includes('Configure your portfolio')) {
            resultsContainer.innerHTML = '';
        }
        
        // Append every new interval (do not use slice(-5): fast sims add many rows per poll and
        // intermediate steps would be skipped, so PnL/value would appear not to update each bar).
        data.results.forEach((result) => {
            if (!document.getElementById(`day-${result.day}`)) {
                addDayResult(result);
            }
        });
        
        // Check for executed one-time rules and trigger evaporation
        checkForExecutedOneTimeRules(data);
        
        // Update hedge margin balance display
        updateHedgeMarginBalance(data);
    }
}

// Function to trigger evaporation effect for one-time rules
function triggerRuleEvaporation() {
    const oneTimeRules = document.querySelectorAll('.trading-rule.one-time-mode');
    oneTimeRules.forEach(rule => {
        rule.classList.add('evaporating');
        // Remove the element after animation completes
        setTimeout(() => {
            rule.remove();
        }, 2000); // Match the CSS animation duration
    });
}

// Function to check for executed one-time rules in simulation results
function checkForExecutedOneTimeRules(data) {
    if (data && data.results && data.results.length > 0) {
        const latestResult = data.results[data.results.length - 1];
        if ((latestResult.one_time_rules_executed || 0) > 0) {
            console.log(`DEBUG: ${latestResult.one_time_rules_executed} one-time rules were executed`);
            triggerRuleEvaporation();
        }
    }
}

// Function to update hedge margin balance display
function updateHedgeMarginBalance(data) {
    const hedgeMarginElement = document.getElementById('hedgeMarginBalance');
    console.log('updateHedgeMarginBalance called with data:', data);
    console.log('hedgeMarginElement found:', !!hedgeMarginElement);
    
    if (hedgeMarginElement && data && data.results && data.results.length > 0) {
        const latestResult = data.results[data.results.length - 1];
        console.log('Latest result hedge_margin_balance:', latestResult.hedge_margin_balance);
        
        if (latestResult.hedge_margin_balance !== undefined) {
            const balance = latestResult.hedge_margin_balance;
            hedgeMarginElement.innerHTML = `<span class="me-2">Hedge Margin:</span><span>$${balance.toFixed(2)}</span>`;
            
            // Color code based on available margin
            if (balance < 1000) {
                hedgeMarginElement.className = 'text-danger';
            } else if (balance < 5000) {
                hedgeMarginElement.className = 'text-warning';
            } else {
                hedgeMarginElement.className = 'text-info';
            }
        }
    }
}

function addDayResult(result) {
    const resultsContainer = document.getElementById('resultsContainer');
    
    const dayDiv = document.createElement('div');
    dayDiv.className = 'day-result';
    dayDiv.id = `day-${result.day}`;
    
    const trades = result.trades || [];
    const prices = result.prices || {};

    if (trades.length > 0) {
        dayDiv.classList.add('trading-day');
    }
    
    if (Object.keys(prices).length === 0) {
        dayDiv.classList.add('market-closed');
    }
    
    let pricesHtml = '';
    if (Object.keys(prices).length > 0) {
        pricesHtml = '<div class="price-display">';
        for (const [ticker, price] of Object.entries(prices)) {
            pricesHtml += `<span class="badge bg-primary me-1">${ticker}: $${price.toFixed(2)}</span>`;
        }
        pricesHtml += '</div>';
    } else {
        pricesHtml = '<div class="text-dark"><i class="fas fa-calendar-times"></i> Market Closed</div>';
    }
    
    let tradesHtml = '';
    if (trades.length > 0) {
        tradesHtml = '<div class="mt-2">';
        trades.forEach(trade => {
            const isBuy = trade.toLowerCase().includes('bought') && !trade.toLowerCase().includes('bought back');
            const isHedge = trade.toLowerCase().includes('hedged') || trade.toLowerCase().includes('shorted') || trade.toLowerCase().includes('bought back');
            let tradeClass, icon;
            
            if (isHedge) {
                tradeClass = 'trade-executed hedge';
                icon = 'fa-shield-alt';
            } else if (isBuy) {
                tradeClass = 'trade-executed buy';
                icon = 'fa-plus-circle';
            } else {
                tradeClass = 'trade-executed sell';
                icon = 'fa-minus-circle';
            }
            
            tradesHtml += `<div class="${tradeClass}"><i class="fas ${icon}"></i> ${trade}</div>`;
        });
        tradesHtml += '</div>';
    }
    
    dayDiv.innerHTML = `
        <div class="d-flex justify-content-between align-items-start">
            <div>
                <h6 class="mb-1">${result.interval_label || `Day ${result.day}`} - ${result.date}</h6>
                ${pricesHtml}
                ${tradesHtml}
            </div>
            <div class="text-end">
                <div class="portfolio-value">$${(result.portfolio_value != null ? Number(result.portfolio_value) : 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</div>
                <small class="text-dark d-block">PnL: $${result.pnl != null ? Number(result.pnl).toFixed(2) : '0.00'}</small>
                ${result.cash != null && !Number.isNaN(Number(result.cash)) ? `<small class="text-dark d-block">Cash: $${Number(result.cash).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</small>` : ''}
            </div>
        </div>
    `;
    
    resultsContainer.appendChild(dayDiv);
}


function showFinalResults(data) {
    console.log('🎯 showFinalResults called with data:', data);
    console.log('🔍 Checking for final metrics existence:', !!data.final_metrics);
    
    if (!data.final_metrics) {
        console.error('❌ No final_metrics found in data!');
        console.log('Available data keys:', Object.keys(data));
        return;
    }

    const isFin = (v) => typeof v === 'number' && Number.isFinite(v);
    const fmtMoney = (v) => (isFin(v) ? v.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : 'N/A');
    const fmtFixed = (v, d) => (isFin(v) ? v.toFixed(d) : 'N/A');
    const fmtPctReturn = (v) => (isFin(v) ? `${v >= 0 ? '+' : ''}${v}%` : 'N/A');
    
    try {
        if (data.final_metrics) {
            const fm = data.final_metrics;
            console.log('📊 Final metrics found:', fm);
            console.log('💰 Final value:', fm.final_value, 'type:', typeof fm.final_value);
            console.log('📈 Total return:', fm.total_return_pct, 'type:', typeof fm.total_return_pct);
            console.log('⚡ Sharpe ratio:', fm.sharpe_ratio, 'type:', typeof fm.sharpe_ratio);
            console.log('📊 Beta:', fm.beta, 'type:', typeof fm.beta);
            
            const finalMetricsCard = document.getElementById('finalMetricsCard');
            const finalMetrics = document.getElementById('finalMetrics');
            console.log('Final metrics card element:', finalMetricsCard);
            console.log('Final metrics element:', finalMetrics);
            if (!finalMetricsCard || !finalMetrics) {
                console.error('finalMetricsCard or finalMetrics element missing from DOM');
                return;
            }
            
            const retCls = isFin(fm.total_return_pct) ? (fm.total_return_pct >= 0 ? 'positive' : 'negative') : '';
            const pnlCls = isFin(fm.total_pnl) ? (fm.total_pnl >= 0 ? 'positive' : 'negative') : '';
            
            finalMetrics.innerHTML = `
            <div class="col">
                <div class="metric-card">
                    <div class="metric-value">$${fmtMoney(fm.final_value)}</div>
                    <div class="metric-label">Final Value</div>
                </div>
            </div>
            <div class="col">
                <div class="metric-card">
                    <div class="metric-value ${retCls}">
                        ${fmtPctReturn(fm.total_return_pct)}
                    </div>
                    <div class="metric-label">Total Return</div>
                </div>
            </div>
            <div class="col">
                <div class="metric-card">
                    <div class="metric-value ${pnlCls}">
                        $${fmtMoney(fm.total_pnl)}
                    </div>
                    <div class="metric-label">Total PnL</div>
                </div>
            </div>
            <div class="col">
                <div class="metric-card">
                    <div class="metric-value">
                        ${fmtFixed(fm.volatility_pct, 2)}${isFin(fm.volatility_pct) ? '%' : ''}
                    </div>
                    <div class="metric-label">Volatility (ann.)</div>
                </div>
            </div>
            <div class="col">
                <div class="metric-card">
                    <div class="metric-value">
                        ${fmtFixed(fm.sharpe_ratio, 3)}
                    </div>
                    <div class="metric-label">Sharpe Ratio</div>
                </div>
            </div>
            <div class="col">
                <div class="metric-card">
                    <div class="metric-value">
                        ${fmtFixed(fm.beta, 3)}
                    </div>
                    <div class="metric-label">Beta</div>
                    ${fm.beta_interpretation ? `<div class="metric-subtitle">${String(fm.beta_interpretation).replace(/</g, '&lt;').replace(/>/g, '&gt;')}</div>` : ''}
                </div>
            </div>
            <div class="col">
                <div class="metric-card">
                    <div class="metric-value">
                        ${fmtFixed(fm.correlation, 3)}
                    </div>
                    <div class="metric-label">Market Correlation</div>
                </div>
            </div>
            <div class="col">
                <div class="metric-card">
                    <div class="metric-value">
                        ${Number.isFinite(Number(fm.hedge_trades_count)) ? fm.hedge_trades_count : 0}
                    </div>
                    <div class="metric-label">Hedge Trades</div>
                </div>
            </div>
            <div class="col">
                <div class="metric-card">
                    <div class="metric-value">
                        $${fmtMoney(isFin(fm.total_hedge_margin_used) ? fm.total_hedge_margin_used : 0)}
                    </div>
                    <div class="metric-label">Margin Used</div>
                </div>
            </div>
            <div class="col">
                <div class="metric-card">
                    <div class="metric-value">
                        $${fmtMoney(isFin(fm.hedge_margin_remaining) ? fm.hedge_margin_remaining : 0)}
                    </div>
                    <div class="metric-label">Margin Remaining</div>
                </div>
            </div>
        `;
        
        
            finalMetricsCard.style.display = 'block';
            console.log('Final metrics card should now be visible');

            // Park the viewport ON the grid itself (not the card header / not the bottom of the page).
            // We defer with rAF + a short timeout so this runs AFTER showAIAdvisor()/showPlotsCard()
            // mutate layout (expanding the chat, revealing the plots card), otherwise their layout
            // shifts would knock our scroll position off-target.
            const focusGrid = () => {
                const target = finalMetrics || finalMetricsCard;
                try {
                    target.scrollIntoView({ behavior: 'smooth', block: 'center' });
                } catch {
                    target.scrollIntoView();
                }
            };
            requestAnimationFrame(() => {
                requestAnimationFrame(() => setTimeout(focusGrid, 60));
            });

            // Mosaic entrance — each tile flips on the Y-axis from back to front, staggered
            // diagonally so they read as a real mosaic of cards turning over to reveal values.
            try {
                const reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
                if (reduceMotion) return;

                const cards = Array.from(finalMetrics.querySelectorAll('.metric-card'));
                finalMetrics.classList.add('is-animating-in'); // hides tiles until WAAPI is queued

                requestAnimationFrame(() => {
                    cards.forEach((card, idx) => {
                        const row = Math.floor(idx / 5);
                        const col = idx % 5;
                        // Slower diagonal stagger so the cascade is clearly readable as a wave.
                        const delay = (row + col) * 180;
                        // Monotonic 180° → 0° flip. The middle keyframe (edge-on at 90°)
                        // is implicit because the rotation is continuous; we only need
                        // start + end. Subtle translateZ + scale adds a touch of depth
                        // so the card "lifts" into place without overshooting.
                        const keyframes = [
                            { opacity: 1, transform: 'rotateY(180deg) translateZ(-30px) scale(0.94)' },
                            { opacity: 1, transform: 'rotateY(0deg) translateZ(0) scale(1)' },
                        ];
                        card.animate(keyframes, {
                            duration: 1500,
                            delay,
                            // Smooth deceleration — the flip slows as it lands flat,
                            // like a real card settling. No overshoot, no bounce.
                            easing: 'cubic-bezier(0.22, 0.61, 0.36, 1)',
                            fill: 'forwards',
                        });
                    });
                    setTimeout(() => finalMetrics.classList.remove('is-animating-in'), 30);
                });
            } catch (e) {
                console.warn('Metric mosaic animation skipped:', e);
                finalMetrics.classList.remove('is-animating-in');
            }
        } else {
            console.log('No final metrics found in data');
        }
        
        // Update progress to 100%
        document.getElementById('progressBar').style.width = '100%';
        document.getElementById('progressText').textContent = 'Simulation Complete!';
    } catch (error) {
        console.error('Error in showFinalResults:', error);
        console.error('Data that caused error:', data);
    }
}

function computeSimulationStartDate(tradingFrequency, durationDays, durationHours) {
    const end = new Date();
    let backDays;
    if (tradingFrequency === 'daily') {
        backDays = Math.min(400, Math.max(durationDays + 7, 14));
    } else if (tradingFrequency === '60m') {
        backDays = Math.min(60, Math.max(durationDays * 10 + 14, 14));
    } else if (tradingFrequency === '1m' || tradingFrequency === '5m' || tradingFrequency === '15m') {
        const h = durationHours || 1;
        backDays = Math.min(60, Math.max(14, Math.ceil(h / 6.5) * 4 + 20));
    } else {
        backDays = 30;
    }
    const start = new Date(end.getFullYear(), end.getMonth(), end.getDate() - backDays);
    return `${start.getFullYear()}-${String(start.getMonth() + 1).padStart(2, '0')}-${String(start.getDate()).padStart(2, '0')}`;
}

function collectFormData() {
    const tickers = [];
    const tickerInputs = document.querySelectorAll('#tickersContainer .ticker-input');
    
    tickerInputs.forEach((input, index) => {
        const tickerInput = input.querySelector('input[type="text"]');
        const sharesInput = input.querySelector('input[type="number"]');
        
        if (tickerInput && tickerInput.value.trim() && sharesInput && sharesInput.value) {
            tickers.push({
                ticker: tickerInput.value.trim().toUpperCase(),
                shares: parseInt(sharesInput.value)
            });
        }
    });
    
    const tradingRules = [];
    const ruleInputs = document.querySelectorAll('#tradingRulesContainer .trading-rule');
    console.log('DEBUG: Found', ruleInputs.length, 'trading rule inputs');
    
    ruleInputs.forEach((input, index) => {
        const tickerSelect = input.querySelector('.ticker-select');
        const actionSelect = input.querySelector('.action-select');
        const conditionSelect = input.querySelector('select:last-of-type');
        const thresholdInput = input.querySelector('input[type="number"]:first-of-type');
        const sharesInput = input.querySelector('input[type="number"]:last-of-type');
        
        console.log(`Rule ${index}:`, {
            ticker: tickerSelect?.value,
            action: actionSelect?.value,
            condition: conditionSelect?.value,
            threshold: thresholdInput?.value,
            shares: sharesInput?.value
        });
        
        if (tickerSelect && tickerSelect.value.trim() && actionSelect.value && conditionSelect.value && thresholdInput.value && sharesInput.value) {
            const isOneTime = input.classList.contains('one-time-mode');
            tradingRules.push({
                ticker: tickerSelect.value.toUpperCase().trim(),
                action: actionSelect.value,
                condition: conditionSelect.value,
                threshold: parseFloat(thresholdInput.value),
                shares: parseInt(sharesInput.value),
                one_time: isOneTime
            });
        }
    });
    
    console.log('DEBUG: Final trading rules array:', tradingRules);
    
    const tradingFrequency = document.getElementById('tradingFrequency').value;
    let span = parseInt(document.getElementById('durationDays').value, 10);
    if (Number.isNaN(span)) {
        span = tradingFrequency === 'daily' ? 30 : 3;
    }

    let duration_days;
    let duration_hours = null;
    if (tradingFrequency === 'daily' || tradingFrequency === '60m') {
        duration_days = span;
    } else {
        duration_days = 1;
        duration_hours = span;
    }

    const startDateStr = computeSimulationStartDate(tradingFrequency, duration_days, duration_hours);

    // Which strategy lane is the user on? The Strategy card's segmented
    // switch governs whether the simulation engine evaluates manual rules or
    // executes the imported script body at each interval. Same setup
    // (intervals, dates, positions, initial cash, hedge); only the
    // per-tick decision logic differs.
    const strategyCard = document.getElementById('strategyCard');
    const strategyMode = strategyCard && strategyCard.dataset.mode === 'imported'
        ? 'imported'
        : 'manual';

    const formData = {
        initial_cash: readInitialCash(),
        duration_days: duration_days,
        duration_hours: duration_hours,
        start_date: startDateStr,
        trading_frequency: tradingFrequency,
        tickers: tickers,
        trading_rules: strategyMode === 'manual' ? tradingRules : [],
        beta_hedge_enabled: document.getElementById('betaHedgeEnabled').checked,
        strategy_mode: strategyMode,
    };

    if (strategyMode === 'imported') {
        const select = document.getElementById('importStrategySelect');
        const id = select ? select.value : '';
        const saved = loadSavedStrategies().find((s) => s.id === id);
        if (saved) {
            formData.strategy_code = saved.code || '';
            formData.strategy_name = saved.name || '';
            formData.strategy_id = saved.id;
        }
    }

    return formData;
}

function validateForm(data) {
    if (data.tickers.length === 0) {
        alert('Please add at least one stock position.');
        return false;
    }

    if (data.initial_cash < 1000) {
        alert('Initial cash must be at least $1,000.');
        return false;
    }

    // Imported mode swaps manual rules for an imported script; require the
    // user to actually pick one before we POST.
    if (data.strategy_mode === 'imported') {
        if (!data.strategy_code || !data.strategy_code.trim()) {
            alert(
                'You\'re on "Imported" mode but no saved strategy is selected.\n\n' +
                'Pick one from the dropdown in the Strategy card, or save one in the Studio first.'
            );
            return false;
        }
    }
    
    // Check if all tickers are valid
    const invalidTickers = [];
    const unvalidatedTickers = [];
    
    const tickerInputs = document.querySelectorAll('#tickersContainer input[type="text"]');
    tickerInputs.forEach(input => {
        if (input.value.trim()) {
            if (input.classList.contains('is-invalid')) {
                invalidTickers.push(input.value.toUpperCase());
            } else if (!input.classList.contains('is-valid')) {
                unvalidatedTickers.push(input.value.toUpperCase());
            }
        }
    });
    
    // Check if all tickers in trading rules are valid
    const tradingRuleTickerInputs = document.querySelectorAll('#tradingRulesContainer .ticker-select');
    tradingRuleTickerInputs.forEach(select => {
        if (select.value.trim()) {
            if (select.classList.contains('is-invalid')) {
                invalidTickers.push(select.value.toUpperCase());
            } else if (!select.classList.contains('is-valid')) {
                unvalidatedTickers.push(select.value.toUpperCase());
            }
        }
    });
    
    // If there are unvalidated tickers, validate them first
    if (unvalidatedTickers.length > 0) {
        alert(`Please wait for ticker validation to complete for: ${unvalidatedTickers.join(', ')}.`);
        return false;
    }
    
    if (invalidTickers.length > 0) {
        console.log('Invalid tickers found:', invalidTickers);
        console.log('Ticker inputs:', tickerInputs);
        console.log('Trading rule inputs:', tradingRuleTickerInputs);
        alert(`Invalid ticker symbols: ${invalidTickers.join(', ')}. Please enter valid ticker symbols that exist in Yahoo Finance.`);
        return false;
    }
    
    const tf = data.trading_frequency;
    if (tf === 'daily') {
        if (data.duration_days < 1 || data.duration_days > 365) {
            alert('Simulation length must be between 1 and 365 days for daily trading.');
            return false;
        }
    } else if (tf === '60m') {
        if (data.duration_days < 1 || data.duration_days > 7) {
            alert('For 60-minute intervals, choose 1–7 calendar days.');
            return false;
        }
    } else if (tf === '1m') {
        const h = data.duration_hours;
        if (h == null || h < 1 || h > 6) {
            alert('For 1-minute intervals, choose 1–6 hours of session data.');
            return false;
        }
    } else if (tf === '5m') {
        const h = data.duration_hours;
        if (h == null || h < 1 || h > 12) {
            alert('For 5-minute intervals, choose 1–12 hours.');
            return false;
        }
    } else if (tf === '15m') {
        const h = data.duration_hours;
        if (h == null || h < 1 || h > 24) {
            alert('For 15-minute intervals, choose 1–24 hours (up to about one day).');
            return false;
        }
    }
    
    return true;
}

/**
 * Stock Positions are opening holdings — they do not spend the cash pile.
 * Simulations establish them at market without debiting cash; buys during
 * the run still use cash (and hedge flows use margin as before). No
 * client-side "positions vs cash" gate here.
 */
function validatePortfolioValue(data) {
    return {
        isValid: true,
        severity: 'success',
        message: 'Portfolio validation passed.',
        details: [],
    };
}

/**
 * Trading Time Interval is a segmented button group. Click handlers call this
 * to: (a) flip the active class, (b) mirror the value into the hidden
 * #tradingFrequency input so existing readers keep working unchanged, and
 * (c) trigger downstream UI updates (duration slider min/max, help text, etc).
 */
function selectTradingFrequency(btn) {
    if (!btn) return;
    const value = btn.dataset.value;
    if (!value) return;
    const hidden = document.getElementById('tradingFrequency');
    if (hidden) hidden.value = value;

    const group = btn.closest('.trading-frequency-buttons');
    if (group) {
        group.querySelectorAll('.ts-interval-btn').forEach((b) => {
            const on = b === btn;
            b.classList.toggle('active', on);
            b.setAttribute('aria-pressed', on ? 'true' : 'false');
        });
    }

    if (typeof updateDurationLimits === 'function') updateDurationLimits();
}

function updateDurationLimits() {
    const tradingFrequency = document.getElementById('tradingFrequency').value;
    const durationSlider = document.getElementById('durationDays');
    const durationValue = document.getElementById('durationValue');
    const durationUnit = document.getElementById('durationUnit');
    const durationLabelTitle = document.getElementById('durationLabelTitle');
    const minDuration = document.getElementById('minDuration');
    const maxDuration = document.getElementById('maxDuration');
    const frequencyHelp = document.getElementById('frequencyHelp');
    const dateRangeInfo = document.getElementById('dateRangeInfo');

    const presets = {
        daily: {
            mode: 'days',
            min: 1,
            max: 365,
            fallback: 30,
            title: 'Simulation length',
            unit: 'days',
            help: 'Daily midprice trading (1 year max)',
        },
        '1m': {
            mode: 'hours',
            min: 1,
            max: 6,
            fallback: 3,
            title: 'Hours of the trading day to include',
            unit: 'hours',
            help: '1m interval trading (6 hour limit)',
        },
        '5m': {
            mode: 'hours',
            min: 1,
            max: 12,
            fallback: 6,
            title: 'Hours of the trading day to include',
            unit: 'hours',
            help: '5m interval trading (12 hour limit)',
        },
        '15m': {
            mode: 'hours',
            min: 1,
            max: 24,
            fallback: 8,
            title: 'Hours to cover (up to one day)',
            unit: 'hours',
            help: '15m interval trading (Day limit)',
        },
        '60m': {
            mode: 'days',
            min: 1,
            max: 7,
            fallback: 3,
            title: 'Calendar days',
            unit: 'days',
            help: 'Hourly interval trading (Week limit)',
        },
    };

    const p = presets[tradingFrequency] || presets.daily;
    durationSlider.min = String(p.min);
    durationSlider.max = String(p.max);

    let v = parseInt(durationSlider.value, 10);
    if (Number.isNaN(v) || v < p.min || v > p.max) {
        v = p.fallback;
        durationSlider.value = String(v);
    } else if (v < p.min) {
        v = p.min;
        durationSlider.value = String(v);
    } else if (v > p.max) {
        v = p.max;
        durationSlider.value = String(v);
    }

    // The inline slider label (#durationValue / #durationUnit / #durationLabelTitle)
    // was removed in favor of the "Last X hours of trading" summary above —
    // guard the writes so this function keeps working if any are absent.
    if (durationValue) durationValue.textContent = String(v);
    if (durationUnit) durationUnit.textContent = p.unit;
    if (durationLabelTitle) durationLabelTitle.textContent = p.title;

    const unitWord = (n) => {
        if (p.unit === 'hours') return n === 1 ? 'hour' : 'hours';
        return n === 1 ? 'day' : 'days';
    };
    minDuration.textContent = `${p.min} ${unitWord(p.min)}`;
    maxDuration.textContent = `${p.max} ${unitWord(p.max)}`;
    frequencyHelp.textContent = p.help;

    // "Last X hours/days of trading" summary that tracks the slider value live.
    const dateRangeSummary = document.getElementById('dateRangeSummary');
    if (dateRangeSummary) {
        dateRangeSummary.textContent = `Last ${v} ${unitWord(v)} of trading`;
    }

    // Detail line: only show the concrete calendar window in daily-style modes
    // (where it actually adds info on top of the summary). Intraday modes
    // would have just repeated "~Xh intraday" so we hide the line entirely.
    if (dateRangeInfo) {
        if (p.mode === 'days') {
            const span = parseInt(durationSlider.value, 10) || p.fallback;
            const now = new Date();
            const st = new Date(now.getFullYear(), now.getMonth(), now.getDate() - span);
            dateRangeInfo.innerHTML =
                `<strong>${st.toLocaleDateString()}</strong> → <strong>${now.toLocaleDateString()}</strong>`;
            dateRangeInfo.hidden = false;
        } else {
            dateRangeInfo.innerHTML = '';
            dateRangeInfo.hidden = true;
        }
    }
}

function initializePortfolioValidation() {
    // Add event listeners to ticker inputs for real-time validation
    const tickersContainer = document.getElementById('tickersContainer');
    if (tickersContainer) {
        // Use event delegation for dynamic content
        tickersContainer.addEventListener('input', function(e) {
            if (e.target.type === 'number' && e.target.placeholder === 'Shares') {
                validatePortfolioInRealTime();
            }
        });
    }
    
    // Add event listener to initial cash input
    const initialCashInput = document.getElementById('initialCash');
    if (initialCashInput) {
        initialCashInput.addEventListener('input', validatePortfolioInRealTime);
    }
    
    // Add event listeners to trading rules
    const tradingRulesContainer = document.getElementById('tradingRulesContainer');
    if (tradingRulesContainer) {
        tradingRulesContainer.addEventListener('input', function(e) {
            if (e.target.type === 'number') {
                validatePortfolioInRealTime();
            }
        });
    }
}

function validatePortfolioInRealTime() {
    // Debounce the validation to avoid too many calls
    clearTimeout(window.portfolioValidationTimeout);
    window.portfolioValidationTimeout = setTimeout(() => {
        try {
            const formData = collectFormData();
            const validation = validatePortfolioValue(formData);
            
            // Update UI to show validation status
            updatePortfolioValidationUI(validation);
        } catch (error) {
            console.log('Portfolio validation error:', error);
        }
    }, 500);
}

function updatePortfolioValidationUI(validation) {
    const statusElement = document.getElementById('portfolioValidationStatus');
    if (!statusElement) {
        return;
    }

    const escapeAttr = (s) => String(s).replace(/"/g, '&quot;');
    const details = Array.isArray(validation.details) ? validation.details : [];
    const tooltip = details.length ? details.join('\n') : validation.message;

    statusElement.removeAttribute('hidden');
    statusElement.classList.remove('is-success', 'is-error', 'is-warning');
    statusElement.classList.add('is-visible');

    if (validation.isValid) {
        statusElement.classList.add('is-success');
        statusElement.removeAttribute('title');
        statusElement.innerHTML =
            '<span class="d-inline-flex align-items-center gap-1"><i class="fas fa-check-circle"></i><span>Portfolio validation passed</span></span>';
        return;
    }

    if (validation.severity === 'error') {
        statusElement.classList.add('is-error');
        statusElement.setAttribute('title', escapeAttr(tooltip));
        statusElement.innerHTML = `<span class="d-inline-flex align-items-center gap-1"><i class="fas fa-times-circle"></i><span>${validation.message}</span></span>`;
        return;
    }

    statusElement.classList.add('is-warning');
    statusElement.setAttribute('title', escapeAttr(tooltip));
    statusElement.innerHTML = `<span class="d-inline-flex align-items-center gap-1"><i class="fas fa-exclamation-triangle"></i><span>${validation.message}</span></span>`;
}

function resetForm() {
    const startBtn = document.getElementById('startBtn');
    const stopBtn = document.getElementById('stopBtn');
    
    startBtn.disabled = false;
    startBtn.innerHTML = '<i class="fas fa-play"></i> Start';
    startBtn.style.display = 'block';
    stopBtn.style.display = 'none';
    
    if (statusInterval) {
        clearInterval(statusInterval);
        statusInterval = null;
    }
    
    currentSimulationId = null;
}

function addTicker() {
    const container = document.getElementById('tickersContainer');
    const tickerInput = document.createElement('div');
    tickerInput.className = 'ticker-input mb-2';
    tickerInput.innerHTML = `
        <div class="input-group">
            <input type="text" class="form-control" placeholder="Ticker (e.g., AAPL)" maxlength="20" style="text-transform: uppercase;" oninput="validateTicker(this)">
            <input type="number" class="form-control" placeholder="Shares" value="100" min="1">
            <button type="button" class="btn btn-outline-danger" onclick="removeTicker(this)">
                <i class="fas fa-trash"></i>
            </button>
        </div>
    `;
    container.appendChild(tickerInput);
    
}

function removeTicker(button) {
    button.closest('.ticker-input').remove();
}

function addTradingRule() {
    const container = document.getElementById('tradingRulesContainer');
    const ruleInput = document.createElement('div');
    ruleInput.className = 'trading-rule mb-2';
    ruleInput.onclick = function() { toggleOneTimeMode(this); };
    ruleInput.title = 'Click to toggle one-time execution mode';
    ruleInput.innerHTML = `
        <div class="input-group">
            <select class="form-select ticker-select" onchange="validateTradingRuleTicker(this)">
                <option value="NVDA">NVDA</option>
                <option value="AAPL">AAPL</option>
                <option value="TSLA">TSLA</option>
                <option value="MSFT">MSFT</option>
                <option value="GOOGL">GOOGL</option>
                <option value="AMZN">AMZN</option>
                <option value="META">META</option>
                <option value="NFLX">NFLX</option>
            </select>
            <select class="form-select action-select">
                <option value="sell">Sell</option>
                <option value="buy">Buy</option>
            </select>
            <select class="form-select">
                <option value="greater_than">Price ></option>
                <option value="less_than">Price <</option>
            </select>
            <input type="number" class="form-control" placeholder="Threshold" step="0.01">
            <input type="number" class="form-control" placeholder="Shares" value="10" min="1">
            <button type="button" class="btn btn-outline-danger" onclick="removeTradingRule(this); event.stopPropagation();">
                <i class="fas fa-trash"></i>
            </button>
        </div>
    `;
    container.appendChild(ruleInput);
}


function validateTickerApiPath(ticker) {
    return '/validate_ticker/' + encodeURIComponent(ticker);
}

function validateTicker(input) {
    const ticker = input.value.toUpperCase().trim();
    const isValidFormat = /^[A-Z0-9.\-^]{1,20}$/.test(ticker) && ticker.length >= 1;
    
    // Remove existing validation classes
    input.classList.remove('is-valid', 'is-invalid', 'is-warning');
    
    if (ticker.length === 0) {
        // No validation styling for empty input
        input.title = '';
        return;
    } else if (!isValidFormat) {
        input.classList.add('is-invalid');
        input.title = 'Invalid ticker format (e.g., AAPL, BRK.B, BF-B, ^GSPC)';
        return;
    }
    
    // Show loading state
    input.classList.add('is-warning');
    input.title = 'Checking ticker validity...';
    
    // Validate ticker against Yahoo Finance
    validateTickerWithAPI(ticker, input);
}

function validateTickerWithAPI(ticker, inputElement) {
    // Debounce API calls to avoid too many requests
    clearTimeout(window.tickerValidationTimeout);
    window.tickerValidationTimeout = setTimeout(() => {
        fetch(validateTickerApiPath(ticker))
            .then(response => response.json())
            .then(data => {
                // Remove loading state
                inputElement.classList.remove('is-warning');
                
                if (data.valid) {
                    inputElement.classList.add('is-valid');
                    inputElement.title = `Valid ticker: ${data.name} (${data.exchange})`;
                    
                    // Update the ticker value to the validated version
                    inputElement.value = data.ticker;
                } else {
                    inputElement.classList.add('is-invalid');
                    inputElement.title = data.error || 'Ticker not found in Yahoo Finance database';
                }
                
                // Trigger portfolio validation after ticker validation
                validatePortfolioInRealTime();
            })
            .catch(() => {
                inputElement.classList.remove('is-warning');
                inputElement.classList.add('is-invalid');
                inputElement.title = 'Error validating ticker. Please try again.';
            });
    }, 1000); // 1 second delay to avoid too many API calls
}

async function validateAllTickers() {
    const tickerInputs = document.querySelectorAll('#tickersContainer input[type="text"]');
    const tradingRuleTickerInputs = document.querySelectorAll('#tradingRulesContainer .ticker-select');
    
    const allInputs = [...tickerInputs, ...tradingRuleTickerInputs];
    const validationPromises = [];
    
    allInputs.forEach(input => {
        if (input.value.trim() && !input.classList.contains('is-valid') && !input.classList.contains('is-invalid')) {
            validationPromises.push(validateTickerWithAPIImmediate(input.value.trim(), input));
        }
    });
    
    if (validationPromises.length > 0) {
        await Promise.all(validationPromises);
    }
}

function validateTickerWithAPIImmediate(ticker, inputElement) {
    return new Promise((resolve) => {
        fetch(validateTickerApiPath(ticker))
            .then(response => response.json())
            .then(data => {
                if (data.valid) {
                    inputElement.classList.remove('is-warning', 'is-invalid');
                    inputElement.classList.add('is-valid');
                    inputElement.title = `Valid ticker: ${data.name} (${data.exchange})`;
                    inputElement.value = data.ticker;
                } else {
                    inputElement.classList.remove('is-warning', 'is-valid');
                    inputElement.classList.add('is-invalid');
                    inputElement.title = data.error || 'Ticker not found in Yahoo Finance database';
                }
                resolve();
            })
            .catch(() => {
                inputElement.classList.remove('is-warning', 'is-valid');
                inputElement.classList.add('is-invalid');
                inputElement.title = 'Error validating ticker. Please try again.';
                resolve();
            });
    });
}

function validateTradingRuleTicker(selectElement) {
    const ticker = selectElement.value.toUpperCase().trim();
    
    // Remove existing validation classes
    selectElement.classList.remove('is-valid', 'is-invalid', 'is-warning');
    
    if (ticker.length === 0) {
        return;
    }
    
    // Show loading state
    selectElement.classList.add('is-warning');
    
    // Validate ticker against Yahoo Finance
    validateTickerWithAPI(ticker, selectElement);
}

function removeTradingRule(button) {
    button.closest('.trading-rule').remove();
}

function toggleOneTimeMode(tradingRule) {
    const isOneTime = tradingRule.classList.contains('one-time-mode');
    
    if (isOneTime) {
        // Turn off one-time mode
        tradingRule.classList.remove('one-time-mode');
        tradingRule.title = 'Click to toggle one-time execution mode';
    } else {
        // Turn on one-time mode
        tradingRule.classList.add('one-time-mode');
        tradingRule.title = 'One-time mode active - rule will execute once then be removed';
    }
}

// AI Chat Functions
function initializeAIChat() {
    // Chat input and send button
    const chatInput = document.getElementById('aiChatInput');
    const sendBtn = document.getElementById('aiSendBtn');
    
    if (chatInput && sendBtn) {
        sendBtn.addEventListener('click', sendAIMessage);
        chatInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendAIMessage();
            }
        });
    }
    
    // Use event delegation — target may be the trash icon inside the button
    document.addEventListener('click', function (event) {
        const btn = event.target && event.target.closest && event.target.closest('#clearChatBtn');
        if (btn) {
            event.preventDefault();
            clearAIChat();
        }
    });
    
    // Quick question buttons
    const quickQuestionBtns = document.querySelectorAll('.quick-question-btn');
    quickQuestionBtns.forEach(btn => {
        btn.addEventListener('click', function() {
            const question = this.getAttribute('data-question');
            if (question) {
                document.getElementById('aiChatInput').value = question;
                sendAIMessage();
            }
        });
    });
}

function showAIAdvisor() {
    // The Teeby widget is now a floating live-chat launcher that's always
    // present in the DOM (see #teebyWidget). Nothing to show/hide on the
    // post-simulation hook anymore — this function is kept so existing
    // call sites still resolve. We could nudge the user by briefly
    // bouncing the launcher here, but the pulse-ring animation already
    // draws attention.
    return;
}

/* ---------- Strategy card segmented switch (Manual ⇄ Imported) ----------
   The Strategy card on the right column hosts two panes (Manual rules
   and Imported saved-strategy). The segmented switch in the header
   flips between them: the active option lights up via a sliding "thumb"
   pill that animates left/right under the buttons. Selection persists
   to localStorage so reloads remember the user's preference.

   The hidden pane is `[hidden]` — existing JS still finds elements by ID
   (e.g. #betaHedgeEnabled, #tradingRulesContainer, #importStrategySelect)
   regardless of which pane is on screen, so no downstream refactor is
   needed for collectFormData / margin display / etc. */
function initStrategyModeSwitch() {
    const card = document.getElementById('strategyCard');
    if (!card) return;
    const switchEl = card.querySelector('.strategy-mode-switch');
    if (!switchEl) return;
    const options = Array.from(switchEl.querySelectorAll('.strategy-mode-option'));
    const thumb = switchEl.querySelector('.strategy-mode-thumb');
    const panes = {
        manual: document.getElementById('strategyManualPane'),
        imported: document.getElementById('strategyImportedPane'),
    };

    const MODE_KEY = 'tradesphere_strategy_mode';
    let stored = null;
    try { stored = localStorage.getItem(MODE_KEY); } catch (_) { /* private mode */ }
    const initial = (stored === 'manual' || stored === 'imported') ? stored : 'manual';

    const moveThumb = (activeBtn) => {
        if (!thumb || !activeBtn) return;
        // Measure relative to the switch's content box (padding-aware).
        const switchRect = switchEl.getBoundingClientRect();
        const btnRect = activeBtn.getBoundingClientRect();
        const left = btnRect.left - switchRect.left;
        const width = btnRect.width;
        thumb.style.left = `${left}px`;
        thumb.style.width = `${width}px`;
    };

    const setMode = (mode) => {
        if (mode !== 'manual' && mode !== 'imported') return;
        card.setAttribute('data-mode', mode);
        let activeBtn = null;
        options.forEach((btn) => {
            const on = btn.dataset.mode === mode;
            btn.classList.toggle('active', on);
            btn.setAttribute('aria-selected', on ? 'true' : 'false');
            if (on) activeBtn = btn;
        });
        Object.entries(panes).forEach(([k, el]) => {
            if (!el) return;
            if (k === mode) el.removeAttribute('hidden');
            else el.setAttribute('hidden', '');
        });
        moveThumb(activeBtn);
        try { localStorage.setItem(MODE_KEY, mode); } catch (_) { /* ignore */ }
    };

    options.forEach((btn) => {
        btn.addEventListener('click', () => setMode(btn.dataset.mode));
    });

    // Initial state — apply persisted/default mode, then re-measure the
    // thumb after layout settles (initial getBoundingClientRect can be
    // off if web fonts haven't loaded yet).
    setMode(initial);
    requestAnimationFrame(() => moveThumb(switchEl.querySelector('.strategy-mode-option.active')));
    window.addEventListener('resize', () => {
        moveThumb(switchEl.querySelector('.strategy-mode-option.active'));
    });
}

/* ---------- Teeby live-chat widget toggle ----------
   Wires the floating launcher to the slide-in chat panel. Open/close
   state is mirrored on a data-state attribute and on aria-expanded so
   CSS + screen readers stay in sync. Escape closes the panel; clicking
   the launcher toggles it; the in-panel close (X) button closes it. */
function initTeebyWidget() {
    const widget = document.getElementById('teebyWidget');
    const launcher = document.getElementById('teebyLauncher');
    const panel = document.getElementById('teebyChatPanel');
    const closeBtn = document.getElementById('teebyCloseBtn');
    const inviteCloseBtn = document.getElementById('teebyInviteClose');
    if (!widget || !launcher || !panel) return;

    // The Teeby invite bubble only greets the user when they first
    // arrive on the dashboard from the landing page. The Next.js shell
    // signals that arrival by appending `?invite=1` to the iframe URL
    // (only on the landing → dashboard launch — header taps and
    // in-iframe links do NOT carry this). Other navigations / reloads
    // get no greeting, which is the intended live-chat-rep behaviour.
    //
    // We also defensively wipe stale dismissal flags from earlier
    // builds that used to persist suppression to localStorage.
    try {
        localStorage.removeItem('tradesphere_teeby_invite_dismissed');
        localStorage.removeItem('tradesphere_teeby_invite_dismissed_v2');
    } catch (_) { /* private mode / disabled — ignore */ }

    const inviteEl = document.getElementById('teebyInvite');
    let shouldGreet = false;
    try {
        shouldGreet = new URLSearchParams(window.location.search).get('invite') === '1';
    } catch (_) { /* very old browsers — leave greet=false */ }

    if (shouldGreet) {
        // Show the invite bubble after a short delay so it lands after
        // the rest of the dashboard has settled. JS-driven (vs a CSS
        // @keyframes) so theme toggles don't strand it mid-state. The
        // element starts with inline `opacity:0;visibility:hidden` to
        // guarantee no first-paint flash — we strip that here, then on
        // the next animation frame toggle the attribute so the CSS
        // transition has a starting point to animate from.
        setTimeout(() => {
            if (widget.getAttribute('data-invite-dismissed') === 'true') return;
            if (widget.getAttribute('data-state') === 'open') return;
            if (inviteEl) inviteEl.removeAttribute('style');
            requestAnimationFrame(() => {
                if (widget.getAttribute('data-invite-dismissed') === 'true') return;
                if (widget.getAttribute('data-state') === 'open') return;
                widget.setAttribute('data-invite-shown', 'true');
            });
        }, 1200);
    }

    // Hide the bubble for the current page only. Re-arriving from the
    // landing page (which adds ?invite=1) will greet the user again;
    // header/in-iframe navigations won't.
    const dismissInvite = () => {
        widget.removeAttribute('data-invite-shown');
        widget.setAttribute('data-invite-dismissed', 'true');
    };

    const setState = (open) => {
        // First open strips the FOUC-guard inline style so the CSS
        // transitions can take over from here on. Without this the
        // chat panel would briefly paint at default browser styles
        // before the cascade settled — same problem we fixed for the
        // invite bubble, same fix.
        if (open && panel.hasAttribute('style')) {
            panel.removeAttribute('style');
        }
        widget.setAttribute('data-state', open ? 'open' : 'closed');
        launcher.setAttribute('aria-expanded', open ? 'true' : 'false');
        panel.setAttribute('aria-hidden', open ? 'false' : 'true');
        if (open) {
            // Opening the chat hides the invite (it's done its job for now).
            // Nothing persisted — next page load will greet the user again.
            dismissInvite();
            const input = document.getElementById('aiChatInput');
            if (input) {
                // Defer focus so the slide-in transition can start first.
                setTimeout(() => input.focus({ preventScroll: true }), 220);
            }
        }
    };

    launcher.addEventListener('click', () => {
        const isOpen = widget.getAttribute('data-state') === 'open';
        setState(!isOpen);
    });

    if (closeBtn) {
        closeBtn.addEventListener('click', (e) => {
            e.preventDefault();
            setState(false);
            launcher.focus({ preventScroll: true });
        });
    }

    if (inviteCloseBtn) {
        inviteCloseBtn.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            dismissInvite();
        });
    }

    document.addEventListener('keydown', (e) => {
        if (e.key !== 'Escape') return;
        if (widget.getAttribute('data-state') !== 'open') return;
        setState(false);
        launcher.focus({ preventScroll: true });
    });
}

function sendAIMessage() {
    const chatInput = document.getElementById('aiChatInput');
    const message = chatInput.value.trim();
    
    if (!message) return;
    
    console.log('sendAIMessage called, currentSimulationId:', currentSimulationId);
    
    // Add user message
    addMessage('user', message);
    chatInput.value = '';
    
    // Show typing indicator
    showTypingIndicator();
    
    // Send to AI - use currentSimulationId if available, otherwise let AI use global portfolio state
    const requestBody = {
        question: message
    };
    
    // Only include simulation_id if we have one and it's not the test simulation
    if (currentSimulationId && currentSimulationId !== 'test-simulation-123') {
        requestBody.simulation_id = currentSimulationId;
    }
    
    // Send to AI
    fetch('/ai_analysis', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(requestBody)
    })
    .then(response => response.json())
    .then(data => {
        hideTypingIndicator();
        
        console.log('AI Response received:', data);
        console.log('Analysis content:', data.analysis);
        
        if (data.success) {
            addMessage('ai', data.analysis);
        } else {
            addMessage('ai', `Sorry, I encountered an error: ${data.error || 'Unknown error'}`);
        }
    })
    .catch(error => {
        hideTypingIndicator();
        addMessage('ai', `Sorry, I couldn't process your request. Please check your internet connection and try again.`);
        console.error('AI Chat Error:', error);
    });
}

function addMessage(sender, text) {
    console.log('addMessage called:', sender, text);
    const chatMessages = document.getElementById('aiChatMessages');
    if (!chatMessages) {
        console.log('chatMessages element not found');
        return;
    }
    
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${sender}-message`;
    
    const time = new Date().toLocaleTimeString();
    const lead =
        sender === 'ai'
            ? teebyChatAvatarHtml(false)
            : '<i class="fas fa-user" aria-hidden="true"></i>';

    messageDiv.innerHTML = `
        <div class="message-content">
            ${lead}
            <div class="message-text">${formatMessage(text)}</div>
        </div>
        <div class="message-time">${time}</div>
    `;
    
    chatMessages.appendChild(messageDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function formatMessage(text) {
    // Convert line breaks to HTML
    text = text.replace(/\n/g, '<br>');
    
    // Format bullet points
    text = text.replace(/\n- /g, '<br>• ');
    text = text.replace(/^- /g, '• ');
    
    // Format numbered lists
    text = text.replace(/\n(\d+)\. /g, '<br>$1. ');
    text = text.replace(/^(\d+)\. /g, '$1. ');
    
    return text;
}

function clearAIChat() {
    const chatMessages = document.getElementById('aiChatMessages');
    if (chatMessages) {
        const chatCollapse = document.getElementById('aiChatCollapse');
        if (chatCollapse) {
            chatCollapse.classList.add('show');
        }

        chatMessages.innerHTML = '';

        const welcomeMessage = document.createElement('div');
        welcomeMessage.className = 'message ai-message';
        welcomeMessage.innerHTML = `
                <div class="message-content">
                    ${teebyChatAvatarHtml(false)}
                    <div class="message-text">
                        Hi! I'm <strong>Teeby</strong>, your AI portfolio assistant. I can analyze your portfolio performance, share insights on your trading strategy, and suggest improvements. 
                        <br><br>
                        Try asking me questions like:
                        <ul>
                            <li>"How is my portfolio performing?"</li>
                            <li>"What are the risks in my current strategy?"</li>
                            <li>"How can I improve my diversification?"</li>
                            <li>"Should I adjust my trading rules?"</li>
                        </ul>
                    </div>
                </div>
                <div class="message-time" id="aiWelcomeTime">${new Date().toLocaleTimeString()}</div>
            `;

        chatMessages.appendChild(welcomeMessage);

        chatMessages.style.backgroundColor = '#d4edda';
        setTimeout(() => {
            chatMessages.style.backgroundColor = '';
        }, 1000);
    }

    const chatInput = document.getElementById('aiChatInput');
    if (chatInput) {
        chatInput.value = '';
    }

    fetch('/clear_chat', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({}),
    })
        .then((response) => response.json())
        .then((data) => {
            if (data.success) {
                const box = document.getElementById('aiChatMessages');
                if (box) {
                    const successDiv = document.createElement('div');
                    successDiv.className = 'alert alert-success alert-dismissible fade show';
                    successDiv.innerHTML = `
                        <i class="fas fa-check-circle"></i> Chat history cleared successfully!
                        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
                    `;
                    box.appendChild(successDiv);
                    setTimeout(() => {
                        if (successDiv.parentNode) {
                            successDiv.parentNode.removeChild(successDiv);
                        }
                    }, 3000);
                }
            } else {
                console.error('Failed to clear chat history:', data.error);
            }
        })
        .catch((error) => {
            console.error('Error clearing chat history:', error);
        });
}

function showTypingIndicator() {
    const chatMessages = document.getElementById('aiChatMessages');
    if (!chatMessages) return;
    
    const typingDiv = document.createElement('div');
    typingDiv.className = 'ai-typing';
    typingDiv.id = 'typingIndicator';
    typingDiv.innerHTML = `
        ${teebyChatAvatarHtml(true)}
        <div class="typing-dots">
            <div class="typing-dot"></div>
            <div class="typing-dot"></div>
            <div class="typing-dot"></div>
        </div>
    `;
    
    chatMessages.appendChild(typingDiv);
    typingDiv.style.display = 'flex';
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function hideTypingIndicator() {
    const typingIndicator = document.getElementById('typingIndicator');
    if (typingIndicator) {
        typingIndicator.remove();
    }
}

// Override the existing updateResults function to show AI advisor and plots
const originalUpdateResults = updateResults;
updateResults = function(data) {
    originalUpdateResults(data);
    checkForExecutedOneTimeRules(data);

    if (data.is_complete && currentSimulationId) {
        if (data.final_metrics) {
            showFinalResults(data);
            showAIAdvisor();
            showPlotsCard();
        } else {
            setTimeout(() => {
                fetch(`/simulation_status/${currentSimulationId}`)
                    .then((response) => response.json())
                    .then((freshData) => {
                        if (freshData.final_metrics) {
                            showFinalResults(freshData);
                            showAIAdvisor();
                            showPlotsCard();
                        }
                    })
                    .catch(() => {});
            }, 1000);
        }
    }
};

// Portfolio Plot Functions
function showPlotsCard() {
    console.log('showPlotsCard called');
    try {
        const plotsCard = document.getElementById('plotsCard');
        console.log('plotsCard element:', plotsCard);
        if (plotsCard) {
            plotsCard.style.display = 'block';
            // Intentionally NOT scrolling here — the chart card lives in the sidebar.
            // We want the page to stay on the metrics grid (scrolled into view by showFinalResults).

            // Load the default plot (portfolio value)
            console.log('Loading default plot...');
            loadPlot('value');
        } else {
            console.error('plotsCard element not found!');
        }
    } catch (error) {
        console.error('Error in showPlotsCard:', error);
    }
}


// ---------- Chart.js rendering ----------
// Cache the active chart and the last-fetched series so the user can swap plot
// types and toggle theme without re-hitting the backend.
let _activeChart = null;
let _chartCache = null; // { timestamps, values, original_value, trading_frequency }
let _currentPlotType = 'value';
// Benchmark overlays (visible on the percentage chart only).
const _benchmarkCache = {}; // { 'SPY': { name, percent_returns: [...] }, ... }
const _activeBenchmarks = new Set(); // canonical symbols currently overlaid
const _BENCHMARK_STYLES = {
    SPY: { name: 'S&P 500', dark: '#fbbf24', light: '#b45309' },
    QQQ: { name: 'NASDAQ',  dark: '#a78bfa', light: '#6d28d9' },
};

function _chartTheme() {
    const dark = (document.documentElement.getAttribute('data-theme') || 'dark') === 'dark';
    return dark
        ? {
            stroke: '#22d3ee',
            strokeStrong: '#0891b2',
            fillTop: 'rgba(34, 211, 238, 0.32)',
            fillBottom: 'rgba(34, 211, 238, 0.0)',
            grid: 'rgba(244, 244, 245, 0.07)',
            text: '#cbd5e1',
            textMuted: '#94a3b8',
            baseline: 'rgba(244, 244, 245, 0.45)',
            positive: '#34d399',
            negative: '#f87171',
            tooltipBg: 'rgba(12, 12, 14, 0.96)',
            tooltipBorder: '#3f3f46',
            tooltipText: '#f4f4f5',
        }
        : {
            stroke: '#0284c7',
            strokeStrong: '#4f46e5',
            fillTop: 'rgba(2, 132, 199, 0.22)',
            fillBottom: 'rgba(2, 132, 199, 0.0)',
            grid: 'rgba(15, 23, 42, 0.08)',
            text: '#334155',
            textMuted: '#64748b',
            baseline: 'rgba(15, 23, 42, 0.35)',
            positive: '#059669',
            negative: '#dc2626',
            tooltipBg: 'rgba(255, 255, 255, 0.98)',
            tooltipBorder: '#cbd5e1',
            tooltipText: '#0f172a',
        };
}

function _fmtCurrency(v) {
    const abs = Math.abs(v);
    const opts = abs >= 1000
        ? { maximumFractionDigits: 0 }
        : { maximumFractionDigits: 2 };
    return '$' + Number(v).toLocaleString(undefined, opts);
}

function _fmtSignedCurrency(v) {
    const sign = v >= 0 ? '+' : '-';
    return sign + _fmtCurrency(Math.abs(v));
}

function _fmtPercent(v) {
    const sign = v >= 0 ? '+' : '';
    return `${sign}${Number(v).toFixed(2)}%`;
}

function _fmtTimestampLabel(ts) {
    // Backend emits 'YYYY-MM-DD' or 'YYYY-MM-DD HH:MM'.
    if (!ts) return '';
    if (ts.length <= 10) return ts;
    return ts.slice(5).replace('T', ' '); // 'MM-DD HH:MM' — compact for axis
}

function _showPlotState(state) {
    const placeholder = document.getElementById('plotPlaceholder');
    const wrap = document.getElementById('plotCanvasWrap');
    const err = document.getElementById('plotError');
    if (placeholder) placeholder.style.display = state === 'placeholder' ? 'block' : 'none';
    if (wrap) wrap.style.display = state === 'chart' ? 'block' : 'none';
    if (err) err.style.display = state === 'error' ? 'block' : 'none';
}

function _renderChart(plotType) {
    if (!_chartCache || !_chartCache.timestamps.length) {
        _showPlotState('error');
        const err = document.getElementById('plotError');
        if (err) err.innerHTML = `
            <i class="fas fa-exclamation-triangle fa-lg mb-2"></i>
            <div class="small">No data points to plot yet — let the simulation run a bit longer.</div>`;
        return;
    }

    const canvas = document.getElementById('plotCanvas');
    if (!canvas || typeof Chart === 'undefined') return;

    const theme = _chartTheme();
    const { timestamps, values, original_value: baseline } = _chartCache;

    // Compute the series for the active plot type.
    // NOTE: value / percent / pnl are linear transforms of the same data, so the LINE SHAPE
    // is identical. We differentiate them stylistically: cyan area (value), diverging
    // green/red area split at 0% (percent), red/green bars (pnl).
    let series, label, yFormatter, tooltipValueFmt;
    let renderMode = 'line';        // 'line' | 'divergingLine' | 'bars'
    if (plotType === 'percentage') {
        series = values.map((v) => baseline ? ((v - baseline) / baseline) * 100 : 0);
        label = 'Portfolio Return';
        yFormatter = (v) => _fmtPercent(v);
        tooltipValueFmt = (v) => _fmtPercent(v);
        renderMode = 'divergingLine';
    } else if (plotType === 'pnl') {
        series = values.map((v) => v - baseline);
        label = 'P&L';
        yFormatter = (v) => _fmtSignedCurrency(v);
        tooltipValueFmt = (v) => _fmtSignedCurrency(v);
        renderMode = 'bars';
    } else {
        series = values.slice();
        label = 'Portfolio Value';
        yFormatter = (v) => _fmtCurrency(v);
        tooltipValueFmt = (v) => _fmtCurrency(v);
        renderMode = 'line';
    }

    // Build a vertical gradient fill from the canvas context.
    const ctx = canvas.getContext('2d');
    const wrap = document.getElementById('plotCanvasWrap');
    const h = (wrap && wrap.clientHeight) || 320;
    const cyanGradient = ctx.createLinearGradient(0, 0, 0, h);
    cyanGradient.addColorStop(0, theme.fillTop);
    cyanGradient.addColorStop(1, theme.fillBottom);

    const baselineAnnotationY = plotType === 'pnl' || plotType === 'percentage' ? 0 : baseline;

    // Per-renderMode dataset configuration.
    let primaryDataset;
    let chartType = 'line';
    if (renderMode === 'bars') {
        // P&L: red/green bars per interval.
        chartType = 'bar';
        primaryDataset = {
            label,
            data: series,
            backgroundColor: (c) => {
                const v = c.parsed && typeof c.parsed.y === 'number' ? c.parsed.y : 0;
                return v >= 0 ? hexToRgba(theme.positive, 0.85) : hexToRgba(theme.negative, 0.85);
            },
            hoverBackgroundColor: (c) => {
                const v = c.parsed && typeof c.parsed.y === 'number' ? c.parsed.y : 0;
                return v >= 0 ? theme.positive : theme.negative;
            },
            borderWidth: 0,
            borderRadius: 3,
            maxBarThickness: 24,
        };
    } else if (renderMode === 'divergingLine') {
        // Percentage: line with diverging green/red fill split at 0%.
        primaryDataset = {
            label,
            data: series,
            borderColor: theme.strokeStrong,
            backgroundColor: 'rgba(0,0,0,0)',
            borderWidth: 2,
            fill: {
                target: { value: 0 },
                above: hexToRgba(theme.positive, 0.22),
                below: hexToRgba(theme.negative, 0.22),
            },
            tension: 0.28,
            pointRadius: 0,
            pointHoverRadius: 5,
            pointHoverBackgroundColor: theme.strokeStrong,
            pointHoverBorderColor: '#fff',
            pointHoverBorderWidth: 2,
            spanGaps: true,
            segment: {
                borderColor: (c) => {
                    const y0 = c.p0.parsed.y;
                    const y1 = c.p1.parsed.y;
                    return (y0 + y1) / 2 >= 0 ? theme.positive : theme.negative;
                },
            },
        };
    } else {
        // Default: portfolio value as a smooth cyan area line.
        primaryDataset = {
            label,
            data: series,
            borderColor: theme.stroke,
            backgroundColor: cyanGradient,
            borderWidth: 2,
            fill: 'origin',
            tension: 0.28,
            pointRadius: 0,
            pointHoverRadius: 5,
            pointHoverBackgroundColor: theme.strokeStrong,
            pointHoverBorderColor: '#fff',
            pointHoverBorderWidth: 2,
            spanGaps: true,
        };
    }

    const chartConfig = {
        type: chartType,
        data: {
            labels: timestamps.map(_fmtTimestampLabel),
            datasets: [primaryDataset],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: theme.tooltipBg,
                    borderColor: theme.tooltipBorder,
                    borderWidth: 1,
                    titleColor: theme.tooltipText,
                    bodyColor: theme.tooltipText,
                    padding: 10,
                    displayColors: false,
                    callbacks: {
                        title: (items) => items.length ? timestamps[items[0].dataIndex] : '',
                        label: (c) => `  ${label}: ${tooltipValueFmt(c.parsed.y)}`,
                    },
                },
            },
            scales: {
                x: {
                    ticks: {
                        color: theme.textMuted,
                        maxRotation: 0,
                        autoSkip: false,
                        // Show only first and last X-axis labels to keep things tidy.
                        callback: function (value, index, allTicks) {
                            const last = allTicks.length - 1;
                            return index === 0 || index === last ? this.getLabelForValue(value) : '';
                        },
                    },
                    grid: { color: theme.grid, drawBorder: false },
                },
                y: {
                    ticks: {
                        color: theme.textMuted,
                        callback: (v) => yFormatter(v),
                    },
                    grid: { color: theme.grid, drawBorder: false },
                },
            },
        },
    };

    // Dashed baseline (original value for 'value', zero for percent/pnl).
    // Skip for bar mode — bars naturally anchor to 0.
    if (renderMode !== 'bars') {
        chartConfig.data.datasets.push({
            type: 'line',
            label: '_baseline',
            data: series.map(() => baselineAnnotationY),
            borderColor: theme.baseline,
            borderWidth: 1,
            borderDash: [4, 4],
            pointRadius: 0,
            pointHoverRadius: 0,
            fill: false,
            tension: 0,
            order: 99,
        });
        chartConfig.options.plugins.tooltip.filter = (item) => item.dataset.label !== '_baseline';
    }

    // Overlay benchmarks on the percentage chart (S&P 500, NASDAQ).
    if (renderMode === 'divergingLine' && _activeBenchmarks.size > 0) {
        const isDark = (document.documentElement.getAttribute('data-theme') || 'dark') === 'dark';
        _activeBenchmarks.forEach((sym) => {
            const benchmark = _benchmarkCache[sym];
            if (!benchmark || !Array.isArray(benchmark.percent_returns)) return;
            const style = _BENCHMARK_STYLES[sym] || { name: sym, dark: '#cbd5e1', light: '#475569' };
            const color = isDark ? style.dark : style.light;
            chartConfig.data.datasets.push({
                type: 'line',
                label: style.name,
                data: benchmark.percent_returns,
                borderColor: color,
                backgroundColor: 'rgba(0,0,0,0)',
                borderWidth: 1.75,
                fill: false,
                tension: 0.28,
                pointRadius: 0,
                pointHoverRadius: 4,
                pointHoverBackgroundColor: color,
                pointHoverBorderColor: '#fff',
                pointHoverBorderWidth: 2,
                spanGaps: true,
                order: 50,
            });
        });
        // Re-enable colored swatches in the tooltip so the user sees which line is which.
        chartConfig.options.plugins.tooltip.displayColors = true;
        chartConfig.options.plugins.tooltip.callbacks.label = (c) => {
            // Format portfolio in percent (same as Y axis), benchmarks too (already %).
            if (c.dataset.label === '_baseline') return null;
            const v = c.parsed.y;
            return v == null
                ? `  ${c.dataset.label}: —`
                : `  ${c.dataset.label}: ${_fmtPercent(v)}`;
        };
    }

    if (_activeChart) {
        _activeChart.destroy();
        _activeChart = null;
    }
    _activeChart = new Chart(ctx, chartConfig);
    _showPlotState('chart');
}

function hexToRgba(hex, alpha) {
    // Accepts #rgb / #rrggbb / rgb()/rgba(); falls through if already rgba.
    if (!hex) return `rgba(0,0,0,${alpha})`;
    if (hex.startsWith('rgba') || hex.startsWith('rgb(')) return hex;
    let h = hex.replace('#', '');
    if (h.length === 3) h = h.split('').map((c) => c + c).join('');
    const r = parseInt(h.slice(0, 2), 16);
    const g = parseInt(h.slice(2, 4), 16);
    const b = parseInt(h.slice(4, 6), 16);
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

function _updateBenchmarkChipsVisibility() {
    const wrap = document.getElementById('benchmarkOverlays');
    if (!wrap) return;
    wrap.style.display = _currentPlotType === 'percentage' ? 'flex' : 'none';
}

function _setBenchmarkChipActive(sym, active) {
    const chip = document.querySelector(`.benchmark-chip[data-benchmark="${sym}"]`);
    if (chip) chip.classList.toggle('active', !!active);
}

function _setBenchmarkChipLoading(sym, loading) {
    const chip = document.querySelector(`.benchmark-chip[data-benchmark="${sym}"]`);
    if (chip) chip.classList.toggle('is-loading', !!loading);
}

async function _ensureBenchmarkLoaded(sym) {
    if (_benchmarkCache[sym]) return true;
    const url = (currentSimulationId && currentSimulationId !== 'test-simulation-123')
        ? `/benchmark_data/${currentSimulationId}/${sym}`
        : `/benchmark_data/current/${sym}`;
    _setBenchmarkChipLoading(sym, true);
    try {
        const res = await fetch(url);
        const data = await res.json();
        if (data && data.success && Array.isArray(data.percent_returns)) {
            _benchmarkCache[sym] = data;
            return true;
        }
        console.warn('Benchmark fetch failed:', data && data.error);
        return false;
    } catch (e) {
        console.error('Benchmark fetch error:', e);
        return false;
    } finally {
        _setBenchmarkChipLoading(sym, false);
    }
}

async function _toggleBenchmark(sym) {
    if (_currentPlotType !== 'percentage') return;
    if (_activeBenchmarks.has(sym)) {
        _activeBenchmarks.delete(sym);
        _setBenchmarkChipActive(sym, false);
        _renderChart(_currentPlotType);
        return;
    }
    const ok = await _ensureBenchmarkLoaded(sym);
    if (!ok) return;
    _activeBenchmarks.add(sym);
    _setBenchmarkChipActive(sym, true);
    _renderChart(_currentPlotType);
}

// Wire up chip clicks once (idempotent across hot reloads).
if (!window.__benchmarkChipsBound) {
    window.__benchmarkChipsBound = true;
    document.addEventListener('click', (ev) => {
        const chip = ev.target.closest('.benchmark-chip');
        if (!chip) return;
        const sym = chip.getAttribute('data-benchmark');
        if (sym) _toggleBenchmark(sym);
    });
}

function loadPlot(plotType) {
    _currentPlotType = plotType;
    _updateBenchmarkChipsVisibility();
    try {
        const plotLoading = document.getElementById('plotLoading');

        document.querySelectorAll('[data-plot-type]').forEach((btn) => btn.classList.remove('active'));
        const activeBtn = document.querySelector(`[data-plot-type="${plotType}"]`);
        if (activeBtn) activeBtn.classList.add('active');

        if (plotLoading) plotLoading.style.display = 'block';
        _showPlotState('placeholder');

        const url = (currentSimulationId && currentSimulationId !== 'test-simulation-123')
            ? `/chart_data/${currentSimulationId}`
            : `/chart_data/current`;

        fetch(url)
            .then((response) => response.json())
            .then((data) => {
                if (data && data.success) {
                    _chartCache = data;
                    _renderChart(plotType);
                } else {
                    _chartCache = null;
                    _showPlotState('error');
                    const err = document.getElementById('plotError');
                    if (err) err.innerHTML = `
                        <i class="fas fa-exclamation-triangle fa-lg mb-2"></i>
                        <div class="small">Couldn't load chart data${data && data.error ? `: ${data.error}` : ''}.</div>
                        <small class="text-dark">Run a simulation to completion to generate charts.</small>`;
                }
            })
            .catch((error) => {
                console.error('Error loading chart data:', error);
                _chartCache = null;
                _showPlotState('error');
                const err = document.getElementById('plotError');
                if (err) err.innerHTML = `
                    <i class="fas fa-exclamation-triangle fa-lg mb-2"></i>
                    <div class="small">Failed to reach the server.</div>`;
            })
            .finally(() => {
                if (plotLoading) plotLoading.style.display = 'none';
            });
    } catch (error) {
        console.error('Error in loadPlot:', error);
    }
}

// Re-render the active chart when the user toggles light/dark so colors stay on-brand.
(function watchThemeForCharts() {
    if (typeof MutationObserver === 'undefined') return;
    const obs = new MutationObserver((muts) => {
        for (const m of muts) {
            if (m.attributeName === 'data-theme' && _chartCache) {
                _renderChart(_currentPlotType);
                break;
            }
        }
    });
    obs.observe(document.documentElement, { attributes: true });
})();

// Make clearAIChat function globally accessible for testing
window.clearAIChat = clearAIChat;

/* =========================================================================
   Import Strategy (Trading Dashboard)
   -------------------------------------------------------------------------
   Editing happens in /strategy_studio. Here the user just picks a saved
   strategy out of the same localStorage list, hits Run, and we POST its code
   to /run_strategy seeded with the dashboard's "Initial Cash Deposit".
   ========================================================================= */

const STRATEGY_STORAGE_KEY = 'tradesphere_strategies_v1';

function loadSavedStrategies() {
    try {
        const raw = localStorage.getItem(STRATEGY_STORAGE_KEY);
        const list = raw ? JSON.parse(raw) : [];
        return Array.isArray(list) ? list : [];
    } catch (_e) {
        return [];
    }
}

function initImportStrategy() {
    // The Imported pane is preview-only on the dashboard. Execution lives on
    // the Live Trading page; here the user just picks a saved strategy out
    // of localStorage and sees its code so they know what's loaded.
    const select = document.getElementById('importStrategySelect');
    const preview = document.getElementById('importStrategyPreview');
    const previewCode = document.getElementById('importStrategyPreviewCode');
    const liveLink = document.getElementById('importStrategyLiveLink');
    const openStudioLink = document.getElementById('openStudioLink');
    if (!select || !preview || !previewCode) return;

    // Keep the Studio + Live Trading shortcuts theme-synced.
    const currentTheme = () =>
        document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';
    if (openStudioLink) {
        try {
            openStudioLink.setAttribute('href', `/strategy_studio?embed=1&theme=${currentTheme()}`);
        } catch (_e) { /* ignore */ }
    }
    if (liveLink) {
        try {
            liveLink.setAttribute('href', `/live_trading?embed=1&theme=${currentTheme()}`);
        } catch (_e) { /* ignore */ }
    }

    function escapeHtml(s) {
        return String(s).replace(/[&<>"']/g, (c) =>
            ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])
        );
    }

    function showPreview() {
        const id = select.value;
        const s = loadSavedStrategies().find((x) => x.id === id);
        if (!s) {
            preview.hidden = true;
            previewCode.textContent = '';
            return;
        }
        previewCode.textContent = s.code || '';
        preview.hidden = false;
    }

    function refresh() {
        const list = loadSavedStrategies()
            .slice()
            .sort((a, b) => (b.updated_at || 0) - (a.updated_at || 0));
        const previousId = select.value;
        if (list.length === 0) {
            select.innerHTML = '<option value="">— No saved strategies —</option>';
            preview.hidden = true;
            previewCode.textContent = '';
            return;
        }
        select.innerHTML = list
            .map((s) => `<option value="${s.id}">${escapeHtml(s.name)}${s.compiled ? '' : ' (uncompiled)'}</option>`)
            .join('');
        const keep = list.find((s) => s.id === previousId);
        select.value = keep ? previousId : list[0].id;
        showPreview();
    }

    select.addEventListener('change', showPreview);

    // Refresh when the user comes back to this tab (e.g. after saving a new
    // strategy in the Studio in another tab) or storage gets mutated.
    window.addEventListener('focus', refresh);
    window.addEventListener('storage', (e) => {
        if (e.key === STRATEGY_STORAGE_KEY) refresh();
    });

    refresh();
}

// `renderImportOutput` (previously rendered the dashboard's inline import-run
// output) has been retired — the dashboard no longer executes imported code.
// Live Trading renders its own log via static/js/live_trading.js.
