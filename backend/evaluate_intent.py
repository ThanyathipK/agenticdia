import asyncio
import json
import logging
import os
import sys

# Ensure app can be imported
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app.semantic_service import classify_workflow, detect_requirement_intent

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("evaluate_intent")

TEST_DATASET = [
    {"user_input": "Add QR Payment", "expected_workflow": "REQUIREMENT", "expected_intent": "REQUIREMENT_REQUEST"},
    {"user_input": "Implement biometric login", "expected_workflow": "REQUIREMENT", "expected_intent": "REQUIREMENT_REQUEST"},
    {"user_input": "Create a new reporting module", "expected_workflow": "REQUIREMENT", "expected_intent": "REQUIREMENT_REQUEST"},
    {"user_input": "Transfer should support OTP", "expected_workflow": "REQUIREMENT", "expected_intent": "REQUIREMENT_REQUEST"},
    {"user_input": "Change maximum transfer limit to 50000", "expected_workflow": "REQUIREMENT", "expected_intent": "REQUIREMENT_REQUEST"},
    {"user_input": "Update ticket US-002 to include SMS alert", "expected_workflow": "REQUIREMENT", "expected_intent": "REQUIREMENT_REQUEST"},
    {"user_input": "Remove Notification", "expected_workflow": "REQUIREMENT", "expected_intent": "REQUIREMENT_REQUEST"},
    {"user_input": "Delete US-005", "expected_workflow": "REQUIREMENT", "expected_intent": "REQUIREMENT_REQUEST"},
    {"user_input": "We no longer need email verification", "expected_workflow": "REQUIREMENT", "expected_intent": "REQUIREMENT_REQUEST"},
    {"user_input": "What does this requirement mean?", "expected_workflow": "QUESTION", "expected_intent": "GENERAL_CHAT"},
    {"user_input": "How does idempotency work here?", "expected_workflow": "QUESTION", "expected_intent": "GENERAL_CHAT"},
    {"user_input": "Can you explain US-001?", "expected_workflow": "QUESTION", "expected_intent": "GENERAL_CHAT"},
    {"user_input": "Hello", "expected_workflow": "CHAT", "expected_intent": "GENERAL_CHAT"},
    {"user_input": "Thanks!", "expected_workflow": "CHAT", "expected_intent": "GENERAL_CHAT"},
    {"user_input": "Ok sounds good", "expected_workflow": "CHAT", "expected_intent": "GENERAL_CHAT"},
    {"user_input": "Export PRD to markdown", "expected_workflow": "COMMAND", "expected_intent": "GENERAL_CHAT"},
    {"user_input": "Run audit check", "expected_workflow": "COMMAND", "expected_intent": "GENERAL_CHAT"},
    {"user_input": "Add dark mode toggle", "expected_workflow": "REQUIREMENT", "expected_intent": "REQUIREMENT_REQUEST"},
    {"user_input": "Modify transaction timeout to 60 seconds", "expected_workflow": "REQUIREMENT", "expected_intent": "REQUIREMENT_REQUEST"},
    {"user_input": "Cancel the credit card feature", "expected_workflow": "REQUIREMENT", "expected_intent": "REQUIREMENT_REQUEST"},
    {"user_input": "Could you clarify the user roles for US-003?", "expected_workflow": "QUESTION", "expected_intent": "GENERAL_CHAT"},
    {"user_input": "Hi there!", "expected_workflow": "CHAT", "expected_intent": "GENERAL_CHAT"},
    {"user_input": "Add multi-currency support", "expected_workflow": "REQUIREMENT", "expected_intent": "REQUIREMENT_REQUEST"},
    {"user_input": "Update the password strength requirements", "expected_workflow": "REQUIREMENT", "expected_intent": "REQUIREMENT_REQUEST"},
    {"user_input": "Drop the legacy XML export", "expected_workflow": "REQUIREMENT", "expected_intent": "REQUIREMENT_REQUEST"},
    {"user_input": "Why is session timeout set to 15 minutes?", "expected_workflow": "QUESTION", "expected_intent": "GENERAL_CHAT"},
    {"user_input": "Good morning", "expected_workflow": "CHAT", "expected_intent": "GENERAL_CHAT"},
    {"user_input": "Implement push notifications for alerts", "expected_workflow": "REQUIREMENT", "expected_intent": "REQUIREMENT_REQUEST"},
    {"user_input": "Change the currency symbol from USD to EUR", "expected_workflow": "REQUIREMENT", "expected_intent": "REQUIREMENT_REQUEST"},
    {"user_input": "Remove SMS 2FA support", "expected_workflow": "REQUIREMENT", "expected_intent": "REQUIREMENT_REQUEST"},
    {"user_input": "What is the difference between epic 1 and epic 2?", "expected_workflow": "QUESTION", "expected_intent": "GENERAL_CHAT"},
    {"user_input": "Thanks for your help", "expected_workflow": "CHAT", "expected_intent": "GENERAL_CHAT"},
    {"user_input": "Add fingerprint authentication", "expected_workflow": "REQUIREMENT", "expected_intent": "REQUIREMENT_REQUEST"},
    {"user_input": "Adjust fee calculation formula for international wires", "expected_workflow": "REQUIREMENT", "expected_intent": "REQUIREMENT_REQUEST"},
    {"user_input": "Discard the previous reporting format", "expected_workflow": "REQUIREMENT", "expected_intent": "REQUIREMENT_REQUEST"},
    {"user_input": "How are audit failures resolved?", "expected_workflow": "QUESTION", "expected_intent": "GENERAL_CHAT"},
    {"user_input": "Awesome work", "expected_workflow": "CHAT", "expected_intent": "GENERAL_CHAT"},
    {"user_input": "Add session activity log", "expected_workflow": "REQUIREMENT", "expected_intent": "REQUIREMENT_REQUEST"},
    {"user_input": "Update retry limit to 3 attempts", "expected_workflow": "REQUIREMENT", "expected_intent": "REQUIREMENT_REQUEST"},
    {"user_input": "Retire the old login screen", "expected_workflow": "REQUIREMENT", "expected_intent": "REQUIREMENT_REQUEST"},
    {"user_input": "Can you explain the data retention policy?", "expected_workflow": "QUESTION", "expected_intent": "GENERAL_CHAT"},
    {"user_input": "Ok", "expected_workflow": "CHAT", "expected_intent": "GENERAL_CHAT"},
    {"user_input": "Add CSV export for statements", "expected_workflow": "REQUIREMENT", "expected_intent": "REQUIREMENT_REQUEST"},
    {"user_input": "Modify user profile picture upload limit to 10MB", "expected_workflow": "REQUIREMENT", "expected_intent": "REQUIREMENT_REQUEST"},
    {"user_input": "Remove legacy OAuth providers", "expected_workflow": "REQUIREMENT", "expected_intent": "REQUIREMENT_REQUEST"},
    {"user_input": "What does acceptance criteria 3 imply?", "expected_workflow": "QUESTION", "expected_intent": "GENERAL_CHAT"},
    {"user_input": "Goodbye", "expected_workflow": "CHAT", "expected_intent": "GENERAL_CHAT"},
    {"user_input": "Add audit trail reporting", "expected_workflow": "REQUIREMENT", "expected_intent": "REQUIREMENT_REQUEST"},
    {"user_input": "Update notification dispatch interval", "expected_workflow": "REQUIREMENT", "expected_intent": "REQUIREMENT_REQUEST"},
    {"user_input": "Cancel scheduled maintenance mode feature", "expected_workflow": "REQUIREMENT", "expected_intent": "REQUIREMENT_REQUEST"},
    {"user_input": "How is user consent stored?", "expected_workflow": "QUESTION", "expected_intent": "GENERAL_CHAT"},
    {"user_input": "Got it", "expected_workflow": "CHAT", "expected_intent": "GENERAL_CHAT"},
    {"user_input": "Add geo-blocking for high-risk regions", "expected_workflow": "REQUIREMENT", "expected_intent": "REQUIREMENT_REQUEST"},
    {"user_input": "Change dashboard refresh rate to 10 seconds", "expected_workflow": "REQUIREMENT", "expected_intent": "REQUIREMENT_REQUEST"},
    {"user_input": "Remove the deprecated API endpoint", "expected_workflow": "REQUIREMENT", "expected_intent": "REQUIREMENT_REQUEST"},
]

