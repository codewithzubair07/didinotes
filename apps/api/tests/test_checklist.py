import json
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.factory import create_app
from app.models import ChecklistRecord, Entry
from app.settings import Settings


def make_app(tmp_path: Path, **overrides) -> TestClient:
    config_dir = Path(__file__).resolve().parents[3] / "config"
    settings = Settings(
        database_url=f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
        config_dir=config_dir,
        audio_dir=tmp_path / "audio",
        rate_limit_per_minute=overrides.pop("rate_limit_per_minute", 1000),
        checklist_mode=overrides.pop("checklist_mode", True),
        **overrides,
    )
    return TestClient(create_app(settings))


def test_anc_checklist_offer_and_decline(tmp_path):
    client = make_app(tmp_path)
    # Turn 1: create ANC entry
    res = client.post(
        "/api/turn",
        json={"session_id": "anc-1", "text": "aaj Rina ANC visit korlam, 1 jon"},
    ).json()
    assert res["ui_hint"] == "confirm"

    # Turn 2: confirm entry -> offers checklist
    res = client.post("/api/turn", json={"session_id": "anc-1", "text": "hyan"}).json()
    assert res["ui_hint"] == "offer_checklist"
    assert "চেকলিস্ট" in res["response_text"] or "checklist" in res["response_text"].lower()

    # Entry is already saved
    factory = client.app.state.session_factory
    with factory() as db:
        entries = list(db.scalars(select(Entry)))
        assert len(entries) == 1
        assert entries[0].status == "confirmed"

    # Turn 3: decline checklist
    res = client.post("/api/turn", json={"session_id": "anc-1", "text": "na"}).json()
    assert res["ui_hint"] == "saved"
    assert "সংরক্ষিত" in res["response_text"] or "saved" in res["response_text"].lower()

    # No checklist record saved
    with factory() as db:
        records = list(db.scalars(select(ChecklistRecord)))
        assert len(records) == 0


def test_anc_checklist_completed_flow_with_danger_signs(tmp_path):
    client = make_app(tmp_path)
    sid = "anc-danger"
    # Entry
    client.post(
        "/api/turn",
        json={"session_id": sid, "text": "aaj Rina-r ANC visit korlam, 1 jon"},
    )
    # Confirm
    res = client.post("/api/turn", json={"session_id": sid, "text": "hyan"}).json()
    assert res["ui_hint"] == "offer_checklist"

    # Accept checklist with Bengali "হ্যাঁ"
    res = client.post("/api/turn", json={"session_id": sid, "text": "হ্যাঁ"}).json()
    assert res["ui_hint"] == "checklist_question"
    assert "প্রথম তিন মাস" in res["response_text"] or "trimester" in res["response_text"].lower()

    # Q1: registered first trimester -> yes
    res = client.post("/api/turn", json={"session_id": sid, "text": "haan"}).json()
    assert res["ui_hint"] == "checklist_question"

    # Q2: checkup done -> yes
    res = client.post("/api/turn", json={"session_id": sid, "text": "yes"}).json()
    assert res["ui_hint"] == "checklist_question"

    # Q3: IFA taken -> no
    res = client.post("/api/turn", json={"session_id": sid, "text": "না"}).json()
    assert res["ui_hint"] == "checklist_question"

    # Q4: swelling/headache (DANGER SIGN) -> yes
    res = client.post("/api/turn", json={"session_id": sid, "text": "ha"}).json()
    assert res["ui_hint"] == "checklist_question"
    assert res["has_danger_sign"] is True
    assert res["danger_banner"] is not None
    assert "ANM" in res["danger_banner"] or "ডাক্তার" in res["danger_banner"]

    # Q5: fever with chills (DANGER SIGN) -> na
    res = client.post("/api/turn", json={"session_id": sid, "text": "na"}).json()
    assert res["ui_hint"] == "checklist_question"
    # Danger sign banner stays active once triggered
    assert res["has_danger_sign"] is True

    # Q6: bleeding (DANGER SIGN) -> skip
    res = client.post("/api/turn", json={"session_id": sid, "text": "porer ta"}).json()
    assert res["ui_hint"] == "checklist_question"

    # Q7: birth plan -> yes (final question)
    res = client.post("/api/turn", json={"session_id": sid, "text": "hyan"}).json()
    assert res["ui_hint"] == "checklist_completed"
    assert res["has_danger_sign"] is True
    assert res["danger_banner"] is not None

    # Verify database persistence
    factory = client.app.state.session_factory
    with factory() as db:
        records = list(db.scalars(select(ChecklistRecord)))
        assert len(records) == 1
        rec = records[0]
        assert rec.checklist_id == "anc"
        assert rec.has_danger_sign is True
        assert rec.beneficiary_ref == "R"
        answers = json.loads(rec.answers)
        assert answers["first_trimester_registration"]["answer"] == "yes"
        assert answers["anc_checkup_done"]["answer"] == "yes"
        assert answers["ifa_tablets_taken"]["answer"] == "no"
        assert answers["swelling_vision_headache"]["answer"] == "yes"
        assert answers["swelling_vision_headache"]["is_danger_sign"] is True
        assert answers["fever_with_chills"]["answer"] == "no"
        assert answers["bleeding"]["answer"] == "skipped"
        assert answers["birth_plan_made"]["answer"] == "yes"


