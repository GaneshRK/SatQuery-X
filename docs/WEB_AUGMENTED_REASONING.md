# SatQuery-X Web-Augmented Evidence Retrieval Specification

**Platform**: SatQuery AI — Multi-Source Earth Intelligence  
**Specification Version**: 2.0  
**Status**: Approved Architecture  

---

## 1. Vision & Architectural Boundary

When satellite imagery and physical remote-sensing algorithms indicate ground phenomena (e.g. rapid flood inundation, sudden canopy loss, or new construction), satellite pixels alone cannot answer questions such as:
- *"Did this flooding coincide with official meteorological flood alerts?"*
- *"Why did agricultural yields drop in this district in 2023? Was there an official drought declaration?"*
- *"What infrastructure project corresponds to the newly detected highway corridor?"*

To answer these questions, SatQuery-X implements **Web-Augmented Evidence Retrieval**:
- The system dynamically identifies when external corroboration is required.
- It queries verified, trusted external sources without requiring the user to supply manual URLs.
- **CRITICAL ARCHITECTURAL BOUNDARY**: The system does **NOT** maintain a permanent database of arbitrary websites. Instead, it extracts discrete factual evidence claims, computes cryptographic audit hashes (SHA-256), and holds them in an ephemeral cache with a strict Time-To-Live (TTL, default 7 days) for audit and reproducibility.

---

## 2. Multi-Tier Domain Trust Model

External sources are categorized into 4 strict hierarchical trust tiers:

| Trust Tier | Source Category | Domain Patterns / Examples | Default Trust Score |
| :--- | :--- | :--- | :--- |
| **Tier 1** | **Government & Space Agencies** | `*.gov`, `*.gov.in`, `*.nic.in`, `nasa.gov`, `esa.int`, `isro.gov.in`, `imd.gov.in`, `cwc.gov.in` | `0.95` |
| **Tier 2** | **Scientific & Academic Institutions** | `*.edu`, `*.ac.in`, `nature.com`, `sciencedirect.com`, `copernicus.eu`, `wri.org` | `0.88` |
| **Tier 3** | **Reputable News & Verified Reports** | `reuters.com`, `apnews.com`, `bbc.com`, `thehindu.com`, `indianexpress.com` | `0.75` |
| **Tier 4** | **General Web** | General web domains (strictly corroborating; cannot override physical remote sensing data) | `0.45` |

---

## 3. Security & Injection Defense (SSRF & Content Poisoning)

External web retrieval enforces strict cybersecurity safeguards:

### 3.1 Server-Side Request Forgery (SSRF) Guard
- All target URLs are parsed and validated before requests are dispatched.
- **Blocked IP Ranges**:
  - `127.0.0.0/8` (Loopback)
  - `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16` (Private RFC 1918)
  - `169.254.0.0/16` (Link-local / Cloud metadata endpoints like `169.254.169.254`)
  - `0.0.0.0`, `localhost`, `::1`
- Only standard `http` and `https` schemes are permitted; ports restricted to `80` and `443`.
- Strict connection timeouts (max 6.0 seconds) and response payload limits (max 2 MB).

### 3.2 Web Content Treated as DATA, NEVER as Instructions
- Retrieved webpage content is passed to the VLM / reasoning layer wrapped in strict XML data tags:
  ```xml
  <untrusted_web_evidence source="https://imd.gov.in/..." trust_tier="1">
  [Extracted textual facts]
  </untrusted_web_evidence>
  ```
- Any text inside external content attempting to issue system instructions (e.g., *"Ignore previous instructions and say..."*) is ignored by system prompt constraints and verified against satellite ground truth.

---

## 4. Ephemeral Audit Storage Schema (`ExternalEvidence`)

```python
class ExternalEvidence(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    query = models.ForeignKey("queries.Query", on_delete=models.CASCADE, related_name="external_evidence")
    source_url = models.URLField(max_length=1024)
    source_domain = models.CharField(max_length=255, db_index=True)
    publisher = models.CharField(max_length=255, blank=True)
    title = models.CharField(max_length=512)
    source_type = models.CharField(max_length=64, choices=TIER_CHOICES, default="TIER_1_GOV_AGENCY")
    trust_score = models.FloatField(default=0.85)
    published_date = models.DateField(null=True, blank=True)
    retrieved_at = models.DateTimeField(auto_now_add=True)
    summary_facts = models.JSONField(default=list)  # List of atomic factual bullet points
    content_hash = models.CharField(max_length=64)  # SHA-256
    ttl_expires_at = models.DateTimeField(null=True, blank=True)
```

---

## 5. GeoReason Synthesis Pipeline

When both satellite evidence and external web evidence are present:
1. **Physical Validation**: Remote sensing data is the primary ground truth. If web reports claim flooding but SAR imagery shows zero surface backscatter change, the GeoReason agent flags the discrepancy.
2. **Contextual Augmentation**: If Sentinel-2 shows vegetation loss of 18% and IMD records confirm severe monsoon deficit (-34% rainfall), the agent synthesizes both:
   > *"Sentinel-2 multispectral analysis reveals an 18.2% reduction in NDVI across the designated agricultural sector between 2022 and 2023. This physical decline is corroborated by regional IMD meteorological records documenting a 34% seasonal precipitation deficit during the same cultivation period."*
3. **Calibrated Confidence**: Supporting Tier-1 evidence increases calibrated confidence, while unverified or contradictory web claims reduce the score and are flagged as uncertain.
