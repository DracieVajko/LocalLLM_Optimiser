# External Blind Review Session

Session id: ext_20261101_091008_c46abb0e
Session token: 56393f521bf2b99138e128d9a349439d
Blind packet: C:\Users\DracieVajko\Downloads\PC_Commands\AI\LM_Studio_Optimiser\.desloppify\review_packet_blind.json
Template output: C:\Users\DracieVajko\Downloads\PC_Commands\AI\LM_Studio_Optimiser\.desloppify\external_review_sessions\ext_20261101_091008_c46abb0e\review_result.template.json
Claude launch prompt: C:\Users\DracieVajko\Downloads\PC_Commands\AI\LM_Studio_Optimiser\.desloppify\external_review_sessions\ext_20261101_091008_c46abb0e\claude_launch_prompt.md
Expected reviewer output: C:\Users\DracieVajko\Downloads\PC_Commands\AI\LM_Studio_Optimiser\.desloppify\external_review_sessions\ext_20261101_091008_c46abb0e\review_result.json

Happy path:
1. Open the Claude launch prompt file and paste it into a context-isolated subagent task.
2. Reviewer writes JSON output to the expected reviewer output path.
3. Submit with the printed --external-submit command.

Reviewer output requirements:
1. Return JSON with top-level keys: session, assessments, issues.
2. session.id must be `ext_20261101_091008_c46abb0e`.
3. session.token must be `56393f521bf2b99138e128d9a349439d`.
4. Include issues with required schema fields (dimension/identifier/summary/related_files/evidence/suggestion/confidence).
5. Use the blind packet only (no score targets or prior context).
