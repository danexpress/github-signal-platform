# Findings

Observations from analyzing real GitHub event data through this pipeline.

---

## F1 — Raw star velocity is noise, not signal

**Date:** 2026-11-19  
**Data window:** 2026-10-01, single 24-hour slice  
**Volume:** 2,073,815 events ingested; 9,508 human-driven stars after bot filtering

### What I expected

Querying the top 10 repositories by WatchEvent count over 24 hours should 
surface meaningfully trending open-source work.

### What I found

The top 10 repos by raw star count were all obscure projects (25-55 stars each):

| Rank | Repository | Stars |
|------|------------|-------|
| 1 | Niko1221/Strata | 55 |
| 2 | debpalash/VoiceStudio | 49 |
| 3 | eternity4719/HowToLiveBetter | 45 |
| 4 | DietrichGebert/ponytail | 44 |
| 5 | NVIDIA/OpenShell | 43 |
| 6 | ifixai-ai/iFixAi | 43 |
| 7 | Panniantong/Agent-Reach | 33 |
| 8 | nanaism/yomiyasu | 28 |
| 9 | OffGridPete/Fieldwatch | 27 |
| 10 | walkinglabs/learn-harness-engineering | 26 |

Meanwhile, known high-signal repositories in the same window:

| Repository | Stars |
|------------|-------|
| anthropics/skills | 12 |
| anthropics/claude-code | 7 |
| microsoft/markitdown | 7 |
| anthropics/financial-services | 6 |
| openai/mcp-extensions | 4 |
| microsoft/vscode | 2 |
| huggingface/transformers | 2 |

### Investigating the top-ranked repos

Three diagnostic queries on the top-10 raw-count leaders:

1. **Coordinated starring**: zero actors starred multiple top-10 repos → no 
   cross-campaign overlap.
2. **Time distribution**: stars spread uniformly over 20-24 hours per repo 
   (1,100-1,420 minute spans) → not a coordinated botnet dump.
3. **Starrer engagement**: for Niko1221/Strata, 50 of 55 starrers (90.9%) 
   had zero other GitHub activity in the 24-hour window.

### Interpretation

Not star bombing. These are drive-by stars — users click through from a link, 
star, leave. Natural behavior for one-off interest.

The problem is methodological: **raw star velocity over short windows 
systematically surfaces transient noise over sustained significance.** 
`anthropics/skills` getting 12 stars from engaged developers is a stronger 
trending signal than Niko1221/Strata getting 55 stars from casual passers-by.

### Implication for the pipeline

Any OSS signal product using raw star counts as a trending metric will 
mislead buyers. The fix requires weighting stars by starrer reputation:

- Account age (older = more likely a real developer)
- Follower count (zero followers = low signal)
- Prior public activity (dormant accounts = less meaningful)
- Repository history of that starrer (similar-category stars = strong signal)

**Next pipeline iteration:** `silver_actors_enriched` table pulling account 
metadata from the GitHub REST API, feeding a `gold_authentic_trending` 
reputation-weighted score.

## F2 — Weighted event scoring is necessary but not sufficient

**Date:** 2026-11-24  
**Data window:** 2026-10-01, single 24-hour slice  
**Context:** Addresses F1's finding by weighting fork/PR/issue activity 
higher than raw stars.

### What happened
A simple composite trending score (stars×3 + forks×5 + PR_opens×10 + 
issue_opens×2 + releases×15 + PR_reviews×4) successfully pushed all 10 of 
F1's drive-by star repos out of the top 10 — they now occupy ranks 18-89.

### But the new top 10 isn't real trending either
| Rank | Repo | Signal | Pattern |
|------|------|--------|---------|
| 1 | plaiiin-hq/market-archive | 40 releases, 0 human engagement | release bot |
| 2 | NousResearch/hermes-agent | 14 stars, 4 forks, 39 PRs, 12 reviews | real activity |
| 3 | aaliyahsolace5-aiDATAOPS/cobol | 48 PRs, 14 issues, 0 stars | bulk-PR bot |
| 4 | merge-demo/mergequeue-bazel | 41 PRs, no stars | test harness |
| ... | | | |
| 10 | PostHog/posthog | 1 star, 13 PRs, 30 reviews | real activity |

3 of 10 look human-driven. The rest are automation.

### Why known heavyweights still don't rank
- microsoft/vscode: rank 102
- vercel/next.js: rank 331
- anthropics/claude-code: rank 361
- huggingface/transformers: rank 1267

These projects get *consistent low-volume high-quality* activity. Bursty 
automated activity outscores sustained human interest under any pure 
event-count scheme, no matter how the events are weighted.

### Implication
**Event-count weighting alone cannot separate trending from automation.** 
Raw stars → drive-by noise. Weighted events → automation bombing. The 
missing ingredient is who-is-doing-the-action — actor reputation, account 
age, prior activity patterns.

### Next iteration
`gold_authentic_trending`: join silver.events to silver.actors_enriched 
(already built), weight every event by starrer/forker/PR-author reputation 
score. Hypothesis: real trending surfaces when the SAME events are weighted 
by whose signal they are, not by what type of event they are.

## F3 — Reputation and diversity constraints beat raw weighting, but 24-hour windows remain too narrow

**Date:** 2026-11-24  
**Context:** Addresses F2's finding (event weighting alone is fooled by automation bombing).

### What was built
`gold_authentic_trending` — each event weighted by both event-type importance 
AND the acting user's reputation score (from silver.actors_enriched). Each 
actor's contribution to a single repo is capped at 20 points to prevent 
single-actor domination.

### What happened to the pathological cases
F2's top 10 automation-bomb repos (workingdir/ornadb, plaiiin-hq/market-archive, 
tirzzbuild/genetik, etc.) all collapsed to rank >1000. The cap enforces that 
any top-ranked repo requires multiple distinct human actors.

### What happened to known heavyweights
Known projects climbed significantly:
- microsoft/winget-pkgs: unranked → #4
- microsoft/onnxruntime: #131 → #36
- microsoft/vscode: #185 → #65

### The caveats this revealed
1. **Enrichment coverage is partial.** Most actors (`avg_actor_reputation ≈ 0.1`) 
   fell through to the unenriched baseline. The diversity cap did most of the 
   work; reputation barely contributed.
2. **Concentration persists under the cap.** `top_actor_share` for top-ranked 
   repos still runs 0.75-0.99 — one actor dominates the raw contribution before 
   capping. The cap flattens the final score; it doesn't fix the underlying skew.
3. **24-hour windows undersample real trending.** Sustained-interest projects 
   (anthropics/*, vercel/next.js) spread activity over weeks. In any single 
   day they register fewer events than a project in a concentrated burst. 
   Commercial trending products (OSS Insight, Runa ROSS) use 7-30 day windows.

### Implication for the pipeline
Three progressive attempts at trending detection, three honest limits. 
The architecture is the right one; the data window is too narrow to fully 
exploit it. Logical V0.4: backfill 7-30 days of GH Archive data, rerun the 
same models, see which signals strengthen vs persist.