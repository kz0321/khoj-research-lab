import unittest
import importlib.util
from pathlib import Path
import json
import os
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from eval.metrics import answer_scores, supporting_fact_scores, paired_bootstrap, paired_ratio_bootstrap, cohen_kappa, task_score, human_grounding_scores, visible_claims
from eval.perturbations import withhold_support
from eval.run import public_document, execute, summarize
from eval.official_hotpot import evaluate as official_evaluate


class EvaluationTests(unittest.TestCase):
    def test_answer_normalization_and_yes_no(self):
        self.assertEqual(answer_scores("The U.S.", "us")["em"],1)
        self.assertEqual(answer_scores("yes it is", "yes")["f1"],0)
        self.assertAlmostEqual(answer_scores("red blue", "red green")["f1"],.5)

    def test_supporting_facts_not_document_only(self):
        score=supporting_fact_scores([["A",0],["A",1]],[["A",1],["B",0]])
        self.assertEqual(score["em"],0)
        self.assertEqual(score["f1"],.5)

    def test_failed_runs_stay_in_denominator(self):
        task={"answer":"yes","supporting_facts":[["A",0]]}
        response={"status":"failed","result":{"answer":"yes","supporting_facts":[["A",0]]}}
        result=task_score(task,response)
        self.assertEqual(result["answer_em"],0)
        self.assertEqual(result["supporting_f1"],0)

    def test_bootstrap_paired_task_units(self):
        result=paired_bootstrap({"a":0,"b":.2},{"a":.1,"b":.3,"extra":1})
        self.assertEqual(result["n_tasks"],2)
        self.assertAlmostEqual(result["difference"],.1)
        self.assertAlmostEqual(result["ci95"][0],.1)

    def test_withhold_preserves_sentence_ids(self):
        docs=[{"id":"d","title":"T","text":"one\ntwo\nthree","sentences":[{"id":0,"text":"one"},{"id":1,"text":"two"},{"id":2,"text":"three"}]}]
        result=withhold_support(docs,[["T",1]])
        self.assertEqual([x["id"] for x in result[0]["sentences"]],[0,2])
        self.assertNotIn("two",result[0]["text"])
        self.assertIn("two",docs[0]["text"])

    def test_gold_never_uploaded(self):
        doc={"id":"x","title":"T","text":"evidence","answer":"secret","supporting_facts":["secret"],"gold_source_urls":["secret"]}
        outgoing=public_document(doc)
        self.assertNotIn("secret",str(outgoing))
        self.assertIsNone(outgoing["sentences"])

    def test_checker_is_not_human_ground_truth(self):
        result=human_grounding_scores([{"status":"supported","claim_id":"c"}])
        self.assertIsNone(result["citation_support_precision"])

    def test_cited_claim_location_conversion(self):
        task={"answer":"x","supporting_facts":[["T",4]]}
        response={"status":"completed","result":{"answer":"x","claims":[{"id":"c","evidence_ids":["E1"]}],
            "evidence":[{"id":"E1","title":"T","location":{"sentence_ids":[4]},"text":"x"},
                        {"id":"E2","title":"D","location":{"sentence_ids":[1]},"text":"noise"}]}}
        result=task_score(task,response)
        self.assertEqual(result["supporting_f1"],1)

    def test_interrater_agreement(self):
        result=cohen_kappa(["supported","unsupported"],["supported","supported"])
        self.assertEqual(result["agreement"],.5)
        self.assertEqual(result["kappa"],0)

    def test_citation_bootstrap_keeps_zero_output_tasks(self):
        result=paired_ratio_bootstrap({"a":(1,2),"b":(0,0)},{"a":(2,2),"b":(0,0)},samples=200)
        self.assertEqual(result["n_tasks"],2)
        self.assertEqual(result["difference"],.5)
        self.assertGreater(result["undefined_bootstrap_samples"],0)
        self.assertEqual(result["ci95"],[.5,.5])

    def test_discarded_ledger_candidates_are_not_output_citations(self):
        result={"mode":"verified","answer":"","claims":[{"id":"A0","status":"insufficient"},{"id":"C1","status":"supported"},{"id":"C2","status":"contradicted"}]}
        self.assertEqual([c["id"] for c in visible_claims(result)],["C1"])

    def test_parity_with_pinned_official_hotpot_scorer(self):
        path=Path(__file__).resolve().parents[1]/"eval/vendor/hotpot_evaluate_v1.py"
        spec=importlib.util.spec_from_file_location("official_hotpot_reference",path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        for pred,gold in [("The U.S.","us"),("red blue","red green"),("yes it is","yes"),("","yes"),("no","no")]:
            actual=answer_scores(pred,gold)
            self.assertEqual(actual["em"],float(module.exact_match_score(pred,gold)))
            self.assertEqual(actual["f1"],module.f1_score(pred,gold)[0])
        for pred,gold in [([["A",0]],[["A",0],["B",1]]),([],[["A",0]])]:
            official={key:0 for key in ["sp_em","sp_f1","sp_prec","sp_recall"]}
            module.update_sp(official,pred,gold)
            actual=supporting_fact_scores(pred,gold)
            self.assertEqual(actual["f1"],official["sp_f1"])

    def test_official_subprocess_reads_unicode_json_on_windows(self):
        task={"id":"unicode-fixture","original_id":"unicode-fixture","answer":"São Paulo","supporting_facts":[["São Paulo",0]]}
        row={"task_id":task["id"],"dataset":"hotpotqa","split":"dev","mode":"verified","repeat":0,"scenario":"clean",
             "scores":{"failed":False,"predicted_supporting_facts":[["São Paulo",0]]},"response":{"result":{"answer":"São Paulo"}}}
        with tempfile.TemporaryDirectory(prefix="khoj-eval-utf8-") as temp:
            target=Path(temp).resolve()
            self.assertEqual(target.parent,Path(tempfile.gettempdir()).resolve())
            with patch("eval.official_hotpot.read_jsonl",side_effect=lambda p:[task] if p.name=="hotpotqa-dev.jsonl" else [row]), patch.dict(os.environ,{"PYTHONUTF8":"0"}):
                result=official_evaluate(target/"test-runs.jsonl","verified","dev",0,"clean",target/"score")
            self.assertEqual(result["metrics"]["em"],1)
            self.assertEqual(result["metrics"]["sp_f1"],1)

    def test_async_api_client_does_not_send_gold(self):
        received=[]
        polls=[]
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def send_json(self,payload,status=200):
                body=json.dumps(payload).encode()
                self.send_response(status);self.send_header("Content-Type","application/json")
                self.send_header("Content-Length",str(len(body)));self.end_headers();self.wfile.write(body)
            def do_POST(self):
                received.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
                self.send_json({"id":"test-run","status":"queued"},202)
            def do_GET(self):
                polls.append(self.path)
                if len(polls)==1:self.send_json({"id":"test-run","status":"running"})
                else:self.send_json({"id":"test-run","status":"completed","result":{"answer":"a test response"}})
        server=ThreadingHTTPServer(("127.0.0.1",0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with patch("eval.run.time.sleep",return_value=None):
                response=execute(f"http://127.0.0.1:{server.server_port}",{"question":"test question","answer":"gold secret","supporting_facts":["gold secret"]},"verified","test-corpus","empty",5)
            self.assertEqual(response["status"],"completed")
            self.assertEqual(len(polls),2)
            self.assertNotIn("gold secret",json.dumps(received))
            self.assertFalse(received[0]["allow_web"])
            self.assertEqual(received[0]["perturbation"]["kind"],"empty")
        finally:
            server.shutdown();server.server_close();thread.join(timeout=2)

    def test_failed_api_usage_does_not_become_zero_cost(self):
        row={"dataset":"hotpotqa","split":"dev","scenario":"clean","mode":"verified","task_id":"t1",
             "scores":{"failed":True,"answered":False,"answer_em":0,"answer_f1":0,"elapsed_seconds":2,
                       "usage":{"input_tokens":0,"output_tokens":0,"unknown_usage_attempts":1,"estimated_cost_usd":None}}}
        summary=summarize([row])["groups"][0]
        self.assertEqual(summary["failed_runs"],1)
        self.assertIsNone(summary["estimated_cost_usd_total"])
        self.assertEqual(summary["unknown_usage_attempts"],1)
        self.assertIsNone(summary["citation_support_precision"])
        corrected=json.loads(json.dumps(row))
        corrected["scores"].update(failed=False,answered=True,answer_em=1,answer_f1=1,usage={"input_tokens":5,"output_tokens":2,"unknown_usage_attempts":0,"estimated_cost_usd":.01})
        rerun=summarize([row,corrected])["groups"][0]
        self.assertEqual(rerun["attempted_runs"],1)
        self.assertEqual(rerun["recorded_attempts_including_explicit_reruns"],2)
        self.assertEqual(rerun["answer_em"],1)
        self.assertEqual(rerun["unknown_usage_attempts"],1)
        self.assertIsNone(rerun["estimated_cost_usd_total"])


if __name__=="__main__":
    unittest.main()
