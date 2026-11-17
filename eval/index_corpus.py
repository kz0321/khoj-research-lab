"""Index a frozen collection without calling the generation model.

Create data/manifests/index.pause to stop cleanly after the current small batch.
Remove that marker before resuming. Stable document IDs and server hashes reuse
already-indexed passages; there is no corpus-wide delete operation.
"""
from __future__ import annotations
import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from eval.prepare_data import DATA,write_json
from eval.run import read_jsonl,request_json,public_document


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api",default="http://127.0.0.1:8778")
    parser.add_argument("--collection",default="frames-frozen")
    parser.add_argument("--batch-size",type=int,default=5)
    parser.add_argument("--pause-file",type=Path,default=DATA/"manifests/index.pause")
    args=parser.parse_args()
    if not 1<=args.batch_size<=20:parser.error("Batch size must be1..20")
    path=(DATA/"corpus"/args.collection/"docs.jsonl").resolve()
    if path.parent.parent!=(DATA/"corpus").resolve():parser.error("Collection must be directly under data/corpus")
    docs=read_jsonl(path)
    started=time.monotonic();processed=cached=0;status="completed"
    request_json(args.api,"/api/collections",{"id":args.collection,"name":args.collection})
    for offset in range(0,len(docs),args.batch_size):
        if args.pause_file.exists():status="paused";break
        batch=docs[offset:offset+args.batch_size]
        result=request_json(args.api,f"/api/collections/{args.collection}/import",{"documents":[public_document(doc) for doc in batch]},timeout=600)
        if result.get("errors"):raise RuntimeError(result["errors"])
        processed+=len(result["imported"])
        cached+=sum(bool(item.get("cached")) for item in result["imported"])
        progress={"utc":datetime.now(timezone.utc).isoformat(),"collection":args.collection,"processed":processed,
                  "expected":len(docs),"cached":cached,"session_elapsed_seconds":round(time.monotonic()-started,3)}
        with (DATA/"manifests/indexing-trace.jsonl").open("a",encoding="utf-8") as stream:
            stream.write(json.dumps(progress)+"\n")
        print(json.dumps(progress),flush=True)
    collection=next(c for c in request_json(args.api,"/api/collections")["collections"] if c["id"]==args.collection)
    if status=="completed" and collection["documents"]!=len(docs):
        raise RuntimeError("Final collection has extra or missing documents; frozen-corpus assumptions are violated")
    summary={"status":status,"collection":collection,"expected_documents":len(docs),"processed_this_session":processed,
             "cached_this_session":cached,"indexing_session_seconds":round(time.monotonic()-started,3),
             "wall_seconds_since_collection_creation_including_pauses":round((datetime.now(timezone.utc)-datetime.fromisoformat(collection["created_at"])).total_seconds(),3),
             "api_llm_calls":0,"embedding_model":request_json(args.api,"/api/status").get("embedding_model"),
             "note":"Local embedding/indexing only; no benchmark generation or temporal audit. Session time includes hash-cache checks; wall time also includes pauses/restarts."}
    write_json(DATA/"manifests"/(args.collection+"-local-index.json"),summary)
    print(json.dumps(summary),flush=True)


if __name__=="__main__":main()