def test_hbnc_checklist_numbers_and_decimals(tmp_path):
    client = make_app(tmp_path)
    sid = "hbnc-num"
    # Entry for newborn
    client.post(
        "/api/turn",
        json={"session_id": sid, "text": "aaj Bablu newborn home visit korlam, 1 jon"},
    )
    # Confirm
    res = client.post("/api/turn", json={"session_id": sid, "text": "yes"}).json()
    assert res["ui_hint"] == "offer_checklist"

    # Accept checklist
    res = client.post("/api/turn", json={"session_id": sid, "text": "haan"}).json()
    assert res["ui_hint"] == "checklist_question"
    # Q1: feeding well -> yes
    res = client.post("/api/turn", json={"session_id": sid, "text": "hyan"}).json()
    assert res["ui_hint"] == "checklist_question"

    # Q2: baby temperature -> 37.5
    res = client.post("/api/turn", json={"session_id": sid, "text": "37.5"}).json()
    assert res["ui_hint"] == "checklist_question"

    # Q3: baby weight -> সাড়ে সাঁইত্রিশ or Bengali digits/words e.g. ২.৮
    res = client.post("/api/turn", json={"session_id": sid, "text": "২.৮ কেজি"}).json()
    assert res["ui_hint"] == "checklist_question"

    # Q4: fever/fast breathing (danger) -> nai
    res = client.post("/api/turn", json={"session_id": sid, "text": "nai"}).json()
    assert res["ui_hint"] == "checklist_question"

    # Q5: cord clean -> yes
    res = client.post("/api/turn", json={"session_id": sid, "text": "yes"}).json()
    assert res["ui_hint"] == "checklist_question"

    # Q6: mother bleeding or fever (danger) -> no
    res = client.post("/api/turn", json={"session_id": sid, "text": "no"}).json()
    assert res["ui_hint"] == "checklist_question"

    # Q7: immunization due -> skip
    res = client.post("/api/turn", json={"session_id": sid, "text": "skip"}).json()
    assert res["ui_hint"] == "checklist_completed"
    assert res["has_danger_sign"] is False

    # Check database
    factory = client.app.state.session_factory
    with factory() as db:
        records = list(db.scalars(select(ChecklistRecord)))
        assert len(records) == 1
        rec = records[0]
        assert rec.checklist_id == "hbnc"
        assert rec.has_danger_sign is False
        answers = json.loads(rec.answers)
        assert answers["baby_temperature"]["answer"] == 37.5
        assert answers["baby_temperature"]["unit"] == "°C"
        assert answers["baby_weight"]["answer"] == 2.8
        assert answers["baby_weight"]["unit"] == "kg"
        assert answers["immunization_due"]["answer"] == "skipped"


def test_checklist_unclear_reask_then_skip(tmp_path):
    client = make_app(tmp_path)
    sid = "hbnc-unclear"
    client.post(
        "/api/turn",
        json={"session_id": sid, "text": "aaj Bablu newborn home visit korlam, 1 jon"},
    )
    client.post("/api/turn", json={"session_id": sid, "text": "hyan"})
    client.post("/api/turn", json={"session_id": sid, "text": "hyan"})

    # Q1: feeding well -> unclear answer 1
    res1 = client.post(
        "/api/turn",
        json={"session_id": sid, "text": "kichu ekta shunechi golmal"},
    ).json()
    assert res1["ui_hint"] == "checklist_unclear"
    assert "আবার বলুন" in res1["response_text"] or "repeat" in res1["response_text"].lower()

    # Unclear answer 2 -> should skip to Q2
    res2 = client.post(
        "/api/turn",
        json={"session_id": sid, "text": "ebar o kichu bujhte parini"},
    ).json()
    assert res2["ui_hint"] == "checklist_question"
    assert "পরের" in res2["response_text"] or "next" in res2["response_text"].lower()
    # Now it is asking Q2 (baby temperature)
    assert "তাপমাত্রা" in res2["response_text"] or "temperature" in res2["response_text"].lower()


