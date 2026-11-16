"""
Unit and integration tests for Milestone 2: NLP-Based Semantic Analysis.

Covers:
- Text preprocessing, normalization, and safety
- Semantic similarity, cosine math, threshold categorization, and caching with instance identity
- Method identification: exact_match, sentence_transformer, token_jaccard_fallback
- Keyword & noun-phrase extraction (with stopwords filtering and first-seen fallback)
- Named Entity Recognition (NER), blank spaCy fallback, and trained pipeline preservation
- Human-readable explanation generation
- Complete NLP pipeline integration across changes
- No-modifications handling (average_semantic_similarity is None, avoids loading ST model)
- Non-breaking attachment to adapt_engine_result (preserving Phase 1 summaries)
- Real comparison adapter integration using existing Phase 1 sample fixtures
- ModelManager lazy singleton, dependency injection, and failure caching
"""

import math
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock

import pytest

# Ensure comparison-engine root and src are in sys.path
COMPARISON_ENGINE_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = COMPARISON_ENGINE_DIR / "src"
REPO_ROOT = COMPARISON_ENGINE_DIR.parent
TEST_FILES_DIR = REPO_ROOT / "test-files"

for directory in (str(COMPARISON_ENGINE_DIR), str(SRC_DIR)):
    if directory not in sys.path:
        sys.path.insert(0, directory)

from api import _run_existing_engine
from result_adapter import adapt_engine_result
from src.nlp.keyword_extraction import (
    DEFAULT_STOP_WORDS,
    compare_keywords,
    extract_keywords,
    extract_keywords_fallback,
)
from src.nlp.model_loader import ModelManager, get_model_manager
from src.nlp.ner import (
    compare_named_entities,
    extract_entities_fallback,
    extract_named_entities,
    has_ner_component,
)
from src.nlp.pipeline import (
    analyze_text_addition,
    analyze_text_modification,
    analyze_text_removal,
    attach_nlp_analysis,
    generate_change_explanation,
    run_nlp_pipeline,
)
from src.nlp.preprocessing import (
    clean_html_text,
    is_empty_or_whitespace,
    normalize_text,
    normalize_whitespace,
)
from src.nlp.semantic_similarity import (
    _EMBEDDING_CACHE,
    SimilarityResult,
    categorize_similarity,
    clear_embedding_cache,
    compute_fallback_similarity,
    compute_semantic_similarity,
    compute_token_similarity_fallback,
    cosine_similarity,
)

V1_FILE = TEST_FILES_DIR / "mini project version 1.html"
V2_FILE = TEST_FILES_DIR / "mini project version 2.html"


# ============================================================================
# 1. Text Preprocessing Tests
# ============================================================================


class TestPreprocessing:
    def test_clean_html_text_basic_whitespace(self):
        raw = "  Hello   world \t from \n  webpage!  "
        assert clean_html_text(raw) == "Hello world from webpage!"

    def test_clean_html_text_unescapes_entities(self):
        raw = "Terms &amp; Conditions &gt; Privacy &quot;Notice&quot; &#39;2024&#39;"
        assert clean_html_text(raw) == "Terms & Conditions > Privacy \"Notice\" '2024'"

    def test_clean_html_text_removes_residual_tags(self):
        raw = "<p>Welcome to <strong>College</strong> portal</p><span>v2.0</span>"
        assert clean_html_text(raw) == "Welcome to College portal v2.0"

    def test_clean_html_text_unicode_normalization(self):
        # Non-breaking space \xa0 and zero-width space \u200b
        raw = "Exam\xa0Schedule\u200b2024"
        assert clean_html_text(raw) == "Exam Schedule 2024"

    def test_clean_html_text_strips_control_characters(self):
        raw = "Valid text\x00\x08with\x1fhidden\x0bcontrol chars"
        assert clean_html_text(raw) == "Valid text with hidden control chars"

    def test_clean_html_text_preserves_punctuation_and_casing(self):
        raw = "Alert: Application deadline is March 15th, 2024! Please submit $50 fee."
        assert clean_html_text(raw) == "Alert: Application deadline is March 15th, 2024! Please submit $50 fee."

    def test_clean_html_text_empty_and_none(self):
        assert clean_html_text(None) == ""
        assert clean_html_text("") == ""
        assert clean_html_text("   \t  \n  ") == ""
        assert clean_html_text(123) == "123"

    def test_is_empty_or_whitespace(self):
        assert is_empty_or_whitespace(None) is True
        assert is_empty_or_whitespace("") is True
        assert is_empty_or_whitespace("   \t\n") is True
        assert is_empty_or_whitespace("content") is False
        assert is_empty_or_whitespace(123) is True

    def test_normalize_whitespace_and_normalize_text(self):
        assert normalize_whitespace("   a   b   c   ") == "a b c"
        assert normalize_text("<p>Hello &amp; World</p>") == "Hello & World"


