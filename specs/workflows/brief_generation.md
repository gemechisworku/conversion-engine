## 1. Purpose

Defines the synthesis of normalized evidence into the hiring signal brief.

## 2. Inputs

* evidence packet
* bench snapshot
* policy guidance
* optional prior company KB page

## 3. Steps

1. load evidence packet
2. normalize signal summaries
3. assign confidence per signal
4. compute research hook
5. compute language guidance
6. attach bench match
7. persist brief
8. update KB and state

## 4. Outputs

* brief_id
* persisted brief
* KB update
* log event

---