# API Translation Reference

goose-proxy translates between the OpenAI Chat Completions API (consumed by Goose) and the Responses API (exposed by lightspeed-stack). This document details every translation performed by the proxy.

## Request Translation

Goose sends `POST /v1/chat/completions`. The proxy translates this into `POST /responses` on the backend.

### Messages

All messages in the `messages` array are translated into the `input` and `instructions` fields of the Responses API request.

#### System Messages

System messages are extracted from the conversation and concatenated (joined with `\n\n`) into the `instructions` parameter. They do not appear in `input`.

```
Chat Completions                          Responses API
─────────────────                         ─────────────
{"role": "system",                   ──>  instructions: "You are helpful."
 "content": "You are helpful."}
```

Multiple system messages (even interleaved with other messages) are all collected and joined:

```
messages: [                               instructions: "Be helpful.\n\nBe concise."
  {"role": "system", "content": "Be helpful."},
  {"role": "user", "content": "Hi"},
  {"role": "system", "content": "Be concise."}
]
```

#### User Messages

User messages support both plain string content and array content (text + images).

**String content:**
```json
// Chat Completions
{"role": "user", "content": "Hello"}

// Responses API
{"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Hello"}]}
```

**Array content (text + images):**
```json
// Chat Completions
{"role": "user", "content": [
  {"type": "text", "text": "Describe this"},
  {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}}
]}

// Responses API
{"type": "message", "role": "user", "content": [
  {"type": "input_text", "text": "Describe this"},
  {"type": "input_image", "image_url": "data:image/png;base64,..."}
]}
```

#### Assistant Messages

Assistant text content and tool calls are translated separately. A single assistant message with both text and tool calls produces multiple input items.

**Text content:**
```json
// Chat Completions
{"role": "assistant", "content": "Hello there!"}

// Responses API
{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Hello there!"}]}
```

**Tool calls:**
```json
// Chat Completions
{"role": "assistant", "tool_calls": [{
  "id": "call_1",
  "type": "function",
  "function": {"name": "get_weather", "arguments": "{\"city\": \"NYC\"}"}
}]}

// Responses API
{"type": "function_call", "call_id": "call_1", "name": "get_weather", "arguments": "{\"city\": \"NYC\"}"}
```

#### Tool Result Messages

```json
// Chat Completions
{"role": "tool", "tool_call_id": "call_1", "content": "{\"temp\": 72}"}

// Responses API
{"type": "function_call_output", "call_id": "call_1", "output": "{\"temp\": 72}"}
```

### Parameters

| Chat Completions       | Responses API       | Notes                                      |
|------------------------|---------------------|--------------------------------------------|
| `model`                | *(not sent)*        | Backend auto-selects the model             |
| `messages`             | `input`             | Translated per message type (see above)    |
| `messages` (system)    | `instructions`      | System messages concatenated               |
| `stream`               | `stream`            | Passed through                             |
| `temperature`          | `temperature`       | Passed through (including `0`)             |
| `max_tokens`           | `max_output_tokens` | Renamed                                    |
| `tools`                | `tools`             | Flattened (see below)                      |
| `tool_choice`          | `tool_choice`       | Unwrapped (see below)                      |
| `stream_options`       | *(dropped)*         | Not applicable to Responses API            |
| *(always set)*         | `store`             | Always `false`                             |

### Tools

Tool definitions are flattened from the nested Chat Completions format:

```json
// Chat Completions
{"type": "function", "function": {"name": "fn", "description": "desc", "parameters": {...}}}

// Responses API
{"type": "function", "name": "fn", "description": "desc", "parameters": {...}}
```

`description` and `parameters` are only included if present in the original.

### Tool Choice

String values (`"auto"`, `"required"`, `"none"`) pass through unchanged.

Object form is unwrapped:
```json
// Chat Completions
{"type": "function", "function": {"name": "my_fn"}}

// Responses API
{"type": "function", "name": "my_fn"}
```

## Response Translation

The backend returns a Responses API response. The proxy translates it into a Chat Completions response.

### Non-Streaming

```
Responses API                             Chat Completions
─────────────                             ─────────────────
response.id                          ──>  id
response.created_at                  ──>  created (cast to int)
response.model                       ──>  model (original request model preferred)
"response"                           ──>  object: "chat.completion"
```

#### Output Mapping

The proxy scans `response.output` for two item types:

- **`message`** items: text parts (`output_text`) are concatenated into `choices[0].message.content`
- **`function_call`** items: mapped to `choices[0].message.tool_calls[]`

```json
// Responses API tool call
{"type": "function_call", "call_id": "call_1", "name": "fn", "arguments": "{}"}

// Chat Completions tool call
{"id": "call_1", "type": "function", "function": {"name": "fn", "arguments": "{}"}}
```

Unknown output types (e.g. `mcp_list_tools`) are silently filtered.

#### Finish Reason

| Condition                      | `finish_reason` |
|--------------------------------|-----------------|
| Response contains tool calls   | `"tool_calls"`  |
| Response status is `incomplete`| `"length"`      |
| Otherwise                      | `"stop"`        |

#### Usage

| Responses API    | Chat Completions     |
|------------------|----------------------|
| `input_tokens`   | `prompt_tokens`      |
| `output_tokens`  | `completion_tokens`  |
| `total_tokens`   | `total_tokens`       |

### Streaming

The backend streams Server-Sent Events (SSE). The proxy translates each event into Chat Completions SSE chunks.

#### Event Mapping

| Responses API Event                       | Chat Completions Chunk                                |
|-------------------------------------------|-------------------------------------------------------|
| `response.created`                        | `delta: {"role": "assistant"}`                        |
| `response.output_text.delta`              | `delta: {"content": "..."}`                           |
| `response.output_item.added` (message)    | `delta: {"role": "assistant"}` (if not yet sent)      |
| `response.output_item.added` (function_call) | `delta: {"tool_calls": [{"index": N, "id": "...", "type": "function", "function": {"name": "...", "arguments": ""}}]}` |
| `response.function_call_arguments.delta`  | `delta: {"tool_calls": [{"index": N, "function": {"arguments": "..."}}]}` |
| `response.completed`                      | Final chunk with `finish_reason` and `usage`          |

The stream terminates with `data: [DONE]\n\n`.

#### Streaming Behavior

- The assistant `role` is emitted exactly once, on the first applicable event
- Tool calls are indexed sequentially as they appear
- Tool call arguments accumulate incrementally via delta events
- `finish_reason` follows the same logic as non-streaming (tool_calls > length > stop)
- Unknown event types are silently skipped

## Endpoints

| Proxy Endpoint             | Backend Endpoint | Method |
|----------------------------|------------------|--------|
| `/v1/chat/completions`     | `/responses`     | POST   |
| `/v1/models`               | *(none)*         | GET    |

The `/v1/models` endpoint returns a hardcoded model list (`rhel-lightspeed/goose`) without querying the backend.
