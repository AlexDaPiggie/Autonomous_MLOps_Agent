Read actual code, configurations and named log entries on the main session. Separate review is optional under rules.md.
Check leakage (including early stopping/tuning on scored outer labels), train/inference mismatch, hardcoded test values, row/fold/class/candidate mismatches and unsupported score claims. Verify provenance and distinguish held-out, conditional meta-CV, replay/training and fully nested scores.
Report demonstrable problems with file/line evidence. Say "no problems found" when appropriate; state scope and unresolved checks. Do not fix code during review.
Record reviewed code/config hashes and paths; reuse unchanged coverage. Review material prediction/validation changes and final configurations. Only actual validity/prediction problems block; style notes do not.
