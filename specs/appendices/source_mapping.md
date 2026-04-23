## 1. Purpose

Maps source categories to system components and usage boundaries.

| Source Type                               | Used By                | Purpose                                  | Restrictions                         |
| ----------------------------------------- | ---------------------- | ---------------------------------------- | ------------------------------------ |
| Crunchbase sample                         | Signal Researcher      | firmographics, funding                   | dataset-only use                     |
| layoffs.fyi                               | Signal Researcher      | layoff signal                            | public structured source             |
| public job posts                          | Signal Researcher      | hiring velocity, AI roles                | no login, respect robots.txt         |
| public press/blogs                        | Signal Researcher      | leadership changes, executive commentary | public only                          |
| BuiltWith/Wappalyzer/public stack signals | Signal Researcher      | tech stack clues                         | public evidence only                 |
| KB pages                                  | all reasoning agents   | durable synthesized knowledge            | must remain evidence-linked          |
| bench summary                             | orchestrator, reviewer | commitment guardrails                    | must reflect latest allowed snapshot |

---