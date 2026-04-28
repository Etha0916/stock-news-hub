"""
config.py — Themes (leaf-level), groups (UI rollup), and RSS sources.
"""
import urllib.parse


# ---------------------------------------------------------------------------
# UI groups (purely cosmetic — articles are NOT tagged with group keys)
# ---------------------------------------------------------------------------
THEME_GROUPS = {
    "mag7": {"label_en": "Magnificent 7",   "label_zh": "美股七雄"},
    "eln":  {"label_en": "ELN Underlyings", "label_zh": "ELN 標的"},
}


# ---------------------------------------------------------------------------
# Theme definitions (leaf level)
# US single-stock themes use the ticker as the display label in both languages.
# ---------------------------------------------------------------------------
THEMES = {
    # === Magnificent 7 individual stocks ===========================
    "aapl": {
        "groups": ["mag7"], "label_en": "AAPL", "label_zh": "AAPL",
        "keywords_high": ["Apple", "AAPL", "蘋果"],
        "keywords_med":  ["iPhone", "iPad", "MacBook", "Tim Cook", "App Store"],
    },
    "msft": {
        "groups": ["mag7"], "label_en": "MSFT", "label_zh": "MSFT",
        "keywords_high": ["Microsoft", "MSFT", "微軟"],
        "keywords_med":  ["Azure", "Satya Nadella", "Copilot", "Xbox"],
    },
    "googl": {
        "groups": ["mag7"], "label_en": "GOOGL", "label_zh": "GOOGL",
        "keywords_high": ["Alphabet", "GOOGL", "GOOG", "字母"],
        "keywords_med":  ["Google", "YouTube", "Sundar Pichai", "Android", "Pixel"],
    },
    "amzn": {
        "groups": ["mag7"], "label_en": "AMZN", "label_zh": "AMZN",
        "keywords_high": ["Amazon", "AMZN", "亞馬遜"],
        "keywords_med":  ["AWS", "Andy Jassy", "Bezos", "Prime Video"],
    },
    "meta": {
        "groups": ["mag7"], "label_en": "META", "label_zh": "META",
        "keywords_high": ["Meta Platforms", "Facebook", "Instagram", "WhatsApp"],
        "keywords_med":  ["Zuckerberg", "Threads", "Reality Labs", "META"],
    },
    "nvda": {
        "groups": ["mag7"], "label_en": "NVDA", "label_zh": "NVDA",
        "keywords_high": ["Nvidia", "NVDA", "輝達"],
        "keywords_med":  ["Jensen Huang", "GeForce", "CUDA", "H100", "Blackwell", "B200"],
    },
    "tsla": {
        # Shared between mag7 and eln
        "groups": ["mag7", "eln"], "label_en": "TSLA", "label_zh": "TSLA",
        "keywords_high": ["Tesla", "TSLA", "特斯拉"],
        "keywords_med":  ["Elon Musk", "Cybertruck", "Model 3", "Model Y", "Robotaxi", "FSD"],
    },

    # === ELN underlyings ===========================================
    "hims": {
        "groups": ["eln"], "label_en": "HIMS", "label_zh": "HIMS",
        "keywords_high": ["Hims & Hers", "Hims and Hers", "HIMS"],
        "keywords_med":  ["GLP-1", "Andrew Dudum"],
    },
    "pltr": {
        "groups": ["eln"], "label_en": "PLTR", "label_zh": "PLTR",
        "keywords_high": ["Palantir", "PLTR"],
        "keywords_med":  ["Alex Karp", "Karp", "Gotham"],
    },
    "mstr": {
        "groups": ["eln"], "label_en": "MSTR", "label_zh": "MSTR",
        "keywords_high": ["MicroStrategy", "Strategy Inc", "MSTR"],
        "keywords_med":  ["Saylor", "Michael Saylor", "Bitcoin Treasury"],
    },
    "snap": {
        "groups": ["eln"], "label_en": "SNAP", "label_zh": "SNAP",
        # Deliberately exclude bare "SNAP" keyword — too noisy ("snap election" etc).
        "keywords_high": ["Snap Inc", "Snapchat"],
        "keywords_med":  ["Evan Spiegel", "Spectacles"],
    },

    # === Standalone themes (no group — render flat) ================
    "semi": {
        "groups": [], "label_en": "Semiconductors", "label_zh": "半導體產業",
        "keywords_high": [
            "TSMC", "ASML", "AMD", "Micron", "Applied Materials",
            "Lam Research", "KLA", "GlobalFoundries", "SK Hynix",
            "Intel Foundry", "Samsung Foundry",
            "台積電", "聯電", "美光", "海力士", "艾司摩爾", "三星電子",
        ],
        "keywords_med": [
            "semiconductor", "chip", "wafer", "foundry", "lithography",
            "EUV", "fab", "nanometer",
            "晶圓", "晶片", "半導體", "代工", "先進製程", "封測",
        ],
    },
    "taiwan_tech": {
        "groups": [], "label_en": "Taiwan Tech", "label_zh": "台灣科技股",
        "keywords_high": [
            "TSMC", "MediaTek", "Hon Hai", "Foxconn", "Delta Electronics",
            "Quanta", "Wistron", "Pegatron", "ASUS", "Acer",
            "Realtek", "Largan", "Compal", "Inventec", "ASE Technology",
            "台積電", "聯發科", "鴻海", "台達電", "廣達", "緯創", "和碩",
            "華碩", "宏碁", "日月光", "瑞昱", "大立光", "仁寶", "英業達",
        ],
        "keywords_med": ["Taiwan", "台灣", "Hsinchu", "新竹"],
    },
    "ai": {
        "groups": [], "label_en": "AI", "label_zh": "人工智慧",
        "keywords_high": [
            "OpenAI", "Anthropic", "ChatGPT", "GPT-4", "GPT-5", "Claude",
            "Gemini", "DeepMind", "Mistral", "Llama", "AGI", "xAI",
            "人工智慧", "生成式 AI", "大型語言模型",
        ],
        "keywords_med": [
            "artificial intelligence", "machine learning", "deep learning",
            "large language model", "LLM", "generative AI", "neural network",
            "AI chip", "AI model",
            "AI 晶片", "深度學習", "機器學習", "神經網路",
        ],
    },
    "fed": {
        "groups": [], "label_en": "Fed Rate", "label_zh": "聯準會利率",
        "keywords_high": [
            "Federal Reserve", "FOMC", "Jerome Powell", "Fed Chair",
            "federal funds rate", "dot plot", "Fed minutes",
            "聯準會", "鮑爾", "聯邦公開市場委員會", "聯邦資金利率",
        ],
        "keywords_med": [
            "rate cut", "rate hike", "interest rate", "monetary policy",
            "CPI", "PPI", "inflation",
            "降息", "升息", "利率", "通膨", "貨幣政策",
        ],
    },
}


