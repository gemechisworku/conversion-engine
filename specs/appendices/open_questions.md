
## 1. Product / Business

* Should multiple contacts at the same company share one lead record or separate lead records?
* What exact pricing language is permitted autonomously?
* What is the exact threshold for “warm lead” channel switching to SMS?

## 2. Technical

* Which parts of competitor-gap generation should be deterministic vs LLM-synthesized?
* Should KB pages be stored in git, object storage, or both?
* What model routing policy will be used per subagent?
* What are the exact deployed webhook contracts (path, headers, signature algorithm, retry semantics) for Resend, Africa's Talking, and Cal.com?
* For HubSpot remote MCP GA, which exact tool names and argument schemas should be treated as canonical for `crm_upsert_lead` and `crm_append_event` in this codebase?
* For Act II inbound identity matching, should local Crunchbase ODM matching prefer exact contact email/phone over email-domain matching when both exist?
* For Act II CFPB lookup, should company aliases/legal names be expanded beyond exact local Crunchbase company name?
* For Act II news lookup, which public source should be canonical when the company has no filings page or press/news page?

## 3. Evaluation

* What exact confidence threshold should trigger classifier abstention?
* What threshold defines “material evidence insufficiency” for send blocking?
* How should false-positive competitor-gap risk be scored in evaluation?

---
