## **1. Overview**

The system follows a **multi-agent orchestration architecture** with:

* Central orchestrator agent
* Specialized subagents
* Tool-based execution layer
* Knowledge base layer
* Observability layer

---

## **2. High-Level Components**

### **A. Data Layer**

* Crunchbase dataset
* layoffs.fyi
* job posts
* public web sources

---

### **B. Processing Layer**

* Signal extraction services
* Feature normalization
* Evidence structuring

---

### **C. Knowledge Layer (KB)**

* Markdown-based structured knowledge
* Includes:

  * company profiles
  * signal briefs
  * competitor analyses
* Supports:

  * indexing
  * logging
  * retrieval

---

### **D. Agent Layer**

#### **1. Lead Orchestrator (Primary Agent)**

* Controls flow
* Delegates tasks
* Decides next actions

#### **2. Subagents**

* Signal Researcher
* AI Maturity Scorer
* Competitor Gap Analyst
* ICP Classifier
* Tone & Claim Reviewer
* Scheduler
* CRM Recorder

---

### **E. Tool Layer**

* Evidence tools
* KB tools
* CRM tools
* Scheduling tools
* Policy tools
* Outreach tools

---

### **F. Execution Layer**

* Email (Resend/MailerSend)
* SMS (Africa’s Talking)
* CRM (HubSpot)
* Calendar (Cal.com)

---

### **G. Observability Layer**

* Langfuse tracing
* Event logging
* Evidence graph

---

## **3. Data Flow**

### **Step-by-step flow**

1. Lead identified
2. Signal enrichment
3. Subagents generate:

   * signal brief
   * AI score
   * competitor gap
4. ICP classification
5. Outreach drafted
6. Reviewer validates
7. Message sent
8. Reply processed
9. Scheduling handled
10. CRM updated
11. Memory + logs updated

---

## **4. Agent Interaction Model**

* Orchestrator runs reasoning loop
* Calls tools or spawns subagents
* Subagents:

  * operate in isolated context
  * return structured outputs

---

## **5. Context Management**

* Active context:

  * current lead
  * conversation state
* External:

  * KB pages
  * structured state store
* Compaction:

  * removes redundant data
  * preserves decisions + references

---

## **6. Failure Handling**

* If signal confidence low → soften language
* If classification uncertain → abstain
* If booking fails → retry or escalate
* If policy violated → block send

---

## **7. Deployment Model**

* Backend services (FastAPI)
* Agent runtime (LLM orchestration layer)
* External integrations via APIs
* Logging via Langfuse

---