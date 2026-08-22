# Security policy

## Secrets

Never commit any of the following:

- Bybit API keys or secrets.
- Telegram bot tokens or private chat identifiers.
- Freqtrade API credentials, database files, trained models, logs, or exported trade data.

Signal mode does not require a Bybit API key. Telegram values belong in `.env`, which is ignored by Git.

Before every commit, run:

```bash
make validate
```

If a secret is committed, revoke it at the provider immediately. Removing it from the latest commit is not sufficient because it remains in Git history.

## Live-trading boundary

The checked-in Compose service and config are dry-run only. A future execution mode must use a separate reviewed configuration, a dedicated Bybit subaccount, least-privilege API permissions, IP restrictions, and withdrawal permissions disabled.
