let currentSimulationId = null;
let statusInterval = null;
let aiChatVisible = false;

function teebyChatAvatarHtml(small) {
    const light =
        typeof window.TEEBY_CHAT_AVATAR_LIGHT_URL === 'string' && window.TEEBY_CHAT_AVATAR_LIGHT_URL
            ? window.TEEBY_CHAT_AVATAR_LIGHT_URL
            : '/static/img/teeby-chat-light.jpg';
    const dark =
        typeof window.TEEBY_CHAT_AVATAR_DARK_URL === 'string' && window.TEEBY_CHAT_AVATAR_DARK_URL
            ? window.TEEBY_CHAT_AVATAR_DARK_URL
            : '/static/img/teeby-chat-dark.jpg';
    const wrapCls = 'teeby-chat-avatar-wrap' + (small ? ' teeby-chat-avatar-wrap--sm' : '');
    const dim = small ? 62 : 84;
    return (
        '<span class="' +
        wrapCls +
        '" aria-hidden="true">' +
        '<img class="teeby-chat-img teeby-chat-img--light" src="' +
        light +
        '" alt="" width="' +
        dim +
        '" height="' +
        dim +
        '" loading="lazy" decoding="async">' +
        '<img class="teeby-chat-img teeby-chat-img--dark" src="' +
        dark +
        '" alt="" width="' +
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

    // Duration slider update
    const durationSlider = document.getElementById('durationDays');
    const durationValue = document.getElementById('durationValue');
    
    if (durationSlider && durationValue) {
        durationSlider.addEventListener('input', function() {
            updateDurationLimits();
        });
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
});

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
    startBtn.innerHTML = '<span class="loading-spinner"></span> Starting...';
    progressCard.style.display = 'block';
    
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
        
        // Add new results
        const latestResults = data.results.slice(-5); // Show last 5 days
        latestResults.forEach(result => {
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
                <div class="portfolio-value">$${(result.portfolio_value != null ? Number(result.portfolio_value) : 0).toLocaleString()}</div>
                <small class="text-dark">P&L: $${result.pnl != null ? Number(result.pnl).toFixed(2) : '0.00'}</small>
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
    
    try {
        if (data.final_metrics) {
            console.log('📊 Final metrics found:', data.final_metrics);
            console.log('💰 Final value:', data.final_metrics.final_value, 'type:', typeof data.final_metrics.final_value);
            console.log('📈 Total return:', data.final_metrics.total_return_pct, 'type:', typeof data.final_metrics.total_return_pct);
            console.log('⚡ Sharpe ratio:', data.final_metrics.sharpe_ratio, 'type:', typeof data.final_metrics.sharpe_ratio);
            console.log('📊 Beta:', data.final_metrics.beta, 'type:', typeof data.final_metrics.beta);
            
            const finalMetricsCard = document.getElementById('finalMetricsCard');
            const finalMetrics = document.getElementById('finalMetrics');
            console.log('Final metrics card element:', finalMetricsCard);
            console.log('Final metrics element:', finalMetrics);
            
            finalMetrics.innerHTML = `
            <div class="col-md-3">
                <div class="metric-card">
                    <div class="metric-value">$${isNaN(data.final_metrics.final_value) ? 'N/A' : data.final_metrics.final_value.toLocaleString()}</div>
                    <div class="metric-label">Final Value</div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="metric-card">
                    <div class="metric-value ${data.final_metrics.total_return_pct >= 0 ? 'positive' : 'negative'}">
                        ${data.final_metrics.total_return_pct >= 0 ? '+' : ''}${data.final_metrics.total_return_pct}%
                    </div>
                    <div class="metric-label">Total Return</div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="metric-card">
                    <div class="metric-value ${data.final_metrics.total_pnl >= 0 ? 'positive' : 'negative'}">
                        $${isNaN(data.final_metrics.total_pnl) ? 'N/A' : data.final_metrics.total_pnl.toLocaleString()}
                    </div>
                    <div class="metric-label">Total P&L</div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="metric-card">
                    <div class="metric-value">
                        ${isNaN(data.final_metrics.sharpe_ratio) ? 'N/A' : data.final_metrics.sharpe_ratio.toFixed(3)}
                    </div>
                    <div class="metric-label">Sharpe Ratio</div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="metric-card">
                    <div class="metric-value">
                        ${isNaN(data.final_metrics.beta) ? 'N/A' : data.final_metrics.beta.toFixed(3)}
                    </div>
                    <div class="metric-label">Beta</div>
                    ${data.final_metrics.beta_interpretation ? `<div class="metric-subtitle">${data.final_metrics.beta_interpretation.replace(/</g, '&lt;').replace(/>/g, '&gt;')}</div>` : ''}
                </div>
            </div>
            <div class="col-md-3">
                <div class="metric-card">
                    <div class="metric-value">
                        ${isNaN(data.final_metrics.correlation) ? 'N/A' : data.final_metrics.correlation.toFixed(3)}
                    </div>
                    <div class="metric-label">Market Correlation</div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="metric-card">
                    <div class="metric-value">
                        ${data.final_metrics.hedge_trades_count || 0}
                    </div>
                    <div class="metric-label">Hedge Trades</div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="metric-card">
                    <div class="metric-value">
                        $${isNaN(data.final_metrics.total_hedge_margin_used) ? '0' : data.final_metrics.total_hedge_margin_used.toLocaleString()}
                    </div>
                    <div class="metric-label">Margin Used</div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="metric-card">
                    <div class="metric-value">
                        $${isNaN(data.final_metrics.hedge_margin_remaining) ? '0' : data.final_metrics.hedge_margin_remaining.toLocaleString()}
                    </div>
                    <div class="metric-label">Margin Remaining</div>
                </div>
            </div>
        `;
        
        
            finalMetricsCard.style.display = 'block';
            console.log('Final metrics card should now be visible');
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

    const formData = {
        initial_cash: parseFloat(document.getElementById('initialCash').value),
        duration_days: duration_days,
        duration_hours: duration_hours,
        start_date: startDateStr,
        trading_frequency: tradingFrequency,
        tickers: tickers,
        trading_rules: tradingRules,
        beta_hedge_enabled: document.getElementById('betaHedgeEnabled').checked
    };
    
    return formData;
}

function validateForm(data) {
    if (data.tickers.length === 0) {
        alert('Please add at least one stock to trade.');
        return false;
    }
    
    if (data.initial_cash < 1000) {
        alert('Initial cash must be at least $1,000.');
        return false;
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
    
    // Validate portfolio value doesn't exceed initial cash
    const portfolioValidation = validatePortfolioValue(data);
    if (!portfolioValidation.isValid) {
        alert(portfolioValidation.message);
        return false;
    }
    
    return true;
}

function validatePortfolioValue(data) {
    const initialCash = data.initial_cash;
    let totalValue = 0;
    let issues = [];
    
    // Check initial positions
    data.tickers.forEach(ticker => {
        if (ticker.shares && ticker.shares > 0) {
            // Estimate value using average stock prices (rough estimates)
            const estimatedPrice = getEstimatedStockPrice(ticker.ticker);
            const positionValue = estimatedPrice * ticker.shares;
            totalValue += positionValue;
            
            if (positionValue > initialCash * 0.5) {
                issues.push(`${ticker.ticker}: ${ticker.shares} shares ≈ $${positionValue.toLocaleString()} (${(positionValue/initialCash*100).toFixed(1)}% of portfolio)`);
            }
        }
    });
    
    // Check trading rules for potential large purchases
    data.trading_rules.forEach(rule => {
        if (rule.action === 'buy' && rule.shares && rule.threshold) {
            const estimatedPrice = getEstimatedStockPrice(rule.ticker);
            const potentialCost = estimatedPrice * rule.shares;
            
            if (potentialCost > initialCash * 0.3) {
                issues.push(`Buy rule for ${rule.ticker}: ${rule.shares} shares ≈ $${potentialCost.toLocaleString()} (${(potentialCost/initialCash*100).toFixed(1)}% of portfolio)`);
            }
        }
    });
    
    // Check if total estimated value exceeds initial cash
    if (totalValue > initialCash) {
        return {
            isValid: false,
            message: `Portfolio value ($${totalValue.toLocaleString()}) exceeds initial cash ($${initialCash.toLocaleString()}). Please reduce position sizes or increase initial cash.`
        };
    }
    
    return {
        isValid: true,
        message: 'Portfolio validation passed.'
    };
}

function getEstimatedStockPrice(ticker) {
    // Rough estimates for common stocks (in USD)
    const priceEstimates = {
        'AAPL': 150, 'MSFT': 300, 'GOOGL': 140, 'AMZN': 120, 'TSLA': 200,
        'NVDA': 800, 'META': 300, 'NFLX': 400, 'GOOG': 140, 'BRK.A': 500000,
        'BRK.B': 350, 'JPM': 150, 'JNJ': 160, 'V': 250, 'PG': 150,
        'UNH': 500, 'HD': 300, 'MA': 400, 'DIS': 100, 'PYPL': 60
    };
    
    return priceEstimates[ticker] || 100; // Default to $100 if unknown
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
            help: 'Daily closes · max 365 days',
        },
        '1m': {
            mode: 'hours',
            min: 1,
            max: 6,
            fallback: 3,
            title: 'Hours of the trading day to include',
            unit: 'hours',
            help: '1m bars · slider = session hours (max 6)',
        },
        '5m': {
            mode: 'hours',
            min: 1,
            max: 12,
            fallback: 6,
            title: 'Hours of the trading day to include',
            unit: 'hours',
            help: '5m bars · max 12 hours',
        },
        '15m': {
            mode: 'hours',
            min: 1,
            max: 24,
            fallback: 8,
            title: 'Hours to cover (up to one day)',
            unit: 'hours',
            help: '15m bars · max 24 hours',
        },
        '60m': {
            mode: 'days',
            min: 1,
            max: 7,
            fallback: 3,
            title: 'Calendar days',
            unit: 'days',
            help: 'Hourly bars · max 7 days',
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

    durationValue.textContent = String(v);
    durationUnit.textContent = p.unit;
    if (durationLabelTitle) {
        durationLabelTitle.textContent = p.title;
    }
    const unitWord = (n) => {
        if (p.unit === 'hours') return n === 1 ? 'hour' : 'hours';
        return n === 1 ? 'day' : 'days';
    };
    minDuration.textContent = `${p.min} ${unitWord(p.min)}`;
    maxDuration.textContent = `${p.max} ${unitWord(p.max)}`;
    frequencyHelp.textContent = p.help;

    const now = new Date();
    if (p.mode === 'days') {
        const span = parseInt(durationSlider.value, 10) || p.fallback;
        const st = new Date(now.getFullYear(), now.getMonth(), now.getDate() - span);
        dateRangeInfo.innerHTML = `
            <strong>${st.toLocaleDateString()}</strong> → <strong>${now.toLocaleDateString()}</strong>
            <br><small class="text-muted">~${span} days</small>`;
    } else {
        const h = parseInt(durationSlider.value, 10) || p.fallback;
        dateRangeInfo.innerHTML = `
            <strong>~${h}h</strong> intraday
            <br><small class="text-muted">Recent sessions; provider limits may apply</small>`;
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
    // Find or create validation status element
    let statusElement = document.getElementById('portfolioValidationStatus');
    if (!statusElement) {
        statusElement = document.createElement('div');
        statusElement.id = 'portfolioValidationStatus';
        statusElement.className = 'alert alert-info mt-2';
        
        // Insert after the tickers container
        const tickersContainer = document.getElementById('tickersContainer');
        if (tickersContainer) {
            tickersContainer.parentNode.insertBefore(statusElement, tickersContainer.nextSibling);
        }
    }
    
    if (validation.isValid) {
        statusElement.className = 'alert alert-success mt-2';
        statusElement.innerHTML = '<i class="fas fa-check-circle"></i> Portfolio validation passed';
    } else {
        statusElement.className = 'alert alert-warning mt-2';
        statusElement.innerHTML = `<i class="fas fa-exclamation-triangle" title="${validation.message}"></i> ${validation.message}`;
    }
}

function resetForm() {
    const startBtn = document.getElementById('startBtn');
    const stopBtn = document.getElementById('stopBtn');
    
    startBtn.disabled = false;
    startBtn.innerHTML = '<i class="fas fa-play"></i> Start Simulation';
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
    console.log('showAIAdvisor called, currentSimulationId:', currentSimulationId);
    const aiAdvisorCard = document.getElementById('aiAdvisorCard');
    if (aiAdvisorCard) {
        console.log('Showing AI advisor card');
        aiAdvisorCard.style.display = 'block';
        
        // Auto-expand chat if not visible
        if (!aiChatVisible) {
            const chatCollapse = document.getElementById('aiChatCollapse');
            if (chatCollapse && !chatCollapse.classList.contains('show')) {
                const collapseInstance = new bootstrap.Collapse(chatCollapse, {show: true});
                aiChatVisible = true;
            }
        }
    } else {
        console.log('AI advisor card not found or no simulation ID');
    }
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
            plotsCard.scrollIntoView({ behavior: 'smooth', block: 'start' });
            
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


function loadPlot(plotType) {
    console.log('loadPlot called with plotType:', plotType);
    try {
        const plotContainer = document.getElementById('plotContainer');
        const plotLoading = document.getElementById('plotLoading');
        
        if (!plotContainer || !plotLoading) {
            console.error('plotContainer or plotLoading not found');
            return;
        }
    
    // Show loading indicator
    plotLoading.style.display = 'block';
    plotContainer.style.display = 'none';
    
    // Update button states
    document.querySelectorAll('[data-plot-type]').forEach(btn => {
        btn.classList.remove('active');
    });
    document.querySelector(`[data-plot-type="${plotType}"]`).classList.add('active');
    
    // Determine which endpoint to use
    let plotUrl;
    if (currentSimulationId && currentSimulationId !== 'test-simulation-123') {
        plotUrl = `/plot/${currentSimulationId}/${plotType}`;
    } else {
        plotUrl = `/plot/current/${plotType}`;
    }
    
    // Fetch the plot
    fetch(plotUrl)
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                // Display the plot
                plotContainer.innerHTML = `<img src="${data.image}" alt="${plotType} plot" class="img-fluid">`;
                plotContainer.style.display = 'block';
            } else {
                // Show error message
                plotContainer.innerHTML = `
                    <div class="text-center text-danger">
                        <i class="fas fa-exclamation-triangle fa-2x mb-2"></i>
                        <p>Error loading plot: ${data.error}</p>
                        <small class="text-dark">Make sure your simulation has completed successfully.</small>
                    </div>
                `;
                plotContainer.style.display = 'block';
            }
        })
        .catch(error => {
            console.error('Error loading plot:', error);
            plotContainer.innerHTML = `
                <div class="text-center text-danger">
                    <i class="fas fa-exclamation-triangle fa-2x mb-2"></i>
                    <p>Failed to load plot. Please try again.</p>
                </div>
            `;
            plotContainer.style.display = 'block';
        })
        .finally(() => {
            plotLoading.style.display = 'none';
        });
    } catch (error) {
        console.error('Error in loadPlot:', error);
    }
}

// Make clearAIChat function globally accessible for testing
window.clearAIChat = clearAIChat;
