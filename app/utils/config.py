import os
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY  = os.getenv("GROQ_API_KEY", "")
LLM_MODEL     = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")
GROQ_BASE_URL = "https://api.groq.com/openai/v1"

# Redis (optional — only used when the redis package is installed and server is reachable)
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_TTL  = int(os.getenv("REDIS_TTL",  "86400"))

WB_BASE_URL        = "https://api.worldbank.org/v2"
WB_RATE_LIMIT      = int(os.getenv("WB_RATE_LIMIT",      "10"))
MAX_CONTEXT_TOKENS = int(os.getenv("MAX_CONTEXT_TOKENS", "4000"))
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8002"))
