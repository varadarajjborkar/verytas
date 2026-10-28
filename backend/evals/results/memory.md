# Inki's memory: recall benchmark

`evals/memory/run.py`, 29 Oct 2026. Does Inki get the turns of a long conversation that its question depends on?

Each case is a conversation 40 to 90 turns long between a creator and the brand team. A decision is made early
(logo variant, budget, date legal cleared, channel, tone, a statistic's caveats), then comes the ordinary traffic
of a working thread: acknowledgements, chatter in English and Hinglish, and other decisions on look-alike
subjects. Sometimes the decision changes later. The last turn asks Inki about it in other words, sometimes in
Hinglish. A case is a hit when every turn holding the answer reaches Inki (or the later change, when there is
one). Five seeds per case vary the length and the placement of everything.

Three sets, so the numbers are honest:
- **tuned**: the 12 cases the policy was developed on;
- **held-out**: 12 cases written after tuning and never tuned against;
- **fresh**: 4 cases where the decision changes, written to judge one idea (a rule that pulled in follow-ups
  of a picked turn); it did not help and was removed.

## Results

| Policy | tuned | held-out | fresh | changed decision reached Inki | turns added |
|---|---|---|---|---|---|
| Recent 12 turns only (Inki before) | 0% | 0% | 0% | 0% | 0 |
| bge-small, meaning only | 63% | | | 100% (tuned) | 11 |
| + acknowledgements not ranked, question alone, shared words blended | 83% | 72% | 65% | 70% (held-out) | 5 to 6 |
| multilingual MiniLM instead (same policy) | 92% | 70% | | 60% (held-out) | 5 |
| **bge-small + question reworded by the fast model** (shipped) | **97%** | **77%** | **100%** | 70% (held-out), 50% (fresh) | 6 |

The rewording comes from a model, so it varies between runs: the held-out figure moved between 67% and 82% across
runs. Read it as about three in four, not as a precise number.

Choices it settled:
- **bge-small-en-v1.5** over paraphrase-multilingual-MiniLM: the same accuracy on unseen cases at 400 MB peak
  memory against 953 MB, on a 4 GB server. Hinglish questions are carried by the rewording, not the embedder.
- **The question alone** ranks the history: mixing in the turns just before it ("ok", "lunch now") pulled the
  ranking toward chatter.
- **Rewording** closes vocabulary gaps the small model can't ("what format" for "do it as a carousel"). Its first
  prompt carried an example that matched a test case and the model copied it; the example was replaced with
  ones unrelated to any case before the numbers above were taken.
- A larger budget (8 turns instead of 6) added nothing: the stand-out test, not the budget, decides how many.

## End to end, with the real models

Through the website, against a local copy of the demo: a 37-message conversation with three decisions early on
and one of them changed halfway. Five questions to Inki, all answered correctly: the logo colour, the changed
budget (15k, not the original 20k), the Hinglish deadline question, the Hinglish logo question, and a question
about something never agreed (Inki said it didn't know rather than inventing). 3 to 5 seconds per answer.

## Still missing

- A changed decision reaches Inki in about half to two thirds of cases where the change is worded unlike the
  question. Inki is told that the later of two disagreeing turns stands, but it has to see both.
- Vocabulary the rewording doesn't guess ("which extra language" for "make a Tamil version") still misses.
