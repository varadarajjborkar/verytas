# User testing (October 2026)

The brief asks for "evidence of user testing or structured feedback where reasonably available" (Round 2)
and "evidence of testing, reliability improvements and changes made during development" (Round 3). Three
people outside the team used the deployed demo on their own and wrote up what worked
and what didn't. Their reviews are below as written, followed by what we took from them and what changed.

## Who took part

| Participant | Relation to the team | Role they tried |
|---|---|---|
| P1 | Classmate | Brand team and creator |
| P2 | Student at the same college, different stream | Brand team and creator |
| P3 | Family member of a team member | Brand team and creator |

None of them work in brand governance, so this tests first-use clarity, not domain fit. All three
know someone on the team, which makes the praise less telling than the criticism; we weigh it that way.

## What they said, grouped

| Theme | Raised by | What they hit |
|---|---|---|
| A first-time visitor can't tell what the product does or where to start | P1, P2 | The sign-in picker asks for a company and a person before explaining anything; asked for a step-by-step guided tour |
| Words and numbers need explaining | P2 | "Draft", "100% Clean", "Escalation" with no explanation |
| A result doesn't say what was checked | P2, P1, P3 | "Clean" without the list of checks run; asked for confidence and reasons behind each decision |
| No sign that a review is running | P2 | After "Run review", unsure whether to click again |
| Empty pages don't say why or what to do | P2 | "Nothing here" with no next step |
| The review form asks for a lot at once | P3 | Many fields before a quick check |
| Cut-off text | P3 | Some titles and labels truncated |
| "AI can make mistakes" without context lowers trust | P3 | Wants the disclaimer kept but backed by how checks work and evidence |
| Verification accuracy must be shown, not claimed | P1 | Can't judge false positives and negatives from the outside |

What they liked: the interface and first impression (P1), separate creator and brand-team workspaces
(P1), and findings that say exactly which claim or figure is wrong and why, rather than a pass or fail
(P1).

## What we changed

Each change links to its commit.

