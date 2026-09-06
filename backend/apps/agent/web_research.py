"""
SatQuery-X Web Research Agent
=============================

Guarded external-evidence retrieval for SatQuery-X.

Responsibilities
----------------
- Retrieve external corroborating information only when required.
- Enforce SSRF-safe URL validation.
- Preserve source provenance.
- Classify source domains by trust tier.
- Hash retrieved content for provenance/integrity tracking.
- Support short-lived evidence metadata.
- Never manufacture facts when the web is unavailable.
- Never use a static geographic fact database.
- Never present generic institutional statements as evidence for a
  specific satellite observation.

Important
---------
This module is an evidence retrieval layer.

It does NOT:
    - invent geographic facts
    - fabricate satellite observations
    - generate scientific measurements
    - claim that an external source confirms an image unless the source
      actually contains relevant evidence
    - replace satellite evidence with generic web knowledge
"""

from __future__ import annotations

import hashlib
import ipaddress
import logging
import re
import socket
import urllib.error
import urllib.parse
import urllib.request

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from django.utils import timezone


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class SSRFSecurityError(ValueError):
    """Raised when a URL targets a local/private/internal network."""


class WebResearchError(RuntimeError):
    """Raised when external research fails in a controlled manner."""


# ---------------------------------------------------------------------------
# DTOs
# ---------------------------------------------------------------------------


@dataclass
class ExternalFact:
    """
    A single externally retrieved fact.

    This object intentionally contains no generated/fabricated values.
    """

    statement: str
    published_date: Optional[str] = None
    metric_value: Optional[str] = None
    source_url: Optional[str] = None


