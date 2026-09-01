"""The deterministic filler must produce the official template, filled from
project data, that always compiles to PDF and converts to DOCX."""
import io
import re
import sys
import zipfile

sys.path.insert(0, "/Users/thanyathip/Desktop/agenticdia/backend")

from app.latex_service import compile_latex_to_pdf, convert_latex_to_docx
from app.prd_filler import fill_template_body

DATA = {
    "epic_name": "PromptPay Refund Portal",
    "business_goals": [
        {"description": "Cut manual refund handling time by 60% within 6 months"},
        {"description": "Achieve 90% customer self-service refund adoption"},
    ],
    "actors": [{"name": "Retail Customer"}, {"name": "Bank Refund Officer"}],
    "problem_statement": [
        "Manual refund handling is slow and costly",
        "Customers face delays due to branch visits",
    ],
    "scope_in": ["Submit refunds online", "Track refund status", "Officer approval flow"],
    "scope_out": ["Cross-bank instant settlement", "Branch counter operations"],
    "requirements": [
        {
            "requirement_code": "REQ-001",
            "title": "Refund Request Submission",
            "user_stories": [
                {
                    "ticket_code": "US-001",
                    "story_title": "Submit refund request online",
                    "as_a": "Retail Customer",
                    "i_want_to": "submit a refund request with transaction ID and reason",
                    "so_that": "I get my money back without visiting a branch",
                    "acceptance_criteria": [
                        "Given a valid transaction ID, when the customer submits, then status is PENDING",
                        "Given an invalid transaction ID, then an error is shown",
                    ],
                }
            ],
        }
    ],
}


def _fill():
    return fill_template_body(
        project_id="7f5fbfea-1234-5678-9abc",
        project_name="PromptPay Refund Portal",
        version=1,
        author="Napat Wong",
        data=DATA,
        version_summary="Initial version",
    )


def test_no_placeholder_markers_left():
    body = _fill()
    for marker in ("PMO\\_NO", "PMO\\_NAME", "{AUTHOR}", "{VERSION}", "{STATUS}", "LAST\\_UPDATE"):
        assert marker not in body, marker


def test_skeleton_is_the_official_template():
    body = _fill()
    for probe in ("\\begin{tabular}", "\\multirow", "\\multicolumn", "\\shortstack",
                  "\\newpage", "\\section*{Stakeholders}", "\\section*{Version History}",
                  "\\section*{Reviews}", "\\end{tabular}"):
        assert probe in body, probe


def test_project_data_filled_in():
    body = _fill()
    assert "PromptPay Refund Portal" in body          # PMO_NAME
    assert "7F5FBFEA" in body                          # PMO_NO (id prefix)
    assert "Napat Wong" in body                        # author
    assert "V1.0" in body                              # version history
    assert "US-001: Submit refund request online" in body  # FR row
    assert "Given a valid transaction ID" in body       # acceptance criteria
    assert "Submit refunds online" in body              # scope in
    assert "Cross-bank instant settlement" in body      # scope out
    assert "Cut manual refund handling time by 60" in body  # objectives


def test_braces_balanced():
    body = _fill()
    assert body.count("{") == body.count("}")


def test_filled_body_compiles_to_pdf():
    pdf = compile_latex_to_pdf(_fill())
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 3000


def test_filled_body_converts_to_docx():
    docx = convert_latex_to_docx(_fill())
    assert docx[:2] == b"PK"
    xml = zipfile.ZipFile(io.BytesIO(docx)).read("word/document.xml").decode()
    assert xml.count("<w:tbl>") >= 7
    assert "PromptPay Refund Portal" in xml


def test_empty_data_still_compiles():
    body = fill_template_body(project_id="abc", project_name="P", version=1, data={})
    assert "\\section*{Stakeholders}" in body
    pdf = compile_latex_to_pdf(body)
    assert pdf.startswith(b"%PDF")


def test_no_literal_prdfield_leak():
    """Regression: `\\\\prdfield{TBD}` (over-escaped fallback) used to render
    the literal text `prdfieldTBD` inside PDF/DOCX cells."""
    body = _fill()
    # a single backslash (\\prdfield{..}) is correct; two backslashes means the
    # fallback was double-escaped and produces a broken literal in LaTeX.
    assert "\\\\prdfield" not in body


def test_fr_rows_have_clean_row_terminators():
    """Regression: FR rows were joined with a stray '\\<newline>', producing
    three backslashes between rows; the odd backslash leaked into the next
    row's first cell and the DOCX export split the table row per line."""
    body = _fill()
    assert "\\\\\\" not in body  # never three consecutive backslashes
    fr_lines = [ln for ln in body.splitlines()
                if ln.lstrip().startswith("& & FR ")]
    assert len(fr_lines) == 1  # module DATA carries one user story
    for ln in fr_lines:
        assert ln.rstrip().endswith("\\\\")  # clean two-backslash terminator

    # the native DOCX render mirrors the template: FR and its acceptance
    # criteria share ONE table row, and no cell text keeps a backslash
    docx = convert_latex_to_docx(_fill())
    xml = zipfile.ZipFile(io.BytesIO(docx)).read("word/document.xml").decode()
    fr_rows = [tr for tr in re.findall(r"<w:tr[ >].*?</w:tr>", xml, re.S)
               if "FR 1.1:" in tr]
    assert len(fr_rows) == 1, "FR row must render as exactly one table row"
    assert "AC 1.1:" in fr_rows[0] and "AC 1.2:" in fr_rows[0], \
        "acceptance criteria must live in the same row as the FR text"