| Theme | What changed | Status |
|---|---|---|
| Where to start | The sign-in page says what Verytas does, with a real finding as the example, before the person picker; the picker itself was cut to what you need to choose ([`0f6d6e2`](https://github.com/varadarajjborkar/verytas/commit/0f6d6e2), [`be5d112`](https://github.com/varadarajjborkar/verytas/commit/be5d112)) | Shipped |
| Where to start | A guided tour on the first visit to each side: a spotlight on each section and a card saying what it is for, with Back, Next and Skip; Settings starts it again ([`901f8f4`](https://github.com/varadarajjborkar/verytas/commit/901f8f4)) | Shipped |
| Words and numbers | Draft, In review, Changes requested and the other statuses explain themselves on hover; the tour explains Draft, Clean and escalation; summaries use plain words with no codes or scores ([`5019f67`](https://github.com/varadarajjborkar/verytas/commit/5019f67), [`901f8f4`](https://github.com/varadarajjborkar/verytas/commit/901f8f4), [`4bb8948`](https://github.com/varadarajjborkar/verytas/commit/4bb8948)) | Shipped |
| What was checked | A clean result lists each check that ran, in plain words, and says which ran only in a simpler form or not at all; the score and "Clean" explain themselves on hover ([`5019f67`](https://github.com/varadarajjborkar/verytas/commit/5019f67)) | Shipped |
| Review running | While a review runs it says what is being checked and how long it takes, beside the elapsed time; a review cut off by a server restart now runs again instead of hanging ([`5019f67`](https://github.com/varadarajjborkar/verytas/commit/5019f67), [`6bb31f2`](https://github.com/varadarajjborkar/verytas/commit/6bb31f2)) | Shipped |
| Empty pages | Each queue tab says why it is empty and what fills it ([`5019f67`](https://github.com/varadarajjborkar/verytas/commit/5019f67)) | Shipped |
| Long form | Only title, channel, text and files are up front; audience, campaign and notes sit under More options, whose header shows their settings ([`5019f67`](https://github.com/varadarajjborkar/verytas/commit/5019f67)) | Shipped |
| Cut-off text | Truncated names and titles show in full on hover; the review heading wraps to two lines ([`5019f67`](https://github.com/varadarajjborkar/verytas/commit/5019f67)); names and descriptions on the sign-in cards no longer clip ([`be5d112`](https://github.com/varadarajjborkar/verytas/commit/be5d112)) | Shipped |
| AI disclaimer | Kept, and now says which checks are plain code, that every finding names its source, that a person makes each call, and the measured accuracy including the weak spot ([`5019f67`](https://github.com/varadarajjborkar/verytas/commit/5019f67)) | Shipped |
| Accuracy | Measured per check and published in [`backend/evals/results`](../../backend/evals/results); the artwork check's false alarms fell from 12.6% to 4.7% this round ([`829ace2`](https://github.com/varadarajjborkar/verytas/commit/829ace2)). Confidence per finding is shown in the review. | Shipped |

## The reviews as written

### P1 (classmate)

> **Key strengths**
>
> 1. *Sleek and professional UI/UX design.* One of the first things that stands out about Verytas is its
> clean, modern, and intuitive interface. The overall design creates a strong first impression and makes the
> platform feel professional from the very beginning of the user journey.
>
> 2. *Multi-user authentication and dedicated dashboards.* The platform caters to both content creators and
> brands through separate login experiences and dedicated dashboards. This role-based approach helps
> streamline workflows and ensures that both parties can access the functionalities relevant to their
> specific needs.
>
> 3. *Detailed and insightful content verification.* A particularly valuable feature is the model that
> verifies the facts, claims, and metrics provided by content creators. Instead of simply labelling
> information as correct or incorrect, the platform provides additional insights into specific
> discrepancies, helping users understand exactly which claims or metrics require attention. This makes the
> verification process more informative and actionable.
>
> 4. *Practical and relevant use case.* Verytas addresses a genuine challenge in brand and creator
> collaborations: the gap between what brands expect and what content creators actually deliver. Brand
> teams often have limited time to manually review all the content produced by creators and verify whether
> it aligns with campaign requirements and agreed-upon claims. Verytas offers a structured and intuitive way
> to address this challenge by bringing content verification and campaign oversight into a single platform.
>
> **Constructive feedback**
>
> 1. *Add an interactive onboarding guide.* Although the landing page and overall UI/UX are impressive,
> understanding the platform's actual functionality from the landing page alone can be challenging. Verytas
> appears to be a comprehensive and dynamic platform with different workflows depending on the user's role
> and use case. Consequently, a first-time visitor may find it difficult to understand exactly how the
> platform works and how it can be useful to them.
>
> Alongside the existing demo, an interactive, step-by-step product walkthrough could significantly improve
> the onboarding experience. For example, a guided flow consisting of steps such as Step 1 of 7, Step 2 of
> 7, and so on, could demonstrate the complete process, from setting up a campaign to reviewing creator
> submissions and verifying claims. A short tutorial or user guide explaining the key features and their
> practical applications would also help users understand the platform's value before exploring it
> independently.
>
> 2. *Ensure the reliability and accuracy of the verification model.* The content verification model is one
> of the platform's most promising features, but its reliability will be critical to its success. Since the
> underlying backend implementation and model performance metrics are not available for assessment, it is
> difficult to determine how effectively it handles false positives and false negatives. Valid claims could
> potentially be flagged incorrectly, while inaccurate claims might go undetected.
>
> Incorporating confidence scores, transparent explanations for verification decisions, and an option for
> manual review could help improve the model's reliability and build greater trust among both brands and
> content creators.
>
> **Overall impression**
>
> Verytas presents a promising solution to a genuine real-world problem, combining a professional user
> experience, role-specific dashboards, and detailed content verification. Its biggest strength lies in
> making a potentially complex brand and creator management process more structured, accessible, and
> actionable.
>
> The primary opportunity for improvement is to make the platform's functionality easier to understand for
> first-time users through interactive onboarding and practical walkthroughs. Alongside this, continued
> attention to the accuracy and transparency of the verification model could further strengthen user
> confidence.
>
> Overall, Verytas offers a compelling concept with a practical use case. With a more guided first-time user
> experience and a reliable verification mechanism, it has the potential to deliver meaningful value to both
> brands and content creators.

### P2 (student at the same college, different stream)

> **Constructive feedback**
>
> 1. *Confusing starting page.* The platform could benefit from a clearer starting page that explains its
> purpose before asking users to choose a company or an individual profile. First-time visitors may find it
> difficult to understand what Verytas does and how it can help them before making these selections. A
> brief introduction explaining the platform's core functionality and the different user roles would make
> onboarding more intuitive and help users understand the product's value from the beginning.
>
> 2. *Difficult words and numbers.* Certain terms and metrics, such as "Draft," "100% Clean," and
> "Escalation," may not be immediately understandable to new users. Without sufficient context, users may
> struggle to interpret these labels and understand their significance within the review process. Adding
> short explanations, tooltips, and clear descriptions of important metrics would make the platform easier
> to understand and help users make better use of the information presented.
>
> 3. *No feedback after running a review.* When users click the "Run Review" button, the platform should
> provide immediate feedback indicating whether the review has started and whether it is still processing.
> Without a visible loading indicator, progress update, or completion message, users may be unsure whether
> their action was successful or whether they need to click the button again. Introducing clear status
> messages and progress indicators would make the review process more transparent and reduce uncertainty.
>
> 4. *Unclear review results.* Although users can see results such as "100% Clean," the platform does not
> clearly explain what was checked or why a particular result was generated. This can make it difficult for
> users to evaluate the reliability and significance of the review. Providing a detailed breakdown of the
> checks performed, the claims verified, and the reasoning behind the results would make the output more
> informative and help users better understand the system's decisions.
>
> 5. *Empty pages.* Some pages display messages such as "Nothing Here" or show zero items without explaining
> why the page is empty or what users should do next. This may leave first-time users confused about
> whether they have missed a step or whether the platform has no relevant information available. Adding
> helpful empty-state messages, clear next steps, and relevant actions, such as creating a review or adding
> information, would make these pages more useful and guide users through the platform.

### P3 (family member of a team member)

> **Constructive feedback**
>
> 1. *Long review forms.* The review form contains numerous fields, which may make it time-consuming and
> difficult for users who want to complete a quick review. Asking for too much information at once can
> increase the effort required to use the platform and may discourage users from completing the process.
> Simplifying the form by prioritizing essential fields, grouping related information, and making optional
> fields clearly identifiable would create a smoother experience. A step-by-step form could also help users
> complete reviews more efficiently without feeling overwhelmed.
>
> 2. *Cut-off text.* Some titles and labels appear incomplete or cut off, making them difficult to read and
> understand. This can prevent users from interpreting important information correctly and may affect their
> ability to navigate the platform confidently. Improving text wrapping, adjusting component widths, and
> ensuring that labels remain visible across different screen sizes would enhance readability and create a
> more polished, professional interface.
>
> 3. *AI warning reduces trust.* The warning that AI can make mistakes is important for communicating the
> limitations of automated verification. However, presenting this warning without sufficient context may
> cause users to question the reliability of the entire platform. Rather than removing the disclaimer,
> Verytas could complement it with transparent explanations of how reviews are conducted, confidence
> indicators where appropriate, and clear evidence supporting verification results. This would help users
> understand both the capabilities and limitations of the AI system while encouraging informed and
> responsible use.
>
> **Overall impression**
>
> Verytas has the potential to simplify content verification and improve collaboration between brands and
> content creators. Addressing lengthy forms, incomplete text, and concerns about AI reliability would
> further improve usability, readability, and user confidence. These improvements could make the platform
> more accessible to new users while creating a more efficient and trustworthy review experience.
