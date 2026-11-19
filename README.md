## Finding: Raw star velocity is noise, not signal

In a 24-hour slice of GitHub events (~2M events, 9.5K human-driven stars), 
the top 10 repos by raw star count were obscure projects with 26-55 stars 
each. Meanwhile, known high-signal repositories registered only 1-12 stars 
in the same window:

- Niko1221/Strata (unknown): 55 stars
- anthropics/skills: 12 stars
- anthropics/claude-code: 7 stars  
- microsoft/vscode: 2 stars
- huggingface/transformers: 2 stars

The top "trending" repos by naive count were dominated by transient drive-by 
interest — 90.9% of their starrers had zero other GitHub activity that day, 
and stars arrived uniformly across 20+ hours (ruling out coordinated 
botnet attacks).

Any OSS signal product relying on raw 24-hour star counts will surface 
these obscure repos over materially important work. The fix requires 
weighting stars by starrer reputation — account age, follower count, 
and prior public activity.