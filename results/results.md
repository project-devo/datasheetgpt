| config | recall@5 | MRR | answer accuracy | citation accuracy | median latency |
|---|---|---|---|---|---|
| 512 chunks (baseline) | 71% | 0.517 | 77% | 73% | 3.9 s |
| 256 chunks | 69% | 0.451 | - | - | - |
| 1024 chunks | 74% | 0.506 | 73% | 67% | 4.4 s |
| hybrid (live) | 82% | 0.515 | 80% | 76% | 5.9 s |
| hybrid + MiniLM | 82% | 0.598 | - | - | - |
| hybrid + bge rerank | 91% | 0.750 | 88% | 84% | 20.1 s |
