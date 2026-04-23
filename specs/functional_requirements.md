## **1. Overview**

This system is an **AI-driven lead generation and conversion engine** for Tenacious Consulting. It automates:

* Prospect discovery
* Signal-based qualification
* Personalized outreach
* Conversation handling
* Meeting booking

The system must produce **high-quality, research-backed outreach** grounded in verifiable public data and maintain **brand integrity, accuracy, and responsiveness**.

---

## **2. Actors**

* **System (AI agents + services)**
* **Synthetic Prospect (challenge environment)**
* **Tenacious Sales Team (human fallback)**
* **Program Staff (evaluation)**

---

## **3. Core Functional Requirements**

### **FR-1: Lead Discovery**

* System MUST ingest company data from:

  * Crunchbase dataset
* System MUST generate candidate leads matching ICP segments

---

### **FR-2: Signal Enrichment**

For each lead, the system MUST:

* Retrieve:

  * Funding events (≤180 days)
  * Job-post data (≤60 days)
  * Layoffs (≤120 days)
  * Leadership changes (≤90 days)
  * Tech stack signals
* Produce structured **evidence records**
* Attach **confidence scores** per signal

---

### **FR-3: AI Maturity Scoring**

* System MUST compute AI maturity score (0–3)
* System MUST provide:

  * Per-signal justification
  * Confidence level
* System MUST avoid unsupported claims

---

### **FR-4: Competitor Gap Analysis**

* Identify 5–10 relevant competitors
* Compute AI maturity for each
* Determine:

  * Prospect percentile in sector
  * Missing practices
* Generate **competitor_gap_brief**

---

### **FR-5: ICP Classification**

* Classify each lead into one of 4 segments
* MUST output:

  * Primary segment
  * Alternate segment
  * Confidence
* MUST support abstention if confidence is low

---

### **FR-6: Hiring Signal Brief Generation**

* Combine all signals into:

  * hiring_signal_brief
* MUST include:

  * Evidence references
  * Confidence per signal
  * Non-overclaiming language markers

---

### **FR-7: Outreach Generation**

* Generate personalized email:

  * Based on signals + competitor gap
  * Adapted to ICP segment
* MUST:

  * Match Tenacious tone
  * Avoid hallucination
  * Adjust language by confidence

---

### **FR-8: Outreach Review (Safety Layer)**

* All drafts MUST be validated for:

  * Tone compliance
  * Evidence grounding
  * No over-claiming
  * No bench over-commitment

---

### **FR-9: Communication Handling**

* System MUST:

  * Receive replies
  * Interpret intent
  * Decide next-best-action:

    * clarify
    * nurture
    * schedule
    * escalate

---

### **FR-10: Multi-Channel Support**

* Email = primary channel
* SMS = scheduling for warm leads
* Voice = optional (human-led discovery call)

---

### **FR-11: Scheduling**

* System MUST:

  * Propose available slots
  * Handle timezone differences
  * Confirm bookings via Cal.com
* MUST update CRM after booking

---

### **FR-12: CRM Integration**

* System MUST:

  * Create/update leads in HubSpot
  * Log all events:

    * outreach
    * replies
    * stage changes
    * bookings

---

### **FR-13: Bench Matching**

* System MUST:

  * Check demand vs available engineers
* MUST NOT:

  * Commit capacity not available

---

### **FR-14: Memory and Knowledge Management**

* System MUST:

  * Store structured knowledge in KB
  * Maintain session state
  * Persist important learnings
* MUST compact context safely

---

### **FR-15: Observability**

* System MUST:

  * Log all agent decisions
  * Track tool usage
  * Track cost per lead
  * Enable traceability for every claim

---

### **FR-16: Policy Compliance**

* System MUST enforce:

  * No fabricated signals
  * No real customer outreach
  * Kill-switch functionality
  * Draft labeling

---

## **4. Success Criteria**

* End-to-end pipeline works autonomously
* Signal-grounded outreach improves response quality
* Conversations progress to booking reliably
* All outputs are auditable and traceable
