# Q3 Roadmap Sync
- **Date:** 2026-07-14
- **Sources:** Mic, System Audio

## Transcript

**[00:00:03] [You]** Okay, thanks for joining everyone. Let's do a quick status check on the Q3 roadmap before we lock the priorities for next sprint.

**[00:00:11] [Call]** Sure. So on the ingestion pipeline side, we finished the schema migration last week. The backfill job is running now, should be done by Thursday.

**[00:00:24] [Call]** One thing to flag — we found about two hundred thousand rows with malformed timestamps from the old system. We're quarantining those into a separate table rather than blocking the migration.

**[00:00:36] [You]** Okay, that's fine, as long as it doesn't block the downstream reporting jobs.

**[00:00:41] [Call]** It doesn't, the reporting jobs already filter on a valid-timestamp flag, so those rows just won't show up until we fix them.

**[00:00:52] [You]** Got it. What about the API rate limiting work? I saw the ticket was still in progress.

**[00:01:00] [Call]** Yeah, that's about seventy percent done. The token bucket implementation is merged, we're just working through the edge cases around burst traffic from the mobile clients.

**[00:01:14] [Call]** We think we'll have it fully tested by end of next week. It's not blocking anything else right now.

**[00:01:22] [You]** Okay. Let's talk about the customer-facing dashboard redesign then, since that's the one with the external deadline.

**[00:01:31] [Call]** Right, so design handed off the final Figma files on Monday. Frontend team started implementation Tuesday. Current estimate is two and a half weeks for the full build, plus QA.

**[00:01:45] [You]** That would put us right at the edge of the September 30th deadline. Is there any risk there?

**[00:01:53] [Call]** The main risk is the new charting library — we haven't used it in production before, and it needs to handle real-time data updates, which is new territory for us.

**[00:02:05] [Call]** We're doing a spike this week to de-risk that specifically. If it doesn't pan out we'd fall back to the existing charting library, which we know works but doesn't look as polished.

**[00:02:18] [You]** Okay, let's revisit that Friday. Can someone own reporting back on the spike results?

**[00:02:25] [Call]** I'll take that. I'll have an update in the team channel by Friday morning.

**[00:02:31] [You]** Perfect. Last item — headcount. We got approval for the two open roles, backend engineer and QA engineer. Recruiting is starting outreach this week.

**[00:02:44] [Call]** Good news. Do we know if either of those will be able to help with the dashboard work, or are they too far out?

**[00:02:52] [You]** Realistically too far out to help with September 30th, but they'll help a lot with Q4 planning. I don't want us over-promising the current team based on headcount that isn't here yet.

**[00:03:05] [Call]** Makes sense. Okay, I think that covers everything on my end.

**[00:03:09] [You]** Great, thanks everyone. Same time next week, and ping me directly if the charting spike looks risky before Friday.
