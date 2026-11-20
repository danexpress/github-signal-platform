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