# ============================================================================
# 2. Semantic Similarity, Cosine Math, and Method Identification Tests
# ============================================================================


class TestSemanticSimilarity:
    def setup_method(self):
        clear_embedding_cache()

    def test_cosine_similarity_identical_vectors(self):
        v = [1.0, 2.0, 3.0]
        assert pytest.approx(cosine_similarity(v, v), rel=1e-5) == 1.0

    def test_cosine_similarity_orthogonal_vectors(self):
        v1 = [1.0, 0.0]
        v2 = [0.0, 1.0]
        assert pytest.approx(cosine_similarity(v1, v2), abs=1e-5) == 0.0

    def test_cosine_similarity_opposite_vectors(self):
        v1 = [1.0, 0.0]
        v2 = [-1.0, 0.0]
        assert pytest.approx(cosine_similarity(v1, v2), abs=1e-5) == -1.0

    def test_cosine_similarity_zero_vectors(self):
        assert cosine_similarity([0.0, 0.0], [1.0, 2.0]) == 0.0
        assert cosine_similarity([], []) == 0.0
        assert cosine_similarity([1.0], [1.0, 2.0]) == 0.0

    def test_categorize_similarity_thresholds(self):
        assert categorize_similarity(1.0) == "identical"
        assert categorize_similarity(0.9995) == "identical"
        assert categorize_similarity(0.85) == "high"
        assert categorize_similarity(0.80) == "high"
        assert categorize_similarity(0.65) == "moderate"
        assert categorize_similarity(0.50) == "moderate"
        assert categorize_similarity(0.35) == "low"
        assert categorize_similarity(0.25) == "low"
        assert categorize_similarity(0.15) == "substantially_different"
        assert categorize_similarity(0.0) == "substantially_different"

    def test_compute_semantic_similarity_identical_texts_exact_match(self):
        text = "The college will conduct examinations in March."
        res = compute_semantic_similarity(text, text)
        assert res.score == 1.0
        assert res.category == "identical"
        assert res.method == "exact_match"
        # Verify tuple unpacking compatibility
        score, category, method = res
        assert score == 1.0
        assert category == "identical"
        assert method == "exact_match"

    def test_compute_semantic_similarity_empty_cases(self):
        res1 = compute_semantic_similarity("", "")
        assert res1.score == 1.0
        assert res1.category == "identical"
        assert res1.method == "exact_match"

        res2 = compute_semantic_similarity("Sample text", "")
        assert res2.score == 0.0
        assert res2.category == "substantially_different"
        assert res2.method == "token_jaccard_fallback"

        res3 = compute_semantic_similarity("", "Sample text")
        assert res3.score == 0.0
        assert res3.category == "substantially_different"
        assert res3.method == "token_jaccard_fallback"

        res4 = compute_semantic_similarity(None, "Sample text")
        assert res4.score == 0.0
        assert res4.category == "substantially_different"
        assert res4.method == "token_jaccard_fallback"

    def test_fallback_token_similarity(self):
        t1 = "the college examinations in march"
        t2 = "the college examinations in april"
        sim = compute_fallback_similarity(t1, t2)
        assert pytest.approx(sim, abs=0.01) == 4 / 6
        assert compute_token_similarity_fallback(t1, t2) == sim

    def test_compute_semantic_similarity_with_mock_model_identifies_method(self):
        mock_model = MagicMock()
        mock_model.encode.side_effect = lambda t: [1.0, 0.0] if "March" in t else [0.0, 1.0]

        res = compute_semantic_similarity(
            "March exams",
            "April exams",
            model=mock_model,
        )
        assert res.score == 0.0
        assert res.category == "substantially_different"
        assert res.method == "sentence_transformer"

    def test_compute_semantic_similarity_model_exception_falls_back_with_method(self):
        mock_model = MagicMock()
        mock_model.encode.side_effect = RuntimeError("GPU out of memory")

        res = compute_semantic_similarity(
            "college examinations",
            "college examinations updated",
            model=mock_model,
        )
        # Should gracefully fall back to token similarity and record method
        assert res.score > 0.0
        assert res.category in ["moderate", "high", "low"]
        assert res.method == "token_jaccard_fallback"

    def test_embedding_cache_instance_identity(self):
        """Verify that cache distinguishes model instance identity in addition to model_name and text."""
        clear_embedding_cache()

        model1 = MagicMock()
        model1.encode.return_value = [1.0, 0.0]

        model2 = MagicMock()
        model2.encode.return_value = [0.0, 1.0]

        text = "Hello world"
        model_name = "test-model"

        # 1. First encoding on model1
        compute_semantic_similarity(text, "Other text", model=model1, model_name=model_name)
        assert model1.encode.call_count == 2

        # 2. Re-encoding same text on the same model1 instance hits cache
        compute_semantic_similarity(text, "Other text", model=model1, model_name=model_name)
        assert model1.encode.call_count == 2  # No new encode calls

        # 3. Encoding on model2 with identical model_name and text must NOT hit model1's cache
        compute_semantic_similarity(text, "Other text", model=model2, model_name=model_name)
        assert model2.encode.call_count == 2  # model2 had to encode its own embeddings

        # 4. Cache clearing works
        clear_embedding_cache()
        assert len(_EMBEDDING_CACHE) == 0

        # After clearing, model1 encodes again
        compute_semantic_similarity(text, "Other text", model=model1, model_name=model_name)
        assert model1.encode.call_count == 4


