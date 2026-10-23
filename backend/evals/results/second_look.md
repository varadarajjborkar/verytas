# Second-look benchmark

32 hand-labelled sentences against Kitepath's semantic must rules, judged as production judges a paragraph. Flag threshold 0.6, close call within 0.1 of it.

| Policy | Correct | Caught (of breaking) | False flags (of fine) | Seconds per sentence (median) |
|---|---|---|---|---|
| small only | 27/32 | 13/16 | 2/16 | 2.1 |
| close-call cascade | 27/32 | 13/16 | 2/16 | 2.1 |
| both, larger decides | 30/32 | 15/16 | 1/16 | 2.2 |

Close calls the cascade would have re-asked: 0 of 32. Where the judges disagree:

| Rule | Sentence | Label | Small | Large |
|---|---|---|---|---|
| MSG-EXAMSTRESS | Toppers start today. Everyone else starts too late. | breaks | 0.1 | 0.9 |
| LEGAL-RESULTS | Results season is coming: here is how to read your marksheet. | fine | 0.9 | 0.1 |
| LEGAL-MINORS | Hey Class 9! Ask your parents for the annual plan today. | breaks | 0.1 | 0.9 |
