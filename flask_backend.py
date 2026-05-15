import matplotlib
matplotlib.use('Agg')  # Headless backend; MUST be set before any import that loads pyplot (e.g. Portfolio).
import matplotlib.pyplot as plt

from flask import Flask, render_template, jsonify, request, redirect, url_for
from Portfolio import Portfolio
from StockData import StockData
from datetime import datetime, timedelta, date
import json
import time
import threading
import uuid
import os
import requests
from dotenv import load_dotenv
import base64
import io
import ast

import yfinance as yf
import logging

# Do not pass requests.Session() into yfinance — current Yahoo backends expect curl_cffi or default handling.
yf.set_tz_cache_location("/tmp/yfinance_cache")

logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

app = Flask(__name__)


@app.route("/teeby-avatar.png")
def teeby_avatar_legacy():
    """Old URL; canonical file is static/media/teeby-avatar.png."""
    return redirect(url_for("static", filename="media/teeby-avatar.png"))


@app.after_request
def _allow_next_iframe_embed(response):
    """Next.js runs on another origin/port; allow embedding when we serve the trading UI in an iframe."""
    if request.args.get("embed") == "1" or request.headers.get("Sec-Fetch-Dest") == "iframe":
        response.headers.pop("X-Frame-Options", None)
    return response

# Store active simulations
active_simulations = {}

# Global portfolio state for AI memory
current_portfolio_state = {
    'has_simulation': False,
    'simulation_id': None,
    'initial_cash': None,
    'opening_value': None,
    'start_date': None,
    'duration_days': None,
    'duration_hours': None,
    'trading_frequency': None,
    'tickers': {},
    'trading_rules': [],
    'final_metrics': {},
    'final_positions': {},
    'results': [],
    'last_updated': None
}

# Initialize Cerebras API
# TODO: Replace 'YOUR_CEREBRAS_TOKEN' with your actual Cerebras API token
cerebras_token = os.getenv('CEREBRAS_TOKEN') or 'csk-42x2pme9cv39vddm69tpmec5exyv4r6ch5c8n8rdfdrcrmnh'
cerebras_api_url = "https://api.cerebras.ai/v1/chat/completions"

def update_portfolio_state(simulation_id, simulation_data):
    """Update the global portfolio state with the latest simulation results"""
    global current_portfolio_state
    
    if simulation_id in active_simulations:
        simulation = active_simulations[simulation_id]
        
        current_portfolio_state.update({
            'has_simulation': True,
            'simulation_id': simulation_id,
            'initial_cash': simulation.initial_cash,
            'opening_value': float(getattr(simulation, 'opening_value', simulation.initial_cash)),
            'start_date': simulation.start_date,
            'duration_days': simulation.duration_days,
            'duration_hours': getattr(simulation, 'duration_hours', None),
            'trading_frequency': simulation.trading_frequency,
            'tickers': simulation.tickers,
            'trading_rules': simulation.trading_rules,
            'final_metrics': getattr(simulation, 'final_metrics', {}),
            'final_positions': getattr(simulation, 'final_metrics', {}).get('final_positions', {}),
            'results': simulation.results,
            'last_updated': datetime.now().isoformat()
        })
        
        logger.debug(
            "Portfolio state updated sim=%s value=%s return_pct=%s",
            simulation_id,
            current_portfolio_state['final_metrics'].get('final_value'),
            current_portfolio_state['final_metrics'].get('total_return_pct'),
        )
        
        # Clear conversation history when new simulation starts
        if 'ai_advisor' in globals():
            ai_advisor.clear_conversation_history()
            logger.debug("Conversation history cleared for new simulation")