# ============================================================================
# 3. Keyword Extraction Tests
# ============================================================================


class TestKeywordExtraction:
    def test_extract_keywords_filters_stopwords(self):
        text = "The examination is scheduled for the students at the university."
        keywords = extract_keywords(text)
        lowered = [k.lower() for k in keywords]
        assert "examination" in lowered or any("examination" in k for k in lowered)
        assert "the" not in lowered
        assert "is" not in lowered
        assert "at" not in lowered

    def test_compare_keywords_college_announcement(self):
        old_text = "The college will conduct examinations in March."
        new_text = "The college has postponed examinations until April."

        diff = compare_keywords(old_text, new_text)
        added_lower = [k.lower() for k in diff["added"]]
        removed_lower = [k.lower() for k in diff["removed"]]
        shared_lower = [k.lower() for k in diff["shared"]]

        assert "postponed" in added_lower
        assert "april" in added_lower
        assert "conduct" in removed_lower
        assert "march" in removed_lower
        assert "college" in shared_lower or "examinations" in shared_lower

    def test_fallback_extract_keywords(self):
        text = "Important update: Admissions will close on Friday."
        kw = extract_keywords_fallback(text, max_keywords=5)
        kw_lower = [k.lower() for k in kw]
        assert "admissions" in kw_lower
        assert "friday" in kw_lower
        assert "important" in kw_lower
        assert "will" not in kw_lower

    def test_extract_keywords_empty_input(self):
        assert extract_keywords("") == []
        assert extract_keywords(None) == []
        assert extract_keywords("   ") == []


