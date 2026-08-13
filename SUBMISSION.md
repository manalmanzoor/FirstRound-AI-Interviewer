# Submission

- **Timestamp:**
- **JD chosen:** Junior AI Engineer — Northwind Labs, Karachi, 0–2 yrs
- **Avatar used:** 2D portrait, viseme lip-sync off TTS audio stream
- **Track:** 10-hour compressed track (PRD §6A) — all 12 core requirements, no bonus modules
- **Candidate for the real interview:** self (no partner available in this window — disclosed choice, not hidden)
- **Consent line:** _(to be written before the real interview in Phase 8 — both interviewer and candidate role are the same person; consent to record and use the recording for grading is given explicitly here)_
- **Links:**
- **Measured latency:**
- **Barge-in proof timestamp:** 2026-08-14, confirmed via `python -m src.realtime.agent console` (local mic/speaker, Gemini Live native VAD + `discard_audio_if_uninterruptible=True`). Interrupting the agent mid-sentence now cuts it off instantly instead of letting it finish the sentence first. Not yet re-confirmed over a real LiveKit room (see known limitations) — will re-verify once room connect is fixed, before this becomes the final proof clip.
- **What works:** Gemini Live conversational flow (greets, asks questions, responds) and native barge-in, proven via local console mode.
- **What's broken / known limitations:** LiveKit WebRTC room connect fails reproducibly on the dev machine (confirmed open upstream bug in livekit/rust-sdks #1188 — "slow Python applications could still exceed the timeout" waiting to send `ReadyForRoomEventRequest`; already on the latest `livekit` package, no fix available yet). Blocks testing/recording the actual video call requirement until resolved or worked around. See ARCHITECTURE.md Phase 1 for full details and ruled-out causes.
- **Bonus attempted:** none (out of scope for the 10-hour track)
