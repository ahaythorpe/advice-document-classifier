"""Regression tests, one per failure the v0 harness actually made.

    python3 -m unittest discover -s tests -v

Each test names the bug it pins. These are not hypothetical edge cases: every
one of them was observed in the v0 output on sample_documents.json, and a fix
that is not pinned is a fix that comes back.
"""

from __future__ import annotations

import datetime
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from advicefiler import entities, evaluate, extract, flags, pipeline  # noqa: E402
from advicefiler.classify import KeywordClassifier  # noqa: E402
from advicefiler.kb import KnowledgeBase  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_samples():
    with open(os.path.join(ROOT, "sample_documents.json")) as fh:
        return extract.from_sample_records(json.load(fh)["documents"])


class SharedRun(unittest.TestCase):
    """One pipeline run, reused — the tests only read from it."""

    @classmethod
    def setUpClass(cls):
        cls.kb = KnowledgeBase.load()
        cls.documents = load_samples()
        cls.result = pipeline.run(cls.kb, cls.documents)
        cls.by_name = {r.name: r for r in cls.result.records}


class TestDates(unittest.TestCase):
    def test_australian_day_first(self):
        """03/04/2024 is 3 April in Australia, not 4 March."""
        parsed = entities.parse_date("03/04/2024")
        self.assertEqual(parsed.value, datetime.date(2024, 4, 3))

    def test_unambiguous_numeric_is_not_flagged_ambiguous(self):
        self.assertFalse(entities.parse_date("22/04/2024").ambiguous)

    def test_month_first_numeric_is_read_but_marked(self):
        parsed = entities.parse_date("04/22/2024")
        self.assertEqual(parsed.value, datetime.date(2024, 4, 22))
        self.assertTrue(parsed.ambiguous)

    def test_dates_sort_chronologically_not_lexically(self):
        """The v0 bug in one assertion.

        sorted(["10 September 2025", "14 March 2024"]) puts September first
        because '0' < '4'. That single comparison filed the March fact find and
        risk profile under the September insurance advice.
        """
        march = entities.parse_date("14 March 2024").value
        september = entities.parse_date("10 September 2025").value
        self.assertLess(march, september)
        self.assertLess(sorted(["10 September 2025", "14 March 2024"])[0],
                        "14 March 2024")   # the string order really is wrong

    def test_word_and_iso_forms(self):
        for raw, expected in (("14 March 2024", datetime.date(2024, 3, 14)),
                              ("14th March 2024", datetime.date(2024, 3, 14)),
                              ("March 14, 2024", datetime.date(2024, 3, 14)),
                              ("2024-03-14", datetime.date(2024, 3, 14))):
            self.assertEqual(entities.parse_date(raw).value, expected, raw)


class TestClientExtraction(unittest.TestCase):
    def test_shared_surname_convention(self):
        _, surnames, key = entities.extract_client("Client: Linh & David Nguyen.")
        self.assertEqual(surnames, ["Nguyen"])
        self.assertEqual(key, "Nguyen")

    def test_two_surnames_are_both_kept(self):
        """v0 took the last capitalised word and would have lost 'Tran'."""
        _, surnames, key = entities.extract_client(
            "Prepared for: Mei Tran and Jordan Okafor.")
        self.assertEqual(surnames, ["Okafor", "Tran"])
        self.assertEqual(key, "Okafor-Tran")

    def test_prepared_for_with_colon(self):
        """Found on a real SOA: 'Prepared for:' with a colon matched nothing."""
        _, _, key = entities.extract_client("Prepared for: Mei Tran.")
        self.assertEqual(key, "Tran")

    def test_client_data_form_is_not_a_client(self):
        """'FACT FIND - CLIENT DATA FORM' produced a client called FORM."""
        _, _, key = entities.extract_client(
            "FACT FIND - CLIENT DATA FORM. Client: Linh Nguyen.")
        self.assertEqual(key, "Nguyen")

    def test_subset_family_keys_merge_only_when_unambiguous(self):
        merged = entities.merge_family_keys(["Tran", "Okafor-Tran"])
        self.assertEqual(merged["Tran"], "Okafor-Tran")
        # Two possible parents means no merge: the tool does not know.
        ambiguous = entities.merge_family_keys(["Tran", "Okafor-Tran", "Tran-Wu"])
        self.assertEqual(ambiguous["Tran"], "Tran")