# ============================================================================
# 4. Named Entity Recognition (NER) & Component Detection Tests
# ============================================================================


class TestNamedEntityRecognition:
    def test_has_ner_component_detection(self):
        assert has_ner_component(None) is False

        model_without_ner = MagicMock()
        model_without_ner.pipe_names = ["sentencizer", "tok2vec"]
        model_without_ner.has_pipe.side_effect = lambda p: p == "sentencizer"
        assert has_ner_component(model_without_ner) is False

        model_with_ner = MagicMock()
        model_with_ner.pipe_names = ["tok2vec", "ner"]
        model_with_ner.has_pipe.side_effect = lambda p: p in ["tok2vec", "ner"]
        assert has_ner_component(model_with_ner) is True

    def test_blank_spacy_pipeline_triggers_regex_fallback(self):
        """A blank spaCy pipeline has no trained NER pipe; it must trigger regex fallback."""
        blank_model = MagicMock()
        blank_model.pipe_names = ["sentencizer"]
        blank_model.has_pipe.return_value = False

        text = "Payment of $150.00 is due by March 15th, 2024."
        entities = extract_named_entities(text, nlp_model=blank_model)

        labels = {e["label"] for e in entities}
        assert "DATE" in labels
        assert "MONEY" in labels
        texts = [e["text"] for e in entities]
        assert any("March" in t or "2024" in t for t in texts)
        assert any("$150" in t for t in texts)

    def test_trained_ner_pipeline_returns_model_entities(self):
        """A trained NER pipeline returns its entities directly."""
        mock_ent = MagicMock()
        mock_ent.text = "Acme Corp"
        mock_ent.label_ = "ORG"

        mock_doc = MagicMock()
        mock_doc.ents = [mock_ent]

        trained_model = MagicMock()
        trained_model.pipe_names = ["ner"]
        trained_model.has_pipe.side_effect = lambda p: p == "ner"
        trained_model.return_value = mock_doc

        entities = extract_named_entities("Acme Corp announced profits.", nlp_model=trained_model)
        assert entities == [{"text": "Acme Corp", "label": "ORG"}]

    def test_valid_ner_model_empty_entities_not_replaced_by_regex(self):
        """If a trained NER model runs and finds 0 entities, return [] without regex overwrite."""
        mock_doc = MagicMock()
        mock_doc.ents = []  # Model found nothing

        trained_model = MagicMock()
        trained_model.pipe_names = ["ner"]
        trained_model.has_pipe.side_effect = lambda p: p == "ner"
        trained_model.return_value = mock_doc

        # Text contains words that regex fallback WOULD match ("March"), but trained model found none
        entities = extract_named_entities("Exams will be held in March.", nlp_model=trained_model)
        assert entities == []

    def test_compare_named_entities_dates(self):
        old_text = "The college will conduct examinations in March."
        new_text = "The college has postponed examinations until April."

        diff = compare_named_entities(old_text, new_text)

        added_texts = [e["text"] for e in diff["added"]]
        removed_texts = [e["text"] for e in diff["removed"]]

        assert "April" in added_texts
        assert "March" in removed_texts
        assert "DATE" in diff["by_label"]
        assert "April" in diff["by_label"]["DATE"]["added"]
        assert "March" in diff["by_label"]["DATE"]["removed"]

    def test_extract_named_entities_regex_fallback(self):
        text = "Payment of $150.00 is due by March 15th, 2024. Contact admin@college.edu"
        entities = extract_entities_fallback(text)

        labels = {e["label"] for e in entities}
        texts = [e["text"] for e in entities]

        assert "DATE" in labels
        assert "MONEY" in labels
        assert any("$150" in t for t in texts)
        assert any("March" in t or "2024" in t for t in texts)

    def test_extract_named_entities_empty_input(self):
        assert extract_named_entities("") == []
        assert extract_named_entities(None) == []


# ============================================================================
# 5. Human-Readable Explanation Tests
# ============================================================================


