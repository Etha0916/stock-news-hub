# Project Scope: stock-news-hub

## In scope

- Financial news ingestion (RSS feeds, 30+ sources)
- Multi-language news support (English + Traditional Chinese)
- Theme classification (Mag7, ELN, Semi, Taiwan Tech, AI, Fed Rates)
- Sentiment analysis (planned)
- Watchlist functionality
- Public API for upstream data consumers

## Out of scope (intentionally)

- Investment advice
- Portfolio recommendations
- Trade execution / broker API
- Strategy backtesting
- Performance benchmarking against any benchmark
- Anything implying "this is what you should buy/sell"

## Related but separate projects

A separate project, **chou-quant** (own repository, own deployment, own
domain), may consume this project's public API to display third-party
strategy recommendations. That project is intentionally NOT part of
stock-news-hub.

stock-news-hub is an **information service**.
chou-quant deals in **strategy signals**.

Different products, different legal exposures, different business models.

## Legal position

stock-news-hub does not provide investment advice. All content is for
informational purposes only. Users are responsible for their own
investment decisions.

stock-news-hub does not receive compensation from any party in exchange
for elevating or displaying particular news items.
