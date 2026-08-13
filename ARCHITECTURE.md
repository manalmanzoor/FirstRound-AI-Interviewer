# Architecture

Living doc — updated at the end of each build phase with what actually
happened, not what was planned. See `PRD.md` for the full design rationale.

## Phase 0 — Keys & Scaffolding

**Gemini Live model ID decision:** pinned to `gemini-2.5-flash-native-audio-preview-12-2025`,
not the newer `gemini-3.1-flash-live-preview`. Reason: LiveKit's Python agents
Gemini plugin has a known, currently-open bug where 3.1 rejects
`send_client_content` with a 1007 error after the first model turn, and
`generate_reply()` / `update_instructions()` / `update_chat_ctx()` are
incompatible with 3.1 models. An interview is inherently multi-turn, so 3.1
is unusable here today regardless of how "current" it looks. Re-check this
before demo day in case the plugin has patched it.

**Session duration finding:** without `contextWindowCompression` enabled,
Gemini Live audio-only sessions cap at 15 minutes and audio+video sessions
cap at 2 minutes. The interview only needs to send the candidate's
**microphone audio** into Gemini Live — the avatar video is rendered
client-side off the TTS/audio stream, not sent to the model — so this should
land in the audio-only 15-minute bucket, comfortably covering the 8+ minute
requirement. Flagging as a Phase 1 acceptance check: confirm no video track
is being fed into the Live API session, and enable
`contextWindowCompression` anyway as a safety margin. WebSocket connections
also terminate around 10 minutes regardless — `SessionResumptionConfig`
(tokens valid 2h) is the mechanism to reconnect without losing context if
the interview runs long.

**Offline reasoning model:** `gemini-2.5-flash` and `gemini-2.5-flash-lite`
are both dead for this (newly created) account — `generate_content` returns
404 "no longer available to new users," even though `models.list()` still
lists them as present. The list endpoint is not a reliable existence check;
only an actual call proves access. Confirmed working replacement:
`gemini-3.5-flash` (offline reasoning), with `gemini-3.1-flash-lite` as the
same-provider fallback if RPM gets tight — same free-tier deal, newer
generation. This is exactly the "don't trust a remembered/hardcoded model
name" risk the PRD called out for the Live model, and it turned out to
apply to the offline model too.

## Graph (filled in during Phase 3.5–5)

## State Object (filled in during Phase 3.5–5)

## Measured Latency (filled in as each piece comes online)

## Known Limitations (filled in honestly as they're found — see PRD §1)
