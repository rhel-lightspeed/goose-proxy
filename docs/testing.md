# Testing & Verification

Quick commands for verifying the proxy and backend connectivity.

## Backend Connectivity

Test the backend directly (bypassing the proxy) to verify credentials and network access:

```bash
curl -v --cert data/development/auth/cert.pem \
     --key data/development/auth/key.pem \
     --proxy <http://proxy:1234> \
     <https://stage-url/v1/response> \
     -H "Content-Type: application/json" \
     -d '{"input": "hello", "store": false}'
```

A `403 Forbidden` response means the RHSM certificate lacks the required entitlements for the lightspeed API. Check your subscription/org authorization on the staging environment.

## Proxy Endpoints

Start the proxy first:

```bash
uv run goose-proxy
```

### Non-Streaming Request

```bash
curl -s http://127.0.0.1:8080/v1/chat/completions \
     -H "Content-Type: application/json" \
     -d '{
       "model": "rhel-lightspeed/goose",
       "messages": [{"role": "user", "content": "Hello"}]
     }' | python3 -m json.tool
```

### Streaming Request

```bash
curl -N http://127.0.0.1:8080/v1/chat/completions \
     -H "Content-Type: application/json" \
     -d '{
       "model": "rhel-lightspeed/goose",
       "messages": [{"role": "user", "content": "Hello"}],
       "stream": true
     }'
```

Each SSE chunk appears as `data: {...}` followed by `data: [DONE]` at the end.

### Models

```bash
curl -s http://127.0.0.1:8080/v1/models | python3 -m json.tool
```

### Health Check

```bash
curl -s http://127.0.0.1:8080/health
```

## Running Tests

```bash
uv run pytest -v
```
