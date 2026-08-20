COMPOSE := docker compose
SERVICE := freqtrade-signal
CONFIG := /freqtrade/user_data/configs/config.signal.json
STRATEGY := TraderAIProSignalStrategy
MODEL := LightGBMRegressor

.PHONY: validate pull up logs down download-data backtest

validate:
	python3 scripts/validate.py
	python3 -m unittest discover -s tests -v
	$(COMPOSE) config --quiet

pull:
	$(COMPOSE) pull

up: validate
	$(COMPOSE) up -d

logs:
	$(COMPOSE) logs -f --tail=200 $(SERVICE)

down:
	$(COMPOSE) down

download-data:
	$(COMPOSE) run --rm $(SERVICE) download-data \
		--config $(CONFIG) \
		--timeframes 5m 15m 1h \
		--days 90

backtest:
	@test -n "$(TIMERANGE)" || (echo "Usage: make backtest TIMERANGE=YYYYMMDD-YYYYMMDD" && exit 2)
	$(COMPOSE) run --rm $(SERVICE) backtesting \
		--config $(CONFIG) \
		--strategy $(STRATEGY) \
		--freqaimodel $(MODEL) \
		--timerange $(TIMERANGE)
