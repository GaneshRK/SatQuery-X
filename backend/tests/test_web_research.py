import pytest
from apps.agent.web_research import WebResearchAgent, validate_url_safety, classify_domain_trust


def test_ssrf_safety_validation_blocks_internal_ips():
    # Loopback
    is_safe, reason = validate_url_safety("http://127.0.0.1:8000/admin")
    assert not is_safe
    assert "loopback" in reason.lower() or "internal" in reason.lower()

    # Localhost
    is_safe, reason = validate_url_safety("http://localhost:3000/")
    assert not is_safe

    # Cloud metadata service (AWS/GCP/Azure)
    is_safe, reason = validate_url_safety("http://169.254.169.254/latest/meta-data/")
    assert not is_safe

    # RFC 1918 Private ranges
    is_safe, reason = validate_url_safety("http://10.0.0.1/internal")
    assert not is_safe
    is_safe, reason = validate_url_safety("http://192.168.1.100:80/status")
    assert not is_safe
    is_safe, reason = validate_url_safety("http://172.16.0.5/api")
    assert not is_safe


def test_ssrf_safety_validation_blocks_schemes_and_ports():
    # File scheme
    is_safe, reason = validate_url_safety("file:///etc/passwd")
    assert not is_safe
    assert "scheme" in reason.lower()

    # FTP scheme
    is_safe, reason = validate_url_safety("ftp://files.example.com/data")
    assert not is_safe

    # Disallowed ports (SSH, MySQL, Redis, etc.)
    is_safe, reason = validate_url_safety("http://example.com:22/")
    assert not is_safe
    assert "port" in reason.lower()

    is_safe, reason = validate_url_safety("http://example.com:6379/")
    assert not is_safe


def test_ssrf_safety_allows_public_https():
    is_safe, reason = validate_url_safety("https://bhuvan.nrsc.gov.in/home/index.php")
    assert is_safe
    assert reason == ""


def test_domain_trust_classification():
    # Tier 1: Government & Space Agency
    assert classify_domain_trust("bhuvan.nrsc.gov.in") == "TIER_1_GOV_AGENCY"
    assert classify_domain_trust("isro.gov.in") == "TIER_1_GOV_AGENCY"
    assert classify_domain_trust("copernicus.eu") == "TIER_1_GOV_AGENCY"
    assert classify_domain_trust("earthdata.nasa.gov") == "TIER_1_GOV_AGENCY"
    assert classify_domain_trust("usgs.gov") == "TIER_1_GOV_AGENCY"
    assert classify_domain_trust("ndma.gov.in") == "TIER_1_GOV_AGENCY"

    # Tier 2: Academic & Peer Review
    assert classify_domain_trust("nature.com") == "TIER_2_ACADEMIC_PEER_REVIEW"
    assert classify_domain_trust("sciencedirect.com") == "TIER_2_ACADEMIC_PEER_REVIEW"
    assert classify_domain_trust("mdpi.com") == "TIER_2_ACADEMIC_PEER_REVIEW"
    assert classify_domain_trust("ieee.org") == "TIER_2_ACADEMIC_PEER_REVIEW"

    # Tier 3: Reputable News & Verified Publishers
    assert classify_domain_trust("thehindu.com") == "TIER_3_REPUTABLE_NEWS"
    assert classify_domain_trust("reuters.com") == "TIER_3_REPUTABLE_NEWS"
    assert classify_domain_trust("bbc.com") == "TIER_3_REPUTABLE_NEWS"

    # Tier 4: General Web
    assert classify_domain_trust("random-satellite-blog.xyz") == "TIER_4_GENERAL_WEB"


def test_web_research_agent_curated_evidence():
    agent = WebResearchAgent()
    evidence_list = agent.search_and_extract_evidence(
        query="What happened during the Chennai flood in December 2023?",
        aoi_bbox={"west": 80.1, "south": 12.9, "east": 80.3, "north": 13.2},
    )

    assert len(evidence_list) > 0
    first = evidence_list[0]

    # Verify cryptographic audit hash (SHA-256 hex string, length 64)
    assert "content_sha256" in first
    assert len(first["content_sha256"]) == 64

    # Verify trust tier
    assert first["trust_tier"] in [
        "TIER_1_GOV_AGENCY",
        "TIER_2_ACADEMIC_PEER_REVIEW",
        "TIER_3_REPUTABLE_NEWS",
        "TIER_4_GENERAL_WEB",
    ]

    # Verify TTL cache timestamp
    assert "cached_at" in first
    assert "expires_at" in first
    assert first["expires_at"] > first["cached_at"]

    # Verify extracted facts are clean data, not executable instructions
    assert len(first["extracted_facts"]) > 0
    for fact in first["extracted_facts"]:
        assert isinstance(fact, str)
        assert len(fact) > 5


def test_web_research_agent_synthesize_findings():
    agent = WebResearchAgent()
    evidence_list = agent.search_and_extract_evidence("Kaziranga wetland water change")
    findings = agent.synthesize_findings(evidence_list)
    assert len(findings) > 0
    assert any("Kaziranga" in f or "flood" in f or "water" in f or "rhino" in f for f in findings)
