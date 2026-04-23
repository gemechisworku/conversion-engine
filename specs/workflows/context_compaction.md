## 1. Purpose

Defines the operational compaction flow.

## 2. Steps

1. evaluate compaction trigger
2. persist current session summary
3. preserve refs and pending actions
4. generate compacted summary
5. log compaction event
6. rehydrate minimal working context

## 3. Required Preservations

* lead state
* brief refs
* pending actions
* policy flags
* last customer intent
* external ids

---