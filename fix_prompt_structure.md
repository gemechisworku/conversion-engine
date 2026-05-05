# Fix Instruction: Strengthen Instruction Reliability in Long Prompts
Associated with `question.md`

## 🧠 Core Problem

Even though the model “sees” the entire prompt during prefill, it does **not treat all parts equally during generation**.

- Generation happens **token-by-token (decode phase)**
- At each step, the model **re-selects what to pay attention to**
- This creates imbalance in influence across the prompt

### Result:
- Early instructions (e.g., “JSON only”) tend to dominate
- Instructions buried after large JSON payloads get **weakened or ignored**
- Leads to:
  - Markdown appearing
  - Hallucinated or invented facts

---

## ⚙️ Why This Happens

### 1. Prefill ≠ Equal Influence
- Prefill loads all tokens into memory (KV cache)
- But **influence is determined during decode**
- Not all tokens are equally retrieved or used

---

### 2. Early Tokens Become Anchors
- First lines of the system prompt:
  - Match training patterns (high authority)
  - Are repeatedly attended to
- These act as **“attention sinks”** (stable anchors)

---

### 3. Large JSON Payload Creates Noise
- Long structured data introduces:
  - Repetition (keys, punctuation)
  - High token density
- Late instructions inside/after this become:
  - Harder to retrieve
  - Less distinct

---

### 4. Positional Bias
- Tokens farther from the current generation step:
  - Are less consistently attended
- Late instructions compete with nearby noisy tokens

---

### 5. Decode Momentum
- Early generated tokens shape later ones
- If the model starts with markdown/prose:
  - That pattern self-reinforces
- Late constraints must fight:
  - Distance + noise + existing trajectory

---

## ✅ Conceptual Fix

### Use “Constraint Reinforcement” (a.k.a. Sandwiching)

Ensure critical instructions are:

1. **Placed early** (to leverage authority and training priors)
2. **Repeated close to generation** (to improve retrieval at decode time)

---

## 🎯 What This Achieves

- Early placement:
  - Sets global behavior expectations
- Late placement:
  - Ensures rules are **fresh and locally accessible**
- Together:
  - Reduces instruction fade
  - Improves consistency in output format and correctness

---

## 📌 Design Principles

### 1. Keep Instructions Short and Explicit
- Compact rules are easier to retrieve repeatedly
- Avoid long descriptive paragraphs

---

### 2. Prioritize Proximity to Generation
- The closer an instruction is to where output begins:
  - The more influence it has during decode

---

### 3. Avoid Burying Critical Rules in Noise
- Do not rely on instructions that appear:
  - After large payloads
  - Inside dense structured data

---

### 4. Reinforce, Don’t Just State Once
- A single instruction is often insufficient in long contexts
- Reinforcement improves reliability

---

### 5. Consider Hard Constraints for Critical Outputs
- When correctness is mandatory:
  - Prefer structured or constrained decoding (e.g., schema enforcement)
- This converts:
  - “follow instructions” → into → “cannot violate constraints”

---

## ⚖️ Tradeoffs

### 1. Increased Token Usage
- Repeating instructions adds to prompt size
- Impacts cost and context window usage

---

### 2. Added Prompt Complexity
- More structure required in message layout
- Must ensure consistency across repeated instructions

---

### 3. Reduced Flexibility (with strict constraints)
- Structured decoding may:
  - Limit expressive outputs
  - Slightly impact performance

---

## 🧭 Guiding Rule

> Critical output constraints must be **both globally visible and locally accessible at generation time**

---

## 🧪 Validation Strategy

- Test behavior with:
  - Long and noisy inputs
  - Instructions placed at different positions
- If output quality changes based on position:
  - You are observing decode-time attention effects

---

## 🧠 Mental Model to Keep

> Prefill makes information available  
> Decode determines what actually influences the output