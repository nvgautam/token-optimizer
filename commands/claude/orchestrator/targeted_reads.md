# Targeted Reads Rule

```
HASH=$(python3 -c "import hashlib,os; print(hashlib.sha256(os.getcwd().encode()).hexdigest())")
IDX=~/.agentflow/cache/$HASH/index/<relative-path>.idx
```
- `.idx` exists → `grep "^<section>:" "$IDX"` → `start-end` → `Read(offset=start, limit=end-start+1)`
- `.idx` absent → read full file
