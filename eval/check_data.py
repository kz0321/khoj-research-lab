"""Validate prepared dataset integrity without accessing a model or network."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from eval.prepare_data import DATA, write_json
from eval.run import read_jsonl


def validate(data:Path=DATA):
    tasks=[]
    for name,count in [("frames-dev",20),("frames-test",100),("hotpotqa-dev",20),("hotpotqa-test",40)]:
        selected=read_jsonl(data/"evaluation"/(name+".jsonl"))
        assert len(selected)==count,(name,len(selected))
        assert len({t["id"] for t in selected})==count
        tasks+=selected
    assert len({t["id"] for t in tasks})==len(tasks)
    assert len({" ".join(t["question"].lower().split()) for t in tasks})==len(tasks)
    collections={t["collection_id"] for t in tasks}
    indexed={};n_docs=0;n_sentences=0
    forbidden={"answer","question","supporting_facts","gold_source_urls","gold_document_ids","frames_prompt_id","original_link"}
    for cid in collections:
        docs=read_jsonl(data/"corpus"/cid/"docs.jsonl")
        indexed[cid]=docs
        assert len({d["id"] for d in docs})==len(docs)
        for doc in docs:
            assert doc["sha256"]==hashlib.sha256(doc["text"].encode()).hexdigest(),doc["id"]
            assert not forbidden.intersection(doc),doc["id"]
            assert doc.get("url") and doc.get("license") and doc.get("source_revision")
            if "sentences" in doc:
                assert doc["text"]=="\n".join(s["text"] for s in doc["sentences"])
                assert len({s["id"] for s in doc["sentences"]})==len(doc["sentences"])
                n_sentences+=len(doc["sentences"])
        n_docs+=len(docs)
    for task in tasks:
        docs=indexed[task["collection_id"]]
        if task["dataset"]=="hotpotqa":
            assert len(docs)==10
            available={(d["title"],s["id"]) for d in docs for s in d["sentences"]}
            assert set(map(tuple,task["supporting_facts"])).issubset(available),task["id"]
        else:
            assert set(task["gold_document_ids"]).issubset({d["id"] for d in docs}),task["id"]
            assert task["gold_document_ids"],task["id"]
    hotpot=json.loads((data/"manifests/hotpotqa.json").read_text(encoding="utf-8"))
    for item in hotpot["collections"]:
        assert item["sha256"]==hashlib.sha256((data/"corpus"/item["collection_id"]/"docs.jsonl").read_bytes()).hexdigest()
    frames=json.loads((data/"manifests/frames.json").read_text(encoding="utf-8"))
    assert frames["corpus_sha256"]==hashlib.sha256((data/"corpus/frames-frozen/docs.jsonl").read_bytes()).hexdigest()
    audits=read_jsonl(data/"evaluation/frames-temporal-audit.jsonl")
    extra=[p.name for p in (data/"corpus").iterdir() if p.is_dir() and p.name not in collections]
    return {"valid":True,"tasks":len(tasks),"collections":len(collections),"canonical_documents":n_docs,
            "hotpot_sentences":n_sentences,"all_gold_support_sentences_found":True,"gold_fields_absent_from_corpus":True,
            "manifest_hashes_match":True,"unreferenced_collection_count":len(extra),
            "frames_human_audits_pending":sum(a.get("status")!="approved" for a in audits),
            "note":"Integrity checks establish dataset structure and source isolation, not semantic answer correctness or temporal validity."}


if __name__=="__main__":
    result=validate()
    write_json(DATA/"manifests/integrity-check.json",result)
    print(json.dumps(result))