class TestExplanationGeneration:
    def test_identical_text_explanation(self):
        expl = generate_change_explanation(
            "Sample text",
            "Sample text",
            "identical",
            [],
            [],
            [],
            [],
        )
        assert "semantically identical" in expl.lower()

    def test_date_update_explanation(self):
        expl = generate_change_explanation(
            "Exams in March",
            "Exams in April",
            "moderate",
            ["postponed", "April"],
            ["conduct", "March"],
            [{"text": "April", "label": "DATE"}],
            [{"text": "March", "label": "DATE"}],
        )
        assert "Date updated from 'March' to 'April'" in expl
        assert "postponed" in expl
        assert "conduct" in expl

    def test_monetary_update_explanation(self):
        expl = generate_change_explanation(
            "Fee is $50",
            "Fee is $75",
            "high",
            ["$75"],
            ["$50"],
            [{"text": "$75", "label": "MONEY"}],
            [{"text": "$50", "label": "MONEY"}],
        )
        assert "Monetary value updated" in expl


# ============================================================================
# 6. Pipeline Integration & Metric Handling Tests
# ============================================================================


class TestNLPPipeline:
    def test_analyze_text_modification_structure_includes_method(self):
        res = analyze_text_modification(
            "The college will conduct examinations in March.",
            "The college has postponed examinations until April.",
        )
        assert "original_text" in res
        assert "updated_text" in res
        assert "similarity_score" in res
        assert "similarity_category" in res
        assert "similarity_method" in res
        assert res["similarity_method"] in {"sentence_transformer", "token_jaccard_fallback", "exact_match"}
        assert "added_keywords" in res
        assert "removed_keywords" in res
        assert "added_entities" in res
        assert "removed_entities" in res
        assert "explanation" in res

    def test_analyze_text_addition_and_removal(self):
        add_res = analyze_text_addition("New exam guidelines published on Monday.")
        assert add_res["text"] == "New exam guidelines published on Monday."
        assert len(add_res["keywords"]) > 0

        rem_res = analyze_text_removal("Old policy deleted.")
        assert rem_res["text"] == "Old policy deleted."
        assert len(rem_res["keywords"]) > 0

    def test_run_nlp_pipeline_empty_changes(self):
        pipeline_res = run_nlp_pipeline([])
        assert pipeline_res["overall"]["total_modifications_analyzed"] == 0
        assert pipeline_res["overall"]["total_additions_analyzed"] == 0
        assert pipeline_res["overall"]["total_removals_analyzed"] == 0
        assert pipeline_res["overall"]["average_semantic_similarity"] is None
        assert pipeline_res["modifications"] == []
        assert pipeline_res["additions"] == []
        assert pipeline_res["removals"] == []
        assert "No text content changes detected." in pipeline_res["overall"]["summary"]

    def test_run_nlp_pipeline_no_modifications_reports_none_avg_similarity(self):
        """When there are no text modifications, average similarity must be None, not 1.0."""
        changes = [
            {
                "id": 1,
                "category": "added",
                "newValue": "New announcement posted.",
            },
            {
                "id": 2,
                "category": "removed",
                "oldValue": "Old announcement deleted.",
            },
        ]
        res = run_nlp_pipeline(changes)
        overall = res["overall"]

        assert overall["total_modifications_analyzed"] == 0
        assert overall["total_additions_analyzed"] == 1
        assert overall["total_removals_analyzed"] == 1
        assert overall["average_semantic_similarity"] is None
        assert "No text modifications were present to assess semantic similarity." in overall["summary"]

    def test_run_nlp_pipeline_avoids_loading_sentence_transformer_without_modifications(self):
        """Sentence Transformer model must NOT be loaded when changes have zero text modifications."""
        mgr = get_model_manager()
        mock_get_st = MagicMock()

        changes = [
            {"id": 1, "category": "added", "newValue": "Section text"},
        ]

        # Use mock sentence transformer to ensure it is never touched
        dummy_st = MagicMock()
        res = run_nlp_pipeline(changes, sentence_model=dummy_st)
        assert dummy_st.encode.call_count == 0

    def test_run_nlp_pipeline_mixed_changes(self):
        changes = [
            {
                "id": "c1",
                "category": "modified",
                "element": "p",
                "oldValue": "The college will conduct examinations in March.",
                "newValue": "The college has postponed examinations until April.",
                "sourcePath": "/html/body/p[1]",
                "targetPath": "/html/body/p[1]",
            },
            {
                "id": "c2",
                "category": "added",
                "element": "div",
                "newValue": "Late registrations close next Friday.",
                "sourcePath": "",
                "targetPath": "/html/body/div[2]",
            },
            {
                "id": "c3",
                "category": "removed",
                "element": "span",
                "oldValue": "Previous rules no longer apply.",
                "sourcePath": "/html/body/span[1]",
                "targetPath": "",
            },
        ]

        res = run_nlp_pipeline(changes)
        overall = res["overall"]

        assert overall["total_modifications_analyzed"] == 1
        assert overall["total_additions_analyzed"] == 1
        assert overall["total_removals_analyzed"] == 1
        assert overall["average_semantic_similarity"] is not None
        assert 0.0 <= overall["average_semantic_similarity"] <= 1.0
        assert len(overall["top_added_keywords"]) > 0
        assert len(overall["top_removed_keywords"]) > 0
        assert len(res["modifications"]) == 1
        assert len(res["additions"]) == 1
        assert len(res["removals"]) == 1
        assert "similarity_method" in res["modifications"][0]

    def test_attach_nlp_analysis_preserves_phase1_contract(self):
        mock_phase1_result = {
            "version1": {"path": "v1.html", "nodes": 100},
            "version2": {"path": "v2.html", "nodes": 110},
            "engineSummary": {
                "totalAdded": 8,
                "totalRemoved": 1,
                "totalModified": 12,
                "totalUnchanged": 80,
            },
            "presentationSummary": {
                "totalPresentationChanges": 21,
            },
            "changes": [
                {
                    "category": "modified",
                    "element": "h1",
                    "oldValue": "Annual Exam 2023",
                    "newValue": "Annual Exam 2024",
                    "sourcePath": "/html/body/h1",
                    "targetPath": "/html/body/h1",
                    "similarity": 0.85,
                }
            ],
        }

        enriched = attach_nlp_analysis(mock_phase1_result)

        # 1. Structural counts must remain untouched
        assert enriched["engineSummary"]["totalAdded"] == 8
        assert enriched["engineSummary"]["totalRemoved"] == 1
        assert enriched["engineSummary"]["totalModified"] == 12
        assert enriched["presentationSummary"]["totalPresentationChanges"] == 21

        # 2. nlpAnalysis payload attached at top level
        assert "nlpAnalysis" in enriched
        nlp = enriched["nlpAnalysis"]
        assert "overall" in nlp
        assert "modifications" in nlp
        assert len(nlp["modifications"]) == 1

    def test_attach_nlp_analysis_exception_safety(self):
        bad_result = {"changes": None}
        safe_res = attach_nlp_analysis(bad_result)
        assert "nlpAnalysis" in safe_res


