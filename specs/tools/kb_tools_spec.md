## 1. Purpose

Defines tools for reading, writing, indexing, and searching the knowledge base.

## 2. Tool Set

* `kb_read_page`
* `kb_write_page`
* `kb_find_pages`
* `kb_update_index`
* `kb_append_log`

## 3. Rules

* KB writes must be auditable
* KB updates must not silently delete critical content
* write paths must be constrained to allowed roots
* KB tools should support versioning metadata where possible

---
