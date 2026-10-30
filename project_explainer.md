# 🤖 My LLM Mini-Project — What I Built & How to Explain It

---

## 🧠 What is this project?

> I built an **AI-powered News Agent + Telegram Chatbot** that fetches real-time news from the internet using the **Model Context Protocol (MCP)** and delivers it as a daily newsletter — and also lets you **chat with it naturally** on Telegram.

---

## 🏗️ The 3 Main Components

### 1. 📡 MCP News Server (Deployed on Vercel)
- **What it is:** A live REST API that acts as the "news brain" of the project
- **What it does:** Fetches real-time news from 5 sources:
  - Google News RSS
  - Hacker News (HN API)
  - TechCrunch (RSS)
  - The Verge (RSS)
  - BBC News (RSS)
- **How it works:** Built with Python serverless functions
- **Where it's deployed:** `https://telegram-chatbot-beige.vercel.app`
- **API Endpoints:**
  - `GET /` → Top news (with category filter: tech, AI, business, world)
  - `GET /search?query=AI` → Search specific topics
  - `GET /sources` → List all sources
- **MCP connection:** Follows the **Model Context Protocol (MCP 2.x)** standard — a protocol that lets AI agents plug into external tools/data sources in a standardized way

---

### 2. 🤖 AI Agent (NewsAgent)
- **What it is:** The "brain" that connects the MCP server to the LLM
- **What it does:**
  - Calls the MCP News Server to fetch articles
  - Passes them to Gemini LLM with a carefully designed prompt
  - Gets back a beautifully written newsletter or chat response
- **LLM used:** Google Gemini (`gemini-3.8-flash`) via Gemini API
- **3 modes of operation:**
  - `generate_daily_newsletter()` — full digest of top news
  - `generate_topic_newsletter()` — focused deep dive on any topic
  - `chat_response()` — conversational answers with live news context

---

### 3. 💬 Telegram Bot (Interface Layer)
- **Bot name:** `@letsgo_disha_bot`
- **What it does:** Lets users interact with the AI agent via Telegram
- **Commands available:**
  - `/start` — Welcome & subscribe to daily digest
  - `/digest` — Get the AI newsletter right now
  - `/digest tech` — Tech-only news
  - `/topic AI agents` — Deep dive on any custom topic
  - `/schedule 08:00` — Change the daily delivery time
  - `/sources` — See all news sources
  - `/status` — Check system health
  - `/help` — Command guide
- **Free-form chat:** Just type anything! e.g. *"what's happening in AI?"* → bot fetches live news and replies conversationally
- **Daily automation:** Automatically sends a newsletter every day at **9:00 AM IST** using APScheduler

---

## 🔄 How It All Connects (Flow)

```
You (Telegram)
      ↓  type "/digest" or "what's new in AI?"
Telegram Bot (@letsgo_disha_bot)
      ↓  calls NewsAgent
AI Agent (NewsAgent)
      ↓  calls MCP Server via HTTP
MCP News Server (Vercel)
      ↓  fetches RSS feeds / APIs
Google News + HN + TechCrunch + BBC + The Verge
      ↓  returns articles as JSON
AI Agent
      ↓  sends articles + prompt to Gemini LLM
Gemini API (gemini-3.8-flash)
      ↓  generates newsletter / chat reply
Telegram Bot
      ↓  sends formatted message back to you
You (Telegram) ✅
```

---

## 🛠️ Technologies Used

| Technology | What I used it for |
|---|---|
| **Python** | All backend code |
| **Model Context Protocol (MCP 2.x)** | Standard protocol for AI tool integration (`mcp` SDK) |
| **Google Gemini API** | LLM for generating newsletters & chat replies (`google-genai` SDK) |
| **python-telegram-bot** | Telegram bot framework |
| **Vercel** | Serverless deployment for MCP server |
| **APScheduler** | Daily automated newsletter scheduling |
| **httpx + feedparser** | Fetching RSS feeds and HTTP APIs |
| **GitHub** | Version control (`github.com/dishaaarao/telegram_chatbot`) |

---

## 🌐 What's Live / Deployed

| Component | URL / Location | Status |
|---|---|---|
| MCP News API | `https://telegram-chatbot-beige.vercel.app` | ✅ Live |
| Telegram Bot | `@letsgo_disha_bot` | ✅ Running |
| Source Code | `github.com/dishaaarao/telegram_chatbot` | ✅ Pushed |

---

## ❓ Critical Professor / Interview Questions Answered