# ============================================================================
# 7. Real Comparison Adapter Integration Test
# ============================================================================


class TestRealComparisonAdapterIntegration:
    def test_real_comparison_adapter_integration(self):
        """End-to-end integration test with real Phase 1 fixtures and adapt_engine_result."""
        assert V1_FILE.is_file(), f"Missing {V1_FILE}"
        assert V2_FILE.is_file(), f"Missing {V2_FILE}"

        with TemporaryDirectory(prefix="test-nlp-real-adapter-") as temp_dir:
            raw_changes, tree_v1, tree_v2 = _run_existing_engine(
                version1_path=V1_FILE,
                version2_path=V2_FILE,
                output_dir=Path(temp_dir),
            )
            adapted = adapt_engine_result(
                raw_changes,
                tree_v1,
                tree_v2,
                version1_name=V1_FILE.name,
                version2_name=V2_FILE.name,
            )

            # Baseline Phase 1 facts
            assert adapted["presentationSummary"]["total"] == 21
            assert adapted["presentationSummary"]["added"] == 8
            assert adapted["presentationSummary"]["removed"] == 1
            assert adapted["presentationSummary"]["modified"] == 12
            assert adapted["engineSummary"]["removed"] == 1
            assert adapted["engineSummary"]["modified"] == 12

            # Enrich with NLP layer
            enriched = attach_nlp_analysis(adapted)

            # 1. Verify Phase 1 structural contract is preserved 100%
            assert enriched["presentationSummary"]["total"] == 21
            assert enriched["presentationSummary"]["added"] == 8
            assert enriched["presentationSummary"]["removed"] == 1
            assert enriched["presentationSummary"]["modified"] == 12
            assert enriched["engineSummary"] == adapted["engineSummary"]

            # 2. Verify NLP analysis payload structure
            assert "nlpAnalysis" in enriched
            nlp = enriched["nlpAnalysis"]
            overall = nlp["overall"]

            assert overall["total_modifications_analyzed"] == 12
            assert overall["total_additions_analyzed"] == 8
            assert overall["total_removals_analyzed"] == 1
            assert overall["average_semantic_similarity"] is not None
            assert 0.0 <= overall["average_semantic_similarity"] <= 1.0

            # 3. Verify each modification contains required NLP fields
            assert len(nlp["modifications"]) == 12
            for mod in nlp["modifications"]:
                assert "similarity_score" in mod
                assert "similarity_category" in mod
                assert "similarity_method" in mod
                assert mod["similarity_method"] in {"sentence_transformer", "token_jaccard_fallback", "exact_match"}
                assert "original_text" in mod
                assert "updated_text" in mod
                assert "explanation" in mod
                assert "added_keywords" in mod
                assert "removed_keywords" in mod
                assert "added_entities" in mod
                assert "removed_entities" in mod

            # 4. Verify additions and removals analyzed
            assert len(nlp["additions"]) == 8
            for add_item in nlp["additions"]:
                assert "text" in add_item
                assert "keywords" in add_item
                assert "entities" in add_item

            assert len(nlp["removals"]) == 1
            for rem_item in nlp["removals"]:
                assert "text" in rem_item
                assert "keywords" in rem_item
                assert "entities" in rem_item


