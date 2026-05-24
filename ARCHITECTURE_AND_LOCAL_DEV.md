# Architecture and local development

How the Next.js shell, Flask trading API/UI, and Render deployment fit together.

## Architecture

- **Frontend**: Next.js application running on port 3000
- **Backend**: Flask application running on port 5002
- **Integration**: The frontend displays the Flask app in an iframe when "Execute Trade" is clicked

## Features

### Frontend (Next.js)
- Main page with typing animation
- Responsive design with Tailwind CSS
- Smooth transition to trading platform
- Back button to return to the main page

### Backend (Flask)
- Portfolio simulation engine
- Real-time stock data integration
- AI-powered portfolio analysis (Cerebras API)
- Interactive trading rules configuration
- Performance metrics and charts
- Beta hedging capabilities

## Production

Code lives on **GitHub**; **Render** should run **two** Web Services from this repo: Flask (`render.yaml`) and Next.js (`render-frontend.yaml`). Share the **Next.js** URL with users so they see the intro first; the Flask URL is loaded in an iframe after **Execute Trades**. See **README.md** for `NEXT_PUBLIC_FLASK_BACKEND_URL` and `SHELL_SITE_URL`.

## Quick Start (local)

### Option 1: One command from repo root (recommended)
```bash
npm install   # once, at repository root
npm run dev   # starts Flask (5002) and Next.js (3000) together
```

### Option 2: Shell script
```bash
./dev_start_fullstack.sh
```
(Run from the repository root.)

### Option 3: Manual (two terminals)

1. **Flask** (listens on `127.0.0.1:5002` by default):
   ```bash
   pip install -r requirements.txt
   FLASK_ENV=development python3 flask_backend.py
   ```

2. **Next.js** (`npm run dev` in `frontend/` starts **both** Next and Flask via `concurrently`; the iframe uses `http://127.0.0.1:5002` in development):
   ```bash
   cd frontend
   npm install
   npm run dev
   ```

   Flask-only in another terminal: from repo root, `npm run backend:dev`. Next-only in `frontend/`: `npm run dev:next` (then you must run Flask separately).

3. **Access the application:**
   - Frontend: http://localhost:3000
   - Backend: http://localhost:5002

## How It Works

1. **Main page**: Users see the Next.js main page with animated code examples
2. **Execute Trade Button**: Clicking this button reveals the Flask trading platform in an iframe
3. **Trading Platform**: Full-featured portfolio simulation with:
   - Portfolio configuration
   - Trading rules setup
   - Real-time simulation
   - AI analysis
   - Performance charts
4. **Back Button**: Users can return to the main page anytime

## Configuration

### Flask Backend
- Port: 5002
- CORS enabled for iframe integration
- AI analysis powered by Cerebras API (optional)

### Next.js Frontend
- Port: 3000
- Tailwind CSS for styling
- Typing animation component
- Responsive iframe integration

## Dependencies

### Backend (Python)
- Flask 2.3.3
- flask-cors 4.0.0+
- yfinance for stock data
- matplotlib for charts
- pandas for data processing
- requests for API calls

### Frontend (Node.js)
- Next.js 15.5.3
- React 19.1.0
- Tailwind CSS 4.1.13
- Motion for animations
- TypeScript support

## Troubleshooting

1. **Iframe not loading**: Ensure Flask backend is running on port 5002
2. **CORS errors**: Make sure flask-cors is installed and enabled
3. **Port conflicts**: Check if ports 3000 or 5002 are already in use
4. **Dependencies**: Run `pip install -r requirements.txt` and `npm install` in the frontend directory

## Development

- Frontend code: `/frontend/src/app/`
- Backend code: `/flask_backend.py`
- Static assets: `/static/`
- Templates: `/templates/`

## API Endpoints

The Flask backend provides several API endpoints:
- `GET /` - Main trading interface
- `POST /start_simulation` - Start portfolio simulation
- `GET /simulation_status/<id>` - Get simulation status
- `POST /ai_analysis` - Get AI portfolio analysis
- `GET /chart_data/<id>` - Portfolio time series for Chart.js

## Security Notes

- The iframe uses sandbox attributes for security
- CORS is configured to allow iframe embedding
- API endpoints are protected with proper error handling
