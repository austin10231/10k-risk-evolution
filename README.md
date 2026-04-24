# 10k-risk-evolution
AI-powered year-over-year risk disclosure analysis system for SEC 10-K filings using AWS and Generative AI.

## Railway Runtime Note

This app currently reads credentials from `st.secrets`.
For Railway deployment, use the startup script below so env vars are auto-written into `.streamlit/secrets.toml` at boot time.

Start command:

```bash
bash scripts/start_railway_streamlit.sh
```

Common required Railway variables:

- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `AWS_REGION`
- `S3_BUCKET`
- `BEDROCK_REGION`

Feature-dependent optional variables:

- `COMPREHEND_REGION`
- `MARKETAUX_API_TOKEN`
- `AGENTCORE_REGION`
- `AGENTCORE_ARN`
- `AGENTCORE_RUNTIME_ARN`
- `AGENTCORE_QUALIFIER`
- `AGENTCORE_RUNTIME_QUALIFIER`
- `AWS_SESSION_TOKEN`