class TestLookalike(SharedRun):
    """SYSTEM.md section 7: an ATP mentioning 'Statement of Advice'."""

    def test_atp_citing_an_soa_is_an_atp(self):
        record = self.by_name["scan_005.pdf"]
        self.assertEqual(record.doc_type, "authority_to_proceed")
        self.assertGreaterEqual(record.confidence, self.kb.confidence_threshold)

    def test_atp_with_no_advice_record_is_still_an_atp(self):
        """v0 called this an SOA and invented a phantom advice event for Patel."""
        record = self.by_name["scan_009.pdf"]
        self.assertEqual(record.doc_type, "authority_to_proceed")
        self.assertIn("atp_without_advice_record",
                      [f.rule_id for f in record.flags])
        self.assertTrue(record.needs_review)

    def test_mentioned_title_scores_far_below_a_worn_title(self):
        classifier = KeywordClassifier(self.kb)
        mentions = extract.ExtractedDocument(
            "mention.pdf",
            "AUTHORITY TO PROCEED. I authorise implementation of the "
            "recommendations in the Statement of Advice dated 14 March 2024. "
            "Date signed: 14 March 2024.")
        result = classifier.classify(mentions)
        self.assertEqual(result.doc_type, "authority_to_proceed")
        self.assertGreater(result.scores["authority_to_proceed"],
                           result.scores["soa"] * 3)

    def test_short_abbreviations_do_not_match_inside_words(self):
        """'CAR' matched 'care'; every document became a Client Advice Record."""
        classifier = KeywordClassifier(self.kb)
        document = extract.ExtractedDocument(
            "care.pdf", "We take care with your insurance cover and carry it over.")
        result = classifier.classify(document)
        self.assertEqual(result.scores.get("car", 0), 0)


class TestGrouping(SharedRun):
    def test_inputs_attach_to_the_advice_they_feed(self):
        for name in ("scan_002.pdf", "scan_003.pdf"):
            record = self.by_name[name]
            self.assertIsNotNone(record.event, name)
            self.assertEqual(record.event.anchor.name, "scan_004.pdf", name)

    def test_march_inputs_did_not_land_on_the_september_event(self):
        """The exact v0 mis-grouping."""
        september = [e for e in self.result.grouping.events
                     if e.date == datetime.date(2025, 9, 10)][0]
        self.assertNotIn("scan_002.pdf", [m.name for m in september.members])
        self.assertNotIn("scan_003.pdf", [m.name for m in september.members])

    def test_explicit_citation_beats_proximity(self):
        record = self.by_name["scan_005.pdf"]
        self.assertIn("explicitly cites", record.attachment_reason)
        self.assertEqual(record.event.anchor.name, "scan_004.pdf")

    def test_authorisation_attaches_backwards(self):
        record = self.by_name["scan_008.pdf"]
        self.assertEqual(record.event.anchor.name, "scan_007.pdf")

    def test_two_separate_events_for_one_family(self):
        self.assertEqual(len(self.result.grouping.events), 2)

    def test_roa_records_its_sub_kind(self):
        record = self.by_name["scan_007.pdf"]
        self.assertIsNotNone(record.roa_sub_kind)
        self.assertEqual(record.roa_sub_kind["id"], "further_advice")

    def test_pds_reaches_its_event_by_product_name(self):
        record = self.by_name["scan_006.pdf"]
        self.assertIsNotNone(record.event)
        self.assertEqual(record.event.anchor.name, "scan_004.pdf")
        self.assertIn("AwesomeSuper", record.attachment_reason)


class TestFlags(SharedRun):
    def test_every_knowledge_base_rule_is_implemented(self):
        coverage = flags.coverage(self.kb)
        self.assertEqual(coverage["not_implemented"], [])
        self.assertEqual(coverage["not_in_knowledge_base"], [])

    def test_risk_mismatch_is_raised_and_does_not_block_filing(self):
        record = self.by_name["scan_003.pdf"]
        matching = [f for f in record.flags if f.rule_id == "risk_mismatch"]
        self.assertEqual(len(matching), 1)
        self.assertFalse(matching[0].blocks_filing)
        self.assertFalse(record.needs_review)
        self.assertIsNotNone(record.event)

    def test_roa_with_a_prior_soa_on_file_is_not_flagged(self):
        record = self.by_name["scan_007.pdf"]
        self.assertNotIn("roa_without_soa", [f.rule_id for f in record.flags])

    def test_fsg_without_a_client_is_not_a_failure(self):
        record = self.by_name["scan_001.pdf"]
        self.assertEqual(record.doc_type, "fsg")
        self.assertFalse(record.needs_review)
        self.assertNotIn("client_unidentified", [f.rule_id for f in record.flags])

    def test_illegible_scan_refuses_rather_than_guesses(self):
        record = self.by_name["scan_010.pdf"]
        self.assertIsNone(record.doc_type)
        self.assertEqual(record.confidence, 0.0)
        self.assertTrue(record.needs_review)

    def test_bad_extraction_caps_confidence(self):
        classifier = KeywordClassifier(self.kb)
        document = extract.ExtractedDocument(
            "shredded.pdf", "S T A T E M E N T  O F  A D V I C E x x x q q", page_count=4)
        self.assertLess(document.quality.score, 0.5)
        self.assertLessEqual(classifier.classify(document).confidence,
                             document.quality.score)