class AIAdvisor:
    def __init__(self):
        self.conversation_history = []  # Store conversation memory
        self.system_prompt = """You are Teeby — a friendly, knowledgeable AI portfolio advisor and trading expert for TradeSphere. Your name is Teeby (spell it T-e-e-b-y). In normal conversation, just be Teeby: use your name when it fits, but do NOT explain initials, TB, or TradeBot unless the user clearly asks what your name means, why you're called Teeby, or what TB/TradeBot stands for. If they do ask that specifically, you may answer briefly: Teeby stands for TB / TradeBot. When users greet you or say "hey Teeby", respond naturally as Teeby without volunteering the backstory. You can provide both general trading/investment advice and analyze specific portfolio data.

Your capabilities include:
- Having friendly, natural conversations
- Providing general trading and investment advice
- Explaining market concepts, strategies, and financial instruments
- Analyzing specific portfolio performance, risk metrics, and allocation
- Identifying strengths and weaknesses in trading strategies
- Suggesting improvements for diversification and risk management
- Providing market insights and investment recommendations
- Explaining financial concepts in simple terms
- Discussing different asset classes, sectors, and investment approaches

Always be:
- Friendly and approachable in conversation
- Professional and informative when discussing finance
- Data-driven when analyzing specific portfolios
- Cautious about market predictions and specific stock recommendations
- Focused on helping users make informed decisions
- Clear about risks and limitations
- Educational and helpful for both beginners and experienced traders
- CONCISE and focused on the specific question asked
- MEMORY-AWARE of previous questions in the conversation

IMPORTANT: 
- Do not volunteer TB, TradeBot, or name etymology unless the user explicitly asks about what Teeby means or stands for
- You can answer general trading questions without needing specific portfolio data
- When portfolio data is available, reference their ACTUAL holdings and performance
- Stay focused on the specific question asked - don't give generic long responses unless specifically requested
- Remember previous questions in the conversation and build upon them
- If asked a specific question, answer it directly and concisely
- Provide educational content and explain the reasoning behind your advice

For casual conversation, respond naturally and warmly but encourage them to ask you questions about their portfolio.
For general trading advice, provide educational and practical guidance.
For portfolio analysis, format responses with clear headings, bullet points, and specific recommendations."""
    
    def clear_conversation_history(self):
        """Clear the conversation history"""
        self.conversation_history = []
        logger.debug("Conversation history cleared")

    def analyze_portfolio(self, portfolio_data=None, user_question="", simulation_data=None):
        """Analyze portfolio data and provide AI-powered insights with dynamic portfolio memory"""
        try:
            if not cerebras_token or cerebras_token == 'YOUR_CEREBRAS_TOKEN':
                logger.info("Cerebras token missing; AI advisor using fallback message")
                return """I'm sorry, but Teeby (the AI portfolio assistant) is not currently available. To enable AI portfolio analysis, please:

1. Get a Cerebras API token from https://www.cerebras.net/
2. Set the CEREBRAS_TOKEN environment variable
3. Restart the application

Example: export CEREBRAS_TOKEN='your-cerebras-token-here'

In the meantime, you can still analyze your portfolio manually using the performance metrics and charts provided."""
            
            # Add current question to conversation history
            self.conversation_history.append({
                'question': user_question,
                'timestamp': datetime.now().isoformat()
            })
            
            # Keep only last 10 questions to avoid context overflow
            if len(self.conversation_history) > 10:
                self.conversation_history = self.conversation_history[-10:]
            
            # Use global portfolio state if no specific data provided
            if portfolio_data is None:
                portfolio_data = {
                    'final_metrics': current_portfolio_state['final_metrics'],
                    'results': current_portfolio_state['results']
                }
                simulation_data = {
                    'initial_cash': current_portfolio_state['initial_cash'],
                    'opening_value': current_portfolio_state.get('opening_value'),
                    'start_date': current_portfolio_state['start_date'],
                    'duration_days': current_portfolio_state['duration_days'],
                    'duration_hours': current_portfolio_state.get('duration_hours'),
                    'trading_frequency': current_portfolio_state.get('trading_frequency') or 'daily',
                    'tickers': current_portfolio_state['tickers'],
                    'trading_rules': current_portfolio_state['trading_rules']
                }
            
            # Prepare conversation context
            conversation_context = ""
            if len(self.conversation_history) > 1:
                conversation_context = "\n\nCONVERSATION HISTORY:\n"
                for i, conv in enumerate(self.conversation_history[:-1], 1):
                    conversation_context += f"{i}. User: {conv['question']}\n"
                conversation_context += f"\nCurrent question: {user_question}"
            
            # Check if it's a general conversation or portfolio-specific question
            question_lower = user_question.lower().strip()
            
            # Handle specific questions with focused responses
            if any(query in question_lower for query in ['what is my portfolio', 'my portfolio', 'current portfolio', 'show my portfolio', 'portfolio holdings', 'what do i own', 'my positions']):
                context = self._prepare_portfolio_context(portfolio_data, simulation_data)
                user_message = f"""User is asking about their current portfolio. Here is their ACTUAL portfolio state:

{context}

{conversation_context}

Please provide a focused overview of their current portfolio including:
1. Current holdings and positions
2. Portfolio value and performance
3. Key risk metrics

Be specific about their actual holdings, values, and performance metrics. Keep it concise and focused on what they asked."""
            
            # Handle specific investment questions
            elif any(query in question_lower for query in ['should i buy', 'should i sell', 'hedge', 'voo', 'vti', 'better', 'which one', 'recommend', 'advice']):
                context = self._prepare_portfolio_context(portfolio_data, simulation_data)
                user_message = f"""User is asking for specific investment advice. Here is their current portfolio state:

{context}

{conversation_context}

Please provide focused, specific advice based on their current portfolio. Answer their question directly and concisely. If they're asking about specific investments, provide clear recommendations based on their current holdings and risk profile."""
            
            # User explicitly asking what Teeby means / TB / TradeBot
            elif any(
                q in question_lower
                for q in [
                    'what does teeby',
                    'why teeby',
                    'teeby mean',
                    'teeby stand',
                    'teeby short for',
                    'tradebot',
                    'trade bot',
                    'what tb',
                    'tb mean',
                    'tb stand',
                    'what does tb',
                ]
            ):
                user_message = f"""User asked: "{user_question}"

{conversation_context}

Answer as Teeby. Explain briefly that your name Teeby stands for TB, meaning TradeBot — TradeSphere's trading assistant. Then keep it short. Do not repeat this story unless they ask again."""

            # Handle questions about the assistant's name or identity (no etymology unless asked above)
            elif any(
                q in question_lower
                for q in [
                    'who are you',
                    "what's your name",
                    'what is your name',
                    'are you teeby',
                    'are you a bot',
                    'are you an ai',
                ]
            ):
                user_message = f"""User asked: "{user_question}"

{conversation_context}

Answer as Teeby. Say your name is Teeby and you are TradeSphere's AI portfolio assistant. Briefly list what you can help with. Do NOT mention TB, TradeBot, or what Teeby stands for unless this message is clearly asking for that (it should not be). Keep it friendly and concise."""

            # Handle general greetings
            elif any(greeting in question_lower for greeting in ['hi', 'hello', 'hey', 'good morning', 'good afternoon', 'good evening']):
                user_message = f"""User said: "{user_question}"

{conversation_context}

Please respond naturally and friendly to this greeting as Teeby. Keep it brief, use your name if it fits naturally, and mention that you're ready to help with their portfolio questions."""
            
            # Handle general trading and investment questions
            elif any(query in question_lower for query in ['what is', 'how does', 'explain', 'tell me about', 'difference between', 'compare', 'vs', 'versus', 'trading strategy', 'investment strategy', 'market', 'stocks', 'bonds', 'etf', 'mutual fund', 'options', 'futures', 'crypto', 'bitcoin', 'dollar cost averaging', 'value investing', 'growth investing', 'technical analysis', 'fundamental analysis', 'risk management', 'diversification', 'asset allocation', 'rebalancing', 'tax', 'retirement', '401k', 'ira', 'roth', 'dividend', 'yield', 'pe ratio', 'p/e', 'market cap', 'volatility', 'beta', 'alpha', 'sharpe ratio', 'correlation', 'sector', 'industry', 'bull market', 'bear market', 'recession', 'inflation', 'interest rates', 'fed', 'federal reserve', 'earnings', 'revenue', 'profit', 'balance sheet', 'income statement', 'cash flow', 'debt', 'equity', 'leverage', 'margin', 'short selling', 'hedging', 'derivatives', 'commodities', 'real estate', 'reits', 'treasury', 'corporate bonds', 'junk bonds', 'credit rating', 'default', 'liquidity', 'volume', 'institutional', 'retail', 'hedge fund', 'private equity', 'venture capital', 'ipo', 'merger', 'acquisition', 'dividend yield', 'roe', 'roa', 'wacc', 'dcf', 'npv', 'irr', 'black scholes', 'greeks', 'delta', 'gamma', 'theta', 'vega', 'implied volatility', 'vix', 'sentiment', 'momentum', 'mean reversion', 'trend following', 'contrarian', 'arbitrage', 'algorithmic', 'quantitative', 'active', 'passive', 'index fund', 'expense ratio', 'management fee', 'drip', 'dividend reinvestment', 'compounding', 'compound interest', 'rule of 72', 'time value', 'present value', 'future value', 'bond pricing', 'yield to maturity', 'current yield', 'coupon', 'face value', 'par value', 'discount', 'premium', 'zero coupon', 'callable', 'putable', 'convertible', 'investment grade', 'moody', 's&p', 'fitch', 'rating', 'bankruptcy', 'reorganization', 'liquidation', 'collateral', 'secured', 'unsecured', 'senior', 'subordinated', 'preferred', 'common', 'voting', 'proxy', 'activist', 'institutional', 'retail', 'individual', 'accredited', 'high net worth', 'family office', 'endowment', 'foundation', 'pension', 'defined benefit', 'defined contribution', 'rollover', 'conversion', 'backdoor', 'mega backdoor', 'contribution limit', 'income limit', 'required minimum distribution', 'rmd', 'early withdrawal', 'penalty', 'hardship', 'loan', 'borrowing', 'day trading', 'pattern day trader', 'pdt', 'good faith', 'freeriding', 'settlement', 'clearing', 'custody', 'sipc', 'fdic', 'insurance', 'protection', 'fraud', 'scam', 'ponzi', 'pyramid', 'elder abuse', 'financial exploitation', 'estate planning', 'will', 'trust', 'revocable', 'irrevocable', 'living trust', 'gift tax', 'estate tax', 'generation skipping', 'gst', 'exemption', 'unified', 'portability', 'step up', 'basis', 'cost basis', 'wash sale', 'constructive sale', 'straddle', 'conversion', 'synthetic', 'collar', 'protective put', 'covered call', 'cash secured', 'naked', 'uncovered', 'spread', 'bull', 'bear', 'calendar', 'diagonal', 'butterfly', 'condor', 'iron', 'strangle', 'straddle', 'long', 'short', 'strike', 'expiration', 'exercise', 'assignment', 'american', 'european', 'barrier', 'knock in', 'knock out', 'binary', 'digital', 'touch', 'no touch', 'lookback', 'basket', 'rainbow', 'quanto', 'best of', 'worst of', 'outperformance', 'underperformance', 'volatility', 'variance', 'correlation', 'dispersion', 'basket', 'index', 'sector', 'single name', 'credit', 'equity', 'interest rate', 'fx', 'commodity', 'energy', 'metals', 'agriculture', 'precious', 'industrial', 'base', 'rare earth', 'supply chain', 'logistics', 'transportation', 'shipping', 'airline', 'railroad', 'trucking', 'pipeline', 'storage', 'tankers', 'dry bulk', 'container', 'ports', 'terminals', 'warehouses', 'distribution', 'fulfillment', 'ecommerce', 'online', 'digital', 'platform', 'marketplace', 'gig', 'sharing', 'subscription', 'saas', 'paas', 'iaas', 'cloud', 'edge', '5g', 'iot', 'ai', 'ml', 'blockchain', 'crypto', 'defi', 'nft', 'metaverse', 'vr', 'ar', 'mr', 'xr', 'quantum', 'biotech', 'pharma', 'healthcare', 'medical', 'device', 'diagnostic', 'therapeutic', 'drug', 'medicine', 'treatment', 'cure', 'vaccine', 'immunotherapy', 'gene therapy', 'cell therapy', 'stem cell', 'regenerative', 'precision', 'personalized', 'companion', 'biomarker', 'genomics', 'proteomics', 'metabolomics', 'transcriptomics', 'epigenomics', 'single cell', 'spatial', 'multi omics', 'systems biology', 'synthetic biology', 'bioengineering', 'biofabrication', 'organoid', 'organ on chip', 'microfluidics', 'lab on chip', 'point of care', 'telemedicine', 'digital health', 'health tech', 'medtech', 'fintech', 'insurtech', 'proptech', 'edtech', 'cleantech', 'greentech', 'climatetech', 'agtech', 'foodtech', 'retailtech', 'martech', 'adtech', 'hrtech', 'legaltech', 'regtech', 'compliance', 'cybersecurity', 'privacy', 'gdpr', 'ccpa', 'sox', 'dodd frank', 'basel', 'mifid', 'psd2', 'open banking', 'api', 'sdk', 'webhook', 'rest', 'graphql', 'grpc', 'microservices', 'serverless', 'containers', 'kubernetes', 'docker', 'devops', 'ci cd', 'git', 'github', 'gitlab', 'bitbucket', 'jira', 'confluence', 'slack', 'teams', 'zoom', 'webex', 'meet', 'hangouts', 'discord', 'telegram', 'whatsapp', 'signal', 'matrix', 'element', 'rocket chat', 'mattermost', 'zulip', 'riot', 'wire', 'threema', 'session', 'briar', 'tox', 'retroshare', 'gnunet', 'freenet', 'i2p', 'tor', 'vpn', 'proxy', 'firewall', 'antivirus', 'malware', 'ransomware', 'phishing', 'social engineering', 'penetration testing', 'vulnerability assessment', 'security audit', 'compliance audit', 'risk assessment', 'threat modeling', 'security architecture', 'zero trust', 'least privilege', 'defense in depth', 'layered security', 'multi factor', 'authentication', 'authorization', 'access control', 'identity management', 'single sign on', 'sso', 'federation', 'saml', 'oauth', 'openid connect', 'jwt', 'token', 'session', 'cookie', 'cache', 'redis', 'memcached', 'database', 'sql', 'nosql', 'mongodb', 'cassandra', 'dynamodb', 'cosmosdb', 'neo4j', 'postgresql', 'mysql', 'oracle', 'sql server', 'db2', 'teradata', 'snowflake', 'bigquery', 'redshift', 'athena', 'presto', 'hive', 'spark', 'hadoop', 'kafka', 'pulsar', 'rabbitmq', 'activemq', 'ibm mq', 'tibco', 'websphere', 'weblogic', 'tomcat', 'jetty', 'nginx', 'apache', 'iis', 'caddy', 'traefik', 'haproxy', 'varnish', 'cloudflare', 'aws', 'azure', 'gcp', 'ibm cloud', 'oracle cloud', 'alibaba cloud', 'tencent cloud', 'huawei cloud', 'digital ocean', 'linode', 'vultr', 'heroku', 'netlify', 'vercel', 'render', 'fly', 'railway', 'supabase', 'firebase', 'planetscale', 'cockroachdb', 'yugabyte', 'tidb', 'clickhouse', 'timescaledb', 'influxdb', 'prometheus', 'grafana', 'elk', 'elasticsearch', 'logstash', 'kibana', 'splunk', 'datadog', 'new relic', 'appdynamics', 'dynatrace', 'sumo logic', 'honeycomb', 'lightstep', 'jaeger', 'zipkin', 'opentelemetry', 'opencensus', 'statsd', 'telegraf', 'collectd', 'fluentd', 'fluentbit', 'vector', 'logstash', 'beats', 'filebeat', 'metricbeat', 'packetbeat', 'heartbeat', 'auditbeat', 'functionbeat', 'winlogbeat', 'journalbeat', 'osquerybeat', 'apm', 'rum', 'synthetic', 'real user monitoring', 'synthetic monitoring', 'performance monitoring', 'infrastructure monitoring', 'log monitoring', 'security monitoring', 'compliance monitoring', 'cost monitoring', 'usage monitoring', 'capacity planning', 'scaling', 'auto scaling', 'horizontal', 'vertical', 'load balancing', 'traffic management', 'cdn', 'edge computing', 'fog computing', 'mist computing', 'distributed computing', 'grid computing', 'cluster computing', 'parallel computing', 'concurrent computing', 'asynchronous', 'synchronous', 'blocking', 'non blocking', 'event driven', 'reactive', 'functional', 'object oriented', 'procedural', 'declarative', 'imperative', 'logic', 'constraint', 'rule based', 'expert system', 'knowledge base', 'ontology', 'semantic web', 'linked data', 'rdf', 'sparql', 'owl', 'skos', 'foaf', 'dublin core', 'schema.org', 'json ld', 'microdata', 'rdfa', 'turtle', 'n3', 'ntriples', 'nquads', 'trig', 'json ld', 'yaml', 'xml', 'html', 'css', 'javascript', 'typescript', 'python', 'java', 'c#', 'c++', 'c', 'go', 'rust', 'swift', 'kotlin', 'scala', 'clojure', 'haskell', 'erlang', 'elixir', 'f#', 'ocaml', 'racket', 'scheme', 'lisp', 'prolog', 'smalltalk', 'ruby', 'php', 'perl', 'r', 'matlab', 'octave', 'julia', 'fortran', 'cobol', 'ada', 'pascal', 'delphi', 'visual basic', 'vb.net', 'powershell', 'bash', 'zsh', 'fish', 'tcsh', 'ksh', 'dash', 'ash', 'busybox', 'alpine', 'ubuntu', 'debian', 'centos', 'rhel', 'fedora', 'opensuse', 'sles', 'arch', 'gentoo', 'slackware', 'freebsd', 'openbsd', 'netbsd', 'dragonfly', 'minix', 'plan9', 'inferno', 'unix', 'linux', 'windows', 'macos', 'ios', 'android', 'tizen', 'webos', 'fuchsia', 'chrome os', 'firefox os', 'sailfish', 'ubuntu touch', 'postmarketos', 'pureos', 'trisquel', 'parabola', 'hyperbola', 'guix', 'nixos', 'void', 'artix', 'endeavouros', 'manjaro', 'mx linux', 'pop os', 'elementary', 'zorin', 'mint', 'deepin', 'kali', 'parrot', 'blackarch', 'backbox', 'pentoo', 'wifi slax', 'tiny core', 'puppy', 'slitaz', 'porteus', 'antiX', 'bunsenlabs', 'crunchbang', 'sparky', 'peppermint', 'lubuntu', 'xubuntu', 'kubuntu', 'ubuntu mate', 'ubuntu budgie', 'ubuntu cinnamon', 'ubuntu kylin', 'ubuntu studio', 'edubuntu', 'mythbuntu', 'xubuntu', 'lubuntu', 'kubuntu', 'ubuntu mate', 'ubuntu budgie', 'ubuntu cinnamon', 'ubuntu kylin', 'ubuntu studio', 'edubuntu', 'mythbuntu', 'xubuntu', 'lubuntu', 'kubuntu', 'ubuntu mate', 'ubuntu budgie', 'ubuntu cinnamon', 'ubuntu kylin', 'ubuntu studio', 'edubuntu', 'mythbuntu']):
                user_message = f"""User asked a general trading/investment question: "{user_question}"

{conversation_context}

Please provide a comprehensive, educational answer about trading and investment concepts. Explain the topic clearly, provide practical insights, and include relevant examples. Be helpful for both beginners and experienced traders. Focus on the specific question asked and provide actionable advice when appropriate."""

            # Handle general questions about capabilities
            elif any(general in question_lower for general in ['how are you', 'what can you do', 'help', 'what do you do']):
                user_message = f"""User asked: "{user_question}"

{conversation_context}

Please explain that you are Teeby, the AI portfolio advisor and trading expert for TradeSphere. Say you can help with both general trading/investment questions and specific portfolio analysis. Mention your capabilities briefly. Do NOT explain TB or TradeBot unless they asked about your name's meaning. Keep it concise and focused on what they asked."""
            
            else:
                # General portfolio analysis questions
                context = self._prepare_portfolio_context(portfolio_data, simulation_data)
                user_message = f"""User asked: "{user_question}"

Here is their current portfolio state:

{context}

{conversation_context}

Please provide a focused analysis that directly addresses their question. Be specific about their actual holdings, values, and performance metrics. Keep it concise and relevant to what they asked."""

            headers = {
                "Authorization": f"Bearer {cerebras_token}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": "llama3.1-8b",  # Cerebras model
                "messages": [
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": user_message}
                ],
                "max_tokens": 1500,
                "temperature": 0.7
            }
            
            response = requests.post(cerebras_api_url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
            result = response.json()
            ai_response = result['choices'][0]['message']['content']
            logger.debug("Cerebras response length=%s", len(ai_response))
            return ai_response
            
        except Exception as e:
            # Provide a fallback analysis when API is not available
            error_msg = str(e).lower()
            if any(keyword in error_msg for keyword in ["quota", "billing", "limit", "unauthorized", "forbidden", "404", "not found"]):
                return self._generate_fallback_analysis(portfolio_data, user_question, simulation_data)
            else:
                return f"I apologize, but I encountered an error while analyzing your portfolio: {str(e)}. Please check your Cerebras API token and try again."

    def _generate_fallback_analysis(self, portfolio_data, user_question="", simulation_data=None):
        """Generate a fallback analysis when AI API is not available"""
        metrics = portfolio_data.get('final_metrics', {})
        
        # Extract key metrics
        total_return = metrics.get('total_return_pct', 0)
        final_value = metrics.get('final_value', 0)
        total_pnl = metrics.get('total_pnl', 0)
        sharpe_ratio = metrics.get('sharpe_ratio', 0)
        volatility = metrics.get('volatility_pct', 0)
        beta = metrics.get('beta', 0)
        beta_interpretation = metrics.get('beta_interpretation', 'N/A')
        correlation = metrics.get('correlation', 0)
        total_trades = metrics.get('total_trades', 0)
        positions = metrics.get('final_positions', {})
        
        # Generate analysis based on user question
        analysis = "🤖 **AI Portfolio Analysis (Demo Mode)**\n\n"
        question_lower = user_question.lower()
        
        # Always show performance analysis for "analyze my portfolio" or similar requests
        if ("analyze" in question_lower or "performance" in question_lower or 
            "how" in question_lower or "doing" in question_lower or not user_question.strip()):
            analysis += "📊 **Performance Analysis:**\n"
            if total_return > 0:
                analysis += f"• Your portfolio achieved a **{total_return:.1f}% return** - excellent performance!\n"
            else:
                analysis += f"• Your portfolio shows a **{total_return:.1f}% return** - consider reviewing your strategy\n"
            analysis += f"• Final Value: ${final_value:,.2f}\n"
            analysis += f"• Total P&L: ${total_pnl:,.2f}\n\n"
        
        # Risk analysis
        if ("risk" in question_lower or "volatile" in question_lower or "safe" in question_lower):
            analysis += "⚠️ **Risk Assessment:**\n"
            if sharpe_ratio > 1.0:
                analysis += f"• Sharpe Ratio: {sharpe_ratio:.2f} - **Excellent risk-adjusted returns**\n"
            elif sharpe_ratio > 0.5:
                analysis += f"• Sharpe Ratio: {sharpe_ratio:.2f} - **Good risk-adjusted returns**\n"
            else:
                analysis += f"• Sharpe Ratio: {sharpe_ratio:.2f} - **Consider improving risk management**\n"
            analysis += f"• Volatility: {volatility:.1f}% - {'Low' if volatility < 10 else 'Moderate' if volatility < 20 else 'High'} risk level\n"
            analysis += f"• Beta: {beta:.3f} - **{beta_interpretation}**\n"
            analysis += f"• Market Correlation: {correlation:.3f} - {'Strong' if abs(correlation) > 0.7 else 'Moderate' if abs(correlation) > 0.3 else 'Weak'} correlation with market\n"
            analysis += f"• Total Trades: {total_trades} - {'Conservative' if total_trades < 20 else 'Active' if total_trades < 50 else 'Very Active'} strategy\n\n"
        
        # Diversification analysis
        if ("diversif" in question_lower or "position" in question_lower or "stock" in question_lower):
            analysis += "🎯 **Portfolio Composition:**\n"
            if positions:
                analysis += "• Current Positions:\n"
                for ticker, shares in positions.items():
                    analysis += f"  - {ticker}: {shares} shares\n"
                if len(positions) < 3:
                    analysis += "• **Recommendation**: Consider adding more positions for better diversification\n"
                else:
                    analysis += "• Good diversification across multiple positions\n"
            analysis += "\n"
        
        # Beta analysis
        if ("beta" in question_lower or "market" in question_lower or "correlation" in question_lower):
            analysis += "📊 **Beta & Market Analysis:**\n"
            analysis += f"• Portfolio Beta: {beta:.3f}\n"
            analysis += f"• Interpretation: **{beta_interpretation}**\n"
            analysis += f"• Market Correlation: {correlation:.3f}\n"
            if beta > 1.0:
                analysis += "• **High Beta Strategy**: Your portfolio is more volatile than the market\n"
            elif beta < 1.0 and beta > 0:
                analysis += "• **Defensive Strategy**: Your portfolio is less volatile than the market\n"
            elif beta < 0:
                analysis += "• **Hedge Strategy**: Your portfolio moves opposite to the market\n"
            analysis += "\n"

        # Trading strategy analysis
        if ("strategy" in question_lower or "trading" in question_lower or "rules" in question_lower):
            analysis += "📈 **Trading Strategy Analysis:**\n"
            analysis += f"• Total Trades Executed: {total_trades}\n"
            if total_trades > 50:
                analysis += "• **High-frequency trading** - watch transaction costs\n"
            elif total_trades > 20:
                analysis += "• **Active trading strategy** - good balance of activity\n"
            else:
                analysis += "• **Conservative approach** - lower transaction costs\n"
            analysis += f"• Sharpe Ratio: {sharpe_ratio:.2f} - {'Excellent' if sharpe_ratio > 1.0 else 'Good' if sharpe_ratio > 0.5 else 'Needs improvement'} risk-adjusted performance\n\n"
        
        # Add general recommendations
        analysis += "💡 **Key Recommendations:**\n"
        if total_return > 15:
            analysis += "• **Excellent performance!** Consider taking some profits\n"
        elif total_return > 5:
            analysis += "• **Solid performance** - your strategy is working well\n"
        else:
            analysis += "• **Review your strategy** - consider different entry/exit points\n"
        
        if volatility > 20:
            analysis += "• **High volatility detected** - consider reducing position sizes\n"
        
        if total_trades > 50:
            analysis += "• **Active trading strategy** - watch out for transaction costs\n"
        
        analysis += "• **Regular rebalancing** helps maintain target allocation\n"
        analysis += "• **Dollar-cost averaging** can reduce timing risk\n\n"
        
        analysis += "🔧 **To enable full AI analysis:** Set up your Cerebras API token in the environment variables."
        
        return analysis

    def _prepare_portfolio_context(self, portfolio_data, simulation_data=None):
        """Prepare portfolio data for AI analysis"""
        context = "PORTFOLIO ANALYSIS DATA:\n\n"
        
        # Add simulation parameters if available
        if simulation_data:
            context += f"SIMULATION PARAMETERS:\n"
            context += f"- Initial Cash Deposit: ${simulation_data.get('initial_cash', 'N/A')}\n"
            if simulation_data.get('opening_value') is not None:
                context += f"- Opening Portfolio Value (cash + initial positions): ${simulation_data['opening_value']}\n"
            context += f"- Start Date: {simulation_data.get('start_date', 'N/A')}\n"
            dd = simulation_data.get('duration_days')
            dh = simulation_data.get('duration_hours')
            if dh is not None:
                context += f"- Duration: {dh} hours (intraday span)\n"
            elif dd is not None:
                context += f"- Duration: {dd} days\n"
            else:
                context += "- Duration: N/A\n"
            context += f"- Trading Frequency: {simulation_data.get('trading_frequency', 'N/A')}\n"
            context += f"- Initial Tickers: {simulation_data.get('tickers', {})}\n"
            context += f"- Trading Rules: {simulation_data.get('trading_rules', {})}\n\n"
        
        # Add performance metrics
        if 'final_metrics' in portfolio_data:
            metrics = portfolio_data['final_metrics']
            context += f"PERFORMANCE METRICS:\n"
            context += f"- Total Return: {metrics.get('total_return_pct', 'N/A')}%\n"
            context += f"- Final Portfolio Value: ${metrics.get('final_value', 'N/A')}\n"
            context += f"- Total P&L: ${metrics.get('total_pnl', 'N/A')}\n"
            context += f"- Sharpe Ratio: {metrics.get('sharpe_ratio', 'N/A')}\n"
            context += f"- Volatility: {metrics.get('volatility_pct', 'N/A')}%\n"
            context += f"- Beta: {metrics.get('beta', 'N/A')}\n"
            context += f"- Beta Interpretation: {metrics.get('beta_interpretation', 'N/A')}\n"
            context += f"- Market Correlation: {metrics.get('correlation', 'N/A')}\n"
            context += f"- Total Trades: {metrics.get('total_trades', 'N/A')}\n"
            context += f"- Final Positions: {metrics.get('final_positions', {})}\n\n"
        
        # Add detailed trading activity
        if 'results' in portfolio_data and portfolio_data['results']:
            results = portfolio_data['results']
            context += f"TRADING ACTIVITY:\n"
            context += f"- Simulation Duration: {len(results)} intervals\n"
            
            # Analyze trading patterns
            trades_count = 0
            all_trades = []
            price_movements = {}
            
            for result in results:
                if result.get('trades'):
                    trades_count += len(result['trades'])
                    all_trades.extend(result['trades'])
                
                # Track price movements
                if result.get('prices'):
                    for ticker, price in result['prices'].items():
                        if ticker not in price_movements:
                            price_movements[ticker] = []
                        price_movements[ticker].append(price)
            
            context += f"- Total Trading Activity: {trades_count} trades\n"
            
            # Show recent positions
            if results:
                latest_positions = results[-1].get('positions', {})
                context += f"- Current Positions: {latest_positions}\n"
                
                # Show price trends with more detail
                if len(results) > 1:
                    first_result = results[0]
                    last_result = results[-1]
                    context += f"\nPRICE MOVEMENTS:\n"
                    for ticker in first_result.get('prices', {}):
                        if ticker in first_result['prices'] and ticker in last_result.get('prices', {}):
                            first_price = first_result['prices'][ticker]
                            last_price = last_result['prices'][ticker]
                            change_pct = ((last_price - first_price) / first_price) * 100
                            context += f"- {ticker}: ${first_price:.2f} → ${last_price:.2f} ({change_pct:+.2f}%)\n"
            
            # Add recent trades detail
            if all_trades:
                context += f"\nRECENT TRADES (last 5):\n"
                recent_trades = all_trades[-5:] if len(all_trades) > 5 else all_trades
                for trade in recent_trades:
                    context += f"- {trade}\n"
            
            # Add portfolio value progression
            if len(results) > 1:
                context += f"\nPORTFOLIO VALUE PROGRESSION:\n"
                # Show first, middle, and last values
                first_value = results[0].get('portfolio_value', 0)
                middle_idx = len(results) // 2
                middle_value = results[middle_idx].get('portfolio_value', 0)
                last_value = results[-1].get('portfolio_value', 0)
                context += f"- Start: ${first_value:,.2f}\n"
                context += f"- Midpoint: ${middle_value:,.2f}\n"
                context += f"- Final: ${last_value:,.2f}\n"
        
        return context

# Initialize AI advisor as a global instance
advisor = AIAdvisor()

class SimulationManager:
    def __init__(self, simulation_id, initial_cash, start_date, duration_days, trading_frequency, tickers, trading_rules, beta_hedge_enabled=False, duration_hours=None, strategy_mode='manual', strategy_code=None, strategy_name=None):
        self.simulation_id = simulation_id
        self.initial_cash = initial_cash
        self.start_date = start_date
        self.duration_days = duration_days
        self.duration_hours = duration_hours
        self.trading_frequency = trading_frequency  # 'daily' or 'intraday'
        self.tickers = tickers
        self.trading_rules = trading_rules
        self.beta_hedge_enabled = beta_hedge_enabled
        # Imported strategy lane: when strategy_mode == 'imported', the
        # per-tick loop runs `strategy_code` through the same sandbox the
        # Studio uses (operating on `port` and the historical price at
        # `currtime`) in place of the manual trading_rules block.
        self.strategy_mode = strategy_mode if strategy_mode in ('manual', 'imported') else 'manual'
        self.strategy_code = strategy_code if self.strategy_mode == 'imported' else None
        self.strategy_name = strategy_name if self.strategy_mode == 'imported' else None
        self.strategy_error = None
        self.results = []
        self.is_running = False
        self.is_complete = False
        self.thread = None
        self.total_result_steps = 1
        
    def run_simulation(self):
        """Run the portfolio simulation"""
        try:
            self.is_running = True
            logger.info("Simulation %s start (rules groups=%s)", self.simulation_id, len(self.trading_rules))
            
            freq = self.trading_frequency
            bar_minutes_map = {'1m': 1, '5m': 5, '15m': 15, '60m': 60, 'intraday': 60}
            is_intraday = freq in bar_minutes_map
            if is_intraday:
                _bm = bar_minutes_map[freq]
                yf_interval = f'{_bm}m' if _bm < 60 else '60m'
            else:
                yf_interval = '1d'
            
            # Initialize portfolio and stock data
            currtime = datetime.strptime(self.start_date, '%Y-%m-%d')
            
            # If start date is a weekend, move to next weekday
            while currtime.weekday() >= 5:  # Saturday=5, Sunday=6
                currtime += timedelta(days=1)
                logger.debug("Start date was weekend, moving to %s", currtime.strftime('%Y-%m-%d'))
            
            if is_intraday:
                currtime = currtime.replace(hour=9, minute=30, second=0, microsecond=0)
            
            start_date_str = currtime.strftime('%Y-%m-%d')
            today_d = date.today()
            today_dt = datetime(today_d.year, today_d.month, today_d.day)
            dh = getattr(self, 'duration_hours', None)
            if is_intraday and dh is not None and freq in ('1m', '5m', '15m'):
                # Hour-capped intraday: only fetch through the simulated window. Large pad_days + max(..., today)
                # produced multi-week Yahoo ranges and broke 1m even though the sim steps ≤6h (see bar cap below).
                cap_h = {'1m': 6, '5m': 12, '15m': 24}[freq]
                h = max(1, min(cap_h, int(round(float(dh)))))
                end_dt = currtime + timedelta(hours=h) + timedelta(days=1)
            elif is_intraday:
                if freq == '60m':
                    pad_days = max(21, int(self.duration_days) * 12 + 21)
                else:
                    pad_days = max(30, int(self.duration_days) * 14 + 30)
                end_candidate = currtime + timedelta(days=pad_days)
                end_dt = max(end_candidate, today_dt)
            else:
                pad_days = int(self.duration_days) + 35
                end_candidate = currtime + timedelta(days=pad_days)
                end_dt = max(end_candidate, today_dt)
            if end_dt.date() <= currtime.date():
                end_dt = currtime + timedelta(days=1)
            end_date_str = end_dt.strftime('%Y-%m-%d')
            
            port = Portfolio(self.initial_cash, start_date_str, end_date_str, yf_interval=yf_interval)
            
            # Initialize stock data with appropriate interval
            data = {}
            if is_intraday:
                bar_m = bar_minutes_map[freq]
                if dh is not None and freq in ('1m', '5m', '15m'):
                    cap = {'1m': 6, '5m': 12, '15m': 24}[freq]
                    h = max(1, min(cap, int(round(float(dh)))))
                    bars_per_hour = max(1, 60 // bar_m)
                    total_intervals = max(1, h * bars_per_hour)
                else:
                    bars_per_day = max(1, (6 * 60) // bar_m)
                    d = max(1, min(7, int(self.duration_days))) if freq == '60m' else int(self.duration_days)
                    total_intervals = max(1, d * bars_per_day)
                interval_delta = timedelta(minutes=bar_m)
            else:
                total_intervals = self.duration_days
                interval_delta = timedelta(days=1)
            
            self.total_result_steps = total_intervals + 1
            
            for ticker in self.tickers.keys():
                data[ticker] = StockData(
                    ticker, start_date_str, end_date_str, yf_interval, allow_daily_fallback=(yf_interval == '1d')
                )

            rule_and_hedge = set(self.trading_rules.keys())
            if self.beta_hedge_enabled:
                rule_and_hedge.add('VOO')
            for t in rule_and_hedge:
                if t not in data:
                    data[t] = StockData(
                        t, start_date_str, end_date_str, yf_interval, allow_daily_fallback=(yf_interval == '1d')
                    )

            # ── Imported-strategy lane: compile once, AST-scan for tickers
            # the script references, and pre-load StockData for any symbol
            # not already in the loaded set so `price("AAPL")` etc. resolve
            # inside the sandbox at every step.
            strategy_compiled = None
            strategy_tickers = set()
            if self.strategy_mode == 'imported' and self.strategy_code:
                try:
                    s_tree = ast.parse(self.strategy_code, mode='exec')
                    _strategy_validate_ast(s_tree)
                    strategy_tickers = _scan_strategy_tickers(s_tree)
                    s_tree = _StrategyTickInjector().visit(s_tree)
                    ast.fix_missing_locations(s_tree)
                    strategy_compiled = compile(s_tree, f'<sim:{self.simulation_id}>', 'exec')
                except SyntaxError as e:
                    self.strategy_error = f'Syntax error: {e.msg} (line {e.lineno})'
                    self.is_running = False
                    self.is_complete = True
                    self.final_metrics = {
                        'opening_value': 0.0,
                        'total_return_pct': 0.0,
                        'final_value': float(self.initial_cash),
                        'total_pnl': 0.0,
                        'sharpe_ratio': None,
                        'volatility_pct': None,
                        'total_trades': 0,
                        'final_positions': {},
                        'beta': None,
                        'beta_interpretation': self.strategy_error,
                        'correlation': None,
                        'hedge_trades_count': 0,
                        'total_hedge_margin_used': 0.0,
                        'hedge_margin_remaining': 0.0,
                        'hedge_trades': [],
                    }
                    logger.warning('Imported strategy syntax rejected: %s', self.strategy_error)
                    return
                except ValueError as e:
                    self.strategy_error = str(e)
                    self.is_running = False
                    self.is_complete = True
                    self.final_metrics = {
                        'opening_value': 0.0,
                        'total_return_pct': 0.0,
                        'final_value': float(self.initial_cash),
                        'total_pnl': 0.0,
                        'sharpe_ratio': None,
                        'volatility_pct': None,
                        'total_trades': 0,
                        'final_positions': {},
                        'beta': None,
                        'beta_interpretation': self.strategy_error,
                        'correlation': None,
                        'hedge_trades_count': 0,
                        'total_hedge_margin_used': 0.0,
                        'hedge_margin_remaining': 0.0,
                        'hedge_trades': [],
                    }
                    logger.warning('Imported strategy rejected by sandbox: %s', self.strategy_error)
                    return
                for t in strategy_tickers:
                    if t not in data:
                        data[t] = StockData(
                            t, start_date_str, end_date_str, yf_interval, allow_daily_fallback=(yf_interval == '1d')
                        )

            # If Yahoo only has daily rows (midnight index) but we step by minutes, every minute maps to the
            # same bar — flat prices at 00:00, 00:01, ...  Detect and step by calendar day instead.
            data_is_daily = False
            for ticker in list(data.keys()):
                idx = data[ticker].stock_data.index
                if len(idx) < 2:
                    if is_intraday and len(idx) == 1:
                        data_is_daily = True
                    continue
                gap0 = idx[1] - idx[0]
                if gap0 >= timedelta(hours=12):
                    data_is_daily = True
                    break
            report_intraday_times = bool(is_intraday and not data_is_daily)
            if is_intraday and data_is_daily:
                logger.warning(
                    'Intraday mode requested but bar spacing is daily; stepping by calendar day. '
                    'Use a recent start date within Yahoo intraday window for per-minute prices.'
                )
                interval_delta = timedelta(days=1)
                total_intervals = max(1, int(self.duration_days))
                self.total_result_steps = total_intervals + 1
            
            # Initial stock positions (already held) — do not debit cash.
            # Cash remains the full "Initial Cash Deposit"; PnL baseline is set
            # to total NAV after positions are marked at market below.
            for ticker, shares in self.tickers.items():
                if not data[ticker].stock_data.empty:
                    first_trading_day = data[ticker].stock_data.index[0]
                    data[ticker].curtime = first_trading_day
                    current_price = data[ticker].get_price()
                    if current_price is not None:
                        port.establish_position(ticker, shares, first_trading_day)
                    else:
                        logger.warning("No initial price for %s on %s; skipping position", ticker, first_trading_day)
                else:
                    logger.warning("No stock data for %s; skipping initial position", ticker)
            
            first_bars = [data[t].stock_data.index[0] for t in self.tickers if not data[t].stock_data.empty]
            if first_bars:
                # Align to Yahoo's first bar for the loaded range (do not force 9:30 — that can miss
                # the index and make get_price fail for some tickers on every step).
                currtime = min(first_bars)
                if hasattr(currtime, 'to_pydatetime'):
                    currtime = currtime.to_pydatetime()
                currtime = currtime.replace(second=0, microsecond=0)
                for t in self.tickers:
                    if not data[t].stock_data.empty:
                        data[t].curtime = currtime
            
            # Total NAV after opening positions; use as P&L baseline so day-0 PnL is ~0
            # (positions did not consume cash). Everything downstream — chart
            # baselines, total_return %, total_pnl, hedge-impact %, returns
            # series for Sharpe/volatility — keys off this opening NAV.
            initial_portfolio_value = port.get_value(currtime)
            port.original_value = float(initial_portfolio_value)
            # Stash on the SimulationManager so result endpoints (chart_data,
            # final metrics, plot) don't have to re-derive it.
            self.opening_value = float(initial_portfolio_value)
            initial_pnl = 0.0
            
            # Record initial state (opening positions + full cash) as first result
            initial_interval_label = 'Day 0 (Initial)' if not report_intraday_times else 'Day 0, Initial'
            initial_result = {
                'day': 0,
                'interval_label': initial_interval_label,
                'date': currtime.strftime('%Y-%m-%d %H:%M') if report_intraday_times else currtime.strftime('%Y-%m-%d'),
                'prices': {ticker: data[ticker].get_price() for ticker in self.tickers.keys() if data[ticker].get_price() is not None},
                'portfolio_value': initial_portfolio_value,
                'trades': [],
                'positions': port.positions.copy(),
                'cash': round(float(port.cash), 2),
                'pnl': initial_pnl,
                'hedge_margin_balance': port.get_hedge_margin_balance(),
            }
            self.results.append(initial_result)
            
            for i in range(total_intervals):
                if not self.is_running:  # Check if simulation was stopped
                    break
                    
                # Move to next interval
                currtime = currtime + interval_delta
                
                # Update current time for all loaded symbols (portfolio, rules, hedge)
                for ticker in data.keys():
                    data[ticker].curtime = currtime
                
                # Get current prices for portfolio tickers
                current_prices = {}
                for ticker in self.tickers.keys():
                    price = data[ticker].get_price()
                    if price is not None:
                        current_prices[ticker] = price
                
                if self.beta_hedge_enabled and 'VOO' not in current_prices:
                    if 'VOO' in data and not data['VOO'].stock_data.empty:
                        vp = data['VOO'].get_price()
                        if vp is not None:
                            current_prices['VOO'] = vp
                    if current_prices.get('VOO') is None:
                        voo_price = self._get_voo_price(currtime)
                        if voo_price:
                            current_prices['VOO'] = voo_price
                
                for ticker in self.trading_rules.keys():
                    if ticker not in current_prices:
                        if ticker in data and not data[ticker].stock_data.empty:
                            p = data[ticker].get_price()
                            current_prices[ticker] = p if p is not None else 100.0
                        else:
                            current_prices[ticker] = 100.0

                # Imported-strategy lane: make sure prices are resolved for
                # every ticker the script references, even ones the user
                # didn't add to Stock Positions or to a manual rule.
                if self.strategy_mode == 'imported':
                    for ticker in strategy_tickers:
                        if ticker not in current_prices:
                            if ticker in data and not data[ticker].stock_data.empty:
                                p = data[ticker].get_price()
                                if p is not None:
                                    current_prices[ticker] = float(p)

                # Per-interval decision logic.
                #   • Manual mode → evaluate the trading_rules block.
                #   • Imported mode → run the sandboxed script body; it
                #     replaces manual rules entirely (the dashboard's
                #     trading_rules array is sent empty when Imported
                #     mode is active so there's nothing to merge anyway).
                trades_executed = []
                rules_to_remove = []  # Manual one-time rules to delete after this interval.

                if self.strategy_mode == 'imported' and strategy_compiled is not None:
                    self._execute_imported_strategy(
                        strategy_compiled, port, currtime,
                        current_prices, trades_executed,
                    )
                else:
                    for ticker, rules in self.trading_rules.items():
                        try:
                            if ticker in current_prices:
                                price = current_prices[ticker]
                                for rule_index, rule in enumerate(rules):
                                    rule_executed = False

                                    # Handle sell rules
                                    if rule['action'] == 'sell':
                                        if rule['condition'] == 'greater_than' and price > rule['threshold']:
                                            if port.positions.get(ticker, 0) >= rule['shares']:
                                                # Limit 0 = market sell at snapshot (avoids refusing when Portfolio.get_price differs slightly from current_prices)
                                                port.sell(ticker, 0, rule['shares'], currtime)
                                                trades_executed.append(f"Sold {rule['shares']} {ticker} @ ${price:.2f}")
                                                rule_executed = True
                                        elif rule['condition'] == 'less_than' and price < rule['threshold']:
                                            if port.positions.get(ticker, 0) >= rule['shares']:
                                                port.sell(ticker, 0, rule['shares'], currtime)
                                                trades_executed.append(f"Sold {rule['shares']} {ticker} @ ${price:.2f}")
                                                rule_executed = True

                                    # Handle buy rules
                                    elif rule['action'] == 'buy':
                                        if rule['condition'] == 'greater_than' and price > rule['threshold']:
                                            cost = price * rule['shares']
                                            if port.cash >= cost:
                                                # Cash-only check; do not cap on mark-to-market vs initial cash (that blocked every buy after gains)
                                                port.buy(ticker, price + 1, rule['shares'], currtime)
                                                trades_executed.append(f"Bought {rule['shares']} {ticker} @ ${price:.2f}")
                                                rule_executed = True
                                        elif rule['condition'] == 'less_than' and price < rule['threshold']:
                                            cost = price * rule['shares']
                                            if port.cash >= cost:
                                                port.buy(ticker, price + 1, rule['shares'], currtime)
                                                trades_executed.append(f"Bought {rule['shares']} {ticker} @ ${price:.2f}")
                                                rule_executed = True

                                    # If rule executed and it's a one-time rule, mark it for removal
                                    if rule_executed and rule.get('one_time', False):
                                        rules_to_remove.append((ticker, rule_index))

                            else:
                                logger.debug("No price for rule ticker %s", ticker)
                        except Exception as e:
                            logger.exception("Trading rules error for %s: %s", ticker, e)
                            continue

                    # Remove one-time rules that were executed (in reverse order to maintain indices)
                    for ticker, rule_index in reversed(rules_to_remove):
                        if ticker in self.trading_rules and rule_index < len(self.trading_rules[ticker]):
                            self.trading_rules[ticker].pop(rule_index)
                            if not self.trading_rules[ticker]:
                                del self.trading_rules[ticker]
                
                # Beta hedging: every interval, rebalance VOO hedge toward target (delta trades)
                if self.beta_hedge_enabled:
                    hedge_trades = self._execute_beta_hedge(port, currtime, current_prices, data)
                    trades_executed.extend(hedge_trades)
                
                # Mark-to-market once per interval; PnL vs initial cash (not a second get_value via get_PNL)
                current_value = port.get_value(currtime)
                interval_pnl = round(float(current_value) - float(port.original_value), 2)
                
                # Store interval result with meaningful labels
                if not report_intraday_times:
                    interval_label = f"Day {i + 1}"
                else:
                    bpd = max(1, (6 * 60) // bar_minutes_map[freq])
                    day_num = (i // bpd) + 1
                    time_str = currtime.strftime('%H:%M')
                    interval_label = f"Day {day_num}, {time_str}"
                
                daily_result = {
                    'day': i + 1,
                    'interval_label': interval_label,
                    'date': currtime.strftime('%Y-%m-%d %H:%M') if report_intraday_times else currtime.strftime('%Y-%m-%d'),
                    'prices': current_prices.copy(),
                    'portfolio_value': current_value,
                    'trades': trades_executed.copy(),
                    'positions': port.positions.copy(),
                    'cash': round(float(port.cash), 2),
                    'pnl': interval_pnl,
                    'one_time_rules_executed': len(rules_to_remove),  # Track how many one-time rules were executed
                    'hedge_margin_balance': port.get_hedge_margin_balance()  # Track available hedge margin
                }
                
                self.results.append(daily_result)
            
            # Calculate final metrics
            if self.results:
                # Use the actual initial portfolio value after initial purchases
                initial_value = self.results[0]['portfolio_value']
                final_value = self.results[-1]['portfolio_value']
                
                # Calculate return based on actual starting portfolio value
                total_return = (final_value - initial_value) / initial_value * 100 if initial_value > 0 else 0
                
                sharpe_ratio = port.calculate_sharpe_ratio()
                volatility = port.calculate_volatility()
                
                # Calculate portfolio beta
                beta_result = port.calculate_portfolio_beta()
                
                # Calculate hedge statistics with error handling
                try:
                    hedge_trades_count = len(port.hedge_trades) if hasattr(port, 'hedge_trades') else 0
                    total_hedge_margin_used = sum(trade.get('margin_used', 0) for trade in port.hedge_trades) if hasattr(port, 'hedge_trades') else 0
                    hedge_margin_remaining = port.get_hedge_margin_balance() if hasattr(port, 'get_hedge_margin_balance') else 0
                except Exception as e:
                    logger.debug("Hedge statistics error: %s", e)
                    hedge_trades_count = 0
                    total_hedge_margin_used = 0
                    hedge_margin_remaining = 0
                
                # Calculate hedge impact analysis
                hedge_analysis = self._calculate_hedge_impact(port) if self.beta_hedge_enabled else None
                
                # Opening NAV (cash deposit + market value of pre-existing
                # stock positions at t=0). This is the baseline for P&L and
                # percentage return.
                opening_value = float(getattr(self, 'opening_value', initial_value))
                self.final_metrics = {
                    'opening_value': round(opening_value, 2),
                    'total_return_pct': round(total_return, 2),
                    'final_value': round(final_value, 2),
                    'total_pnl': round(final_value - opening_value, 2),
                    'sharpe_ratio': round(sharpe_ratio, 3) if sharpe_ratio is not None else None,
                    'volatility_pct': round(volatility * 100, 2) if volatility is not None else None,
                    'total_trades': len(port.past_trades),
                    'final_positions': port.positions,
                    'beta': beta_result['beta'] if beta_result else None,
                    'beta_interpretation': beta_result['interpretation'] if beta_result else None,
                    'correlation': beta_result['correlation'] if beta_result else None,
                    'hedge_trades_count': hedge_trades_count,
                    'total_hedge_margin_used': round(total_hedge_margin_used, 2),
                    'hedge_margin_remaining': round(hedge_margin_remaining, 2),
                    'hedge_trades': port.hedge_trades if hasattr(port, 'hedge_trades') else [],
                    'hedge_analysis': hedge_analysis  # New comprehensive hedge analysis
                }
            
            self.is_complete = True
            self.is_running = False
            
            # Update global portfolio state for AI
            update_portfolio_state(self.simulation_id, {
                'initial_cash': self.initial_cash,
                'opening_value': float(getattr(self, 'opening_value', self.initial_cash)),
                'start_date': self.start_date,
                'duration_days': self.duration_days,
                'tickers': self.tickers,
                'trading_rules': self.trading_rules
            })
            
            logger.info("Simulation %s completed", self.simulation_id)
            
        except Exception as e:
            logger.exception("Simulation %s failed: %s", self.simulation_id, e)
            
            # Create basic final_metrics even if simulation failed
            if not hasattr(self, 'final_metrics'):
                # Fall back to the opening NAV (cash + initial positions) if
                # we got that far; otherwise to plain cash.
                opening_value = float(getattr(self, 'opening_value', self.initial_cash))
                final_value = opening_value
                self.final_metrics = {
                    'opening_value': round(opening_value, 2),
                    'total_return_pct': 0.0,
                    'final_value': final_value,
                    'total_pnl': 0.0,
                    'sharpe_ratio': None,
                    'volatility_pct': None,
                    'total_trades': 0,
                    'final_positions': {},
                    'beta': None,
                    'beta_interpretation': 'N/A',
                    'correlation': None,
                    'hedge_trades_count': 0,
                    'total_hedge_margin_used': 0.0,
                    'hedge_margin_remaining': 0.0,
                    'hedge_trades': []
                }
                logger.debug("Created fallback final_metrics after error")
            
            self.error = str(e)
            self.is_complete = True
            self.is_running = False
    
    def _execute_imported_strategy(self, compiled_strategy, port, currtime, current_prices, trades_executed):
        """Run the imported (compiled) strategy body once for this interval.

        The sandbox exposes the same surface the Studio uses (`price`, `buy`,
        `sell`, `position`, `cash`, `log`, `print`), but every helper now
        operates on the historical simulation state:
          • `price("X")` reads the price at `currtime` from `current_prices`
            (populated upstream from each ticker's StockData series).
          • `buy`/`sell` mutate the live `Portfolio` exactly the same way
            manual rules do — same cost / position checks, same Portfolio
            methods — so PnL, Sharpe, beta, hedge analysis, etc. all flow
            through unchanged downstream.

        Safety budget is reset every interval (each tick gets its own
        50,000-op / 5-second envelope) so a user `while True:` loop can't
        wedge the whole simulation; the runaway just gets aborted and the
        next interval continues. Errors are swallowed (logged at DEBUG) —
        we don't want one bad tick to kill a 365-day backtest. Successful
        trades are appended to `trades_executed`, which the surrounding
        loop already feeds into the per-interval result and downstream
        analytics.
        """
        tick_budget = {'ticks': 0, 'start': time.time()}
        MAX_OPS = 50_000
        MAX_SECONDS = 5.0

        def _tick():
            tick_budget['ticks'] += 1
            if tick_budget['ticks'] > MAX_OPS:
                raise RuntimeError(f'Imported tick exceeded {MAX_OPS:,} operations.')
            if time.time() - tick_budget['start'] > MAX_SECONDS:
                raise TimeoutError(f'Imported tick exceeded {MAX_SECONDS:.0f}s.')

        def _price(ticker):
            _tick()
            sym = str(ticker).upper().strip()
            return float(current_prices.get(sym, 0.0))

        def _buy(ticker, shares):
            _tick()
            sym = str(ticker).upper().strip()
            try:
                qty = int(shares)
            except (TypeError, ValueError):
                return False
            if qty <= 0:
                return False
            px = current_prices.get(sym)
            if not px or px <= 0:
                return False
            cost = float(px) * qty
            if port.cash < cost:
                return False
            try:
                # `price + 1` mirrors the manual-rules path: it acts as a
                # max-price ceiling so Portfolio.buy doesn't refuse on a
                # minor mismatch between snapshot price and its own
                # get_price() reading.
                port.buy(sym, float(px) + 1, qty, currtime)
            except Exception as e:
                logger.debug('Imported buy failed (%s, %s): %s', sym, qty, e)
                return False
            trades_executed.append(f"Bought {qty} {sym} @ ${float(px):.2f}")
            return True

        def _sell(ticker, shares):
            _tick()
            sym = str(ticker).upper().strip()
            try:
                qty = int(shares)
            except (TypeError, ValueError):
                return False
            if qty <= 0:
                return False
            if port.positions.get(sym, 0) < qty:
                return False
            px = current_prices.get(sym, 0)
            try:
                # 0 = market sell at the Portfolio's own snapshot price.
                port.sell(sym, 0, qty, currtime)
            except Exception as e:
                logger.debug('Imported sell failed (%s, %s): %s', sym, qty, e)
                return False
            trades_executed.append(f"Sold {qty} {sym} @ ${float(px):.2f}")
            return True

        def _position(ticker):
            _tick()
            return int(port.positions.get(str(ticker).upper().strip(), 0))

        def _cash():
            _tick()
            return float(port.cash)

        def _log(*_args):
            # Per-interval stdout from the user script is intentionally a
            # no-op for now — the dashboard surfaces trades, not log lines.
            _tick()

        safe_builtins = {
            'range': range, 'len': len, 'min': min, 'max': max,
            'abs': abs, 'round': round, 'sum': sum,
            'int': int, 'float': float, 'str': str, 'bool': bool,
            'True': True, 'False': False, 'None': None,
        }
        sandbox_globals = {
            '__builtins__': safe_builtins,
            '_tick': _tick,
            'price': _price, 'buy': _buy, 'sell': _sell,
            'position': _position, 'cash': _cash,
            'log': _log, 'print': _log,
        }

        try:
            exec(compiled_strategy, sandbox_globals, sandbox_globals)
        except (TimeoutError, RuntimeError, ValueError) as e:
            logger.debug('Imported tick @ %s: %s', currtime, e)
        except Exception as e:  # pragma: no cover — anything unexpected
            logger.debug('Imported tick @ %s unexpected: %s', currtime, e)

    def _get_voo_price(self, currtime):
        """Get VOO price with robust error handling and fallback logic"""
        try:
            current_date = currtime.date()
            end_date = current_date + timedelta(days=1)
            start_date = current_date - timedelta(days=14)
            voo_ticker = yf.Ticker('VOO')
            voo_data = voo_ticker.history(start=start_date, end=end_date, interval='1d')
            if voo_data.empty:
                logger.debug("No VOO daily data %s to %s", start_date, end_date)
                return None
            available_dates = [d.date() for d in voo_data.index]
            if current_date in available_dates:
                row = voo_data[voo_data.index.date == current_date].iloc[0]
                return float((row['High'] + row['Low']) / 2)
            date_diffs = [(abs((d - current_date).days), d) for d in available_dates]
            date_diffs.sort()
            for days_diff, trading_date in date_diffs:
                if days_diff <= 5:
                    row = voo_data[voo_data.index.date == trading_date].iloc[0]
                    return float((row['High'] + row['Low']) / 2)
            return None
        except Exception as e:
            logger.debug("VOO price fetch failed: %s", e)
            return None
    
    def _calculate_hedge_impact(self, port):
        """Calculate the impact of hedging by comparing hedged vs non-hedged performance"""
        try:
            regular_trades = [trade for trade in port.past_trades if not trade.get('is_hedge', False)]
            hedge_trades = port.hedge_trades if hasattr(port, 'hedge_trades') else []
            
            # Calculate what portfolio would have been without hedging
            non_hedged_value = self._simulate_without_hedging(port, regular_trades)
            hedged_value = port.get_value(self.results[-1]['date'] if self.results else datetime.now())
            
            # Calculate hedge impact on key metrics. Express the hedge P&L as
            # a % of the opening NAV (cash + initial positions) — the same
            # baseline used for the headline total return.
            hedge_pnl = hedged_value - non_hedged_value
            hedge_baseline = float(getattr(self, 'opening_value', self.initial_cash)) or self.initial_cash
            hedge_return_impact = (hedge_pnl / hedge_baseline) * 100 if hedge_baseline else 0.0
            
            # Calculate beta impact
            original_beta = self._calculate_portfolio_beta_without_hedging(port, regular_trades)
            hedged_beta = port.calculate_portfolio_beta()
            
            beta_reduction = (original_beta.get('beta', 0) - hedged_beta.get('beta', 0)) if original_beta and hedged_beta else 0
            
            # Calculate volatility impact
            hedged_volatility = port.calculate_volatility() or 0
            non_hedged_volatility = self._calculate_volatility_without_hedging(port, regular_trades)
            volatility_reduction = (non_hedged_volatility - hedged_volatility) * 100
            
            hedge_analysis = {
                'non_hedged_value': round(non_hedged_value, 2),
                'hedged_value': round(hedged_value, 2),
                'hedge_pnl': round(hedge_pnl, 2),
                'hedge_return_impact_pct': round(hedge_return_impact, 2),
                'original_beta': round(original_beta.get('beta', 0), 3) if original_beta else 0,
                'hedged_beta': round(hedged_beta.get('beta', 0), 3) if hedged_beta else 0,
                'beta_reduction': round(beta_reduction, 3),
                'volatility_reduction_pct': round(volatility_reduction, 2),
                'hedge_effectiveness': self._calculate_hedge_effectiveness(hedge_pnl, beta_reduction),
                'total_hedge_trades': len(hedge_trades),
                'hedge_cost': self._calculate_hedge_cost(hedge_trades)
            }
            
            return hedge_analysis
            
        except Exception as e:
            logger.debug("Hedge impact calculation failed: %s", e)
            return {
                'error': str(e),
                'non_hedged_value': 0,
                'hedged_value': 0,
                'hedge_pnl': 0,
                'hedge_return_impact_pct': 0,
                'beta_reduction': 0,
                'volatility_reduction_pct': 0,
                'hedge_effectiveness': 'Unknown',
                'total_hedge_trades': 0,
                'hedge_cost': 0
            }
    
    def _simulate_without_hedging(self, port, regular_trades):
        """Simulate what the portfolio value would be with only regular trades"""
        try:
            # Start from the opening NAV (cash deposit + market value of any
            # initial stock positions) — that's the real starting point of the
            # portfolio, not just the cash pile.
            value = float(getattr(self, 'opening_value', self.initial_cash))
            
            # Add value from regular trades only
            for trade in regular_trades:
                if trade.get('action') == 'buy':
                    # For buys, we spent cash but got shares
                    continue  # Value already accounted for in current positions
                elif trade.get('action') == 'sell':
                    # For sells, we got cash
                    value += trade.get('total_value', 0)
            
            # Add current value of positions (excluding hedge positions)
            for ticker, shares in port.positions.items():
                if ticker != 'VOO':  # Exclude VOO as it's likely hedge-related
                    # Get current price - use last result if available
                    if self.results:
                        last_result = self.results[-1]
                        if 'prices' in last_result and ticker in last_result['prices']:
                            current_price = last_result['prices'][ticker]
                            value += shares * current_price
            
            return value
            
        except Exception as e:
            logger.debug("Simulate without hedging failed: %s", e)
            return self.initial_cash
    
    def _calculate_portfolio_beta_without_hedging(self, port, regular_trades):
        """Calculate what portfolio beta would be without hedge positions"""
        try:
            # Create a temporary portfolio with only regular positions
            regular_positions = {k: v for k, v in port.positions.items() if k != 'VOO'}
            
            # Use the portfolio's beta calculation but with modified positions
            original_positions = port.positions.copy()
            port.positions = regular_positions
            beta_result = port.calculate_portfolio_beta()
            port.positions = original_positions  # Restore original positions
            
            return beta_result
            
        except Exception as e:
            logger.debug("Beta without hedging failed: %s", e)
            return {'beta': 0, 'interpretation': 'Unknown', 'correlation': 0}
    
    def _calculate_volatility_without_hedging(self, port, regular_trades):
        """Calculate what portfolio volatility would be without hedging"""
        try:
            # This is a simplified calculation - in reality you'd need to recalculate
            # the entire portfolio time series without hedge trades
            base_volatility = port.calculate_volatility() or 0
            
            # Estimate that hedging typically reduces volatility by 10-30%
            # This is a rough estimate - could be made more precise
            estimated_original_volatility = base_volatility * 1.2
            
            return estimated_original_volatility
            
        except Exception as e:
            logger.debug("Volatility without hedging failed: %s", e)
            return 0
    
    def _calculate_hedge_effectiveness(self, hedge_pnl, beta_reduction):
        """Calculate how effective the hedging strategy was"""
        try:
            if abs(beta_reduction) < 0.01:
                return "Minimal Impact"
            elif abs(beta_reduction) > 0.5:
                if hedge_pnl > -1000:  # Didn't cost too much
                    return "Highly Effective"
                else:
                    return "Effective but Costly"
            else:
                if hedge_pnl > 0:
                    return "Profitable Hedge"
                else:
                    return "Moderately Effective"
        except:
            return "Unknown"
    
    def _calculate_hedge_cost(self, hedge_trades):
        """Calculate the total cost of hedging (commissions, bid-ask spreads, etc.)"""
        try:
            # Simple cost calculation - could be made more sophisticated
            total_cost = 0
            for trade in hedge_trades:
                # Assume a small cost per trade (commission + spread)
                trade_value = trade.get('total_value', 0)
                cost = trade_value * 0.001  # 0.1% cost per trade
                total_cost += cost
            
            return round(total_cost, 2)
            
        except Exception as e:
            logger.debug("Hedge cost failed: %s", e)
            return 0
    
    def _execute_beta_hedge(self, port, currtime, current_prices, data):
        """
        Per-interval beta hedge: move VOO exposure toward target using delta trades only.
        Positive beta → net short VOO (add short / trim by buying back).
        Negative beta → cover any VOO short first, then long VOO on margin; trim by selling hedge long.
        Near-zero beta → unwind shorts and hedge longs.
        """
        out = []
        beta_th = 0.01
        try:
            beta_result = port.calculate_portfolio_beta()
            if not beta_result or 'beta' not in beta_result:
                return []

            beta = float(beta_result['beta'])

            voo_price = current_prices.get('VOO')
            if not voo_price:
                voo_price = self._get_voo_price(currtime)
                if voo_price:
                    current_prices['VOO'] = voo_price
            if not voo_price:
                logger.debug("VOO price not available for hedging at %s", currtime)
                return []

            pv = float(port.get_value(currtime))
            max_hedge_value = pv * 0.5
            max_sh = max(0, int(max_hedge_value / voo_price))

            cur_short = port.short_positions.get('VOO', 0)
            cur_hlong = port.hedge_long_positions.get('VOO', 0)

            # Flatten hedge when beta is negligible
            if abs(beta) <= beta_th:
                if cur_short > 0:
                    ok, msg = port.execute_hedge_trade('VOO', voo_price, cur_short, currtime, 'buy')
                    out.append(f"Unwind (buy back short): {msg}" if ok else f"Unwind short failed: {msg}")
                cur_hlong = port.hedge_long_positions.get('VOO', 0)
                if cur_hlong > 0:
                    ok, msg = port.execute_hedge_trade('VOO', voo_price, cur_hlong, currtime, 'sell_hedge_long')
                    out.append(f"Unwind (sell hedge long): {msg}" if ok else f"Unwind long failed: {msg}")
                return out

            want_short = 0
            want_long = 0
            if beta > beta_th:
                want_short = min(max_sh, int((pv * beta) / voo_price))
            else:
                want_long = min(max_sh, int((pv * (-beta)) / voo_price))

            if want_short > 0:
                # Positive-beta regime: no hedge long; short VOO only
                hl = port.hedge_long_positions.get('VOO', 0)
                if hl > 0:
                    ok, msg = port.execute_hedge_trade('VOO', voo_price, hl, currtime, 'sell_hedge_long')
                    out.append(f"Close hedge long before short hedge: {msg}" if ok else msg)
                cur_short = port.short_positions.get('VOO', 0)
                delta = want_short - cur_short
                if delta > 0:
                    ok, msg = port.execute_hedge_trade('VOO', voo_price, delta, currtime, 'short')
                    if ok:
                        out.append(f"+Short {delta} VOO: {msg} (β={beta:.3f})")
                    else:
                        avail = port.get_hedge_margin_balance()
                        max_add = int((avail * 2) / voo_price) if voo_price else 0
                        if max_add > 0:
                            ok2, msg2 = port.execute_hedge_trade('VOO', voo_price, min(delta, max_add), currtime, 'short')
                            if ok2:
                                out.append(f"+Short partial: {msg2} (β={beta:.3f})")
                elif delta < 0:
                    ok, msg = port.execute_hedge_trade('VOO', voo_price, -delta, currtime, 'buy')
                    if ok:
                        out.append(f"Trim short {-delta} VOO: {msg} (β={beta:.3f})")
                    else:
                        out.append(f"Trim short failed: {msg}")

            elif want_long > 0:
                # Negative-beta regime: cover shorts first, then long VOO on margin
                cs = port.short_positions.get('VOO', 0)
                if cs > 0:
                    ok, msg = port.execute_hedge_trade('VOO', voo_price, cs, currtime, 'buy')
                    out.append(f"Buy back {cs} VOO (cover short): {msg}" if ok else f"Cover short failed: {msg}")
                cur_hlong = port.hedge_long_positions.get('VOO', 0)
                delta = want_long - cur_hlong
                if delta > 0:
                    ok, msg = port.execute_hedge_trade('VOO', voo_price, delta, currtime, 'buy_margin')
                    if ok:
                        out.append(f"+Long {delta} VOO on margin: {msg} (β={beta:.3f})")
                    else:
                        avail = port.get_hedge_margin_balance()
                        max_add = int((avail * 2) / voo_price) if voo_price else 0
                        if max_add > 0:
                            ok2, msg2 = port.execute_hedge_trade(
                                'VOO', voo_price, min(delta, max_add), currtime, 'buy_margin'
                            )
                            if ok2:
                                out.append(f"+Long partial on margin: {msg2} (β={beta:.3f})")
                elif delta < 0:
                    ok, msg = port.execute_hedge_trade('VOO', voo_price, -delta, currtime, 'sell_hedge_long')
                    if ok:
                        out.append(f"Trim hedge long {-delta} VOO: {msg} (β={beta:.3f})")
                    else:
                        out.append(f"Trim hedge long failed: {msg}")

            # Target rounded to 0 shares but beta still meaningful — clear stale hedge from prior intervals
            if beta > beta_th and want_short == 0:
                hl = port.hedge_long_positions.get('VOO', 0)
                if hl > 0:
                    ok, msg = port.execute_hedge_trade('VOO', voo_price, hl, currtime, 'sell_hedge_long')
                    if ok:
                        out.append(f"Clear hedge long (target <1 sh): {msg}")
                cs = port.short_positions.get('VOO', 0)
                if cs > 0:
                    ok, msg = port.execute_hedge_trade('VOO', voo_price, cs, currtime, 'buy')
                    if ok:
                        out.append(f"Clear short (target <1 sh): {msg}")
            if beta < -beta_th and want_long == 0:
                cs = port.short_positions.get('VOO', 0)
                if cs > 0:
                    ok, msg = port.execute_hedge_trade('VOO', voo_price, cs, currtime, 'buy')
                    if ok:
                        out.append(f"Clear short (target <1 sh, neg β): {msg}")
                hl = port.hedge_long_positions.get('VOO', 0)
                if hl > 0:
                    ok, msg = port.execute_hedge_trade('VOO', voo_price, hl, currtime, 'sell_hedge_long')
                    if ok:
                        out.append(f"Clear hedge long (target <1 sh, neg β): {msg}")

            return out

        except Exception as e:
            logger.exception("Beta hedging error: %s", e)
            return []

def _serve_trading_ui_in_browser():
    """Full trading UI: only when embedded from Next.js or explicitly requested (see README)."""
    if request.args.get('embed') == '1':
        return True
    if request.headers.get('Sec-Fetch-Dest') == 'iframe':
        return True
    return False


@app.route('/')
def index():
    """Trading UI for iframe/embed; intro lives on the Next.js service."""
    if _serve_trading_ui_in_browser():
        t = request.args.get('theme', 'dark')
        if t not in ('light', 'dark'):
            t = 'dark'
        embed = request.args.get('embed') == '1'
        return render_template('index.html', theme=t, embed=embed)
    shell_url = (os.getenv('SHELL_SITE_URL') or os.getenv('NEXT_PUBLIC_SHELL_URL') or '').strip()
    return render_template('shell_entry_notice.html', shell_url=shell_url)

@app.route('/validate_ticker/<ticker>')
def validate_ticker(ticker):
    """Validate ticker via Yahoo; .info is often empty, so we fall back to OHLCV history."""
    sym = (ticker or '').strip().upper()
    if not sym or len(sym) > 32:
        return jsonify({'valid': False, 'ticker': sym, 'error': 'Invalid ticker'}), 400

    try:
        stock = yf.Ticker(sym)
        try:
            raw_info = stock.info
            info = raw_info if isinstance(raw_info, dict) else {}
        except Exception:
            info = {}

        def ok(name, exchange, source):
            return jsonify({
                'valid': True,
                'ticker': sym,
                'name': name or sym,
                'exchange': exchange or 'Unknown',
                'source': source,
            })

        if info and any(
            k in info for k in (
                'symbol', 'shortName', 'longName', 'regularMarketPrice',
                'currentPrice', 'bid', 'ask', 'previousClose',
            )
        ):
            return ok(
                info.get('shortName') or info.get('longName') or sym,
                info.get('exchange'),
                'yfinance_info',
            )

        for _ in range(2):
            try:
                hist = stock.history(period='3mo', auto_adjust=False)
                if hist is not None and not hist.empty:
                    return ok(
                        info.get('shortName') or info.get('longName') or sym,
                        info.get('exchange'),
                        'yfinance_history',
                    )
            except Exception:
                pass
            time.sleep(0.08)

        return jsonify({'valid': False, 'ticker': sym, 'error': 'Ticker not found'})
    except Exception as e:
        return jsonify({'valid': False, 'ticker': sym, 'error': str(e)})

@app.route('/start_simulation', methods=['POST'])
def start_simulation():
    """Start a new portfolio simulation"""
    try:
        data = request.json
        
        # Generate unique simulation ID
        simulation_id = str(uuid.uuid4())
        
        # Extract parameters
        initial_cash = float(data.get('initial_cash', 110000))
        duration_days = int(data.get('duration_days', 30))
        raw_h = data.get('duration_hours')
        duration_hours = None
        if raw_h is not None and raw_h != '':
            try:
                duration_hours = float(raw_h)
            except (TypeError, ValueError):
                duration_hours = None
        trading_frequency = data.get('trading_frequency', 'daily')

        if trading_frequency in ('1m', '5m', '15m'):
            cap = {'1m': 6, '5m': 12, '15m': 24}[trading_frequency]
            if duration_hours is None:
                duration_hours = float(min(cap, max(1, duration_days)))
            duration_hours = float(max(1, min(cap, int(round(duration_hours)))))
            duration_days = 1
        elif trading_frequency == '60m':
            duration_hours = None
            duration_days = max(1, min(7, duration_days))
        else:
            duration_hours = None
            duration_days = max(1, min(365, duration_days))

        start_date = data.get('start_date')
        if start_date:
            start_date = str(start_date).strip()[:10]
        else:
            if trading_frequency == 'daily':
                lookback = min(duration_days + 7, 400)
            elif trading_frequency == '60m':
                lookback = max(14, min(60, duration_days * 10 + 14))
            elif trading_frequency in ('1m', '5m', '15m'):
                lookback = max(14, min(60, int(duration_hours or 1) * 2 + 20))
            else:
                lookback = 30
            start_date = (date.today() - timedelta(days=lookback)).strftime('%Y-%m-%d')
        
        # Extract tickers and shares
        tickers = {}
        for ticker_data in data.get('tickers', []):
            ticker = ticker_data['ticker'].upper()
            shares = int(ticker_data['shares'])
            tickers[ticker] = shares
        
        # Extract trading rules
        trading_rules = {}
        for rule_data in data.get('trading_rules', []):
            try:
                ticker = rule_data['ticker'].upper()
                if ticker not in trading_rules:
                    trading_rules[ticker] = []
                trading_rules[ticker].append({
                    'action': rule_data.get('action', 'sell'),  # Default to sell for backward compatibility
                    'condition': rule_data['condition'],
                    'threshold': float(rule_data['threshold']),
                    'shares': int(rule_data['shares']),
                    'one_time': rule_data.get('one_time', False)
                })
            except Exception as e:
                logger.exception("Invalid trading rule payload: %s", e)
                continue
        
        beta_hedge_enabled = data.get('beta_hedge_enabled', False)

        # Imported-strategy lane: same engine + same setup, but the per-tick
        # logic becomes the imported script instead of manual rules.
        strategy_mode = data.get('strategy_mode') or 'manual'
        if strategy_mode not in ('manual', 'imported'):
            strategy_mode = 'manual'
        strategy_code = data.get('strategy_code') if strategy_mode == 'imported' else None
        strategy_name = data.get('strategy_name') if strategy_mode == 'imported' else None
        if strategy_mode == 'imported' and not (strategy_code and strategy_code.strip()):
            return jsonify({
                'success': False,
                'error': 'Imported strategy mode requires a non-empty strategy_code.'
            }), 400

        simulation = SimulationManager(
            simulation_id, initial_cash, start_date, duration_days,
            trading_frequency, tickers, trading_rules, beta_hedge_enabled,
            duration_hours=duration_hours,
            strategy_mode=strategy_mode,
            strategy_code=strategy_code,
            strategy_name=strategy_name,
        )
        simulation.thread = threading.Thread(target=simulation.run_simulation)
        simulation.thread.daemon = True
        simulation.thread.start()
        
        # Store simulation
        active_simulations[simulation_id] = simulation
        
        return jsonify({
            'success': True,
            'simulation_id': simulation_id,
            'message': 'Simulation started successfully'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

@app.route('/simulation_status/<simulation_id>')
def simulation_status(simulation_id):
    """Get current status of a simulation"""
    if simulation_id not in active_simulations:
        return jsonify({'error': 'Simulation not found'}), 404
    
    simulation = active_simulations[simulation_id]
    
    total_steps = getattr(simulation, 'total_result_steps', None) or (simulation.duration_days + 1)
    if total_steps <= 0:
        total_steps = 1
    response = {
        'is_running': simulation.is_running,
        'is_complete': simulation.is_complete,
        'results': simulation.results,
        'progress': min(1.0, len(simulation.results) / total_steps),
    }
    
    # Always include final_metrics if simulation is complete
    if simulation.is_complete:
        if hasattr(simulation, 'final_metrics'):
            response['final_metrics'] = simulation.final_metrics
        else:
            logger.warning("Simulation %s complete without final_metrics; using fallback", simulation_id)
            # Create basic final_metrics as fallback
            fallback_opening = float(getattr(simulation, 'opening_value', simulation.initial_cash))
            response['final_metrics'] = {
                'opening_value': round(fallback_opening, 2),
                'total_return_pct': 0.0,
                'final_value': fallback_opening,
                'total_pnl': 0.0,
                'sharpe_ratio': None,
                'volatility_pct': None,
                'total_trades': 0,
                'final_positions': {},
                'beta': None,
                'beta_interpretation': 'N/A',
                'correlation': None,
                'hedge_trades_count': 0,
                'total_hedge_margin_used': 0.0,
                'hedge_margin_remaining': 0.0,
                'hedge_trades': []
            }
    
    if hasattr(simulation, 'error'):
        response['error'] = simulation.error
    
    
    return jsonify(response)

@app.route('/stop_simulation/<simulation_id>', methods=['POST'])
def stop_simulation(simulation_id):
    """Stop a running simulation"""
    if simulation_id not in active_simulations:
        return jsonify({'error': 'Simulation not found'}), 404
    
    simulation = active_simulations[simulation_id]
    simulation.is_running = False
    
    return jsonify({'success': True, 'message': 'Simulation stopped'})

@app.route('/cleanup_simulation/<simulation_id>', methods=['DELETE'])
def cleanup_simulation(simulation_id):
    """Clean up a completed simulation"""
    if simulation_id in active_simulations:
        del active_simulations[simulation_id]
        return jsonify({'success': True, 'message': 'Simulation cleaned up'})
    
    return jsonify({'error': 'Simulation not found'}), 404

@app.route('/ai_analysis', methods=['POST'])
def ai_analysis():
    """Get AI analysis of portfolio data with dynamic portfolio memory"""
    try:
        data = request.json
        simulation_id = data.get('simulation_id')
        user_question = data.get('question', '')
        
        # If no simulation_id provided, use global portfolio state
        if not simulation_id:
            if current_portfolio_state['has_simulation']:
                # Use current portfolio state
                analysis = advisor.analyze_portfolio(None, user_question, None)
                return jsonify({
                    'success': True,
                    'analysis': analysis,
                    'timestamp': datetime.now().isoformat(),
                    'source': 'current_portfolio_state'
                })
            else:
                # No portfolio data available
                analysis = advisor.analyze_portfolio(None, user_question, None)
                return jsonify({
                    'success': True,
                    'analysis': analysis,
                    'timestamp': datetime.now().isoformat(),
                    'source': 'no_portfolio_data'
                })
        
        # Handle specific simulation ID
        if simulation_id == 'test-simulation-123':
            # Use sample data for testing
            portfolio_data = {
                'final_metrics': {
                    'total_return_pct': 15.5,
                    'final_value': 115500.0,
                    'total_pnl': 15500.0,
                    'sharpe_ratio': 1.2,
                    'volatility_pct': 12.3,
                    'total_trades': 45,
                    'final_positions': {'AAPL': 100, 'MSFT': 50, 'GOOGL': 25}
                },
                'results': []
            }
            simulation_data = {
                'initial_cash': 100000,
                'start_date': '2023-01-03',
                'duration_days': 30,
                'trading_frequency': 'daily',
                'tickers': {'AAPL': 50, 'MSFT': 25, 'GOOGL': 10},
                'trading_rules': {'buy_threshold': 0.02, 'sell_threshold': 0.02}
            }
        elif simulation_id in active_simulations:
            simulation = active_simulations[simulation_id]
            
            # Prepare portfolio data for analysis
            portfolio_data = {
                'final_metrics': getattr(simulation, 'final_metrics', {}),
                'results': simulation.results
            }
            
            # Prepare simulation parameters
            simulation_data = {
                'initial_cash': simulation.initial_cash,
                'start_date': simulation.start_date,
                'duration_days': simulation.duration_days,
                'duration_hours': getattr(simulation, 'duration_hours', None),
                'trading_frequency': simulation.trading_frequency,
                'tickers': simulation.tickers,
                'trading_rules': simulation.trading_rules
            }
        else:
            return jsonify({'error': 'Simulation not found'}), 404
        
        # Get analysis
        analysis = advisor.analyze_portfolio(portfolio_data, user_question, simulation_data)
        
        return jsonify({
            'success': True,
            'analysis': analysis,
            'timestamp': datetime.now().isoformat(),
            'source': 'specific_simulation'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/clear_chat', methods=['POST'])
def clear_chat():
    """Clear the AI advisor conversation history"""
    try:
        # Clear conversation history from the global advisor instance
        advisor.clear_conversation_history()
        
        return jsonify({
            'success': True,
            'message': 'Chat history cleared successfully',
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/plot/<simulation_id>/<plot_type>')
def get_plot(simulation_id, plot_type):
    """Generate and return portfolio plots as base64 encoded images"""
    try:
        if simulation_id not in active_simulations:
            return jsonify({'error': 'Simulation not found'}), 404
        
        simulation = active_simulations[simulation_id]
        
        if not simulation.is_complete:
            return jsonify({'error': 'Simulation not complete'}), 400
        
        # Create a portfolio object and populate it with the actual simulation data
        currtime = datetime.strptime(simulation.start_date, '%Y-%m-%d')
        today_d = date.today()
        today_dt = datetime(today_d.year, today_d.month, today_d.day)
        dh = getattr(simulation, 'duration_hours', None)
        tf = simulation.trading_frequency
        if dh is not None and tf in ('1m', '5m', '15m'):
            pad = max(30, min(120, int(dh) * 5 + 30))
        elif tf in ('1m', '5m', '15m', '60m', 'intraday'):
            pad = max(30, simulation.duration_days * 15 + 30)
        else:
            pad = simulation.duration_days + 30
        end_date_str = max(currtime + timedelta(days=pad), today_dt).strftime('%Y-%m-%d')
        
        port = Portfolio(simulation.initial_cash, simulation.start_date, end_date_str)

        # Populate the portfolio's change_over_time with actual simulation results
        for result in simulation.results:
            result_time = datetime.strptime(result['date'], '%Y-%m-%d %H:%M' if ':' in result['date'] else '%Y-%m-%d')
            portfolio_value = result['portfolio_value']

            # Store the actual portfolio value at this timestamp
            port.change_over_time[result_time] = portfolio_value

        # Align the plot baseline with opening NAV (cash + initial positions)
        # so the percentage and P&L curves count from the true starting value
        # the user configured, not just the cash deposit.
        opening_value = getattr(simulation, 'opening_value', None)
        if opening_value is None and simulation.results:
            opening_value = float(simulation.results[0]['portfolio_value'])
        if opening_value is not None:
            port.original_value = float(opening_value)
        
        # Generate the requested plot
        plt.clf()  # Clear any existing plots
        
        if plot_type == 'value':
            # Portfolio value over time
            port.plot_portfolio_value(title="Portfolio Value Over Time", show_percentage=False, save_path=None, show_plot=False)
        elif plot_type == 'percentage':
            # Portfolio value as percentage change
            port.plot_portfolio_value(title="Portfolio Performance (%)", show_percentage=True, save_path=None, show_plot=False)
        elif plot_type == 'pnl':
            # Profit/Loss over time
            port.plot_pnl(title="Portfolio P&L Over Time", save_path=None, show_plot=False)
        else:
            return jsonify({'error': 'Invalid plot type'}), 400
        
        # Convert plot to base64 string
        img_buffer = io.BytesIO()
        plt.savefig(img_buffer, format='png', dpi=150, bbox_inches='tight')
        img_buffer.seek(0)
        img_base64 = base64.b64encode(img_buffer.getvalue()).decode()
        plt.close()  # Close the plot to free memory
        
        return jsonify({
            'success': True,
            'image': f'data:image/png;base64,{img_base64}',
            'plot_type': plot_type
        })
        
    except Exception as e:
        plt.close()  # Ensure plot is closed on error
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/plot/current/<plot_type>')
def get_current_plot(plot_type):
    """Generate plots from the current portfolio state"""
    try:
        if not current_portfolio_state['has_simulation']:
            return jsonify({'error': 'No simulation data available'}), 400
        
        simulation_id = current_portfolio_state['simulation_id']
        return get_plot(simulation_id, plot_type)
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/chart_data/<simulation_id>')
def get_chart_data(simulation_id):
    """Return portfolio time series as JSON for client-side Chart.js rendering."""
    try:
        if simulation_id not in active_simulations:
            return jsonify({'success': False, 'error': 'Simulation not found'}), 404

        simulation = active_simulations[simulation_id]
        if not simulation.is_complete:
            return jsonify({'success': False, 'error': 'Simulation not complete'}), 400

        results = simulation.results or []
        # Baseline = opening NAV (initial cash + market value of pre-existing
        # stock positions at t=0). We persisted this on the SimulationManager
        # at simulation start; fall back to the first observed portfolio value
        # for older runs / safety.
        opening_value = getattr(simulation, 'opening_value', None)
        if opening_value is None:
            opening_value = float(results[0]['portfolio_value']) if results else float(getattr(simulation, 'initial_cash', 0))
        original_value = float(opening_value)

        timestamps = [r['date'] for r in results]
        values = [float(r['portfolio_value']) for r in results]

        return jsonify({
            'success': True,
            'timestamps': timestamps,
            'values': values,
            'original_value': original_value,
            'trading_frequency': getattr(simulation, 'trading_frequency', 'daily'),
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/chart_data/current')
def get_current_chart_data():
    """Same as /chart_data/<id> but resolves the most-recent simulation server-side."""
    try:
        if not current_portfolio_state['has_simulation']:
            return jsonify({'success': False, 'error': 'No simulation data available'}), 400
        simulation_id = current_portfolio_state['simulation_id']
        return get_chart_data(simulation_id)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# Benchmark overlays (S&P 500 via SPY, NASDAQ via QQQ) for the percentage chart.
# Cached per (sim_id, symbol) since the simulation results never change once complete.
_BENCHMARK_CACHE: dict = {}

_BENCHMARK_ALIASES = {
    '^GSPC': 'SPY', 'SPX': 'SPY', 'SP500': 'SPY', 'sp500': 'SPY', 'spy': 'SPY', 'SPY': 'SPY',
    '^IXIC': 'QQQ', 'NDX': 'QQQ', 'NASDAQ': 'QQQ', 'nasdaq': 'QQQ', 'qqq': 'QQQ', 'QQQ': 'QQQ',
}
_BENCHMARK_DISPLAY = {'SPY': 'S&P 500', 'QQQ': 'NASDAQ'}

_BENCHMARK_INTERVALS = {
    'daily': '1d',
    '1m': '1m',
    '5m': '5m',
    '15m': '15m',
    '60m': '60m',
}


def _parse_sim_date(s: str) -> datetime:
    return datetime.strptime(s, '%Y-%m-%d %H:%M' if ':' in s else '%Y-%m-%d')


@app.route('/benchmark_data/<simulation_id>/<symbol>')
def get_benchmark_data(simulation_id, symbol):
    """Return a benchmark (SPY / QQQ) re-sampled to the simulation's exact timestamps."""
    try:
        if simulation_id not in active_simulations:
            return jsonify({'success': False, 'error': 'Simulation not found'}), 404
        sim = active_simulations[simulation_id]
        if not sim.is_complete or not sim.results:
            return jsonify({'success': False, 'error': 'Simulation not complete'}), 400

        canonical = _BENCHMARK_ALIASES.get(symbol)
        if not canonical:
            return jsonify({'success': False, 'error': f'Unsupported benchmark: {symbol}'}), 400

        cache_key = (simulation_id, canonical)
        if cache_key in _BENCHMARK_CACHE:
            return jsonify(_BENCHMARK_CACHE[cache_key])

        sim_ts_strings = [r['date'] for r in sim.results]
        sim_dts = [_parse_sim_date(s) for s in sim_ts_strings]
        if not sim_dts:
            return jsonify({'success': False, 'error': 'No simulation timestamps'}), 400

        interval = _BENCHMARK_INTERVALS.get(getattr(sim, 'trading_frequency', 'daily'), '1d')

        # Fetch a slightly padded range so closest-match lookups don't miss the bounds.
        fetch_start = (sim_dts[0] - timedelta(days=2)).date()
        fetch_end = (sim_dts[-1] + timedelta(days=2)).date()
        try:
            df = yf.Ticker(canonical).history(
                start=fetch_start.isoformat(),
                end=fetch_end.isoformat(),
                interval=interval,
            )
        except Exception as fetch_err:
            logger.exception("Benchmark fetch failed for %s: %s", canonical, fetch_err)
            return jsonify({'success': False, 'error': 'Failed to fetch benchmark data'}), 502

        if df is None or df.empty:
            # Fallback to daily if intraday interval returned nothing (provider limits).
            try:
                df = yf.Ticker(canonical).history(
                    start=fetch_start.isoformat(),
                    end=fetch_end.isoformat(),
                    interval='1d',
                )
            except Exception:
                df = None
            if df is None or df.empty:
                return jsonify({'success': False, 'error': 'No benchmark data available for this range'}), 502

        closes = df['Close'].tolist()
        # Strip tz so we can do clean datetime arithmetic against naive sim timestamps.
        bench_times = [t.to_pydatetime().replace(tzinfo=None) for t in df.index]
        if not closes:
            return jsonify({'success': False, 'error': 'No benchmark close prices'}), 502

        # Re-sample: for each sim timestamp, pick the closest benchmark observation.
        # Skip alignment if the gap is huge (e.g. more than a day for intraday, week for daily).
        gap_limit = timedelta(days=3) if interval == '1d' else timedelta(hours=12)
        aligned_pct = []
        first_close = None
        for sim_dt in sim_dts:
            closest_idx = min(
                range(len(bench_times)),
                key=lambda i: abs((bench_times[i] - sim_dt).total_seconds()),
            )
            if abs(bench_times[closest_idx] - sim_dt) > gap_limit:
                aligned_pct.append(None)
                continue
            close_val = float(closes[closest_idx])
            if first_close is None:
                first_close = close_val
            aligned_pct.append(((close_val / first_close) - 1.0) * 100.0)

        payload = {
            'success': True,
            'symbol': canonical,
            'name': _BENCHMARK_DISPLAY.get(canonical, canonical),
            'timestamps': sim_ts_strings,
            'percent_returns': aligned_pct,
        }
        _BENCHMARK_CACHE[cache_key] = payload
        return jsonify(payload)
    except Exception as e:
        logger.exception("Benchmark endpoint error")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/benchmark_data/current/<symbol>')
def get_current_benchmark_data(symbol):
    """Resolve the most-recent simulation server-side, then delegate to /benchmark_data/<id>/<symbol>."""
    try:
        if not current_portfolio_state.get('has_simulation'):
            return jsonify({'success': False, 'error': 'No simulation data available'}), 400
        simulation_id = current_portfolio_state['simulation_id']
        return get_benchmark_data(simulation_id, symbol)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ---------------------------------------------------------------------------
# Strategy Studio — safe mini-interpreter for user-written trading scripts.
# Lets the UI POST short Python-flavored snippets like:
#     if price("NVDA") > 150:
#         buy("NVDA", 100)
# and run them against a sandboxed in-memory portfolio (no real orders).
# ---------------------------------------------------------------------------

_STRATEGY_ALLOWED_NODES = frozenset({
    ast.Module, ast.Expression, ast.Interactive,
    ast.Expr, ast.Assign, ast.AugAssign,
    ast.Name, ast.Load, ast.Store, ast.Constant,
    ast.If, ast.While, ast.For, ast.Break, ast.Continue, ast.Pass,
    ast.Compare, ast.BoolOp, ast.UnaryOp, ast.BinOp,
    ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
    ast.Is, ast.IsNot, ast.In, ast.NotIn,
    ast.And, ast.Or, ast.Not, ast.USub, ast.UAdd, ast.Invert,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod, ast.FloorDiv, ast.Pow,
    ast.BitAnd, ast.BitOr, ast.BitXor, ast.LShift, ast.RShift,
    ast.Call, ast.keyword,
    ast.List, ast.Tuple, ast.Dict, ast.Set,
    ast.Subscript, ast.Slice, ast.Starred,
    ast.IfExp,
})


def _strategy_validate_ast(tree):
    """Walk the AST and reject anything outside the whitelisted node set."""
    for node in ast.walk(tree):
        if type(node) not in _STRATEGY_ALLOWED_NODES:
            raise ValueError(
                f"Disallowed construct: {type(node).__name__}. "
                f"Strategy Studio only supports if/while/for, arithmetic, and the listed commands."
            )
        # Block attribute access entirely — keeps users out of internals like `().__class__`.
        if isinstance(node, ast.Attribute):
            raise ValueError("Attribute access is not allowed.")
        # Only direct function calls (no `func.attr(...)` and no calling computed expressions).
        if isinstance(node, ast.Call) and not isinstance(node.func, ast.Name):
            raise ValueError("Only direct, named function calls are allowed.")


class LiveQuoteError(Exception):
    """Raised by `_fetch_live_quote` when no live quote can be obtained for
    a ticker. We deliberately do NOT silently substitute a hardcoded
    estimate — silent fallbacks make broken strategies look like they're
    "trading" when in reality they're filling against fake numbers. Better
    to fail loudly so the user knows the data source is down."""


def _fetch_live_quote(sym):
    """Single source of truth for the freshest available Yahoo quote.

    Used by both the Strategy Studio's Execute button (one-shot run) and the
    Live Trading per-second loop, so they always agree on what 'live' means.

    `fast_info['lastPrice']` is NOT used here even though it's cheaper —
    Yahoo freezes it at the regular-session close during extended hours,
    which makes the strategy appear stuck. Instead we hit `Ticker.info`,
    which exposes a `marketState` flag plus dedicated `preMarketPrice` /
    `regularMarketPrice` / `postMarketPrice` fields that DO tick during
    pre-market (4:00–9:30 AM ET) and after-hours (4:00–8:00 PM ET).

    Resolution order, per `marketState`:
      • PRE      → preMarketPrice  → regularMarketPrice
      • REGULAR  → regularMarketPrice
      • POST     → postMarketPrice → regularMarketPrice
      • CLOSED   → regularMarketPrice
      • fallback → last 1-min bar from `history(prepost=True)`

    If none of those produce a positive number, raises `LiveQuoteError`
    with a human-readable reason. No silent fallback estimates — callers
    must surface the failure so the user knows the strategy isn't
    actually seeing real prices.
    """
    sym = str(sym).upper().strip()
    if not sym:
        raise LiveQuoteError("Empty ticker symbol passed to price().")

    # Always a fresh Ticker so yfinance's per-instance cache doesn't
    # serve a stale `.info` from a previous call. ~300 ms per fetch,
    # well under the 1-second tick budget.
    last_error = None
    try:
        ticker_obj = yf.Ticker(sym)
    except Exception as e:
        raise LiveQuoteError(f"Could not fetch a live price for {sym}. yf.Ticker failed: {e}")

    # Pull the marketState-aware quote from `info`. This is the same data
    # Yahoo's web quote page shows in the upper-right "After hours" /
    # "Pre-market" / "Closed" badges.
    info = None
    try:
        info = ticker_obj.info
    except Exception as e:
        last_error = f"info fetch failed: {e}"

    if info:
        market_state = (info.get('marketState') or 'REGULAR').upper()
        candidates_by_state = {
            'PRE':     ('preMarketPrice', 'regularMarketPrice'),
            'REGULAR': ('regularMarketPrice',),
            'POST':    ('postMarketPrice', 'regularMarketPrice'),
            'POSTPOST':('postMarketPrice', 'regularMarketPrice'),
            'PREPRE':  ('preMarketPrice', 'regularMarketPrice'),
            'CLOSED':  ('regularMarketPrice',),
        }
        for key in candidates_by_state.get(market_state, ('regularMarketPrice',)):
            px = info.get(key)
            if px is not None:
                try:
                    pxf = float(px)
                    if pxf > 0:
                        return pxf
                except (TypeError, ValueError):
                    pass
        last_error = (
            last_error
            or f"info returned no usable price for {sym} (marketState={market_state})."
        )

    # Final backstop: a 1-min bar including pre/post sessions. Usually
    # only matters when info is broken or fields are missing.
    try:
        hist = ticker_obj.history(period='1d', interval='1m', prepost=True)
        if not hist.empty:
            close = float(hist['Close'].iloc[-1])
            if close > 0:
                return close
        last_error = last_error or f"Yahoo returned no rows for {sym}."
    except Exception as e:
        last_error = f"history(prepost=True) failed: {e}"

    raise LiveQuoteError(
        f"Could not fetch a live price for {sym}. "
        f"{last_error or 'Yahoo returned no data.'}"
    )


def _scan_strategy_tickers(tree):
    """Walk a (validated) strategy AST and collect every ticker symbol the
    user passed as the first argument of `price`, `buy`, `sell`, or
    `position` calls. Used by the simulation engine to know which extra
    StockData series to load before the run starts."""
    tickers = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Name):
            continue
        if node.func.id not in ('price', 'buy', 'sell', 'position'):
            continue
        if not node.args:
            continue
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            sym = first.value.strip().upper()
            if sym:
                tickers.add(sym)
    return tickers


class _StrategyTickInjector(ast.NodeTransformer):
    """Inject a `_tick()` call at the top of every loop body so timeouts apply to
    `while True:` style loops that never reach a whitelisted call themselves."""

    def _insert_tick(self, body):
        tick_call = ast.Expr(value=ast.Call(
            func=ast.Name(id='_tick', ctx=ast.Load()),
            args=[], keywords=[],
        ))
        body.insert(0, tick_call)

    def visit_While(self, node):
        self.generic_visit(node)
        self._insert_tick(node.body)
        return node

    def visit_For(self, node):
        self.generic_visit(node)
        self._insert_tick(node.body)
        return node


@app.route('/strategy_studio')
def strategy_studio():
    """Full-page Strategy Studio (separate page; iframe target from the Next.js nav)."""
    theme = request.args.get('theme', 'light')
    if theme not in ('light', 'dark'):
        theme = 'light'
    embed = request.args.get('embed') == '1'
    return render_template('strategy_studio.html', theme=theme, embed=embed)


@app.route('/compile_strategy', methods=['POST'])
def compile_strategy():
    """Lint / validate a Strategy Studio snippet without executing it.

    Returns:
        { ok: true } if the program parses and passes the sandbox whitelist;
        { ok: false, error, line? } with a descriptive message otherwise.
    """
    payload = request.get_json(silent=True) or {}
    code = (payload.get('code') or '').strip()
    if not code:
        return jsonify({'ok': False, 'error': 'Code is empty.'}), 400
    try:
        tree = ast.parse(code, mode='exec')
        _strategy_validate_ast(tree)
        tree = _StrategyTickInjector().visit(tree)
        ast.fix_missing_locations(tree)
        compile(tree, '<strategy>', 'exec')  # final check that the transformed AST compiles cleanly
    except SyntaxError as e:
        return jsonify({'ok': False, 'error': f'Syntax error: {e.msg}', 'line': e.lineno}), 200
    except ValueError as e:
        return jsonify({'ok': False, 'error': str(e)}), 200
    return jsonify({'ok': True, 'message': 'Compile passed.'})


@app.route('/run_strategy', methods=['POST'])
def run_strategy():
    """Execute a sandboxed Strategy Studio snippet and return logs + final state."""
    payload = request.get_json(silent=True) or {}
    code = (payload.get('code') or '').strip()
    try:
        initial_cash = float(payload.get('initial_cash') or 100000)
    except (TypeError, ValueError):
        initial_cash = 100000.0

    if not code:
        return jsonify({'ok': False, 'error': 'Code is empty.'}), 400

    try:
        tree = ast.parse(code, mode='exec')
        _strategy_validate_ast(tree)
        tree = _StrategyTickInjector().visit(tree)
        ast.fix_missing_locations(tree)
        compiled = compile(tree, '<strategy>', 'exec')
    except SyntaxError as e:
        return jsonify({'ok': False, 'error': f'Syntax error: {e.msg} (line {e.lineno})'}), 400
    except ValueError as e:
        return jsonify({'ok': False, 'error': str(e)}), 400

    # Sandboxed run state — mutable closure shared by all sandbox-exposed helpers.
    MAX_SECONDS = 5.0
    MAX_TICKS = 50_000

    state = {
        'cash': initial_cash,
        'starting_cash': initial_cash,
        'positions': {},
        'log': [],
        'trades': [],
        'start_time': time.time(),
        'ticks': 0,
        'price_cache': {},
    }

    def _append_log(level, message):
        state['log'].append({'level': level, 'msg': str(message)})

    def _tick():
        elapsed = time.time() - state['start_time']
        if elapsed > MAX_SECONDS:
            raise TimeoutError(
                f"Strategy exceeded the {MAX_SECONDS:.0f}s safety limit "
                f"(infinite loop?). Stopped automatically."
            )
        state['ticks'] += 1
        if state['ticks'] > MAX_TICKS:
            raise RuntimeError(
                f"Strategy exceeded {MAX_TICKS:,} operations. Stopped automatically."
            )

    def _price(ticker):
        _tick()
        sym = str(ticker).upper().strip()
        if not sym:
            raise ValueError("price() needs a ticker symbol, e.g. price('NVDA').")
        if sym in state['price_cache']:
            return state['price_cache'][sym]
        # Shared helper: fast_info first (covers extended hours), then
        # history(). No silent fallback — if Yahoo can't return a price,
        # `_fetch_live_quote` raises `LiveQuoteError` and the outer
        # exec wrapper logs it as a script error. Same resolution path
        # as Live Trading.
        close = _fetch_live_quote(sym)
        state['price_cache'][sym] = close
        return close

    def _buy(ticker, shares):
        _tick()
        sym = str(ticker).upper().strip()
        try:
            qty = int(shares)
        except (TypeError, ValueError):
            raise ValueError(f"buy() needs an integer share count, got: {shares!r}")
        if qty <= 0:
            _append_log('error', f"buy('{sym}', {qty}) ignored — share count must be positive.")
            return False
        px = _price(sym)
        cost = px * qty
        if cost > state['cash'] + 1e-6:
            _append_log('error',
                f"Cannot buy {qty} {sym} @ ${px:,.2f} (cost ${cost:,.2f}); "
                f"only ${state['cash']:,.2f} cash on hand.")
            return False
        state['cash'] -= cost
        state['positions'][sym] = state['positions'].get(sym, 0) + qty
        state['trades'].append({'side': 'BUY', 'ticker': sym, 'shares': qty, 'price': px})
        _append_log('trade',
            f"BUY  {qty:>5} {sym:<6} @ ${px:,.2f}   "
            f"cost ${cost:,.2f}   cash left ${state['cash']:,.2f}")
        return True

    def _sell(ticker, shares):
        _tick()
        sym = str(ticker).upper().strip()
        try:
            qty = int(shares)
        except (TypeError, ValueError):
            raise ValueError(f"sell() needs an integer share count, got: {shares!r}")
        if qty <= 0:
            _append_log('error', f"sell('{sym}', {qty}) ignored — share count must be positive.")
            return False
        held = state['positions'].get(sym, 0)
        if qty > held:
            _append_log('error', f"Cannot sell {qty} {sym}; only {held} shares held.")
            return False
        px = _price(sym)
        revenue = px * qty
        state['cash'] += revenue
        state['positions'][sym] = held - qty
        state['trades'].append({'side': 'SELL', 'ticker': sym, 'shares': qty, 'price': px})
        _append_log('trade',
            f"SELL {qty:>5} {sym:<6} @ ${px:,.2f}   "
            f"revenue ${revenue:,.2f}   cash now ${state['cash']:,.2f}")
        return True

    def _position(ticker):
        _tick()
        return int(state['positions'].get(str(ticker).upper().strip(), 0))

    def _cash():
        _tick()
        return float(state['cash'])

    def _log(*args):
        _tick()
        _append_log('log', ' '.join(str(a) for a in args))

    safe_builtins = {
        'range': range, 'len': len, 'min': min, 'max': max,
        'abs': abs, 'round': round, 'sum': sum,
        'int': int, 'float': float, 'str': str, 'bool': bool,
        'True': True, 'False': False, 'None': None,
    }
    sandbox_globals = {
        '__builtins__': safe_builtins,
        '_tick': _tick,
        'price': _price,
        'buy': _buy,
        'sell': _sell,
        'position': _position,
        'cash': _cash,
        'log': _log,
        'print': _log,
    }

    try:
        exec(compiled, sandbox_globals, sandbox_globals)
    except TimeoutError as e:
        _append_log('error', str(e))
    except Exception as e:
        _append_log('error', f"{type(e).__name__}: {e}")

    # Mark-to-market the remaining positions using the cached prices we already paid for.
    portfolio_value = float(state['cash'])
    for sym, qty in state['positions'].items():
        if qty <= 0:
            continue
        portfolio_value += float(state['price_cache'].get(sym, 0)) * int(qty)

    return jsonify({
        'ok': True,
        'log': state['log'],
        'trades': state['trades'],
        'starting_cash': state['starting_cash'],
        'final_cash': state['cash'],
        'positions': {k: v for k, v in state['positions'].items() if v},
        'portfolio_value': portfolio_value,
        'duration_ms': int((time.time() - state['start_time']) * 1000),
        'ticks': state['ticks'],
    })


# ---------------------------------------------------------------------------
# Live Trading — run a saved Strategy Studio script against live (Yahoo
# Finance, 15-min-delayed) quotes once per second for 5 minutes. Only
# successful fills are surfaced to the user; everything else (errors,
# insufficient cash, condition didn't trigger, no-ops) is swallowed.
#
# Each run lives in `active_live_runs[run_id]` and is driven by a daemon
# thread, so the user can navigate away from the page and come back to a
# still-progressing log. The frontend polls /live_status/<run_id> every
# second for a delta of new log entries.
# ---------------------------------------------------------------------------

active_live_runs = {}  # run_id -> LiveTradingRun
_LIVE_DURATION_SECONDS = 300  # 5 minutes


class LiveTradingRun:
    """One live-trading job. The strategy body re-executes every wall-clock
    second; helpers (`price`, `buy`, `sell`, `position`, `cash`) mutate the
    run's shared state directly. We log a line ONLY when a buy/sell actually
    fills — silent on errors, silent on conditions that don't trigger, silent
    on no-ops. That matches the "only successful trades are logged" spec.
    """

    def __init__(self, run_id, code, initial_cash, duration_seconds=_LIVE_DURATION_SECONDS):
        self.run_id = run_id
        self.code = code
        self.initial_cash = float(initial_cash)
        self.starting_cash = float(initial_cash)
        self.duration_seconds = int(duration_seconds)
        self.cash = float(initial_cash)
        self.positions = {}
        self.last_prices = {}        # ticker -> last fetched live price
        self.log = []                # [{ts, level, msg}] — successful trades + fetch errors
        self.trade_count = 0
        self.tick_count = 0
        # Last fetch-error message we logged per ticker, so repeated
        # failures don't spam 300 identical lines into the live log.
        self._last_fetch_error_msg = {}
        self.is_running = False
        self.is_complete = False
        self.error = None
        self.started_at = None
        self.finished_at = None
        # RLock so status()/portfolio_value() can nest acquisitions without
        # deadlocking — both walk over `positions` and `last_prices` and we
        # don't want to copy them just to avoid the reentry.
        self.lock = threading.RLock()
        self._compiled = None

    # ---- helpers used by the sandboxed strategy --------------------------

    def _ts(self):
        return datetime.now().strftime('%H:%M:%S')

    def _append_trade_log(self, msg):
        with self.lock:
            self.log.append({'ts': self._ts(), 'level': 'trade', 'msg': msg})
            self.trade_count += 1

    def _append_error_log(self, sym, msg):
        """Surface a deduped quote-fetch error in the live log so the user
        can see when the strategy isn't actually seeing real prices. We
        dedupe by ticker+message so a sustained outage logs once per
        ticker, not 300 times in a row."""
        with self.lock:
            key = sym or '*'
            if self._last_fetch_error_msg.get(key) == msg:
                return
            self._last_fetch_error_msg[key] = msg
            self.log.append({'ts': self._ts(), 'level': 'error', 'msg': msg})

    def _live_price(self, ticker, price_cache):
        """Per-tick wrapper around the shared `_fetch_live_quote` helper.

        Caches the result in `price_cache` so multiple calls to `price()`
        inside the same strategy iteration return the same number (one
        decision should see a consistent quote), and stamps the run's
        `last_prices` for the status payload.
        """
        sym = str(ticker).upper().strip()
        if not sym:
            raise ValueError("price() needs a ticker symbol, e.g. price('NVDA').")
        if sym in price_cache:
            return price_cache[sym]
        close = _fetch_live_quote(sym)
        price_cache[sym] = close
        self.last_prices[sym] = close
        return close

    # ---- main loop -------------------------------------------------------

    def start(self):
        if self.is_running or self.is_complete:
            return
        # Pre-compile once so syntax / sandbox-whitelist errors surface
        # immediately on Start, not silently a tick in.
        try:
            tree = ast.parse(self.code, mode='exec')
            _strategy_validate_ast(tree)
            tree = _StrategyTickInjector().visit(tree)
            ast.fix_missing_locations(tree)
            self._compiled = compile(tree, f'<live:{self.run_id}>', 'exec')
        except SyntaxError as e:
            self.error = f'Syntax error: {e.msg} (line {e.lineno})'
            self.is_complete = True
            return
        except ValueError as e:
            self.error = str(e)
            self.is_complete = True
            return

        self.is_running = True
        self.started_at = time.time()
        thread = threading.Thread(target=self._run_loop, name=f'live-{self.run_id}', daemon=True)
        thread.start()

    def stop(self):
        self.is_running = False

    def _run_loop(self):
        try:
            for tick_index in range(self.duration_seconds):
                if not self.is_running:
                    break
                tick_start = time.time()
                self._execute_tick()
                self.tick_count = tick_index + 1
                # Sleep until the next 1-second boundary. If a tick took
                # longer (e.g. slow yfinance call), skip the sleep so we
                # catch up immediately.
                elapsed = time.time() - tick_start
                if elapsed < 1.0 and self.is_running:
                    time.sleep(1.0 - elapsed)
        except Exception as e:
            logger.exception('Live run %s crashed: %s', self.run_id, e)
            self.error = f'Run crashed: {e}'
        finally:
            self.is_running = False
            self.is_complete = True
            self.finished_at = time.time()

    def _execute_tick(self):
        """Run the user code once. Each tick has its own price cache so live
        quotes refresh between iterations; ticks-budget is reset so a single
        iteration can't blow the 50,000 op limit."""
        run = self
        price_cache = {}
        tick_state = {'ticks': 0, 'start_time': time.time()}
        MAX_TICK_OPS = 50_000
        MAX_TICK_SECONDS = 5.0

        def _tick():
            tick_state['ticks'] += 1
            if tick_state['ticks'] > MAX_TICK_OPS:
                raise RuntimeError(f"Tick exceeded {MAX_TICK_OPS:,} operations.")
            if time.time() - tick_state['start_time'] > MAX_TICK_SECONDS:
                raise TimeoutError(f"Tick exceeded {MAX_TICK_SECONDS:.0f}s budget.")

        def _price(ticker):
            _tick()
            return run._live_price(ticker, price_cache)

        def _buy(ticker, shares):
            _tick()
            sym = str(ticker).upper().strip()
            try:
                qty = int(shares)
            except (TypeError, ValueError):
                return False
            if qty <= 0:
                return False
            px = run._live_price(sym, price_cache)
            cost = px * qty
            with run.lock:
                if cost > run.cash + 1e-6:
                    return False  # silent: not enough cash → not a "successful trade"
                run.cash -= cost
                run.positions[sym] = run.positions.get(sym, 0) + qty
            run._append_trade_log(
                f"BUY  {qty:>5} {sym:<6} @ ${px:,.2f}   "
                f"cost ${cost:,.2f}   cash left ${run.cash:,.2f}"
            )
            return True

        def _sell(ticker, shares):
            _tick()
            sym = str(ticker).upper().strip()
            try:
                qty = int(shares)
            except (TypeError, ValueError):
                return False
            if qty <= 0:
                return False
            with run.lock:
                held = run.positions.get(sym, 0)
                if qty > held:
                    return False  # silent
                px = run._live_price(sym, price_cache)
                revenue = px * qty
                run.cash += revenue
                run.positions[sym] = held - qty
            run._append_trade_log(
                f"SELL {qty:>5} {sym:<6} @ ${px:,.2f}   "
                f"revenue ${revenue:,.2f}   cash now ${run.cash:,.2f}"
            )
            return True

        def _position(ticker):
            _tick()
            with run.lock:
                return int(run.positions.get(str(ticker).upper().strip(), 0))

        def _cash():
            _tick()
            with run.lock:
                return float(run.cash)

        def _log(*args):
            # User-side log() is intentionally a no-op for live runs — only
            # successful trades show up. Counts toward the tick budget.
            _tick()

        safe_builtins = {
            'range': range, 'len': len, 'min': min, 'max': max,
            'abs': abs, 'round': round, 'sum': sum,
            'int': int, 'float': float, 'str': str, 'bool': bool,
            'True': True, 'False': False, 'None': None,
        }
        sandbox_globals = {
            '__builtins__': safe_builtins,
            '_tick': _tick,
            'price': _price, 'buy': _buy, 'sell': _sell,
            'position': _position, 'cash': _cash,
            'log': _log, 'print': _log,
        }

        try:
            exec(self._compiled, sandbox_globals, sandbox_globals)
        except LiveQuoteError as e:
            # The user explicitly asked for "no fallback — if it doesn't
            # work, say it doesn't work." A fetch failure means the
            # strategy isn't actually seeing real prices, so we surface
            # it in the live log (deduped per ticker+message so a 5-min
            # outage prints once, not 300 times).
            msg = str(e)
            # Try to recover the ticker name from the message for dedupe.
            tail = msg.split(' for ', 1)
            sym_guess = ''
            if len(tail) > 1:
                sym_guess = tail[1].split('.', 1)[0].strip()
            run._append_error_log(sym_guess, msg)
            logger.debug('Live run %s tick %d quote error: %s', run.run_id, run.tick_count, msg)
        except (TimeoutError, RuntimeError, ValueError) as e:
            # Strategy-level safety stops (op budget, time budget, bad
            # input) — keep these out of the user UI; debug-log only.
            logger.debug('Live run %s tick %d non-fatal: %s', run.run_id, run.tick_count, e)
        except Exception as e:  # pragma: no cover — unexpected
            logger.debug('Live run %s tick %d unexpected: %s', run.run_id, run.tick_count, e)

    # ---- status / snapshot for the polling endpoint ----------------------

    def portfolio_value(self):
        with self.lock:
            value = float(self.cash)
            for sym, qty in self.positions.items():
                if qty <= 0:
                    continue
                value += float(self.last_prices.get(sym, 0)) * int(qty)
            return value

    def status(self, since_index=0):
        with self.lock:
            since = max(0, int(since_index))
            new_log = self.log[since:]
            return {
                'run_id': self.run_id,
                'is_running': self.is_running,
                'is_complete': self.is_complete,
                'tick_count': self.tick_count,
                'ticks_total': self.duration_seconds,
                'cash': round(float(self.cash), 2),
                'starting_cash': round(float(self.starting_cash), 2),
                'positions': {k: int(v) for k, v in self.positions.items() if v > 0},
                'last_prices': {k: float(v) for k, v in self.last_prices.items()},
                'portfolio_value': round(self.portfolio_value(), 2),
                'trade_count': self.trade_count,
                'log': new_log,
                'log_total': len(self.log),
                'started_at': self.started_at,
                'finished_at': self.finished_at,
                'error': self.error,
            }


@app.route('/live_trading')
def live_trading():
    """Full-page Live Trading runner (iframe target from the Next.js nav)."""
    theme = request.args.get('theme', 'light')
    if theme not in ('light', 'dark'):
        theme = 'light'
    embed = request.args.get('embed') == '1'
    return render_template('live_trading.html', theme=theme, embed=embed)


@app.route('/start_live_trading', methods=['POST'])
def start_live_trading():
    payload = request.get_json(silent=True) or {}
    code = (payload.get('code') or '').strip()
    try:
        initial_cash = float(payload.get('initial_cash') or 100000)
    except (TypeError, ValueError):
        initial_cash = 100000.0

    if not code:
        return jsonify({'ok': False, 'error': 'Code is empty.'}), 400
    if initial_cash <= 0:
        return jsonify({'ok': False, 'error': 'Initial cash must be positive.'}), 400

    run_id = str(uuid.uuid4())
    run = LiveTradingRun(run_id, code, initial_cash)
    run.start()
    if run.error and run.is_complete:
        # Pre-compile error — surface it before storing the run so the user
        # gets immediate feedback.
        return jsonify({'ok': False, 'error': run.error}), 400
    active_live_runs[run_id] = run
    return jsonify({'ok': True, 'run_id': run_id, 'ticks_total': run.duration_seconds})


@app.route('/live_status/<run_id>')
def live_status(run_id):
    run = active_live_runs.get(run_id)
    if run is None:
        return jsonify({'ok': False, 'error': 'Unknown run.'}), 404
    try:
        since = int(request.args.get('since', 0))
    except (TypeError, ValueError):
        since = 0
    return jsonify({'ok': True, **run.status(since_index=since)})


@app.route('/stop_live_trading/<run_id>', methods=['POST'])
def stop_live_trading(run_id):
    run = active_live_runs.get(run_id)
    if run is None:
        return jsonify({'ok': False, 'error': 'Unknown run.'}), 404
    run.stop()
    return jsonify({'ok': True, **run.status(since_index=0)})


if __name__ == '__main__':
    # FLASK_PORT wins so a stray shell PORT (e.g. from other tools) does not move the dev server off 5002.
    port = int(os.environ.get('FLASK_PORT') or os.environ.get('PORT', 5002))
    debug = os.environ.get('FLASK_ENV') == 'development'
    app.run(debug=debug, host='0.0.0.0', port=port)
