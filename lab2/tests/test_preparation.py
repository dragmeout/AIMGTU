import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/"scripts"))
import prepare_data as kb


class PreparationTests(unittest.TestCase):
    def test_external_redirect_and_subdomain_trick_rejected(self):
        for url in ["https://magtu.ru.evil.example/a", "http://career.magtu.ru/a", "https://support.google.com/a", "https://u:p@career.magtu.ru/a"]:
            with self.assertRaises(ValueError):
                kb.check_url(url, ["career.magtu.ru", "magtu.ru"])

    def test_data_path_cannot_escape(self):
        with self.assertRaises(ValueError):
            kb.safe_path("../secret.txt")

    def test_list_table_links_and_garbage(self):
        html = '''<body><nav>menu noise</nav><article id="main"><h1>Тест</h1><h2>Услуга</h2>
          <p>Проверка&nbsp;текста <a href="/help">Инструкция</a></p><script>evil()</script>
          <ul><li>Первый шаг</li><li>Второй шаг</li></ul>
          <table><tr><th>Услуга</th><th>Адрес</th></tr><tr><td>Справка</td><td>248</td></tr></table>
          <form><input value="secret">Ф.И.О.</form></article></body>'''
        src={"document_title":"Тест","source":"https://career.magtu.ru/test/","content_selector":"#main"}
        blocks = kb.html_blocks(html.encode(), src)
        text = "\n".join(b["text"] for b in blocks)
        self.assertIn("- Первый шаг\n- Второй шаг", text)
        self.assertIn("| Справка | 248 |", text)
        self.assertIn("https://career.magtu.ru/help", text)
        for bad in ("menu noise", "evil()", "secret", "Ф.И.О."):
            self.assertNotIn(bad,text)

    def test_complex_table_requires_review(self):
        src={"document_title":"T","source":"https://career.magtu.ru/","content_selector":"article"}
        html=b'<article><table><tr><td colspan="2">Merged</td></tr></table></article>'
        with self.assertRaises(ValueError):
            kb.html_blocks(html,src)

    def test_windows_do_not_lose_last_word(self):
        text = " ".join(f"слово{i}" for i in range(361))
        ranges = list(kb.window_ranges(text))
        self.assertTrue(text[ranges[-1][0]:ranges[-1][1]].endswith("слово360"))
        covered = {x for a,b in ranges for x in text[a:b].split()}
        self.assertEqual(covered,set(text.split()))

    def test_pdf_pages_and_handwritten_date(self):
        docs = kb.jsonl_read(kb.DATA/"documents/clean_documents.jsonl")
        d = next(x for x in docs if x["document_id"]=="practice-regulation-vo-2024")
        b = next(x for x in d["blocks"] if x["section_path"][-1]=="6.4.")
        self.assertEqual(b["pages"],[13])
        self.assertIn("- титульный лист;",b["text"])
        self.assertIn("- приложения.",b["text"])
        self.assertEqual(d["date"],"2024-03-13")
        self.assertIn("visual_check",d["date_basis"])
        self.assertNotIn("Всего листов",d["text"])
        self.assertNotIn("результа ты",d["text"])

    def test_scan_and_failed_domains_not_indexed(self):
        ids={d["document_id"] for d in kb.jsonl_read(kb.DATA/"documents/clean_documents.jsonl")}
        self.assertNotIn("practice-framework-scan-2020",ids)
        self.assertNotIn("scholarships",ids)
        self.assertNotIn("learning-portal",ids)

    def test_undated_html_is_not_download_date(self):
        for d in kb.jsonl_read(kb.DATA/"documents/clean_documents.jsonl"):
            if d["document_type"] != "local_regulation":
                self.assertIsNone(d["date"])
                self.assertIn("2026-10-04",d["fetched_at"])

    def test_metadata_and_full_coverage(self):
        self.assertTrue(kb.validate()["passed"])

    def test_repeated_offline_build_has_same_chunks(self):
        names=[kb.DATA/f"chunks/{m}.jsonl" for m in ("fixed","semantic","final")]
        before=[p.read_bytes() for p in names]
        kb.build()
        self.assertEqual(before,[p.read_bytes() for p in names])

    def test_final_lists_preserve_point_context(self):
        chunks=kb.jsonl_read(kb.DATA/"chunks/final.jsonl")
        matches=[c for c in chunks if "6.4. В общем виде" in c["text"] and "- приложения." in c["text"]]
        self.assertTrue(matches)
        self.assertTrue(any(13 in c["pages"] for c in matches))

    def test_evidence_exists_for_all_answerable_cases(self):
        docs={d["document_id"]:d for d in kb.jsonl_read(kb.DATA/"documents/clean_documents.jsonl")}
        for q in kb.jsonl_read(kb.DATA/"evaluation/questions.jsonl"):
            if q["expected_decision"]=="answer":
                self.assertTrue(all(kb.comparable(x) in kb.comparable(docs[q["document_id"]]["text"]) for x in q["evidence"]),q["question_id"])


if __name__ == "__main__":
    unittest.main()