def test_strict_no_medical_advice_across_system(tmp_path):
    """
    CRITICAL CONSTRAINT: The app must NEVER give medical advice, clinical diagnosis,
    drug dosing, or treatment prescriptions.
    """
    client = make_app(tmp_path)
    sid = "clinical-safety"
    client.post(
        "/api/turn",
        json={"session_id": sid, "text": "aaj Rina ANC visit korlam, 1 jon"},
    )
    client.post("/api/turn", json={"session_id": sid, "text": "hyan"})
    res = client.post("/api/turn", json={"session_id": sid, "text": "hyan"}).json()

    # Forbidden clinical advice words that must never appear in system messages
    forbidden_terms = [
        "paracetamol",
        "antibiotic",
        "mg",
        "tablet din",
        "dawa din",
        "medicine",
        "prescription",
        "diagnosis",
        "diagnosed",
        "treatment",
        "chikitsa",
        "osudh",
        "ঔষধ দিন",
        "চিকিৎসা",
    ]

    all_responses = [res["response_text"]]
    # Trigger danger sign
    res = client.post("/api/turn", json={"session_id": sid, "text": "yes"}).json()
    all_responses.append(res["response_text"])
    res = client.post("/api/turn", json={"session_id": sid, "text": "yes"}).json()
    all_responses.append(res["response_text"])
    res = client.post("/api/turn", json={"session_id": sid, "text": "yes"}).json()
    all_responses.append(res["response_text"])
    res = client.post("/api/turn", json={"session_id": sid, "text": "yes"}).json()  # danger sign
    all_responses.append(res["response_text"])
    if res.get("danger_banner"):
        all_responses.append(res["danger_banner"])

    for text in all_responses:
        lower = text.lower()
        for term in forbidden_terms:
            assert term not in lower, f"Clinical advice term '{term}' found in response: '{text}'"

    # Verify danger banner is strictly a notification/referral, not medical advice
    banner = res["danger_banner"]
    assert "ANM বা ডাক্তারকে জানান" in banner
    assert "Please inform your ANM or doctor" in banner


def test_completed_checklists_appear_in_claims_count(tmp_path):
    client = make_app(tmp_path)
    sid = "claim-count-test"
    # Complete an ANC checklist
    client.post(
        "/api/turn",
        json={"session_id": sid, "text": "aaj Rina ANC visit korlam, 1 jon"},
    )
    client.post("/api/turn", json={"session_id": sid, "text": "hyan"})
    client.post("/api/turn", json={"session_id": sid, "text": "hyan"})
    for _ in range(7):
        client.post("/api/turn", json={"session_id": sid, "text": "skip"})

    # Check claims endpoint
    # The default mock event date is today (e.g., current month)
    from app.clock import today_local
    month_str = today_local().strftime("%Y-%m")
    claim_data = client.get(f"/api/claims/{month_str}").json()
    assert claim_data["completed_checklists_count"] >= 1


def test_entry_view_includes_checklist_and_safe_ref(tmp_path):
    client = make_app(tmp_path)
    sid = "entry-view-test"
    client.post(
        "/api/turn",
        json={"session_id": sid, "text": "aaj Rina ANC visit korlam, 1 jon"},
    )
    client.post("/api/turn", json={"session_id": sid, "text": "hyan"})
    client.post("/api/turn", json={"session_id": sid, "text": "hyan"})
    for _ in range(7):
        client.post("/api/turn", json={"session_id": sid, "text": "skip"})

    # Get entry from API
    from app.clock import today_local
    today_str = today_local().strftime("%Y-%m-%d")
    entries = client.get(f"/api/entries?date={today_str}").json()
    assert len(entries) == 1
    entry = entries[0]
    # Verify beneficiary_ref is pseudonymized (R, not Rina)
    assert entry["beneficiary_ref"] == "R"
    assert "Rina" not in str(entry["beneficiary_ref"])

    # Verify checklist embedded in entry
    assert entry["checklist"] is not None
    assert entry["checklist"]["checklist_id"] == "anc"
    assert entry["checklist"]["beneficiary_ref"] == "R"
    assert len(entry["checklist"]["answers"]) == 7


def test_parse_checklist_number_units_and_words():
    from app.config_loader import default_lexicon
    from app.dialogue.manager import parse_checklist_number
    from app.nlu.text import normalise

    lexicon = default_lexicon()
    # Direct decimals
    assert parse_checklist_number("37.5", normalise("37.5"), lexicon) == 37.5
    assert parse_checklist_number("37.5°C", normalise("37.5°C"), lexicon) == 37.5
    # Bengali digits
    assert parse_checklist_number("২.৫ কেজি", normalise("২.৫ কেজি"), lexicon) == 2.5
    assert parse_checklist_number("সাড়ে সাঁইত্রিশ", normalise("সাড়ে সাঁইত্রিশ"), lexicon) == 37.5

