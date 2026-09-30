# Chat response continuity

This runbook addresses a ChatGPT Work answer that visibly stops mid-sentence. It is an operational recovery rule, not a claim that the repository can fix the ChatGPT client or transport. The cause of a particular interruption requires a request ID or client/server diagnostic evidence.

## During a long project turn

1. Choose one bounded outcome for the turn. Keep the visible response short: current finding, completed action, and the exact next step. Put large evidence or diffs in the issue/PR or an appropriate persistent artifact and link them.
2. Before a lengthy tool sequence, identify the exact work key, current main/PR, authoritative external artifact or runtime version, and the last durable checkpoint. Do not copy a dated chat summary into live state.
3. At a meaningful completed phase, persist only the minimal checkpoint needed to resume: work key, scope, exact artifact/commit/version, verified result, remaining units, and whether any write occurred. Use the retained GitHub issue or the existing Source Map checkpoint protocol. Do not create a second mutable task queue.
4. On each visible update, distinguish **verified** work from an in-progress operation. Do not announce completion before readback. Do not rely on a partially streamed answer as proof of a write.
5. If the answer is likely to become long, finish a coherent small section and continue in a later turn from the saved checkpoint. HỌC90 tutoring still asks one learner question at a time and waits for the learner's response; no checkpoint or explanation alone raises mastery.

## After a response stops

- If the app offers Continue, use it once for the unfinished explanation. For a project operation, first ask the assistant to identify the last verified operation and read current issue/PR/Drive/Supabase state before any retry.
- Do not repeat a tool write just because its confirmation text was cut off. Read back the destination, then resume only unfinished work. A tool failure or missing visible text is not authority to relax source or promotion gates.
- If Continue fails, start a focused turn with: “Tiếp tục từ checkpoint đã xác minh của work key <key>. Kiểm tra live issue/PR và artifact/runtime trước khi ghi; nêu việc đã hoàn tất, việc còn lại, rồi xử lý đúng phần chưa xong. Trả lời ngắn theo từng chặng.”
- If a short, tool-free answer also repeatedly stops, compare the same request on another network/device and record the app version, local time and timezone, thread/task ID, screenshot, whether Continue/Regenerate works, and any visible error. Send those diagnostics through ChatGPT feedback/support. This evidence distinguishes client, connection, and generation failures better than repo logs can.

A cut-off ChatGPT message does not imply that a HỌC90 session was paused or that a Source Map operation committed. Confirm those states in their own stores. The repository cannot guarantee uninterrupted streaming or infer an exact platform finish reason from a screenshot alone.
