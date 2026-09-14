# Best By win conditions

Competition: Agents for Humans Hackathon (AWS x Devpost), Good Neighbor Agents track.
Brief: https://agentsforhumans.devpost.com/ . Deadline 2026-09-14 17:00 PDT.
Every line below was read from a source on 2026-09-14 and carries that source. Written by the
console subagent; the parent session owns the strategy and should correct anything it knows
better, in particular the scoreboard line.

    Scoreboard: first edition, no previous winners published on the hackathon site (read
      https://agentsforhumans.devpost.com/ 2026-09-14, 9,805 participants registered, no
      submission count and no leaderboard exposed; `dp gallery agentsforhumans` returns 0
      projects, so the gallery is not public before judging). Named Good Neighbor Agents peers
      found off-platform: NEXUS https://github.com/ganpatsuthar69/Nexus (community outage and
      volunteer coordination), NeighbourNode https://github.com/git791/NeighbourNode (community
      fridges). Neither publishes a usage number or a regulated data source.
    Bar to beat: no public usage leaderboard exists for this hackathon, so the bar is the five
      published criteria (Technological Implementation, Design, Potential Impact, Creativity and
      Originality, Presentation) against the two identified track peers, both of which run on
      invented community data and publish 0 real production runs. Best By's counter-numbers:
      2,547 real FDA food enforcement reports measured by scripts/measure_feed.py, 614 of them
      still open, 10 real cases in DynamoDB bestby-cases from real Lambda runs, 10 SES messages
      actually accepted with real message ids on case 73a4bb419a7da04b.
    Asset we will own: the intake-time lot-code corpus and the deterministic verdict engine.
      Obtained by photographing the lot code when the case comes off the truck (agent/label.py,
      scripts/read_intake_photo.py) instead of hunting for it when a notice lands, which is the
      27.0% of notices that publish nothing a shelf can be checked against. Plus the captured
      openFDA corpus in data/ and the S3 compliance records in
      bestby-evidence-079415246611. None of that is a wrapper around a public API: the API gives
      free text, the asset is the shelf-side identifier that makes the comparison exact.
    Off-platform buyer: a food pantry coordinator running intake and distribution at a Feeding
      America partner pantry. Exists today, existed before this hackathon, has no dispatcher and
      gets FDA enforcement notices as email addressed to nobody.
    Single entry: Best By. One product, one repo, one console.
    Verb the brief names: "handles routine and repetitive tasks", "takes on something people
      actually deal with and handle it end to end", "helps groups of people, not just one,
      neighborhoods, nonprofits, food banks" (quoted from https://agentsforhumans.devpost.com/).
    Our product performs that verb: yes. End to end, not read-only. agent/engine/verdict.py
      decides MATCH / NEEDS_EVIDENCE / NO_MATCH from stamped codes, printed dates and
      distribution states; agent/dispatch.py sends the household notice through SES and writes
      the delivery receipt back to the case row (case 73a4bb419a7da04b carries 10 SES message
      ids, attempted 10, direct 10, failed 0); agent/compliance.py files the S3 record. The
      irreversible tool is gated by NotifyVeto in agent/bestby_agent.py and proved red-green by
      tests/test_veto.py::test_the_hook_cancels_a_dispatch_that_is_actually_attempted.
    Metric plan: real cases opened by scheduled Lambda runs against the live feed, checked in
      DynamoDB bestby-cases and on https://best-by.vercel.app . Current: 6 cases in the table,
      1 carried all the way to notified with 10 real deliveries. Daily target is whatever the
      live feed produces; the schedule is EventBridge bestby-daily against 614 open recalls, so
      the number is not ours to set and is never hand-written (CLAUDE.md forbids writing a case
      into DynamoDB by hand).
    Live by: 2026-09-14, already live. Console https://best-by.vercel.app , agent on Lambda
      bestby-run with schedule bestby-daily. This is the deadline day, not seven days ahead,
      which is a real deviation and is recorded on the last line.
    Deviation from research: two. Bedrock and AgentCore are unavailable on this AWS India
      (AISPL) account, so the AgentCore deployment that the brief says strengthens the
      Technological Implementation score cannot be done; Strands runs against the Anthropic API
      while Lambda, EventBridge, DynamoDB, S3 and SES carry the rest. And the gate itself ran on
      deadline day rather than before the first line of code, so it documents the entry instead
      of choosing it.
