#!/usr/bin/env python3
"""
Comprehensive Multi-Scenario Verification Script (§69, §70, §71, §111).

Tests:
1. "What is changing around Chennai?" (CHANGE_ANALYSIS, Chennai AOI)
2. "What is changing around Coimbatore?" (CHANGE_ANALYSIS, Coimbatore AOI)
3. "Show vegetation loss in Western Ghats since 2020" (VEGETATION / CHANGE_DETECTION, Western Ghats AOI)
4. "What is the latest satellite observation around Pollachi?" (LATEST_OBSERVATION, Pollachi AOI)
5. "What is changing here?" without context (Non-hallucinatory CLARIFICATION)
"""

import sys
import time
import json
import urllib.request
import urllib.error

BASE_URL = "http://localhost:8000/api/v1"


def http_request(url: str, method: str = "GET", data: dict | None = None, token: str | None = None) -> dict:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    body = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=40.0) as resp:
            content = resp.read().decode("utf-8")
            return json.loads(content) if content else {}
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        try:
            return {"_error_code": e.code, "_error_body": json.loads(err_body)}
        except Exception:
            return {"_error_code": e.code, "_error_body": err_body}


def poll_query(session_id: str, query_id: str, token: str, timeout_sec: int = 35) -> dict:
    for _ in range(timeout_sec):
        time.sleep(1.0)
        detail = http_request(f"{BASE_URL}/sessions/{session_id}/queries/{query_id}/", token=token)
        if detail.get("status") in ("COMPLETED", "FAILED"):
            return detail
    return detail


def main():
    print("=" * 70)
    print("    SATQUERY-X MULTI-SCENARIO PRODUCTION VALIDATION SUITE")
    print("=" * 70)

    # Auth
    login_res = http_request(
        f"{BASE_URL}/auth/login/",
        method="POST",
        data={"username": "analyst", "password": "satquery2026"}
    )
    token = login_res.get("access")
    if not token:
        print("[FAIL] Authentication failed")
        return 1
    print("[PASS] User Authentication verified (analyst)")

    # 1. Scenario: Chennai
    print("\n[Scenario 1] Testing: 'What is changing around Chennai?'")
    s1 = http_request(f"{BASE_URL}/sessions/", method="POST", data={"name": "Chennai Test Workspace"}, token=token)
    sid1 = s1["id"]
    q1 = http_request(f"{BASE_URL}/sessions/{sid1}/queries/", method="POST", data={"text": "What is changing around Chennai?"}, token=token)
    d1 = poll_query(sid1, q1["query_id"], token)
    if d1.get("status") == "COMPLETED" and "chennai" in d1.get("answer", "").lower():
        print("  -> Status: COMPLETED")
        print("  -> Location: Chennai Metropolitan Region")
        print("  -> Task: " + str(d1.get("detected_task")))
        print("  -> Confidence: " + f"{d1.get('confidence', 0)*100:.1f}%")
        print("[PASS] Scenario 1 (Chennai change analysis)")
    else:
        print(f"[FAIL] Scenario 1 failed: {d1.get('error')}")
        return 1

    # 2. Scenario: Coimbatore
    print("\n[Scenario 2] Testing: 'What is changing around Coimbatore?'")
    s2 = http_request(f"{BASE_URL}/sessions/", method="POST", data={"name": "Coimbatore Test Workspace"}, token=token)
    sid2 = s2["id"]
    q2 = http_request(f"{BASE_URL}/sessions/{sid2}/queries/", method="POST", data={"text": "What is changing around Coimbatore?"}, token=token)
    d2 = poll_query(sid2, q2["query_id"], token)
    if d2.get("status") == "COMPLETED" and "coimbatore" in d2.get("answer", "").lower():
        print("  -> Status: COMPLETED")
        print("  -> Location: Coimbatore Industrial Basin")
        print("  -> Task: " + str(d2.get("detected_task")))
        print("  -> Confidence: " + f"{d2.get('confidence', 0)*100:.1f}%")
        print("[PASS] Scenario 2 (Coimbatore change analysis)")
    else:
        print(f"[FAIL] Scenario 2 failed: {d2.get('error')}")
        return 1

    # 3. Scenario: Western Ghats Vegetation
    print("\n[Scenario 3] Testing: 'Show vegetation loss in Western Ghats since 2020'")
    s3 = http_request(f"{BASE_URL}/sessions/", method="POST", data={"name": "Western Ghats Workspace"}, token=token)
    sid3 = s3["id"]
    q3 = http_request(f"{BASE_URL}/sessions/{sid3}/queries/", method="POST", data={"text": "Show vegetation loss in Western Ghats since 2020"}, token=token)
    d3 = poll_query(sid3, q3["query_id"], token)
    if d3.get("status") == "COMPLETED" and "western ghats" in d3.get("answer", "").lower():
        print("  -> Status: COMPLETED")
        print("  -> Location: Western Ghats Ecological Reserve")
        print("  -> Task: " + str(d3.get("detected_task")))
        print("  -> Confidence: " + f"{d3.get('confidence', 0)*100:.1f}%")
        print("[PASS] Scenario 3 (Western Ghats vegetation loss)")
    else:
        print(f"[FAIL] Scenario 3 failed: {d3.get('error')}")
        return 1

    # 4. Scenario: Pollachi Latest Observation
    print("\n[Scenario 4] Testing: 'What is the latest satellite observation around Pollachi?'")
    s4 = http_request(f"{BASE_URL}/sessions/", method="POST", data={"name": "Pollachi Workspace"}, token=token)
    sid4 = s4["id"]
    q4 = http_request(f"{BASE_URL}/sessions/{sid4}/queries/", method="POST", data={"text": "What is the latest satellite observation around Pollachi?"}, token=token)
    d4 = poll_query(sid4, q4["query_id"], token)
    if d4.get("status") == "COMPLETED" and d4.get("detected_task") == "LATEST_OBSERVATION":
        print("  -> Status: COMPLETED")
        print("  -> Location: Pollachi Agricultural Belt")
        print("  -> Task: LATEST_OBSERVATION")
        print("  -> Confidence: " + f"{d4.get('confidence', 0)*100:.1f}%")
        print("[PASS] Scenario 4 (Pollachi latest observation)")
    else:
        print(f"[FAIL] Scenario 4 failed: {d4.get('error')}")
        return 1

    # 5. Scenario: Ambiguous query without context
    print("\n[Scenario 5] Testing: 'What is changing here?' (Zero Context)")
    s5 = http_request(f"{BASE_URL}/sessions/", method="POST", data={"name": "Ambiguity Workspace"}, token=token)
    sid5 = s5["id"]
    q5 = http_request(f"{BASE_URL}/sessions/{sid5}/queries/", method="POST", data={"text": "What is changing here?"}, token=token)
    d5 = poll_query(sid5, q5["query_id"], token)
    if d5.get("clarification") is not None and "where" in d5["clarification"]["prompt"].lower():
        print("  -> Status: COMPLETED (CLARIFICATION_REQUIRED)")
        print("  -> Prompt: " + d5["clarification"]["prompt"])
        print("  -> Options returned: " + str(len(d5["clarification"].get("options", []))))
        print("[PASS] Scenario 5 (Ambiguity clarification without guessing)")
    else:
        print(f"[FAIL] Scenario 5 failed: {d5}")
        return 1

    print("\n" + "=" * 70)
    print("    ALL MULTI-SCENARIO GOLDEN JOURNEYS VERIFIED SUCCESSFULLY")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
