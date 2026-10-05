"""Local lexical inspection of final chunks; no generated answers."""
import argparse
import json
from prepare_data import DATA, jsonl_read, rank

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("query")
parser.add_argument("--top-k", type=int, default=3)
args = parser.parse_args()
if not 1 <= args.top_k <= 20:
    parser.error("top-k must be between 1 and 20")
for score, _, c in rank(args.query, jsonl_read(DATA/"chunks/final.jsonl"))[:args.top_k]:
    print(json.dumps({"score":round(score,6), "chunk_id":c["chunk_id"], "document_title":c["document_title"],
                      "source":c["source"], "date":c["date"], "pages":c["pages"],
                      "validity_status":c["validity_status"], "allowed_use":c["allowed_use"], "text":c["text"]}, ensure_ascii=False))