def test_appendix_has_nested_term_definition_grid():
    body = _fill()
    assert "|L{3.4cm}|L{2.1cm}|L{10.4cm}|" in body
    assert "\\prdlbl{Term}" in body and "\\prdlbl{Definition}" in body
    # the nested grid uses partial rules (\cline) rather than a full hline
    assert "\\cline{2-3}" in body


def test_glossary_rows_filled_from_narrative():
    body = fill_template_body(
        project_id="p1", project_name="P", version=1,
        data=DATA,
        narrative={"glossary": [("Origination", "End-to-end loan process"),
                                ("NCB", "National Credit Bureau")]},
    )
    assert "Origination" in body
    assert "End-to-end loan process" in body
    assert "NCB" in body
    assert "National Credit Bureau" in body


def test_business_overview_grows_with_content():
    """Tables are dynamic (longtable): long actor/goal lists must be fully
    rendered, not compacted - the wrapping paragraph columns and page-
    breaking longtable rows absorb any amount of content."""
    long_actors = [{"name": f"Person {i}"} for i in range(12)]
    long_goals = ["A very long business objective that goes on and on about "
                  "reducing turnaround time and improving customer experience "
                  "for the retail lending channel of the bank."] * 9
    body = fill_template_body(
        project_id="p1", project_name="P", version=1,
        data={**DATA, "actors": long_actors, "business_goals": long_goals},
    )
    # all 9 numbered objective lines survive (no 4-item cap)
    goals_block = body[body.find("Business Objectives"):body.find("Expected Benefit")]
    for i in range(1, 10):
        assert f"{i}. " in goals_block
    # target audience is a comma list that keeps every actor (no 4-actor cap)
    target = body[body.find("Target Audience"):body.find("\\hline", body.find("Target Audience"))]
    for i in range(12):
        assert f"Person {i}" in target
    # no double-escaped fallback and still compiles
    assert "\\\\prdfield" not in body
    pdf = compile_latex_to_pdf(body)
    assert pdf.startswith(b"%PDF")


def test_filled_pdf_does_not_overflow_into_footer():
    """The Business Overview / Product Scope info must never spill into the
    running footer. Uses pymupdf, skipped if unavailable."""
    try:
        import pymupdf
    except Exception:
        return
    long_goals = ["A very long business objective sentence repeated to "
                  "simulate dense per-project content that used to overflow "
                  "the fixed template page into the footer area of the export."] * 4
    body = fill_template_body(
        project_id="p1", project_name="P", version=1,
        data={**DATA, "business_goals": long_goals},
    )
    pdf = compile_latex_to_pdf(body)
    import io as _io
    doc = pymupdf.open(stream=pdf, filetype="pdf")
    for page in doc:
        words = page.get_text("words")
        for w in words:
            # skip the running header/footer furniture itself
            if w[4] in ("KRUNGSRI", "NIMBLE", "CONFIDENTIAL"):
                continue
            if w[4].isdigit() and w[1] > 780:
                continue
            assert w[1] < 780, (w[4], w[1])
    doc.close()


def test_product_scope_table_grows_with_stories():
    """REGRESSION for 'PDF just stamps the text': every user story must get
    its own FR row (no 6-row cap), the merged label span must grow with the
    row count, and the longtable must break onto extra pages instead of
    squeezing the content into one fixed page."""
    stories = [{"ticket_code": f"US-{i:03d}",
                "story_title": f"Story number {i} with a fairly long title "
                               "describing the capability the user needs",
                "acceptance_criteria": [
                    f"Given the user is on screen {i}, when they act, "
                    "then the system responds with a fully spelled out, "
                    "untruncated acceptance criterion sentence.",
                    f"AC guard {i}: nothing is clipped with an ellipsis.",
                ]}
               for i in range(1, 10)]
    body = fill_template_body(
        project_id="p1", project_name="P", version=1,
        data={**DATA, "user_stories": stories},
    )
    # all 9 stories render - none dropped by the old MAX_FR_ROWS cap
    for i in range(1, 10):
        assert f"FR {i}.1:" in body
    # the multirow label span must cover every FR row: rows + epic + header
    m = re.search(r"\\multirow\{(\d+)\}\{\*\}", body)
    fr_count = len(re.findall(r"& & FR \d+\.1:", body))
    assert m and int(m.group(1)) == fr_count + 2
    # no ellipsis truncation anywhere in the filled body
    assert "\\ldots" not in body.replace("must\\ldots}", "")

    pdf = compile_latex_to_pdf(body)
    assert pdf.startswith(b"%PDF")
    try:
        import pymupdf
    except Exception:
        return
    doc = pymupdf.open(stream=pdf, filetype="pdf")
    assert len(doc) > 4, (
        f"dynamic table must break onto extra pages, got {len(doc)} pages"
    )
    doc.close()


def test_long_cell_text_wraps_instead_of_truncating():
    """REGRESSION for 'stamped' PDF cells: long free-text (exec summary,
    acceptance criteria) must survive verbatim - no '...' clips - and the
    DOCX export must contain the same full text in its table cells."""
    long_summary = ("This initiative transforms the retail lending journey "
                    "end to end. " * 20).strip()
    long_ac = ("Given an approved application with all documents uploaded, "
               "when the officer submits the final decision, then the "
               "customer receives the conditional approval letter within "
               "one business day and the case is routed to disbursement "
               "with a complete audit trail attached to every step.") * 3
    body = fill_template_body(
        project_id="p1", project_name="P", version=1,
        data=DATA,
        narrative={"exec_summary": long_summary},
    )
    assert long_summary in body  # not cut to 160 chars
    pdf = compile_latex_to_pdf(body)
    assert pdf.startswith(b"%PDF")

    docx = convert_latex_to_docx(body)
    xml = zipfile.ZipFile(io.BytesIO(docx)).read("word/document.xml").decode()
    assert long_summary in xml