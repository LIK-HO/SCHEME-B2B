# Security

Не хранить в репозитории:

- Airtable PAT;
- MAX bot token;
- FNS access token;
- SMTP password;
- любые пользовательские API keys.

Для GitHub Actions использовать repository secrets.

Не логировать Authorization headers, access tokens и SMTP credentials.

Airtable и MAX вызываются только по HTTPS.