# ---------------------------------------------------------------------------
# RSS source builders
# ---------------------------------------------------------------------------
def google_news_rss(query: str, lang: str = "en") -> str:
    q = urllib.parse.quote(query)
    if lang == "en":
        return f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
    return f"https://news.google.com/rss/search?q={q}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"


def yahoo_finance_ticker_rss(ticker: str) -> str:
    return f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US"


# ---------------------------------------------------------------------------
# RSS source list
# ---------------------------------------------------------------------------
RSS_SOURCES = []

# Yahoo Finance per-ticker feeds — Mag7 + ELN underlyings
for ticker in ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA",
               "HIMS", "PLTR", "MSTR", "SNAP"]:
    RSS_SOURCES.append({"name": f"Yahoo:{ticker}", "url": yahoo_finance_ticker_rss(ticker)})

# Google News searches in English
EN_QUERIES = [
    "Magnificent 7 stocks",
    "semiconductor industry",
    "TSMC OR ASML OR Nvidia",
    "artificial intelligence",
    "Federal Reserve interest rate",
    "FOMC decision",
    "site:reuters.com semiconductor",
    "site:reuters.com Federal Reserve",
    "site:reuters.com artificial intelligence",
    "Palantir OR PLTR earnings",
    "MicroStrategy OR MSTR Bitcoin",
    "Hims Hers Health HIMS",
    "Snap Inc Snapchat earnings",
]
for q in EN_QUERIES:
    RSS_SOURCES.append({"name": f"GoogleEN:{q[:40]}", "url": google_news_rss(q, "en")})

# Google News searches in Traditional Chinese (Taiwan)
ZH_QUERIES = [
    "台積電",
    "聯發科 OR 鴻海 OR 廣達",
    "半導體 產業",
    "人工智慧 AI",
    "聯準會 利率",
    "輝達 Nvidia",
]
for q in ZH_QUERIES:
    RSS_SOURCES.append({"name": f"GoogleZH:{q[:40]}", "url": google_news_rss(q, "zh")})
