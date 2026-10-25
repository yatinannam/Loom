from app.extraction.normalize import entity_id, evidence_supported, normalize_name


def test_variants_share_key():
    assert normalize_name("The Acme  Technologies.") == normalize_name("acme technologies")
    assert normalize_name("acme technologies") == "acme technologies"


def test_entity_id_slug():
    assert entity_id("Project Falcon") == "project-falcon"
    assert entity_id("NVIDIA Jetson") == "nvidia-jetson"
    assert entity_id("Wi-Fi 6") == "wi-fi-6"


def test_the_only_stripped_as_leading_word():
    assert normalize_name("Theodore") == "theodore"


def test_evidence_exact_with_case_and_whitespace_differences():
    text = "Alice works at Acme Technologies and leads the\nAutonomous Systems team."
    assert evidence_supported("alice works at acme technologies and leads the autonomous systems team", text)


def test_evidence_high_token_overlap_supported():
    text = "The Autonomous Systems team developed Project Falcon, which uses the EdgeCore platform."
    assert evidence_supported("Autonomous Systems team developed Project Falcon which uses EdgeCore", text)


def test_evidence_not_in_text_rejected():
    text = "Alice works at Acme Technologies."
    assert not evidence_supported("Bob founded Initech in 1999", text)
    assert not evidence_supported("", text)
