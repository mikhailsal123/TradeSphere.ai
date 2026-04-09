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
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt

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
            context += f"- Initial Cash: ${simulation_data.get('initial_cash', 'N/A')}\n"
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
    def __init__(self, simulation_id, initial_cash, start_date, duration_days, trading_frequency, tickers, trading_rules, beta_hedge_enabled=False, duration_hours=None):
        self.simulation_id = simulation_id
        self.initial_cash = initial_cash
        self.start_date = start_date
        self.duration_days = duration_days
        self.duration_hours = duration_hours
        self.trading_frequency = trading_frequency  # 'daily' or 'intraday'
        self.tickers = tickers
        self.trading_rules = trading_rules
        self.beta_hedge_enabled = beta_hedge_enabled
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
            
            # Initial purchases with real market prices using the same stock data objects
            for ticker, shares in self.tickers.items():
                if not data[ticker].stock_data.empty:
                    first_trading_day = data[ticker].stock_data.index[0]
                    data[ticker].curtime = first_trading_day
                    current_price = data[ticker].get_price()
                    if current_price is not None:
                        port.buy(ticker, current_price, shares, first_trading_day)
                    else:
                        logger.warning("No initial price for %s on %s; skipping purchase", ticker, first_trading_day)
                else:
                    logger.warning("No stock data for %s; skipping initial purchase", ticker)
            
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
            
            # Calculate portfolio value right after initial purchases (single mark; PnL from that value)
            initial_portfolio_value = port.get_value(currtime)
            initial_pnl = round(float(initial_portfolio_value) - float(port.original_value), 2)
            
            # Record initial state (after purchases) as first result
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
                
                # Check trading conditions and execute trades
                trades_executed = []
                rules_to_remove = []  # Track one-time rules that should be removed
                
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
                
                self.final_metrics = {
                    'total_return_pct': round(total_return, 2),
                    'final_value': round(final_value, 2),
                    'total_pnl': round(final_value - self.initial_cash, 2),
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
                final_value = self.initial_cash  # Fallback to initial cash
                self.final_metrics = {
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
            
            # Calculate hedge impact on key metrics
            hedge_pnl = hedged_value - non_hedged_value
            hedge_return_impact = (hedge_pnl / self.initial_cash) * 100
            
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
            # Start with initial cash
            value = self.initial_cash
            
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
        simulation = SimulationManager(
            simulation_id, initial_cash, start_date, duration_days,
            trading_frequency, tickers, trading_rules, beta_hedge_enabled,
            duration_hours=duration_hours,
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
            response['final_metrics'] = {
                'total_return_pct': 0.0,
                'final_value': simulation.initial_cash,
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

if __name__ == '__main__':
    # FLASK_PORT wins so a stray shell PORT (e.g. from other tools) does not move the dev server off 5002.
    port = int(os.environ.get('FLASK_PORT') or os.environ.get('PORT', 5002))
    debug = os.environ.get('FLASK_ENV') == 'development'
    app.run(debug=debug, host='0.0.0.0', port=port)