### Q1. Which MCP did we use and why?
* **Which exact library:** We used the **Official Anthropic Python MCP SDK** (`mcp>=2.0.0` on PyPI), importing from `mcp.server.mcpserver import MCPServer`.
* **Why did we choose MCP?**
  1. **Open Standard:** MCP is the open-source protocol initiated by Anthropic that is becoming the universal standard for AI tool calling (supported across industry by Claude Desktop, Cursor, Zed, etc.).
  2. **Clean Decoupling:** Instead of hardcoding RSS scraping logic directly into the AI agent, MCP separates the **Tool Provider (MCP Server)** from the **Tool Consumer (AI Agent)**.
  3. **Reusability:** Any other MCP-compatible agent or developer can connect to our news tools without modifying our aggregator.
  4. **Multi-Transport Flexibility:** Supports standard `stdio` (local subprocess), `SSE` (Server-Sent Events), and REST/HTTP endpoints (which we deployed onto Vercel).

---

### Q2. What is LangGraph and what is it doing in our project?
* **Clear, honest answer:** **LangGraph is NOT used in our current code.**
* **What LangGraph is:** LangGraph is a library by LangChain designed to build **stateful, multi-agent cyclical workflows** using graph data structures (nodes = functions/agents, edges = conditional transitions/loops).
* **Why we didn't use it in this project:**
  - Our agent workflow is a clean, focused, linear pipeline:
    $$\text{User Request} \longrightarrow \text{MCP Tool Fetch} \longrightarrow \text{LLM Synthesis} \longrightarrow \text{Telegram Output}$$
  - Using LangGraph for a single-agent linear pipeline would introduce unnecessary overhead, dozens of heavy sub-dependencies, and slow cold-start times on serverless platforms.
* **How to answer if your sir asks how LangGraph fits in:**
  > *"Our current architecture uses a lightweight, direct Python agent. However, if we extend this project into a collaborative multi-agent newsroom (e.g., Researcher Agent $\rightarrow$ Fact-Checker Agent $\rightarrow$ Editor Agent with iterative feedback loops), LangGraph would be the ideal state-machine library to coordinate those cyclical agent loops."*

---

### Q3. What is LangChain and why didn't we use it instead of MCP?
* **What LangChain is:** A popular high-level framework that wraps LLMs, prompts, and vector databases into chains.
* **Why we built with native MCP + Gemini SDK instead of LangChain:**
  1. **Direct Protocol vs Wrapper:** LangChain is an abstraction wrapper. We wanted to implement **MCP**, which is the actual underlying open protocol standard.
  2. **Speed & Lightweight Footprint:** Native Python with the official `google-genai` SDK and `mcp` library starts in milliseconds and avoids the dependency bloat of LangChain.
  3. **API Stability:** LangChain has frequent breaking updates and complex class hierarchies. Using clean, modular Python gives us full control over error handling, retries, and formatting.

---

## 💡 Other Key Concepts to Explain to Your Sir

### What is an AI Agent?
> An AI agent is a program that can **take autonomous actions** to complete a goal — not just answer static questions. My agent: (1) determines what news is needed, (2) executes tool calls to the MCP server, (3) synthesizes the retrieved data with an LLM, and (4) delivers formatted output to Telegram.

### What is RAG (Retrieval Augmented Generation)?
> Our project uses a RAG-like pattern: instead of the LLM relying only on static training data (which might be months old), it **retrieves real, current news** first (via MCP), then generates an answer **grounded in verified facts from today**.

### What is a Serverless Function?
> Instead of keeping an expensive virtual machine running 24/7, Vercel runs my MCP server **only on demand**. It sleeps when idle and executes in milliseconds when invoked.

---

## 📁 Project File Structure

```
telegram_chatbot/
├── mcp_server/          # MCP Server (local protocol version)
│   ├── server.py        # MCPServer with 5 tools
│   ├── sources.py       # Multi-source news aggregator
│   └── models.py        # Pydantic data schemas
├── agent/               # AI Agent
│   ├── news_agent.py    # Main agent (newsletter + chat logic)
│   ├── mcp_client.py    # Client supporting direct, SSE, and HTTP modes
│   ├── llm.py           # Gemini/OpenAI/Groq unified client
│   └── prompts.py       # Prompt engineering for news and chat
├── telegram_bot/        # Telegram Bot
│   ├── bot.py           # All command handlers + free-form MessageHandler
│   └── scheduler.py     # Daily automation (APScheduler)
├── api/                 # Vercel deployment
│   ├── news.py          # Standalone serverless handler
│   └── vercel.json      # Routing configuration
├── run_bot.py           # Main bot entry point
└── .env                 # API keys (kept secret, ignored by git)
```

---

## 🏆 What Makes This Project Special

1. **Real MCP Standard** — Uses actual Anthropic MCP 2.x specifications, not simulated tool mocks.
2. **Live Deployed API** — MCP server is live on Vercel, accessible globally over HTTPS.
3. **Multi-Source Aggregation** — Unifies 5 distinct news feeds (Hacker News, Google News, TechCrunch, BBC, The Verge).
4. **Free-form Conversational AI** — Accepts plain questions and automatically pulls relevant live news before responding.
5. **Daily Scheduled Automation** — Runs background jobs at 9:00 AM IST autonomously.
6. **Production Best Practices** — Secure environment separation, scrubbing secrets from Git, and robust HTML fallback delivery.