# ============================================================================
# 8. ModelManager & Dependency Injection Tests
# ============================================================================


class TestModelManager:
    def test_singleton_instance(self):
        m1 = get_model_manager()
        m2 = get_model_manager()
        assert m1 is m2

    def test_dependency_injection_sentence_transformer(self):
        mgr = ModelManager()
        dummy_model = MagicMock()
        mgr.set_sentence_transformer("custom-model", dummy_model)
        assert mgr.get_sentence_transformer("custom-model") is dummy_model

    def test_dependency_injection_spacy_model(self):
        mgr = ModelManager()
        dummy_spacy = MagicMock()
        mgr.set_spacy_model("custom-spacy", dummy_spacy)
        assert mgr.get_spacy_model("custom-spacy") is dummy_spacy

    def test_failed_model_load_is_cached_and_not_repeated(self):
        """Failed model loads must be cached as None so expensive imports are not repeated."""
        mgr = ModelManager()
        # Attempt to load non-existent sentence transformer model
        res1 = mgr.get_sentence_transformer("non-existent-st-model-xyz", raise_on_error=False)
        assert res1 is None
        assert "non-existent-st-model-xyz" in mgr._st_models
        assert mgr._st_models["non-existent-st-model-xyz"] is None

        # Subsequent call returns None immediately from cache
        res2 = mgr.get_sentence_transformer("non-existent-st-model-xyz", raise_on_error=False)
        assert res2 is None
