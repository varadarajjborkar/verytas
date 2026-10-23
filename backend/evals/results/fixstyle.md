# Fix-style benchmark

Simulated reviewers, 100 fixes per rule, averaged over 200 runs. Share of fixes the reviewer took (all rounds / last 50).

| Rule (best operation) | Best possible | Model alone | Greedy | Thompson |
|---|---|---|---|---|
| a dig at rivals (rewrite keeps the offer) | 80% | 53% / 53% | 74% / 76% | 74% / 78% |
| jargon (swap the words) | 85% | 52% / 51% | 80% / 81% | 80% / 83% |
| a countdown (delete the line) | 70% | 52% / 52% | 64% / 65% | 64% / 66% |
