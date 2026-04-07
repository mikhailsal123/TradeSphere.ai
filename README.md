# TradeSphere.ai

A sophisticated portfolio simulation and trading platform with AI-powered insights.

## Features

- **Real-time Portfolio Simulation**: Test trading strategies with historical data
- **Multiple Time Intervals**: Daily, hourly, 15-minute, 5-minute, and 1-minute simulations
- **AI Portfolio Advisor**: Get intelligent insights and recommendations
- **Advanced Trading Rules**: Set automated buy/sell conditions
- **Risk Management**: Beta hedging and portfolio optimization
- **Interactive Charts**: Visualize performance and trends

## Deployment (Render + GitHub)

Use **two** Render Web Services from the same GitHub repo (different names, different URLs):

1. **Flask backend** — `render.yaml` (`gunicorn flask_backend:app`). Serves the trading UI only when opened with `?embed=1` or inside an iframe, so people who open the backend URL directly see a short notice instead of skipping the intro.
2. **Next.js frontend** — `render-frontend.yaml` (`npm run build` / `npm start` in `frontend/`). This is the URL you share with users: **intro first**, then **Execute Trades** loads the Flask app in an iframe.

**Required on the Next.js service:** set `NEXT_PUBLIC_FLASK_BACKEND_URL` to the **Flask** service URL (no trailing slash), then trigger a new deploy so the client bundle picks it up.

**Optional on the Flask service:** set `SHELL_SITE_URL` to your **Next.js** URL so the backend’s stub page includes a “Go to intro” button.

Local production build: `./set_next_iframe_backend_url.sh https://your-flask.onrender.com` then `cd frontend && npm run build`.

Helper checklists: `./render_backend_setup_hints.sh` and `./render_frontend_setup_hints.sh`.

## Local Development

### Prerequisites
- Python 3.8+
- Node.js 16+

### Backend Setup
```bash
# Install Python dependencies
pip install -r requirements.txt

# Set up environment variables
export CEREBRAS_TOKEN="your-cerebras-token-here"

# Run the Flask server
python3 flask_backend.py
```

Optional: run the standalone terminal portfolio demo with `python3 portfolio_simulation_demo.py`. For how the Next shell and Flask app connect, see `ARCHITECTURE_AND_LOCAL_DEV.md`.

### Frontend Setup
```bash
# Navigate to frontend directory
cd frontend

# Install dependencies
npm install

# Starts Next.js and Flask together (Flask on 127.0.0.1:5002)
npm run dev
```

From the **repository root**, the same thing:

```bash
npm install
npm run dev
```

Next.js-only (you must start Flask yourself, e.g. `npm run backend:dev` from the repo root): `npm run dev:next` inside `frontend/`.

If Flask runs on another host/port locally, set `NEXT_PUBLIC_FLASK_DEV_URL` in `frontend/.env.development.local` (only used when `next dev` is running).

## Technology Stack

- **Backend**: Python Flask, yfinance, pandas; trading UI in Jinja templates + `static/`
- **Main page shell**: Next.js (React) in `frontend/`, embeds the Flask app in an iframe
- **AI**: Cerebras API for portfolio analysis (optional)
- **Charts**: Chart.js in the Flask UI; matplotlib on the server where used

## API Endpoints

- `POST /start_simulation` - Start a new portfolio simulation
- `GET /simulation_status/<id>` - Get simulation progress
- `POST /ai_analysis` - Get AI portfolio insights
- `GET /validate_ticker/<ticker>` - Validate stock ticker symbols

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## License

MIT License - see LICENSE file for details

## Support

For questions or support, please open an issue on GitHub.