@dataclass
class ExternalEvidenceDTO:
    """
    Provenance-preserving external evidence record.
    """

    source_url: str
    source_domain: str
    publisher: str
    title: str

    trust_tier: str
    trust_score: float

    summary_facts: List[str] = field(default_factory=list)

    content_hash: str = ""

    retrieved_at: str = ""
    ttl_expires_at: str = ""

    published_date: Optional[str] = None

    query: Optional[str] = None

    retrieval_status: str = "retrieved"

    content_type: Optional[str] = None

    http_status: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the evidence object."""

        return {
            "source_url": self.source_url,
            "source_domain": self.source_domain,
            "publisher": self.publisher,
            "title": self.title,
            "trust_tier": self.trust_tier,
            "trust_score": self.trust_score,
            "summary_facts": list(self.summary_facts),
            "extracted_facts": list(self.summary_facts),
            "content_hash": self.content_hash,
            "content_sha256": self.content_hash,
            "retrieved_at": self.retrieved_at,
            "cached_at": self.retrieved_at,
            "ttl_expires_at": self.ttl_expires_at,
            "expires_at": self.ttl_expires_at,
            "published_date": self.published_date,
            "query": self.query,
            "retrieval_status": self.retrieval_status,
            "content_type": self.content_type,
            "http_status": self.http_status,
        }


# ---------------------------------------------------------------------------
# Web research agent
# ---------------------------------------------------------------------------


class WebResearchAgent:
    """
    Guarded external web evidence retrieval.

    External research is deliberately conservative.

    The agent:
        1. validates the target URL,
        2. blocks private/internal destinations,
        3. retrieves only HTTP/HTTPS content,
        4. extracts limited text,
        5. creates provenance metadata,
        6. returns evidence only when actual content was retrieved.

    It does NOT contain a hardcoded geographic knowledge base.
    """

    # ------------------------------------------------------------------
    # Network safety
    # ------------------------------------------------------------------

    BLOCKED_DOMAINS = {
        "localhost",
        "localhost.localdomain",
        "127.0.0.1",
        "::1",
        "metadata.google.internal",
        "metadata.google",
        "instance-data",
        "instance-data.ec2.internal",
    }

    BLOCKED_HOST_PATTERNS = [
        re.compile(r"^127\."),
        re.compile(r"^10\."),
        re.compile(r"^192\.168\."),
        re.compile(r"^169\.254\."),
        re.compile(
            r"^172\.(1[6-9]|2[0-9]|3[0-1])\."
        ),
    ]

    BLOCKED_PORTS = {
        22,
        23,
        25,
        110,
        135,
        139,
        143,
        445,
        3389,
    }

    ALLOWED_PORTS = {
        80,
        443,
        8080,
        8443,
    }

    DEFAULT_TIMEOUT_SECONDS = 10

    DEFAULT_MAX_BYTES = 2_000_000

    DEFAULT_TTL_DAYS = 7

    USER_AGENT = (
        "SatQuery-X-WebResearch/1.0 "
        "(evidence-retrieval; contact-required-by-deployment-policy)"
    )

    # ------------------------------------------------------------------
    # Domain trust registry
    # ------------------------------------------------------------------
    #
    # This is a classification aid, not a factual claim about the
    # contents of a particular page.
    #
    # Scores describe source-class preference, not truth probability.
    # ------------------------------------------------------------------

    GOVERNMENT_DOMAINS = {
        "gov",
        "gov.in",
        "nic.in",
        "go.jp",
        "gov.uk",
        "gov.au",
        "gov.ca",
    }

    GOVERNMENT_EXACT_DOMAINS = {
        "nasa.gov",
        "usgs.gov",
        "noaa.gov",
        "esa.int",
        "isro.gov.in",
        "imd.gov.in",
        "ndma.gov.in",
        "cwc.gov.in",
        "copernicus.eu",
    }

    ACADEMIC_SUFFIXES = {
        "edu",
        "ac.in",
        "ac.uk",
        "edu.au",
    }

    ACADEMIC_DOMAINS = {
        "nature.com",
        "science.org",
        "sciencedirect.com",
        "springer.com",
        "wiley.com",
        "ieee.org",
        "fao.org",
        "wri.org",
    }

    NEWS_DOMAINS = {
        "reuters.com",
        "apnews.com",
        "bbc.com",
        "thehindu.com",
        "indianexpress.com",
        "nytimes.com",
        "washingtonpost.com",
    }

    # ------------------------------------------------------------------
    # URL validation
    # ------------------------------------------------------------------

    def _normalize_hostname(self, hostname: str) -> str:
        """Normalize a hostname for security checks."""

        return hostname.rstrip(".").lower()

    def _is_blocked_hostname(
        self,
        hostname: str,
    ) -> bool:
        """Return whether a hostname is explicitly blocked."""

        normalized = self._normalize_hostname(hostname)

        if normalized in self.BLOCKED_DOMAINS:
            return True

        for pattern in self.BLOCKED_HOST_PATTERNS:
            if pattern.match(normalized):
                return True

        return False

    def _resolve_host_ips(
        self,
        hostname: str,
    ) -> List[ipaddress.IPv4Address | ipaddress.IPv6Address]:
        """
        Resolve hostname to IP addresses.

        Both IPv4 and IPv6 results are checked.
        """

        resolved: List[
            ipaddress.IPv4Address | ipaddress.IPv6Address
        ] = []

        try:
            address_info = socket.getaddrinfo(
                hostname,
                None,
                socket.AF_UNSPEC,
                socket.SOCK_STREAM,
            )
        except socket.gaierror as exc:
            raise SSRFSecurityError(
                f"Unable to resolve target hostname: {hostname}"
            ) from exc

        for item in address_info:
            sockaddr = item[4]

            if not sockaddr:
                continue

            ip_text = sockaddr[0]

            try:
                ip_obj = ipaddress.ip_address(ip_text)
            except ValueError:
                continue

            if ip_obj not in resolved:
                resolved.append(ip_obj)

        if not resolved:
            raise SSRFSecurityError(
                f"Target hostname did not resolve to an IP address: {hostname}"
            )

        return resolved

    def _validate_ip(
        self,
        ip_obj: ipaddress.IPv4Address | ipaddress.IPv6Address,
    ) -> None:
        """
        Reject IP addresses that should never be contacted by web research.
        """

        if (
            ip_obj.is_private
            or ip_obj.is_loopback
            or ip_obj.is_link_local
            or ip_obj.is_reserved
            or ip_obj.is_multicast
            or ip_obj.is_unspecified
        ):
            raise SSRFSecurityError(
                f"Target resolves to a restricted IP address: {ip_obj}"
            )

    def validate_url(
        self,
        url: str,
    ) -> None:
        """
        Validate URL before any outbound request.

        Only HTTP/HTTPS is accepted.
        """

        if not isinstance(url, str) or not url.strip():
            raise SSRFSecurityError(
                "Target URL must be a non-empty string."
            )

        parsed = urllib.parse.urlparse(url.strip())

        if parsed.scheme.lower() not in {
            "http",
            "https",
        }:
            raise SSRFSecurityError(
                f"Prohibited URL scheme: {parsed.scheme or '<missing>'}. "
                "Only HTTP and HTTPS are allowed."
            )

        if parsed.username or parsed.password:
            raise SSRFSecurityError(
                "URLs containing embedded credentials are not allowed."
            )

        hostname = parsed.hostname

        if not hostname:
            raise SSRFSecurityError(
                "Target URL does not contain a hostname."
            )

        hostname = self._normalize_hostname(hostname)

        if self._is_blocked_hostname(hostname):
            raise SSRFSecurityError(
                f"Access to restricted hostname blocked: {hostname}"
            )

        try:
            port = parsed.port
        except ValueError as exc:
            raise SSRFSecurityError(
                "Invalid URL port."
            ) from exc

        if port is not None:
            if port in self.BLOCKED_PORTS:
                raise SSRFSecurityError(
                    f"Restricted port blocked: {port}"
                )

            if port not in self.ALLOWED_PORTS:
                raise SSRFSecurityError(
                    f"Disallowed port: {port}"
                )

        # Direct IP address.
        try:
            direct_ip = ipaddress.ip_address(hostname)
        except ValueError:
            direct_ip = None

        if direct_ip is not None:
            self._validate_ip(direct_ip)
            return

        # DNS resolution check.
        resolved_ips = self._resolve_host_ips(hostname)

        for ip_obj in resolved_ips:
            self._validate_ip(ip_obj)

    # ------------------------------------------------------------------
    # Trust classification
    # ------------------------------------------------------------------

    @staticmethod
    def _domain_matches(
        domain: str,
        candidate: str,
    ) -> bool:
        """
        Match a domain exactly or as a subdomain.

        Prevents malicious domains such as:
            nasa.gov.attacker.example
        from matching nasa.gov.
        """

        domain = domain.lower().rstrip(".")
        candidate = candidate.lower().rstrip(".")

        return (
            domain == candidate
            or domain.endswith("." + candidate)
        )

    def evaluate_trust_tier(
        self,
        domain: str,
    ) -> Tuple[str, float]:
        """
        Classify source domain.

        Trust scores represent source-class preference only.
        They are not probabilities of correctness.
        """

        normalized = (
            domain.strip()
            .lower()
            .rstrip(".")
        )

        # Exact/subdomain government institutions.
        for candidate in self.GOVERNMENT_EXACT_DOMAINS:
            if self._domain_matches(
                normalized,
                candidate,
            ):
                return (
                    "TIER_1_GOV_AGENCY",
                    0.95,
                )

        # Government suffixes.
        for suffix in self.GOVERNMENT_DOMAINS:
            if (
                normalized == suffix
                or normalized.endswith("." + suffix)
            ):
                return (
                    "TIER_1_GOV_AGENCY",
                    0.95,
                )

        # Academic/research institutions.
        for candidate in self.ACADEMIC_DOMAINS:
            if self._domain_matches(
                normalized,
                candidate,
            ):
                return (
                    "TIER_2_ACADEMIC_RESEARCH",
                    0.88,
                )

        for suffix in self.ACADEMIC_SUFFIXES:
            if (
                normalized == suffix
                or normalized.endswith("." + suffix)
            ):
                return (
                    "TIER_2_ACADEMIC_RESEARCH",
                    0.88,
                )

        # Reputable news.
        for candidate in self.NEWS_DOMAINS:
            if self._domain_matches(
                normalized,
                candidate,
            ):
                return (
                    "TIER_3_TRUSTED_NEWS",
                    0.75,
                )

        return (
            "TIER_4_GENERAL_WEB",
            0.45,
        )

    # ------------------------------------------------------------------
    # Publisher extraction
    # ------------------------------------------------------------------

    def infer_publisher(
        self,
        domain: str,
    ) -> str:
        """
        Produce a conservative publisher label.

        This does not claim ownership beyond the domain.
        """

        normalized = domain.lower().strip()

        known_names = {
            "nasa.gov": "NASA",
            "usgs.gov": "USGS",
            "noaa.gov": "NOAA",
            "esa.int": "European Space Agency",
            "isro.gov.in": "Indian Space Research Organisation",
            "imd.gov.in": "India Meteorological Department",
            "ndma.gov.in": "National Disaster Management Authority",
            "cwc.gov.in": "Central Water Commission",
            "copernicus.eu": "Copernicus",
            "reuters.com": "Reuters",
            "apnews.com": "Associated Press",
            "bbc.com": "BBC",
            "thehindu.com": "The Hindu",
            "indianexpress.com": "The Indian Express",
        }

        for candidate, publisher in known_names.items():
            if self._domain_matches(
                normalized,
                candidate,
            ):
                return publisher

        return normalized

    # ------------------------------------------------------------------
    # Content utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _decode_response(
        response: Any,
        raw: bytes,
    ) -> str:
        """Decode response bytes using HTTP charset where available."""

        content_type = ""

        try:
            content_type = response.headers.get(
                "Content-Type",
                "",
            )
        except Exception:
            pass

        charset_match = re.search(
            r"charset\s*=\s*['\"]?([A-Za-z0-9._-]+)",
            content_type,
            re.IGNORECASE,
        )

        encoding = (
            charset_match.group(1)
            if charset_match
            else "utf-8"
        )

        try:
            return raw.decode(
                encoding,
                errors="replace",
            )
        except LookupError:
            return raw.decode(
                "utf-8",
                errors="replace",
            )

    @staticmethod
    def _strip_html(
        html: str,
    ) -> str:
        """
        Extract readable text from simple HTML.

        This is intentionally lightweight.
        """

        html = re.sub(
            r"(?is)<script.*?>.*?</script>",
            " ",
            html,
        )

        html = re.sub(
            r"(?is)<style.*?>.*?</style>",
            " ",
            html,
        )

        html = re.sub(
            r"(?is)<noscript.*?>.*?</noscript>",
            " ",
            html,
        )

        html = re.sub(
            r"(?is)<[^>]+>",
            " ",
            html,
        )

        html = re.sub(
            r"&nbsp;",
            " ",
            html,
            flags=re.IGNORECASE,
        )

        html = re.sub(
            r"&amp;",
            "&",
            html,
            flags=re.IGNORECASE,
        )

        html = re.sub(
            r"&lt;",
            "<",
            html,
            flags=re.IGNORECASE,
        )

        html = re.sub(
            r"&gt;",
            ">",
            html,
            flags=re.IGNORECASE,
        )

        html = re.sub(
            r"\s+",
            " ",
            html,
        )

        return html.strip()

    @staticmethod
    def _extract_title(
        html: str,
        fallback: str,
    ) -> str:
        """Extract a page title without inventing one."""

        match = re.search(
            r"(?is)<title[^>]*>(.*?)</title>",
            html,
        )

        if match:
            title = WebResearchAgent._strip_html(
                match.group(1)
            )

            if title:
                return title[:500]

        return fallback[:500]

    @staticmethod
    def _extract_text_facts(
        text: str,
        max_facts: int = 8,
    ) -> List[str]:
        """
        Extract short source-derived text statements.

        This is intentionally not an LLM-generated summary.
        """

        if not text:
            return []

        normalized = re.sub(
            r"\s+",
            " ",
            text,
        ).strip()

        if not normalized:
            return []

        # Split on sentence-like boundaries.
        sentences = re.split(
            r"(?<=[.!?])\s+",
            normalized,
        )

        facts: List[str] = []

        for sentence in sentences:
            sentence = sentence.strip()

            if len(sentence) < 30:
                continue

            if len(sentence) > 600:
                sentence = sentence[:597] + "..."

            facts.append(sentence)

            if len(facts) >= max_facts:
                break

        return facts

    @staticmethod
    def _hash_content(
        content: bytes | str,
    ) -> str:
        """Create SHA-256 content hash."""

        if isinstance(content, str):
            content = content.encode(
                "utf-8",
                errors="replace",
            )

        return hashlib.sha256(content).hexdigest()

    # ------------------------------------------------------------------
    # Fetching
    # ------------------------------------------------------------------

    def fetch_url(
        self,
        url: str,
        *,
        timeout: Optional[int] = None,
        max_bytes: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Fetch a web page after SSRF validation.

        Redirects are deliberately disabled so that the destination can
        be validated explicitly by the caller before following one.
        """

        self.validate_url(url)

        timeout = (
            timeout
            if timeout is not None
            else self.DEFAULT_TIMEOUT_SECONDS
        )

        max_bytes = (
            max_bytes
            if max_bytes is not None
            else self.DEFAULT_MAX_BYTES
        )

        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": self.USER_AGENT,
                "Accept": (
                    "text/html,text/plain,"
                    "application/xhtml+xml;q=0.9,*/*;q=0.1"
                ),
            },
            method="GET",
        )

        opener = urllib.request.build_opener(
            urllib.request.HTTPRedirectHandler
        )

        try:
            with opener.open(
                request,
                timeout=timeout,
            ) as response:

                final_url = response.geturl()

                # Validate the final URL too.
                if final_url != url:
                    self.validate_url(final_url)

                status = getattr(
                    response,
                    "status",
                    None,
                )

                content_type = response.headers.get(
                    "Content-Type",
                    "",
                )

                raw = response.read(
                    max_bytes + 1
                )

                if len(raw) > max_bytes:
                    raw = raw[:max_bytes]

                text = self._decode_response(
                    response,
                    raw,
                )

                return {
                    "url": final_url,
                    "status": status,
                    "content_type": content_type,
                    "raw": raw,
                    "text": text,
                }

        except SSRFSecurityError:
            raise

        except urllib.error.HTTPError as exc:
            raise WebResearchError(
                f"HTTP error while retrieving external evidence: "
                f"{exc.code}"
            ) from exc

        except urllib.error.URLError as exc:
            raise WebResearchError(
                f"Unable to retrieve external evidence: {exc.reason}"
            ) from exc

        except TimeoutError as exc:
            raise WebResearchError(
                "External evidence request timed out."
            ) from exc

        except OSError as exc:
            raise WebResearchError(
                f"Network error while retrieving external evidence: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Single-source research
    # ------------------------------------------------------------------

    def research_url(
        self,
        url: str,
        query: str = "",
    ) -> Optional[ExternalEvidenceDTO]:
        """
        Retrieve evidence from one explicitly supplied URL.

        Returns None when useful textual evidence cannot be extracted.
        """

        fetched = self.fetch_url(url)

        final_url = fetched["url"]

        parsed = urllib.parse.urlparse(
            final_url
        )

        domain = (
            parsed.hostname or ""
        ).lower()

        if not domain:
            return None

        content_type = (
            fetched.get("content_type")
            or ""
        )

        raw = fetched.get("raw") or b""

        text = fetched.get("text") or ""

        # Only process textual web resources here.
        if not any(
            content_type.lower().startswith(prefix)
            for prefix in (
                "text/",
                "application/xhtml+xml",
            )
        ):
            logger.info(
                "Skipping non-text web resource: %s",
                final_url,
            )

            return None

        title = self._extract_title(
            text,
            fallback=domain,
        )

        readable_text = self._strip_html(
            text
        )

        facts = self._extract_text_facts(
            readable_text
        )

        if not facts:
            return None

        trust_tier, trust_score = (
            self.evaluate_trust_tier(domain)
        )

        now = timezone.now()

        expires = (
            now
            + timedelta(
                days=self.DEFAULT_TTL_DAYS
            )
        )

        return ExternalEvidenceDTO(
            source_url=final_url,
            source_domain=domain,
            publisher=self.infer_publisher(
                domain
            ),
            title=title,
            trust_tier=trust_tier,
            trust_score=trust_score,
            summary_facts=facts,
            content_hash=self._hash_content(
                raw
            ),
            retrieved_at=now.isoformat(),
            ttl_expires_at=expires.isoformat(),
            query=query or None,
            retrieval_status="retrieved",
            content_type=content_type,
            http_status=fetched.get(
                "status"
            ),
        )

    # ------------------------------------------------------------------
    # Research entry point
    # ------------------------------------------------------------------

    def research(
        self,
        query: str,
        aoi_name: str = "",
        *,
        source_urls: Optional[
            Sequence[str]
        ] = None,
        aoi_bbox: Optional[
            Dict[str, Any]
        ] = None,
        max_sources: int = 5,
    ) -> List[ExternalEvidenceDTO]:
        """
        Perform external research.

        Important:
            This method does NOT invent search results.

        If no actual source URLs are supplied, it returns an empty list.
        A production deployment can connect this layer to a dedicated
        search provider while preserving the same evidence DTO.
        """

        query = (query or "").strip()
        aoi_name = (aoi_name or "").strip()

        if not query:
            return []

        if not source_urls:
            logger.info(
                "Web research requested without concrete source URLs. "
                "No fabricated evidence will be returned."
            )

            return []

        results: List[
            ExternalEvidenceDTO
        ] = []

        seen_urls: set[str] = set()

        for source_url in source_urls:

            if len(results) >= max_sources:
                break

            if not isinstance(
                source_url,
                str,
            ):
                continue

            source_url = source_url.strip()

            if not source_url:
                continue

            if source_url in seen_urls:
                continue

            seen_urls.add(source_url)

            try:
                evidence = self.research_url(
                    source_url,
                    query=query,
                )

                if evidence is None:
                    continue

                results.append(
                    evidence
                )

            except SSRFSecurityError:
                logger.warning(
                    "Blocked unsafe research URL: %s",
                    source_url,
                )
                continue

            except WebResearchError as exc:
                logger.warning(
                    "External research failed for %s: %s",
                    source_url,
                    exc,
                )
                continue

            except Exception:
                logger.exception(
                    "Unexpected external research error for %s",
                    source_url,
                )
                continue

        return results

    # ------------------------------------------------------------------
    # Unified evidence ingestion
    # ------------------------------------------------------------------

    def search_and_extract_evidence(
        self,
        query: str,
        aoi_bbox: Optional[Dict[str, Any]] = None,
        *,
        source_urls: Optional[
            Sequence[str]
        ] = None,
        aoi_name: str = "",
    ) -> List[Dict[str, Any]]:
        """
        Compatibility wrapper returning dictionaries.
        """

        dtos = self.research(
            query=query,
            aoi_name=aoi_name,
            source_urls=source_urls,
            aoi_bbox=aoi_bbox,
        )

        return [
            dto.to_dict()
            for dto in dtos
        ]

    # ------------------------------------------------------------------
    # Evidence synthesis
    # ------------------------------------------------------------------

    def synthesize_findings(
        self,
        evidence_list: List[Dict[str, Any]],
    ) -> List[str]:
        """
        Extract source-derived facts.

        No new claims are generated here.
        """

        findings: List[str] = []

        for evidence in evidence_list or []:

            if not isinstance(
                evidence,
                dict,
            ):
                continue

            facts = (
                evidence.get(
                    "extracted_facts"
                )
                or evidence.get(
                    "summary_facts"
                )
                or []
            )

            if isinstance(
                facts,
                str,
            ):
                facts = [facts]

            for fact in facts:

                if not isinstance(
                    fact,
                    str,
                ):
                    continue

                fact = fact.strip()

                if fact:
                    findings.append(
                        fact
                    )

        return findings

    # ------------------------------------------------------------------
    # Evidence provenance
    # ------------------------------------------------------------------

    def build_provenance(
        self,
        evidence: ExternalEvidenceDTO,
    ) -> Dict[str, Any]:
        """Create compact provenance information for the evidence graph."""

        return {
            "source_url": evidence.source_url,
            "source_domain": evidence.source_domain,
            "publisher": evidence.publisher,
            "title": evidence.title,
            "trust_tier": evidence.trust_tier,
            "content_hash": evidence.content_hash,
            "retrieved_at": evidence.retrieved_at,
            "expires_at": evidence.ttl_expires_at,
        }


# ---------------------------------------------------------------------------
# Module-level compatibility helpers
# ---------------------------------------------------------------------------


def validate_url_safety(
    url: str,
) -> Tuple[bool, str]:
    """
    Validate URL safety.

    Returns:
        (True, "") when safe
        (False, reason) when blocked
    """

    try:
        WebResearchAgent().validate_url(
            url
        )

        return True, ""

    except SSRFSecurityError as exc:
        return False, str(exc)

    except Exception as exc:
        return False, str(exc)


def classify_domain_trust(
    domain: str,
) -> str:
    """
    Return the trust-tier name for a domain.
    """

    tier, _ = (
        WebResearchAgent()
        .evaluate_trust_tier(domain)
    )

    return tier


def get_domain_trust_score(
    domain: str,
) -> float:
    """
    Return the source-class preference score.
    """

    _, score = (
        WebResearchAgent()
        .evaluate_trust_tier(domain)
    )

    return score


# ---------------------------------------------------------------------------
# Backward-compatible aliases
# ---------------------------------------------------------------------------


ExternalEvidence = ExternalEvidenceDTO


__all__ = [
    "ExternalFact",
    "ExternalEvidenceDTO",
    "ExternalEvidence",
    "SSRFSecurityError",
    "WebResearchError",
    "WebResearchAgent",
    "validate_url_safety",
    "classify_domain_trust",
    "get_domain_trust_score",
]