async def run_evaluation():
    print(f"==================================================")
    print(f" Starting Intent & Workflow Evaluation Framework")
    print(f" Total Test Cases: {len(TEST_DATASET)}")
    print(f"==================================================")

    workflow_correct = 0
    intent_correct = 0
    misclassifications = []

    for i, test_case in enumerate(TEST_DATASET, start=1):
        user_input = test_case["user_input"]
        exp_wf = test_case["expected_workflow"]
        exp_intent = test_case["expected_intent"]

        try:
            wf_res = await classify_workflow(user_input)
            pred_wf = wf_res.get("workflow", "").upper()
            wf_reason = wf_res.get("reason", "")
        except Exception as e:
            pred_wf = "ERROR"
            wf_reason = str(e)

        try:
            intent_res = await detect_requirement_intent(user_input)
            pred_intent = intent_res.get("intent", "").upper()
            intent_conf = intent_res.get("confidence", 0.0)
            intent_reason = intent_res.get("reason", "")
        except Exception as e:
            pred_intent = "ERROR"
            intent_conf = 0.0
            intent_reason = str(e)

        wf_match = (pred_wf == exp_wf)
        intent_match = (pred_intent == exp_intent)

        if wf_match:
            workflow_correct += 1
        if intent_match:
            intent_correct += 1

        if not wf_match or not intent_match:
            misclassifications.append({
                "test_index": i,
                "user_input": user_input,
                "expected_workflow": exp_wf,
                "predicted_workflow": pred_wf,
                "workflow_reason": wf_reason,
                "expected_intent": exp_intent,
                "predicted_intent": pred_intent,
                "intent_confidence": intent_conf,
                "intent_reason": intent_reason
            })
            print(f"[{i:02d}] ❌ FAIL | Input: '{user_input}'")
            print(f"      Workflow: Expected {exp_wf}, Got {pred_wf}")
            print(f"      Intent:   Expected {exp_intent}, Got {pred_intent} (Conf: {intent_conf})")
        else:
            print(f"[{i:02d}] ✅ PASS | Input: '{user_input}' -> WF: {pred_wf}, Intent: {pred_intent}")

    total = len(TEST_DATASET)
    wf_accuracy = (workflow_correct / total) * 100
    intent_accuracy = (intent_correct / total) * 100

    print(f"\n==================================================")
    print(f" EVALUATION RESULTS SUMMARY")
    print(f"==================================================")
    print(f" Total Tests Run        : {total}")
    print(f" Workflow Accuracy      : {wf_accuracy:.2f}% ({workflow_correct}/{total})")
    print(f" Intent Accuracy        : {intent_accuracy:.2f}% ({intent_correct}/{total})")
    print(f" Total Misclassifications: {len(misclassifications)}")
    print(f"==================================================")

    report = {
        "total_tests": total,
        "workflow_accuracy": wf_accuracy,
        "intent_accuracy": intent_accuracy,
        "misclassifications_count": len(misclassifications),
        "misclassifications": misclassifications
    }

    report_path = "evaluation_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"Detailed misclassification report saved to {report_path}")

if __name__ == "__main__":
    asyncio.run(run_evaluation())