class TestPlacement(SharedRun):
    def test_nothing_is_written(self):
        from advicefiler.storage import ProposalOnlyTarget
        with self.assertRaises(NotImplementedError):
            ProposalOnlyTarget().commit(self.result.plan)

    def test_every_document_is_placed_somewhere(self):
        self.assertEqual(len(self.result.plan.files), len(self.result.records))
        for planned in self.result.plan.files:
            self.assertTrue(planned.filename)
            self.assertTrue(planned.folder)

    def test_event_folder_follows_the_naming_pattern(self):
        folders = set("/".join(p.folder) for p in self.result.plan.files)
        self.assertIn("Nguyen/2024-03 — Retirement & Super Consolidation [SOA]",
                      folders)
        self.assertIn("Nguyen/2025-09 — Insurance [ROA · further advice]", folders)

    def test_licensee_material_is_not_an_orphan(self):
        record = self.by_name["scan_001.pdf"]
        self.assertEqual(record.placement, "_Licensee documents")

    def test_colliding_filenames_are_suffixed_not_overwritten(self):
        names = ["/".join(p.folder + (p.filename,)) for p in self.result.plan.files]
        self.assertEqual(len(names), len(set(names)))


class TestEvaluation(SharedRun):
    def test_ground_truth_covers_every_sample(self):
        truth = evaluate.GroundTruth.load(os.path.join(ROOT, "ground_truth.json"))
        for record in self.result.records:
            self.assertTrue(truth.has(record.name), record.name)

    def test_no_confident_and_wrong_answers(self):
        truth = evaluate.GroundTruth.load(os.path.join(ROOT, "ground_truth.json"))
        stats = evaluate.score(evaluate.compare(self.result, truth))
        self.assertEqual(stats["confident_and_wrong"], 0)

    def test_calibration_refuses_when_the_sample_cannot_calibrate(self):
        """A sweep with no confident-wrong answers anywhere has proven nothing.

        Recommending 0.00 from it would be arithmetically right and practically
        dangerous, so recommend_threshold returns None and says why.
        """
        truth = evaluate.GroundTruth.load(os.path.join(ROOT, "ground_truth.json"))
        rows = evaluate.calibrate(self.kb, self.documents, truth,
                                  thresholds=[0.0, 0.3, 0.6, 0.9])
        recommended, rationale = evaluate.recommend_threshold(rows)
        self.assertIsNone(recommended)
        self.assertIn("cannot calibrate", rationale)


class TestKnowledgeBaseIsTheSourceOfTruth(SharedRun):
    def test_advice_records_are_found_by_role_not_by_id(self):
        """CAR must already be treated as an advice record, before DBFO lands."""
        self.assertIn("car", self.kb.advice_record_ids)
        self.assertIn("soa", self.kb.advice_record_ids)
        self.assertTrue(self.kb.is_advice_record("car"))

    def test_a_new_advice_record_type_needs_no_code_change(self):
        """Rename the statutory label and the pipeline should follow it."""
        import copy
        data = copy.deepcopy(self.kb.data)
        for doc in data["documents"]:
            if doc["id"] == "car":
                doc["classifier_hints"]["title_patterns"] = ["Client Advice Record"]
        trial = KnowledgeBase(data, path=self.kb.path)
        document = extract.ExtractedDocument(
            "car.pdf",
            "CLIENT ADVICE RECORD\nClient: Mei Tran.\n"
            "Scope of advice: superannuation. The advice and the reasons for it. "
            "Cost of advice and benefits to the provider are set out. "
            "Date of advice: 1 July 2026.")
        result = pipeline.run(trial, [document])
        record = result.records[0]
        self.assertEqual(record.doc_type, "car")
        self.assertEqual(len(result.grouping.events), 1)
        self.assertEqual(result.grouping.events[0].record_type, "car")

    def test_unknown_flag_ids_are_rejected(self):
        from advicefiler.model import Flag
        from advicefiler.kb import KnowledgeBaseError
        with self.assertRaises(KnowledgeBaseError):
            Flag.from_rule(self.kb, "invented_in_code", "nope")


if __name__ == "__main__":
    unittest.main(verbosity=2)
