"""Local Streamlit interface for the shipping document checker."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import streamlit as st

from src.pipeline import validate_submission
from src.service import (
    ProcessingArtifacts,
    UploadedAttachment,
    comparison_rows,
    dataset_rows,
    process_dataset,
    process_single_email,
    submission_bytes,
    write_artifacts,
)


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_BUNDLE = PROJECT_ROOT.parent / "sdoc-hackathon-bundle"
DEFAULT_OUTPUT = PROJECT_ROOT / "output"

CATEGORY_LABELS = {
    "BL_COMPARISON": "Document Comparison Request",
    "SI_REQUEST": "New SI Request",
    "INVOICE_QUERY": "Invoice Query",
    "GENERAL": "General Message",
    "SPAM": "Spam",
}


st.set_page_config(
    page_title="Shipping Document Verification",
    page_icon="🚢",
    layout="wide",
)

st.markdown(
    """
    <style>
      .block-container {padding-top: 2rem; padding-bottom: 3rem;}
      .app-kicker {color: #2563eb; font-size: .82rem; font-weight: 700; letter-spacing: .12em; text-transform: uppercase;}
      .app-title {font-size: 2.35rem; font-weight: 750; line-height: 1.15; margin: .25rem 0;}
      .app-subtitle {color: #64748b; font-size: 1.05rem; margin-bottom: 1.2rem;}
      .process-flow {background: #f8fafc; border: 1px solid #e2e8f0; border-radius: .8rem; padding: .85rem 1rem; color: #334155; margin-bottom: 1.25rem;}
      .result-note {padding: .8rem 1rem; border-radius: .65rem; background: #f8fafc; border-left: 4px solid #64748b;}
      div[data-testid="stMetric"] {background: #f8fafc; border: 1px solid #e2e8f0; padding: .8rem; border-radius: .7rem;}
    </style>
    <div class="app-kicker">Local rule-based workflow</div>
    <div class="app-title">Shipping Document Verification</div>
    <div class="app-subtitle">From Email Inbox to Discrepancy Report</div>
    <div class="process-flow">Email &nbsp;→&nbsp; Classification &nbsp;→&nbsp; SI/BL Extraction &nbsp;→&nbsp; Comparison &nbsp;→&nbsp; Result</div>
    """,
    unsafe_allow_html=True,
)


def uploaded_attachment(uploaded_file: Any) -> UploadedAttachment | None:
    if uploaded_file is None:
        return None
    return UploadedAttachment(uploaded_file.name, uploaded_file.getvalue())


def load_email_json(uploaded_file: Any) -> dict[str, Any]:
    try:
        parsed = json.loads(uploaded_file.getvalue().decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Email file must be valid UTF-8 JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("Email JSON must contain one object")
    return parsed


def render_single_result(artifacts: ProcessingArtifacts) -> None:
    email = artifacts.emails[0]
    email_id = email["email_id"]
    result = artifacts.submission[email_id]
    detail = artifacts.internal_results[email_id]

    st.subheader("Email Information")
    cols = st.columns(4)
    cols[0].metric("Email ID", email_id)
    cols[1].metric("Sender", str(email.get("from", "—")))
    cols[2].metric("Category", CATEGORY_LABELS[result["category"]])
    cols[3].metric("Status", result["status"].replace("_", " ").title())
    st.caption(f"Subject: {email.get('subject', '')}")

    st.subheader("Classification Result")
    st.info(CATEGORY_LABELS[result["category"]])
    if result["category"] != "BL_COMPARISON":
        st.markdown('<div class="result-note">No document comparison required.</div>', unsafe_allow_html=True)
        return

    st.subheader("SI / BL Extracted Fields")
    st.dataframe(comparison_rows(detail), hide_index=True, width="stretch")

    st.subheader("Final Result")
    if result["status"] == "OK":
        st.success("No mismatch detected.")
    elif result["status"] == "MISMATCH":
        st.error("Mismatch detected")
        for mismatch in detail["mismatches"]:
            st.markdown(
                f"- **{mismatch['field']}**: SI = `{mismatch['si_value']}` / BL = `{mismatch['bl_value']}`"
            )
    else:
        st.warning("Human Review Required")
        st.write(f"Reason: `{result['review_reason']}`")
        st.write(detail.get("detail", "The case could not be processed reliably."))


def run_dataset_with_progress(bundle_path: str) -> ProcessingArtifacts:
    progress = st.progress(0.0)
    status = st.empty()

    def update(completed: int, total: int, email_id: str) -> None:
        ratio = completed / total if total else 1.0
        progress.progress(min(ratio, 1.0))
        if completed < total:
            status.caption(f"Processing {email_id} · {completed}/{total} completed")
        else:
            status.caption(f"Completed {completed}/{total} emails")

    return process_dataset(bundle_path, update)


def render_summary(artifacts: ProcessingArtifacts) -> None:
    summary = artifacts.summary
    categories = summary["category_counts"]
    first = st.columns(4)
    first[0].metric("Total Emails", summary["emails_processed"])
    first[1].metric("Document Comparison", categories.get("BL_COMPARISON", 0))
    first[2].metric("New SI Request", categories.get("SI_REQUEST", 0))
    first[3].metric("Invoice Query", categories.get("INVOICE_QUERY", 0))
    second = st.columns(5)
    second[0].metric("General Message", categories.get("GENERAL", 0))
    second[1].metric("Spam", categories.get("SPAM", 0))
    second[2].metric("Mismatch", summary["mismatch"])
    second[3].metric("No Mismatch", summary["no_mismatch"])
    second[4].metric("Human Review", summary["manual_review"])


def render_dataset_table(artifacts: ProcessingArtifacts) -> None:
    rows = dataset_rows(artifacts)
    st.subheader("Results")
    left, right = st.columns(2)
    categories = sorted({row["category"] for row in rows})
    selected_categories = left.multiselect("Category", categories, default=categories)
    outcome = right.selectbox(
        "Outcome",
        ["All", "Mismatch", "No Mismatch", "Human Review"],
    )

    filtered = [row for row in rows if row["category"] in selected_categories]
    if outcome == "Mismatch":
        filtered = [row for row in filtered if row["comparison status"] == "MISMATCH"]
    elif outcome == "No Mismatch":
        filtered = [
            row
            for row in filtered
            if row["category"] == "BL_COMPARISON" and row["comparison status"] == "OK"
        ]
    elif outcome == "Human Review":
        filtered = [row for row in filtered if row["comparison status"] == "NEEDS_REVIEW"]
    st.caption(f"Showing {len(filtered)} of {len(rows)} emails")
    st.dataframe(filtered, hide_index=True, width="stretch", height=520)


bundle_path = st.sidebar.text_input("Participant bundle", value=str(DEFAULT_BUNDLE))
st.sidebar.caption("All processing stays on this computer.")

single_tab, dataset_tab, submission_tab = st.tabs(["Single Case", "Full Dataset", "Submission"])

with single_tab:
    st.header("Single Case")
    st.write("Upload one email JSON and, when applicable, its SI and draft BL attachments.")
    email_file = st.file_uploader("Email JSON", type=["json"], key="single_email")
    upload_cols = st.columns(2)
    si_file = upload_cols[0].file_uploader(
        "Shipping Instruction (SI)",
        type=["txt", "pdf", "docx", "xlsx"],
        key="single_si",
    )
    bl_file = upload_cols[1].file_uploader(
        "Draft Bill of Lading (BL)",
        type=["txt", "pdf", "docx", "xlsx"],
        key="single_bl",
    )
    if st.button("Process", type="primary", key="process_single"):
        if email_file is None:
            st.error("Upload an email JSON before processing.")
        else:
            try:
                email = load_email_json(email_file)
                st.session_state.single_artifacts = process_single_email(
                    email,
                    uploaded_attachment(si_file),
                    uploaded_attachment(bl_file),
                )
            except (OSError, ValueError) as exc:
                st.error(str(exc))
    if "single_artifacts" in st.session_state:
        render_single_result(st.session_state.single_artifacts)

with dataset_tab:
    st.header("Full Dataset")
    st.write("Run the verified pipeline across the complete local participant bundle.")
    if st.button("Run Full Dataset", type="primary", key="run_dataset"):
        try:
            artifacts = run_dataset_with_progress(bundle_path)
            st.session_state.dataset_artifacts = artifacts
            st.session_state.dataset_bundle = str(Path(bundle_path).expanduser().resolve())
            write_artifacts(artifacts, DEFAULT_OUTPUT)
            st.success("Full dataset processed successfully.")
        except (OSError, ValueError, RuntimeError) as exc:
            st.error(str(exc))
    if "dataset_artifacts" in st.session_state:
        render_summary(st.session_state.dataset_artifacts)
        render_dataset_table(st.session_state.dataset_artifacts)

with submission_tab:
    st.header("Submission")
    st.write("Generate and validate the complete `submission.json` using the existing pipeline.")
    if st.button("Generate Submission", type="primary", key="generate_submission"):
        try:
            resolved_bundle = str(Path(bundle_path).expanduser().resolve())
            artifacts = st.session_state.get("dataset_artifacts")
            if artifacts is None or st.session_state.get("dataset_bundle") != resolved_bundle:
                with st.spinner("Processing participant dataset..."):
                    artifacts = process_dataset(resolved_bundle)
                st.session_state.dataset_artifacts = artifacts
                st.session_state.dataset_bundle = resolved_bundle
            inbox_sample = json.loads((Path(resolved_bundle) / "sample_submission.json").read_text())
            validate_submission(artifacts.submission, inbox_sample)
            write_artifacts(artifacts, DEFAULT_OUTPUT)
            st.session_state.submission_ready = True
            st.success("Submission generated and schema validated successfully.")
        except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
            st.session_state.submission_ready = False
            st.error(str(exc))

    if st.session_state.get("submission_ready") and "dataset_artifacts" in st.session_state:
        artifacts = st.session_state.dataset_artifacts
        st.metric("Emails in submission", len(artifacts.submission))
        st.success("Schema valid · all participant email IDs are present")
        st.download_button(
            "Download submission.json",
            data=submission_bytes(artifacts.submission),
            file_name="submission.json",
            mime="application/json",
            type="primary",
        )
